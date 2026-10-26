import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ProjectDetail } from '../src/api/types'

const mocks = vi.hoisted(() => ({
  create: vi.fn(), get: vi.fn(), files: vi.fn(), poll: vi.fn(), switchProject: vi.fn(), version: vi.fn(), chatProject: { id: null as number | null },
}))
vi.mock('../src/api/dataSource', () => ({ api: {
  createProject: mocks.create, getProject: mocks.get, getProjectFiles: mocks.files,
} }))
vi.mock('../src/api/importFlow', () => ({ waitForIndexing: mocks.poll }))
vi.mock('../src/store/chatStore', () => ({ chatStore: { getState: () => ({ projectId: mocks.chatProject.id, switchProject: mocks.switchProject }) } }))
vi.mock('../src/store/workbenchStore', () => ({ workbenchStore: { getState: () => ({ setIndexVersion: mocks.version }) } }))

const { projectStore } = await import('../src/store/projectStore')
function detail(status: ProjectDetail['status'] = 'ready', id = 1): ProjectDetail {
  return { id, name: `project-${id}`, root_path: '/repo', head_commit: 'abc', head_branch: 'main', indexed_at: '', index_epoch: 1,
    files: 24, symbols: 120, chunks: 40, edges: 0, concepts: 0, concept_instances: 0, status }
}

beforeEach(() => {
  vi.resetAllMocks()
  mocks.chatProject.id = null
  mocks.create.mockResolvedValue({ id: 1, name: 'project-1', root_path: '/repo', status: 'indexing', head_commit: null, head_branch: null })
  mocks.get.mockResolvedValue(detail())
  mocks.files.mockResolvedValue([])
  mocks.switchProject.mockResolvedValue(undefined)
  mocks.poll.mockResolvedValue(detail())
  projectStore.setState({ projects: [], currentProjectId: null, currentDetail: null, files: [], indexActivities: {}, importing: false, importError: '', error: '', loading: false })
})

describe('索引任务反馈', () => {
  it('受理后立即显示运行状态，完成同步后显示真实计数，并可关闭', async () => {
    let finish!: (value: ProjectDetail) => void
    mocks.poll.mockReturnValue(new Promise<ProjectDetail>(resolve => { finish = resolve }))
    await projectStore.getState().importProject('/repo')
    expect(projectStore.getState().importing).toBe(false)
    expect(projectStore.getState().indexActivities[1].phase).toBe('indexing')
    expect(projectStore.getState().currentDetail?.name).toBe('project-1')
    finish(detail())
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('ready'))
    expect(projectStore.getState().projects[0].symbols).toBe(120)
    projectStore.getState().dismissIndexActivity(1)
    expect(projectStore.getState().indexActivities[1]).toBeUndefined()
  })

  it('网络失败仅中断检查，恢复不会重复提交导入', async () => {
    mocks.poll.mockRejectedValueOnce(new Error('网络中断')).mockResolvedValueOnce(detail())
    await projectStore.getState().importProject('/repo')
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('unavailable'))
    projectStore.getState().resumeIndexing(1)
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('ready'))
    expect(mocks.create).toHaveBeenCalledTimes(1)
  })

  it('轮询上限明确暂停，用户继续检查后能完成', async () => {
    mocks.poll.mockResolvedValueOnce(detail('indexing')).mockResolvedValueOnce(detail())
    await projectStore.getState().importProject('/repo')
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('paused'))
    projectStore.getState().resumeIndexing(1)
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('ready'))
    expect(mocks.create).toHaveBeenCalledTimes(1)
  })

  it('切走项目后，原索引完成不覆盖当前详情，也不加载错误项目文件', async () => {
    let finish!: (value: ProjectDetail) => void
    mocks.poll.mockReturnValue(new Promise<ProjectDetail>(resolve => { finish = resolve }))
    await projectStore.getState().importProject('/repo')
    projectStore.setState({ currentProjectId: 2, currentDetail: detail('ready', 2) })
    finish(detail())
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('ready'))
    expect(projectStore.getState().currentDetail?.id).toBe(2)
    expect(mocks.files).not.toHaveBeenCalled()
  })

  it('文件列表同步失败能恢复检查，既有索引不重复建立', async () => {
    mocks.files.mockRejectedValueOnce(new Error('文件列表读取失败')).mockResolvedValueOnce([])
    await projectStore.getState().importProject('/repo')
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('unavailable'))
    expect(projectStore.getState().indexActivities[1].message).toContain('索引已建立')
    projectStore.getState().resumeIndexing(1)
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('ready'))
    expect(mocks.create).toHaveBeenCalledTimes(1)
  })

  it('真正索引失败仅经用户重试重新提交，并保留原始 ref', async () => {
    mocks.poll.mockResolvedValueOnce(detail('failed')).mockResolvedValueOnce(detail())
    await projectStore.getState().importProject('/repo', '原名字', 'agent-v1')
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('failed'))
    expect(mocks.create).toHaveBeenCalledTimes(1)
    await projectStore.getState().retryIndexing(1)
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('ready'))
    expect(mocks.create).toHaveBeenNthCalledWith(2, { root_path: '/repo', name: '原名字', ref: 'agent-v1' })
  })

  it('选择正在索引的项目会恢复检查，重复恢复不会创建多个轮询', async () => {
    let finish!: (value: ProjectDetail) => void
    mocks.get.mockResolvedValue(detail('indexing'))
    mocks.poll.mockReturnValue(new Promise<ProjectDetail>(resolve => { finish = resolve }))
    await projectStore.getState().selectProject(1)
    expect(projectStore.getState().indexActivities[1].phase).toBe('indexing')
    projectStore.getState().resumeIndexing(1)
    expect(mocks.poll).toHaveBeenCalledTimes(1)
    mocks.get.mockResolvedValue(detail())
    finish(detail())
    await vi.waitFor(() => expect(projectStore.getState().indexActivities[1].phase).toBe('ready'))
  })
})
