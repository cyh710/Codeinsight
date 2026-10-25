import { describe, expect, it } from 'vitest'
import { isTestCode, readingGraph } from '../src/components/graph/readingGraphModel'
import type { GraphEdge, GraphNode, GraphResponse } from '../src/api/types'

function node(id: number, path = 'src/store.py'): GraphNode {
  return {
    id,
    name: `f${id}`,
    qualname: `store.f${id}`,
    path,
    kind: 'function',
    lineno: id,
    end_lineno: id + 1,
    is_async: false,
    is_private: false,
    in_degree: 0,
    out_degree: 0,
    concept_ids: [],
    depth: id === 1 ? 0 : 1,
  }
}
function edge(src: number, dst: number, extra: Partial<GraphEdge> = {}): GraphEdge {
  return { src, dst, kind: 'call', lineno: src + 10, confidence: 1, uncertain: false, ...extra }
}
function graph(nodes: GraphNode[], edges: GraphEdge[]): GraphResponse {
  return {
    mode: 'focus',
    center: { qualname: 'store.f1', path: 'src/store.py', lineno: 1 },
    depth: 1,
    kinds: ['call'],
    nodes,
    edges,
    truncated: false,
  }
}

describe('局部调用阅读', () => {
  it('根据边方向区分调用者与目标，保留多处调用证据，不把其他关系或邻居间连线放入中心关系', () => {
    const incoming = edge(2, 1)
    const outgoing = edge(1, 3)
    const secondCall = edge(1, 3, { lineno: 30 })
    const model = readingGraph(
      graph(
        [node(1), node(2), node(3), node(4)],
        [incoming, outgoing, secondCall, edge(2, 3), edge(1, 4, { kind: 'inherits' })],
      ),
    )
    expect(model.callers.map((item) => item.node.id)).toEqual([2])
    expect(model.callees.map((item) => item.node.id)).toEqual([3])
    expect(model.callees[0].edges).toEqual([outgoing, secondCall])
    expect(model.callers[0].edges).toEqual([incoming])
  })

  it('双向调用保留两侧，自递归单独表示，不伪装成流程顺序', () => {
    const recursive = edge(1, 1)
    const model = readingGraph(graph([node(1), node(2)], [edge(2, 1), edge(1, 2), recursive]))
    expect(model.callers.map((item) => item.node.id)).toEqual([2])
    expect(model.callees.map((item) => item.node.id)).toEqual([2])
    expect(model.recursiveCalls).toEqual([recursive])
  })

  it('优先使用索引文件角色；缺少角色时按明确测试路径识别，不把普通业务名当测试', () => {
    expect(isTestCode('tests/test_store.py')).toBe(true)
    expect(isTestCode('src/store_test.py')).toBe(true)
    expect(isTestCode('backend/latest_store.py')).toBe(false)
    expect(isTestCode('checks/a.py', [{ path: 'checks/a.py', role: 'test' }])).toBe(true)
    expect(isTestCode('tests/domain.py', [{ path: 'tests/domain.py', role: 'source' }])).toBe(false)
    const model = readingGraph(graph([node(1), node(2, 'tests/test_store.py')], [edge(2, 1)]))
    expect(model.callers[0].isTest).toBe(true)
  })

  it('不确定边的置信度与调用行号原样保留', () => {
    const uncertain = edge(1, 2, { confidence: 0.6, uncertain: true, lineno: 82 })
    const model = readingGraph(graph([node(1), node(2)], [uncertain]))
    expect(model.callees[0].edges).toEqual([uncertain])
  })

  it('不为缺失中心或悬空边生成节点，返回顺序不受后端节点顺序影响', () => {
    expect(readingGraph(graph([node(2)], [edge(1, 2)])).center).toBeNull()
    const nodes = [node(1), node(2), node(3)]
    const edges = [edge(1, 3), edge(1, 2), edge(1, 99)]
    const first = readingGraph(graph(nodes, edges))
    const second = readingGraph(graph([...nodes].reverse(), [...edges].reverse()))
    expect(first.callees.map((item) => item.node.id)).toEqual([2, 3])
    expect(second.callees.map((item) => item.node.id)).toEqual([2, 3])
  })
})
