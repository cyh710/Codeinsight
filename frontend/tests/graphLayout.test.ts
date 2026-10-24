/**
 * 关系图布局：分层必须反映跳数；列内重心排序要真的影响顺序；
 * 同一份数据两次布局结果完全一致（不用力导向就是为了这个）。
 */
import { describe, expect, it } from 'vitest'
import { COL_GAP, NODE_HEIGHT, NODE_WIDTH, ROW_GAP, layoutGraph } from '../src/components/graph/graphLayout'
import type { GraphEdge, GraphNode } from '../src/api/types'

function node(
  id: number,
  qualname: string,
  depth: number | null,
  extra: Partial<GraphNode> = {},
): GraphNode {
  return {
    id,
    qualname,
    name: qualname.split('.').pop() ?? qualname,
    kind: 'function',
    path: 'src/x.py',
    lineno: id,
    end_lineno: id + 1,
    is_async: false,
    is_private: false,
    in_degree: 0,
    out_degree: 0,
    concept_ids: [],
    depth,
    ...extra,
  }
}

function edge(src: number, dst: number): GraphEdge {
  return { src, dst, kind: 'call', lineno: 1, confidence: 1, uncertain: false }
}

describe('layoutGraph', () => {
  it('按跳数分列：中心在第 0 列，每深一跳右移一列', () => {
    const nodes = [node(1, 'a.center', 0), node(2, 'a.left', 1), node(3, 'a.right', 1), node(4, 'a.deep', 2)]
    const pos = layoutGraph(nodes, [edge(1, 2), edge(1, 3), edge(2, 4)])
    expect(pos.get(1)!.x).toBe(0)
    expect(pos.get(2)!.x).toBe(NODE_WIDTH + COL_GAP)
    expect(pos.get(3)!.x).toBe(NODE_WIDTH + COL_GAP)
    expect(pos.get(4)!.x).toBe(2 * (NODE_WIDTH + COL_GAP))
    // 同一列内不重叠
    expect(Math.abs(pos.get(2)!.y - pos.get(3)!.y)).toBe(NODE_HEIGHT + ROW_GAP)
  })

  it('列内按上一列邻居的重心排序，而不是纯字典序', () => {
    // 深度 1：aa 与 zz 都连中心 → 字典序 aa, zz
    // 深度 2：zzz 连 aa，aaa 连 zz → 重心法应把 zzz 排在 aaa 前面
    const nodes = [
      node(1, 'c', 0),
      node(2, 'aa', 1),
      node(3, 'zz', 1),
      node(4, 'zzz', 2),
      node(5, 'aaa', 2),
    ]
    const pos = layoutGraph(nodes, [edge(1, 2), edge(1, 3), edge(2, 4), edge(3, 5)])
    expect(pos.get(4)!.y).toBeLessThan(pos.get(5)!.y)
  })

  it('同一跳超过 6 个节点时折到子列，不把画布拉成一列', () => {
    const nodes = [node(1, 'c', 0), ...Array.from({ length: 8 }, (_, i) => node(i + 2, `n${i}`, 1))]
    const pos = layoutGraph(nodes, [edge(1, 2)])
    const first = pos.get(2)!
    const seventh = pos.get(8)!
    expect(seventh.x).toBe(first.x + NODE_WIDTH + COL_GAP)
    expect(seventh.y).toBe(first.y)
    // 第 7 个（下标 6）与第 1 个同列
    expect(pos.get(9)!.y).toBe(first.y + NODE_HEIGHT + ROW_GAP)
  })

  it('概览图（depth 全为 null）排成网格且不重叠', () => {
    const nodes = Array.from({ length: 6 }, (_, i) => node(i + 1, `s${i}`, null))
    const pos = layoutGraph(nodes, [])
    const seen = new Set<string>()
    for (const p of pos.values()) seen.add(`${p.x},${p.y}`)
    expect(seen.size).toBe(6)
    expect(pos.get(1)!.x).toBe(0)
    expect(pos.get(2)!.y).toBe(pos.get(1)!.y)
  })

  it('空图返回空映射，且同一输入结果稳定', () => {
    expect(layoutGraph([], []).size).toBe(0)
    const nodes = [node(1, 'b', 0), node(2, 'a', 1)]
    const first = layoutGraph(nodes, [edge(1, 2)])
    const second = layoutGraph(nodes, [edge(1, 2)])
    expect([...first.entries()]).toEqual([...second.entries()])
  })
})
