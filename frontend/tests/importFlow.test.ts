/**
 * 建索引轮询测试：注入 stub 的 getProject，验证"轮到终态为止"
 * 与"到次数上限返回最后一次、不抛错"两个关键行为。
 */
import { describe, expect, it, vi } from 'vitest'
import { waitForIndexing } from '../src/api/importFlow'
import type { ProjectDetail } from '../src/api/types'
import { ApiError } from '../src/api/client'

const failure = (status: number) => new ApiError({ status, code: 'internal_error', title: '暂不可读', hint: '', detail: '' })

function detailOf(status: string): ProjectDetail {
  return {
    id: 1,
    name: 'demo',
    root_path: '/d',
    status: status as ProjectDetail['status'],
    head_commit: '',
    head_branch: '',
    indexed_at: '',
    index_epoch: 0,
    files: 0,
    symbols: 0,
    chunks: 0,
    edges: 0,
    concepts: 0,
    concept_instances: 0,
  }
}

describe('waitForIndexing', () => {
  it('首次和中途 5xx 后自动恢复，错误也占用原轮询次数', async () => {
    const getProject = vi.fn().mockRejectedValueOnce(failure(503))
      .mockResolvedValueOnce(detailOf('indexing')).mockRejectedValueOnce(failure(500))
      .mockResolvedValueOnce(detailOf('ready'))
    const ticks: string[] = [], onError = vi.fn()
    const result = await waitForIndexing(getProject, 1, {
      intervalMs: 1, maxAttempts: 3, onError, onTick: d => ticks.push(d.status),
    })
    expect(result.status).toBe('ready')
    expect(getProject).toHaveBeenCalledTimes(4)
    expect(onError).toHaveBeenCalledTimes(2)
    expect(ticks).toEqual(['indexing', 'ready'])
  })

  it('项目不存在不重试，不把 4xx 当暂时索引状态', async () => {
    const error = failure(404), getProject = vi.fn().mockRejectedValue(error), onError = vi.fn()
    await expect(waitForIndexing(getProject, 1, { intervalMs: 1, onError })).rejects.toBe(error)
    expect(getProject).toHaveBeenCalledTimes(1)
    expect(onError).not.toHaveBeenCalled()
  })

  it('持续不可读达到上限就停止，保留最后一个错误', async () => {
    const error = failure(503), getProject = vi.fn().mockRejectedValue(error)
    await expect(waitForIndexing(getProject, 1, { intervalMs: 1, maxAttempts: 2 })).rejects.toBe(error)
    expect(getProject).toHaveBeenCalledTimes(3)
  })

  it('网络错误后取消检查，既不等待下一次请求也不重建索引', async () => {
    const controller = new AbortController(), getProject = vi.fn().mockRejectedValue(new TypeError('offline'))
    await expect(waitForIndexing(getProject, 1, { signal: controller.signal,
      onError: () => controller.abort(), intervalMs: 10_000 })).rejects.toHaveProperty('name', 'AbortError')
    expect(getProject).toHaveBeenCalledTimes(1)
  })

  it('已取消检查的迟到响应不触发状态回调', async () => {
    const controller = new AbortController(), onTick = vi.fn()
    let finish!: (value: ProjectDetail) => void
    const pending = waitForIndexing(() => new Promise<ProjectDetail>(resolve => { finish = resolve }), 1,
      { signal: controller.signal, onTick })
    controller.abort()
    finish(detailOf('ready'))
    await expect(pending).rejects.toHaveProperty('name', 'AbortError')
    expect(onTick).not.toHaveBeenCalled()
  })

  it('轮到终态为止：indexing → indexing → ready 停', async () => {
    const seq = ['indexing', 'indexing', 'ready']
    let call = 0
    const getProject = vi.fn(async () => detailOf(seq[Math.min(call++, seq.length - 1)]))
    const ticks: string[] = []
    const final = await waitForIndexing(getProject, 1, {
      intervalMs: 1,
      onTick: (d) => ticks.push(d.status),
    })
    expect(final.status).toBe('ready')
    expect(getProject).toHaveBeenCalledTimes(3)
    expect(ticks).toEqual(['indexing', 'indexing', 'ready'])
  })

  it('failed 也是终态，立即停', async () => {
    const getProject = vi.fn(async () => detailOf('failed'))
    const final = await waitForIndexing(getProject, 1, { intervalMs: 1 })
    expect(final.status).toBe('failed')
    expect(getProject).toHaveBeenCalledTimes(1)
  })

  it('次数上限用尽：返回最后一次的详情，不抛错', async () => {
    const getProject = vi.fn(async () => detailOf('indexing'))
    const final = await waitForIndexing(getProject, 1, { intervalMs: 1, maxAttempts: 3 })
    expect(final.status).toBe('indexing')
    expect(getProject).toHaveBeenCalledTimes(4) // 首次 + 3 次轮询
  })
})
