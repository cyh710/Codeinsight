/** 用现有 Markdown AST 映射回原文位置，DOM 文字只作预览。 */
import type { KnowledgeTopic, KnowledgeReadingContext } from '../../api/types'
interface SourceNode {
  type: string; value?: string; children?: SourceNode[]
  position?: { start: { offset?: number }; end: { offset?: number } }
  data?: Record<string, unknown>
}
export function textOffsets(raw: string, value: string, base: number): number[] | null {
  const offsets = [base]
  let source = 0, visible = 0
  const named: Record<string, string> = { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: '\u00a0' }
  while (visible < value.length) {
    if (raw[source] === '\\' && raw[source + 1] === value[visible]) { source += 2; visible++; offsets.push(base + source); continue }
    const entity = /^&(#x[\da-f]+|#\d+|[a-z]+);/i.exec(raw.slice(source))
    if (entity) {
      const name = entity[1]
      const decoded = name.startsWith('#x') ? String.fromCodePoint(parseInt(name.slice(2), 16)) : name.startsWith('#') ? String.fromCodePoint(Number(name.slice(1))) : named[name]
      if (decoded && value.slice(visible).startsWith(decoded)) {
        for (let n = 1; n <= decoded.length; n++) offsets.push(base + source + (n === decoded.length ? entity[0].length : 0))
        source += entity[0].length; visible += decoded.length; continue
      }
    }
    if (raw[source] === value[visible]) { source++; visible++; offsets.push(base + source); continue }
    return null
  }
  return offsets
}
export function sourcePositions() {
  return (tree: SourceNode, file: { value: unknown }) => {
    const source = String(file.value)
    const visit = (node: SourceNode) => {
      const from = node.position?.start.offset, to = node.position?.end.offset
      if (node.value !== undefined && from !== undefined && to !== undefined) {
        let raw = source.slice(from, to), base = from, value = node.value
        if (node.type === 'inlineCode') {
          const fence = /^`+/.exec(raw)?.[0].length ?? 0
          base += fence; raw = raw.slice(fence, -fence).replace(/\n/g, ' ')
          if (raw.startsWith(' ') && raw.endsWith(' ') && raw.trim()) { raw = raw.slice(1, -1); base++ }
        } else if (node.type === 'code') {
          const newline = raw.indexOf('\n')
          if (/^\s*(```|~~~)/.test(raw)) { base += newline + 1; raw = raw.slice(newline + 1) }
          value += '\n'
        }
        if (['text', 'inlineCode', 'code'].includes(node.type)) {
          const offsets = textOffsets(raw, value, base)
          if (offsets) node.data = { ...node.data, ...(node.type === 'text' ? { hName: 'span' } : {}), hProperties: { 'data-source-map': JSON.stringify(offsets) } }
        }
      }
      node.children?.forEach(visit)
    }
    visit(tree)
  }
}
function sourcePoint(node: Node, offset: number, end: boolean): { section: string; offset: number } | null {
  if (node.nodeType !== Node.TEXT_NODE) {
    const child = node.childNodes[end ? Math.max(0, offset - 1) : offset]
    if (!child) return null
    const walker = document.createTreeWalker(child, NodeFilter.SHOW_TEXT)
    const texts: Node[] = child.nodeType === Node.TEXT_NODE ? [child] : []
    while (walker.nextNode()) texts.push(walker.currentNode)
    node = (end ? texts.at(-1) : texts[0]) ?? child
    offset = end ? node.textContent?.length ?? 0 : 0
  }
  const element = node.parentElement?.closest<HTMLElement>('[data-source-map]')
  const section = element?.closest<HTMLElement>('[data-section-id]')?.dataset.sectionId
  if (!element || !section) return null
  const range = document.createRange(); range.selectNodeContents(element); range.setEnd(node, offset)
  const offsets: number[] = JSON.parse(element.dataset.sourceMap!)
  const mapped = offsets[range.toString().length]
  return mapped === undefined ? null : { section, offset: mapped }
}
export function selectedKnowledge(root: HTMLElement, topic: KnowledgeTopic): KnowledgeReadingContext {
  const selection = getSelection()
  if (!selection || selection.isCollapsed || !selection.rangeCount) throw new Error('请先选中教材正文中的一段文字。')
  const range = selection.getRangeAt(0)
  if (!root.contains(range.startContainer) || !root.contains(range.endContainer)) throw new Error('选区必须位于同一篇教材内。')
  const start = sourcePoint(range.startContainer, range.startOffset, false), end = sourcePoint(range.endContainer, range.endOffset, true)
  if (!start || !end) throw new Error('请选择正文文字，目录、按钮和来源说明不属于正文选区。')
  const from = topic.sections.findIndex(s => s.id === start.section), to = topic.sections.findIndex(s => s.id === end.section)
  if (from < 0 || to < from) throw new Error('无法定位这段原文，请重新选择。')
  const ranges = topic.sections.slice(from, to + 1).map((section, i, sections) => ({ section_id: section.id, start_offset: i === 0 ? start.offset : 0, end_offset: i === sections.length - 1 ? end.offset : section.content.length }))
  return { kind: 'knowledge', topic_id: topic.id, title: topic.title, section_id: start.section, section_title: topic.sections[from].title, version: topic.version, selection: { ranges }, preview: selection.toString() }
}
