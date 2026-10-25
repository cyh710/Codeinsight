/** 局部阅读只解释中心的直接调用；不从无向跳数猜调用方向或执行顺序。 */
import type { FileEntry, GraphEdge, GraphNode, GraphResponse } from '../../api/types'

export interface ReadingConnection {
  node: GraphNode
  edges: GraphEdge[]
  isTest: boolean
}

export interface ReadingGraph {
  center: GraphNode | null
  callers: ReadingConnection[]
  callees: ReadingConnection[]
  recursiveCalls: GraphEdge[]
}

export function isTestCode(path: string, files: Pick<FileEntry, 'path' | 'role'>[] = []): boolean {
  const indexed = files.find((file) => file.path === path)
  if (indexed) return indexed.role === 'test'
  return /(^|\/)(tests?|__tests__)(\/|$)|(^|\/)test_[^/]*\.py$|_test\.py$/.test(
    path.replaceAll('\\', '/'),
  )
}

export function readingGraph(
  data: GraphResponse,
  files: Pick<FileEntry, 'path' | 'role'>[] = [],
): ReadingGraph {
  const center = data.nodes.find((node) => node.qualname === data.center?.qualname) ?? null
  if (!center) return { center: null, callers: [], callees: [], recursiveCalls: [] }
  const nodes = new Map(data.nodes.map((node) => [node.id, node]))
  const callers = new Map<number, ReadingConnection>()
  const callees = new Map<number, ReadingConnection>()
  const recursiveCalls: GraphEdge[] = []
  const add = (map: Map<number, ReadingConnection>, id: number, edge: GraphEdge) => {
    const node = nodes.get(id)
    if (!node) return
    const existing = map.get(id)
    if (existing) existing.edges.push(edge)
    else map.set(id, { node, edges: [edge], isTest: isTestCode(node.path, files) })
  }
  for (const edge of data.edges) {
    if (edge.kind !== 'call') continue
    if (edge.src === center.id && edge.dst === center.id) recursiveCalls.push(edge)
    else if (edge.dst === center.id) add(callers, edge.src, edge)
    else if (edge.src === center.id) add(callees, edge.dst, edge)
  }
  const sorted = (map: Map<number, ReadingConnection>) =>
    [...map.values()].sort(
      (a, b) =>
        a.node.path.localeCompare(b.node.path) ||
        a.node.lineno - b.node.lineno ||
        a.node.id - b.node.id,
    )
  return { center, callers: sorted(callers), callees: sorted(callees), recursiveCalls }
}
