/**
 * streamQuery 接线测试：fetch 桩（tests/helpers/http.ts 的夹具）喂完整
 * SSE 流，验证"解析 → 事件回调 → 收尾"的整条链路。
 */
import { afterEach, describe, expect, it, vi } from 'vitest'
import { streamQuery } from '../src/api/stream'
import { fakeResponse, sseResponse } from './helpers/http'

const FULL_STREAM = [
  'event: meta\ndata: {"task_id":"t1","conversation_id":"c-42","model":"m","tools":[]}\n\n',
  'event: tool\ndata: {"name":"search_code","status":"running","summary":"搜索"}\n\n',
  'event: evidence\ndata: {"path":"backend/a.py","lineno":10,"end_lineno":20,"qualname":"backend.a.f","snippet":"def f","lanes":["symbol"],"concepts":[]}\n\n',
  'event: delta\ndata: {"text":"答案"}\n\n',
  'event: answer\ndata: {"facts":[],"inferences":[],"citations":[],"abstained":false,"reason":""}\n\n',
  'event: done\ndata: {"abstained":false,"reason":""}\n\n',
]

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('streamQuery 接线', () => {
  it('完整流：事件按序送达，正常收尾 aborted=false', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(FULL_STREAM)))
    const names: string[] = []
    const result = await streamQuery({ project_id: 1, question: 'q' }, (e) => names.push(e.event))
    expect(result.aborted).toBe(false)
    expect(result.error).toBeUndefined()
    expect(names).toEqual(['meta', 'tool', 'evidence', 'delta', 'answer', 'done'])
  })

  it('error 后有 done：不提前收尾，事件全收', async () => {
    const wire = [
      'event: delta\ndata: {"text":"说到一半"}\n\n',
      'event: error\ndata: {"code":"upstream_error","title":"上游 502","hint":"重试"}\n\n',
      'event: done\ndata: {"abstained":false,"reason":""}\n\n',
    ]
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(sseResponse(wire)))
    const names: string[] = []
    const result = await streamQuery({ project_id: 1, question: 'q' }, (e) => names.push(e.event))
    expect(result.aborted).toBe(false)
    expect(names).toEqual(['delta', 'error', 'done'])
  })

  it('非 2xx：返回 aborted + 错误说明，不抛异常', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        fakeResponse({
          ok: false,
          status: 500,
          json: { error: { code: 'internal_error', title: '服务异常', hint: '', detail: '' } },
        }),
      ),
    )
    const result = await streamQuery({ project_id: 1, question: 'q' }, () => {})
    expect(result.aborted).toBe(true)
    expect(result.error?.title).toContain('500')
  })

  it('网络异常：归一为连接错误，不抛异常', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('ECONNREFUSED')))
    const result = await streamQuery({ project_id: 1, question: 'q' }, () => {})
    expect(result.aborted).toBe(true)
    expect(result.error?.code).toBe('network')
  })

  it('用户预中止：aborted=true 且不算错误', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation((_url: string, init?: RequestInit) =>
        init?.signal?.aborted
          ? Promise.reject(new DOMException('Aborted', 'AbortError'))
          : Promise.resolve(sseResponse(FULL_STREAM)),
      ),
    )
    const controller = new AbortController()
    controller.abort()
    const result = await streamQuery({ project_id: 1, question: 'q' }, () => {}, controller.signal)
    expect(result.aborted).toBe(true)
    expect(result.error).toBeUndefined()
  })
})
