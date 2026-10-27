/** 旧概念解读的独有文字仍可阅读，已在正文出现的段落不重复展示。 */
export function additionalExplanation(summary: string, items: { text: string }[]): string[] {
  const plain = (s: string) => s.replace(/[*_`#\s]/g, '')
  let shown = plain(summary)
  const extra: string[] = []
  for (const item of items) {
    const text = item.text.trim()
    const comparable = plain(text)
    if (!comparable || shown.includes(comparable)) continue
    extra.push(text)
    shown += comparable
  }
  return extra
}
