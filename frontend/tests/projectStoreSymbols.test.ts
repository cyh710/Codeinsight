/**
 * 左栏按需拉符号的 store 行为。
 *
 * 背景：契约 §0.4 把 `limit` 上限压在 500，而织忆这种项目有 6543 个符号
 * ——一次性拉不全（左栏只覆盖 31/688 个文件，展开其余文件是空的）。
 * 所以改成展开文件时按 path 拉。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ListResponse, SymbolListItem } from '../src/api/types'

const listProjectSymbols = vi.fn()

vi.mock('../src/api/dataSource', () => ({
  api: {
    listProjects: vi.fn(async () => []),
    getProject: vi.fn(async () => ({
      id: 1,
      name: 'demo',
      root_path: '/d',
      status: 'ready',
      head_commit: '',
      head_branch: '',
      indexed_at: '',
      index_epoch: 1,
      files: 2,
      symbols: 7,
      chunks: 0,
      edges: 0,
      concepts: 0,
      concept_instances: 0,
    })),
    getProjectFiles: vi.fn(async () => [
      { path: 'a.py', language: 'python', role: 'source', content_sha256: '', size_bytes: 0, line_count: 0, symbol_count: 2 },
      { path: 'b.py', language: 'python', role: 'source', content_sha256: '', size_bytes: 0, line_count: 0, symbol_count: 5 },
    ]),
    listProjectSymbols: (...args: unknown[]) => listProjectSymbols(...args),
  },
  isMockMode: false,
}))

const { projectStore } = await import('../src/store/projectStore')

function sym(qualname: string, path: string, lineno: number): SymbolListItem {
  return {
    id: lineno,
    qualname,
    name: qualname.split('.').pop() ?? qualname,
    kind: 'function',
    path,
    lineno,
    end_lineno: lineno + 1,
    header: 'def f():',
    docstring: null,
    n_lines: 2,
    is_async: false,
    is_private: false,
    is_dunder: false,
    in_degree: 0,
    out_degree: 0,
    concept_ids: [],
  }
}

beforeEach(() => {
  listProjectSymbols.mockReset()
  projectStore.setState({
    currentProjectId: 1,
    symbolsByPath: new Map(),
    loadingPaths: new Set(),
  })
})

describe('projectStore.loadSymbolsForPath', () => {
  it('按 path 拉符号并存进 symbolsByPath', async () => {
    const items = [sym('a.one', 'a.py', 1), sym('a.two', 'a.py', 5)]
    listProjectSymbols.mockResolvedValue({ items, total: 2 } as ListResponse<SymbolListItem>)

    await projectStore.getState().loadSymbolsForPath('a.py')

    expect(listProjectSymbols).toHaveBeenCalledWith(1, { path: 'a.py', limit: 500 })
    expect(projectStore.getState().symbolsByPath.get('a.py')).toEqual(items)
  })

  it('已加载过的路径不再重复请求', async () => {
    listProjectSymbols.mockResolvedValue({ items: [], total: 0 } as ListResponse<SymbolListItem>)
    await projectStore.getState().loadSymbolsForPath('a.py')
    await projectStore.getState().loadSymbolsForPath('a.py')
    expect(listProjectSymbols).toHaveBeenCalledTimes(1)
  })

  it('并发请求同一路径只发一次', async () => {
    let resolve: (v: ListResponse<SymbolListItem>) => void = () => {}
    listProjectSymbols.mockImplementation(
      () => new Promise<ListResponse<SymbolListItem>>((r) => { resolve = r }),
    )
    const p1 = projectStore.getState().loadSymbolsForPath('a.py')
    const p2 = projectStore.getState().loadSymbolsForPath('a.py')
    expect(listProjectSymbols).toHaveBeenCalledTimes(1)
    resolve({ items: [], total: 0 })
    await Promise.all([p1, p2])
  })

  it('拉取失败时记成空列表，不把错误抛给左栏', async () => {
    listProjectSymbols.mockRejectedValue(new Error('boom'))
    await projectStore.getState().loadSymbolsForPath('a.py')
    expect(projectStore.getState().symbolsByPath.get('a.py')).toEqual([])
    // loadingPaths 要清掉，否则左栏会一直转圈
    expect(projectStore.getState().loadingPaths.has('a.py')).toBe(false)
  })

  it('没有选中项目时什么都不做', async () => {
    projectStore.setState({ currentProjectId: null })
    await projectStore.getState().loadSymbolsForPath('a.py')
    expect(listProjectSymbols).not.toHaveBeenCalled()
  })
})
