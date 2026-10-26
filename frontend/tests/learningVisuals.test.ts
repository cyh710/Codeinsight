import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import type { KnowledgeAsset } from '../src/api/types'
import LearningMarkdown from '../src/components/learning/LearningMarkdown'
import { resolveVisualAsset } from '../src/components/learning/visualAssets'

const sha = 'a'.repeat(64)
const asset: KnowledgeAsset = {
  id: 'sample', topic_id: 'sample-topic', section_id: 'example', title: '返回值的去向',
  description: '打印显示 36，普通函数无 return 时正常返回 None。', width: 440, height: 560,
  author: 'CodeInsight', license: 'Apache-2.0', source_ids: [], sha256: sha,
  href: `/knowledge/assets/sample/${sha}`, media_type: 'image/svg+xml',
}

describe('受维护教材图示', () => {
  it('只启用当前清单中的资源，不加载远程图和未知地址', () => {
    expect(resolveVisualAsset('/knowledge/assets/sample', [asset])).toEqual(asset)
    for (const src of ['https://example.com/a.png', '/knowledge/assets/unknown', '/knowledge/assets/../secret']) {
      expect(resolveVisualAsset(src, [asset])).toBeUndefined()
    }
    expect(resolveVisualAsset('/knowledge/assets/sample', [{ ...asset, href: 'https://other/a.svg' }])).toBeUndefined()
    const html = renderToStaticMarkup(createElement(LearningMarkdown, {
      text: '![外部图](https://example.com/a.png)', assets: [asset],
    }))
    expect(html).not.toContain('<img')
    expect(html).toContain('外部图')
  })

  it('图片预留尺寸，图注映射真实原文的 UTF-16 偏移，不产生 p 内嵌 figure', () => {
    const caption = '中文 😀 & 返回值'
    const text = `![${caption}](/knowledge/assets/sample)`
    const html = renderToStaticMarkup(createElement(LearningMarkdown, { text, assets: [asset], selectable: true }))
    expect(html).toContain(`src="/api${asset.href}"`)
    expect(html).toContain('width="440" height="560"')
    expect(html).toContain('<figcaption>')
    expect(html).not.toContain('<p><figure')
    const map = JSON.parse(/data-source-map="([^"]+)"/.exec(html)![1]) as number[]
    expect(map[0]).toBe(2)
    expect(map.at(-1)).toBe(2 + caption.length)
    expect(text.slice(map[3], map[5])).toBe('😀')
  })
})
