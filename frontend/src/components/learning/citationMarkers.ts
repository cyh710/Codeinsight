import type { Citation } from '../../api/types'

interface Node { type: string; value?: string; url?: string; children?: Node[] }

/** 只转换普通正文中的已解析引用；代码与既有链接保持原样。 */
export function citationMarkers(options: { citations: Citation[]; label?: 'number' | 'file' }) {
  return (root: Node) => {
    const visit = (node: Node) => {
      if (['code', 'inlineCode', 'link', 'image'].includes(node.type)) return
      if (!node.children) return
      node.children = node.children.flatMap(child => {
        if (child.type !== 'text' || !child.value) { visit(child); return [child] }
        const text = child.value, parts: Node[] = []
        const pattern = /\[([^\]\n]+):(\d+)(?:-(\d+))?\]/g
        let cursor = 0
        for (const match of text.matchAll(pattern)) {
          const index = options.citations.findIndex(c => c.path === match[1] && c.lineno === Number(match[2]))
          if (index < 0) continue
          if (match[3] && Number(match[3]) < Number(match[2])) continue
          if (match.index > cursor) parts.push({ type: 'text', value: text.slice(cursor, match.index) })
          const name = match[1].split('/').pop() || match[1]
          const label = options.label === 'file' ? `${name}:${match[2]}${match[3] ? `–${match[3]}` : ''}` : `[${index + 1}]`
          parts.push({ type: 'link', url: `/__code_ref/${index}`, children: [{ type: 'text', value: label }] })
          cursor = match.index + match[0].length
        }
        if (cursor < text.length) parts.push({ type: 'text', value: text.slice(cursor) })
        return parts.length ? parts : [child]
      })
    }
    visit(root)
  }
}
