/**
 * mock 层测试：派生逻辑（度数、symbol_count、callers/callees）与契约
 * 形状。快照用小型注入（字段形状与真实快照一致），并加载一次**真实
 * 快照**验证它能被完整消费（对契约形状的最直接检验）。
 */
import { beforeAll, describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { mockApi, provideSnapshot, setMockStreamDelay } from '../src/api/mock'
import type { SymbolListItem } from '../src/api/types'

interface MiniSnapshot {
  project: { id: number; name: string; root_path: string; head_commit: string; head_branch: string }
  files: Array<{ path: string; language: string; role: string; content_sha256: string; size_bytes: number; line_count: number; in_chunk_index: boolean }>
  modules: Array<{ qualname: string; path: string; docstring: string }>
  symbols: Array<{ qualname: string; name: string; kind: string; path: string; lineno: number; end_lineno: number; header: string; docstring: string; n_lines: number; is_async: boolean; is_private: boolean }>
  edges: Array<{ src_qualname: string; dst_name: string; dst_qualname: string | null; kind: string; path: string; lineno: number; confidence: number }>
  concepts: unknown[]
  flows: unknown[]
}

const mini: MiniSnapshot = {
  project: { id: 1, name: 'demo', root_path: '/demo', head_commit: 'abc', head_branch: 'main' },
  files: [
    { path: 'a.py', language: 'python', role: 'source', content_sha256: 'x', size_bytes: 10, line_count: 2, in_chunk_index: true },
    { path: 'b.py', language: 'python', role: 'source', content_sha256: 'y', size_bytes: 20, line_count: 4, in_chunk_index: true },
  ],
  modules: [{ qualname: 'a', path: 'a.py', docstring: '模块 a' }],
  symbols: [
    { qualname: 'a.entry', name: 'entry', kind: 'function', path: 'a.py', lineno: 1, end_lineno: 2, header: 'def entry():', docstring: '', n_lines: 2, is_async: false, is_private: false },
    { qualname: 'a.helper', name: 'helper', kind: 'function', path: 'a.py', lineno: 5, end_lineno: 6, header: 'def helper():', docstring: '', n_lines: 2, is_async: false, is_private: false },
    { qualname: 'b.worker', name: 'worker', kind: 'method', path: 'b.py', lineno: 1, end_lineno: 4, header: 'def worker():', docstring: '干活', n_lines: 4, is_async: false, is_private: false },
  ],
  edges: [
    { src_qualname: 'a.entry', dst_name: 'a.helper', dst_qualname: 'a.helper', kind: 'call', path: 'a.py', lineno: 2, confidence: 1.0 },
    { src_qualname: 'b.worker', dst_name: 'a.helper', dst_qualname: 'a.helper', kind: 'call', path: 'b.py', lineno: 2, confidence: 1.0 },
    { src_qualname: 'a.entry', dst_name: 'getattr', dst_qualname: null, kind: 'call', path: 'a.py', lineno: 3, confidence: 0.5 },
  ],
  concepts: [],
  flows: [],
}

beforeAll(() => {
  provideSnapshot(mini as never)
  setMockStreamDelay(0)
})

describe('mock 派生逻辑', () => {
  it('符号度数从 call 边派生（不可解析的动态调用不计入度）', async () => {
    const res = await mockApi.listProjectSymbols(1)
    const byName = new Map(res.items.map((s: SymbolListItem) => [s.name, s]))
    // helper 被两个确定调用指向
    expect(byName.get('helper')?.in_degree).toBe(2)
    // entry 发起 3 个 call，其中 1 个 dst_qualname 为 null（不确定）不计
    expect(byName.get('entry')?.out_degree).toBe(1)
    expect(res.total).toBe(3)
  })

  it('file.symbol_count 从符号派生', async () => {
    const files = await mockApi.getProjectFiles(1)
    const a = files.find((f) => f.path === 'a.py')
    expect(a?.symbol_count).toBe(2)
  })

  it('符号详情：callers/callees 按边派生，不确定边标 uncertain', async () => {
    const detail = await mockApi.getSymbol(1, 'a.helper')
    expect(detail.callers.map((c) => c.qualname)).toEqual(['a.entry', 'b.worker'])
    expect(detail.callers.every((c) => !c.uncertain)).toBe(true)

    const entry = await mockApi.getSymbol(1, 'a.entry')
    const dynamic = entry.callees.find((c) => c.qualname === 'getattr')
    expect(dynamic?.uncertain).toBe(true)
  })

  it('查询参数过滤：q / kind / 分页', async () => {
    const helpers = await mockApi.listProjectSymbols(1, { q: 'helper' })
    expect(helpers.total).toBe(1)
    const methods = await mockApi.listProjectSymbols(1, { kind: 'method' })
    expect(methods.total).toBe(1)
    const paged = await mockApi.listProjectSymbols(1, { limit: 2, offset: 1 })
    expect(paged.items).toHaveLength(2)
    expect(paged.total).toBe(3)
  })

  it('不存在的符号抛 ApiError（code=symbol_not_found）', async () => {
    await expect(mockApi.getSymbol(1, 'nope')).rejects.toMatchObject({
      code: 'symbol_not_found',
      status: 404,
    })
  })

  it('concepts 如实为空（快照没有概念，不编造）', async () => {
    const res = await mockApi.listConcepts(1)
    expect(res).toEqual({ items: [], total: 0 })
  })

  it('changes 返回契约 §7.1 的 M1–M5 空壳', async () => {
    const res = await mockApi.getChanges(1)
    expect(res.files).toEqual({ added: [], modified: [], deleted: [] })
    expect(res.impacted).toEqual({ modules: [], symbols: [], concept_ids: [] })
  })
})

describe('mock 流式回放', () => {
  it('事件序满足契约 §8.3：meta 开头、answer/done 各一次、done 收尾', async () => {
    const names: string[] = []
    const result = await mockApi.streamQuery({ project_id: 1, question: '哪里是入口' }, (e) => names.push(e.event))
    expect(result.aborted).toBe(false)
    expect(names[0]).toBe('meta')
    expect(names[names.length - 1]).toBe('done')
    expect(names.filter((n) => n === 'answer')).toHaveLength(1)
    expect(names.filter((n) => n === 'done')).toHaveLength(1)
  })

  it('answer 的 facts 都带 file:line 引用（ADR 0006/0007）', async () => {
    let sawFact = 0
    let ok = true
    await mockApi.streamQuery({ project_id: 1, question: 'x' }, (e) => {
      if (e.event === 'answer') {
        for (const f of e.data.facts) {
          sawFact += 1
          if (!f.citation.path || f.citation.lineno < 1) ok = false
        }
      }
    })
    expect(sawFact).toBeGreaterThan(0)
    expect(ok).toBe(true)
  })
})

describe('真实快照可被完整消费', () => {
  it('public/mock/sample-index.json 的每个符号都能查详情（抽样）', async () => {
    const raw = readFileSync(
      fileURLToPath(new URL('../public/mock/sample-index.json', import.meta.url)),
      'utf-8',
    )
    const snapshot = JSON.parse(raw) as MiniSnapshot
    provideSnapshot(snapshot as never)

    const files = await mockApi.getProjectFiles(1)
    expect(files.length).toBeGreaterThan(600)

    // 抽样快照里行数最大的符号：详情应能派生且带源码占位。
    const symbols = (await mockApi.listProjectSymbols(1, { limit: 500 })).items
    const hero = [...symbols].sort((x, y) => y.n_lines - x.n_lines)[0]
    const detail = await mockApi.getSymbol(1, hero.qualname)
    expect(detail.qualname).toBe(hero.qualname)
    expect(detail.source.length).toBeGreaterThan(0)
  })
})
