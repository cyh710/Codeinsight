/**
 * 文件树模型（纯逻辑，无 React——直接单测）。
 *
 * 两条规则来自契约与 ADR 0015：
 * - `vendored`/`generated` **弱化显示**（契约 §3.6）：整目录都是第三方/生成
 *   代码时折叠成一个节点，不再往下展开；
 * - 其余 role 正常显示，测试/配置/文档加小徽标。
 */
import type { FileEntry, FileRole, SymbolKind, SymbolListItem } from '../../api/types'

export interface TreeNode {
  kind: 'dir' | 'file' | 'folded'
  /** 显示名（最后一段）。 */
  name: string
  /** 仓库根起的完整路径（posix）。 */
  path: string
  file?: FileEntry
  /** folded 节点收纳的文件数。 */
  foldedCount?: number
  children?: TreeNode[]
}

/** 弱化档（ADR 0015 第二档）：不是项目自己的代码。 */
export function isDeemphasizedRole(role: FileRole): boolean {
  return role === 'vendored' || role === 'generated'
}

export function buildFileTree(files: FileEntry[]): TreeNode[] {
  const root: TreeNode = { kind: 'dir', name: '', path: '', children: [] }

  for (const file of files) {
    const parts = file.path.split('/')
    let node = root
    for (let i = 0; i < parts.length - 1; i++) {
      const seg = parts.slice(0, i + 1).join('/')
      node.children ??= []
      let next = node.children.find((c) => c.kind === 'dir' && c.path === seg)
      if (!next) {
        next = { kind: 'dir', name: parts[i], path: seg, children: [] }
        node.children.push(next)
      }
      node = next
    }
    node.children ??= []
    node.children.push({ kind: 'file', name: parts[parts.length - 1], path: file.path, file })
  }

  const sortNodes = (nodes: TreeNode[]): TreeNode[] => {
    const order = (n: TreeNode) => (n.kind === 'dir' ? 0 : n.kind === 'folded' ? 1 : 2)
    return nodes
      .map((n) => (n.children ? { ...n, children: sortNodes(n.children) } : n))
      .sort((a, b) => order(a) - order(b) || a.name.localeCompare(b.name))
  }

  return sortNodes(collapseDeemphasized(root.children ?? []))
}

/**
 * 整棵子树都是 vendored/generated → 折成一个节点。
 * 目录下只要有一个项目自己的文件，就不折（那里还有真实代码要看）。
 */
function collapseDeemphasized(nodes: TreeNode[]): TreeNode[] {
  const result: TreeNode[] = []
  for (const node of nodes) {
    if (node.kind !== 'dir') {
      result.push(node)
      continue
    }
    // 判定与计数都基于**折叠前**的原始子树：先递归折叠会把纯第三方子目录
    // 换成 folded 节点，届时文件清单就丢了（folded 不携带 FileEntry）。
    const files = collectFiles(node.children ?? [])
    const allDeemphasized = files.length > 0 && files.every((f) => isDeemphasizedRole(f.role))
    if (allDeemphasized) {
      result.push({
        kind: 'folded',
        name: `${node.name}/`,
        path: node.path,
        foldedCount: files.length,
      })
    } else {
      result.push({ ...node, children: collapseDeemphasized(node.children ?? []) })
    }
  }
  return result
}

function collectFiles(nodes: TreeNode[]): FileEntry[] {
  const out: FileEntry[] = []
  const walk = (list: TreeNode[]) => {
    for (const n of list) {
      if (n.file) out.push(n.file)
      if (n.children) walk(n.children)
    }
  }
  walk(nodes)
  return out
}

/** 按前缀过滤；命中路径上的目录自动展开（filter 模式下不看 expandedDirs）。 */
export function filterTree(nodes: TreeNode[], query: string): TreeNode[] {
  const q = query.trim().toLowerCase()
  if (!q) return nodes

  const keep = (node: TreeNode): TreeNode | null => {
    if (node.kind === 'file' || node.kind === 'folded') {
      return node.path.toLowerCase().includes(q) ? node : null
    }
    const children = (node.children ?? [])
      .map(keep)
      .filter((c): c is TreeNode => c !== null)
    if (children.length > 0) return { ...node, children }
    return node.path.toLowerCase().includes(q) ? { ...node, children: [] } : null
  }

  return nodes
    .map(keep)
    .filter((n): n is TreeNode => n !== null)
}

/** 按 path 分组符号（左栏"点开文件看符号"用）。 */
export function groupSymbolsByPath(symbols: SymbolListItem[]): Map<string, SymbolListItem[]> {
  const map = new Map<string, SymbolListItem[]>()
  for (const s of symbols) {
    const list = map.get(s.path) ?? []
    list.push(s)
    map.set(s.path, list)
  }
  for (const list of map.values()) {
    list.sort((a, b) => a.lineno - b.lineno)
  }
  return map
}

const KIND_LABEL: Record<SymbolKind, string> = {
  module: 'mod',
  class: 'cls',
  function: 'fn',
  method: 'm',
  property: 'prop',
  constant: 'const',
}

export function symbolKindLabel(kind: SymbolKind): string {
  return KIND_LABEL[kind] ?? kind
}
