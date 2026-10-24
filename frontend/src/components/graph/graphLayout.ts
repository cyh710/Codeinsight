/**
 * 关系图布局：**不做力导向**，用确定性的分列布局。
 *
 * 理由：
 * - 力导向每次打开位置都不一样，同一条调用关系没法在两次浏览间对照；
 * - 分层（中心 → 1 跳 → 2 跳）本身就是这张图要表达的信息（源文档 §2.2-6）；
 * - 纯函数可以直接单测，不用起浏览器。
 *
 * 列内顺序用**重心法**（按邻列邻居的平均下标排序），少一些交叉线。
 */
import type { GraphEdge, GraphNode } from '../../api/types'

export const NODE_WIDTH = 208
export const NODE_HEIGHT = 96
export const COL_GAP = 72
export const ROW_GAP = 22

/**
 * 一跳里可能有二三十个邻居。若竖着排成一列，fitView 会被高度压到 0.2 倍，
 * 字全糊掉。所以**每一跳是一个横向的带**，带内超过 6 行就折到下一子列——
 * 子列仍属同一跳（x 只用于排布，不表示距离）。
 */
const MAX_ROWS = 6

export interface Point {
  x: number
  y: number
}

export function layoutGraph(
  nodes: GraphNode[],
  edges: GraphEdge[],
): Map<number, Point> {
  const positions = new Map<number, Point>()
  if (nodes.length === 0) return positions

  const hasDepth = nodes.some((n) => n.depth !== null)
  if (!hasDepth) {
    // 概览图：按后端给的顺序（调用度降序）排成网格。
    const cols = Math.min(5, Math.max(1, Math.ceil(Math.sqrt(nodes.length))))
    nodes.forEach((node, i) => {
      positions.set(node.id, {
        x: (i % cols) * (NODE_WIDTH + COL_GAP),
        y: Math.floor(i / cols) * (NODE_HEIGHT + ROW_GAP),
      })
    })
    return positions
  }

  const maxDepth = Math.max(...nodes.map((n) => n.depth ?? 0))
  const columns: GraphNode[][] = Array.from({ length: maxDepth + 1 }, () => [])
  for (const node of nodes) columns[node.depth ?? 0].push(node)
  for (const column of columns) column.sort(byQualname)

  // 重心排序：第 d 列按它在第 d-1 列里的邻居位置排序。
  const indexInColumn = new Map<number, number>()
  columns[0].forEach((node, i) => indexInColumn.set(node.id, i))
  const incoming = neighborIndex(edges)
  for (let d = 1; d < columns.length; d++) {
    const score = new Map<number, number>()
    for (const node of columns[d]) {
      const previous = (incoming.get(node.id) ?? [])
        .filter((other) => indexInColumn.has(other))
        .map((other) => indexInColumn.get(other)!)
      score.set(
        node.id,
        previous.length > 0 ? previous.reduce((a, b) => a + b, 0) / previous.length : Number.POSITIVE_INFINITY,
      )
    }
    columns[d].sort(
      (a, b) => (score.get(a.id)! - score.get(b.id)!) || byQualname(a, b),
    )
    columns[d].forEach((node, i) => indexInColumn.set(node.id, i))
  }

  const cellW = NODE_WIDTH + COL_GAP
  const cellH = NODE_HEIGHT + ROW_GAP
  const tallestRows = Math.min(MAX_ROWS, Math.max(...columns.map((c) => c.length)))

  let bandX = 0
  columns.forEach((column) => {
    // 带内折行：先竖着填，填满 6 行再开下一个子列。
    const rows = Math.min(MAX_ROWS, column.length)
    const subColumns = Math.ceil(column.length / MAX_ROWS)
    const offset = ((tallestRows - rows) * cellH) / 2
    column.forEach((node, i) => {
      positions.set(node.id, {
        x: bandX + Math.floor(i / MAX_ROWS) * cellW,
        y: offset + (i % MAX_ROWS) * cellH,
      })
    })
    // 整带用同一段 x 区间；带与带之间自然留下一个 COL_GAP。
    bandX += subColumns * cellW
  })
  return positions
}

function byQualname(a: GraphNode, b: GraphNode): number {
  return a.qualname.localeCompare(b.qualname) || a.lineno - b.lineno
}

/** 每个节点 → 与它相连（任意方向）的节点 id 列表。 */
function neighborIndex(edges: GraphEdge[]): Map<number, number[]> {
  const out = new Map<number, number[]>()
  const add = (a: number, b: number) => {
    const list = out.get(a)
    if (list) list.push(b)
    else out.set(a, [b])
  }
  for (const edge of edges) {
    add(edge.src, edge.dst)
    add(edge.dst, edge.src)
  }
  return out
}
