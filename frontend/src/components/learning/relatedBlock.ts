import type { LearningTarget } from '../../api/types'
import { resolveLearningLink } from './links'

type Node = { type: string; url?: string; identifier?: string; children?: Node[] }

/** 在 Markdown 语法树上保留完整顶层块，列表、表格、代码不会被字符截断。 */
export function relatedBlock({ target }: { target: LearningTarget }) {
  return (tree: Node) => {
    const definitions = new Map(tree.children?.filter(n => n.type === 'definition').map(n => [n.identifier, n.url]))
    const matches = (node: Node): boolean => {
      if (node.type === 'code' || node.type === 'inlineCode') return false
      const url = node.type === 'link' ? node.url : node.type === 'linkReference' ? definitions.get(node.identifier) : undefined
      if (url && resolveLearningLink(url, [target], false)) return true
      return node.children?.some(matches) ?? false
    }
    const block = tree.children?.find(n => n.type !== 'definition' && matches(n))
    tree.children = block ? [block, ...(tree.children?.filter(n => n.type === 'definition') ?? [])] : []
  }
}
