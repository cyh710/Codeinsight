import { describe, expect, it } from 'vitest'
import { readSseBody } from '../src/api/stream'
import { sseResponse } from './helpers/http'
import type { SseEvent } from '../src/api/types'

async function collectAsync(chunks: string[]): Promise<SseEvent[]> {
  const events: SseEvent[] = []
  const res = sseResponse(chunks)
  const reader = (res.body as unknown as { getReader: () => ReadableStreamDefaultReader<Uint8Array> }).getReader()
  await readSseBody(reader, (e) => events.push(e))
  return events
}

describe('SSE 解析（契约 §8.3 词汇表）', () => {
  it('完整事件序：meta → tool/evidence/delta 交错 → answer → done', async () => {
    const wire = [
      'event: meta\ndata: {"task_id":"t1","conversation_id":"c1","model":"m","tools":["search_code"]}\n\n',
      'event: tool\ndata: {"name":"search_code","status":"running","summary":"搜索"}\n\n',
      'event: evidence\ndata: {"path":"a.py","lineno":1,"end_lineno":2,"qualname":"a.f","snippet":"def f():","lanes":["bm25"],"concepts":[]}\n\n',
      'event: delta\ndata: {"text":"你看"}\n\n',
      'event: tool\ndata: {"name":"search_code","status":"ok","summary":"命中"}\n\n',
      'event: delta\ndata: {"text":"这里"}\n\n',
      'event: answer\ndata: {"facts":[],"inferences":[],"citations":[],"abstained":false,"reason":""}\n\n',
      'event: done\ndata: {"abstained":false,"reason":""}\n\n',
    ]
    const events = await collectAsync(wire)
    expect(events.map((e) => e.event)).toEqual([
      'meta', 'tool', 'evidence', 'delta', 'tool', 'delta', 'answer', 'done',
    ])
    const meta = events[0]
    if (meta.event !== 'meta') throw new Error('unreachable')
    expect(meta.data.conversation_id).toBe('c1')
    const ev = events[2]
    if (ev.event !== 'evidence') throw new Error('unreachable')
    expect(ev.data.lanes).toEqual(['bm25'])
  })

  it('帧跨 chunk 断开也能接上（半个 JSON 落在下一个 chunk）', async () => {
    const events = await collectAsync([
      'event: delta\ndata: {"text":"半',
      '截的话"}\n\n',
    ])
    expect(events).toEqual([{ event: 'delta', data: { text: '半截的话' } }])
  })

  it('坏 JSON 帧跳过，不毁掉后续事件', async () => {
    const events = await collectAsync([
      'event: delta\ndata: {broken json\n\n',
      'event: delta\ndata: {"text":"好的"}\n\n',
    ])
    expect(events).toEqual([{ event: 'delta', data: { text: '好的' } }])
  })

  it('error 之后 done 仍然到来（契约：done 必发）', async () => {
    const events = await collectAsync([
      'event: error\ndata: {"code":"upstream_error","title":"上游 502","hint":"重试"}\n\n',
      'event: done\ndata: {"abstained":false,"reason":""}\n\n',
    ])
    expect(events.map((e) => e.event)).toEqual(['error', 'done'])
  })

  it('注释行与事件名缺 data 的帧被忽略', async () => {
    const events = await collectAsync([
      ': keep-alive\n\n',
      'event: delta\n\n',
      'event: delta\ndata: {"text":"x"}\n\n',
    ])
    expect(events).toEqual([{ event: 'delta', data: { text: 'x' } }])
  })
})
