/**
 * 建索引轮询测试：注入 stub 的 getProject，验证"轮到终态为止"
 * 与"到次数上限返回最后一次、不抛错"两个关键行为。
 */
import { describe, expect, it, vi } from 'vitest'
import { waitForIndexing } from '../src/api/importFlow'
import type { ProjectDetail } from '../src/api/types'

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
