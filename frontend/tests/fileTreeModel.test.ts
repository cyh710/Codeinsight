/**
 * 文件树模型测试：vendored 折叠（ADR 0015 第二档的弱化显示）、
 * 目录排序（目录在前）、过滤与自动展开。
 */
import { describe, expect, it } from 'vitest'
import { buildFileTree, filterTree, isDeemphasizedRole } from '../src/components/tree/fileTreeModel'
import type { FileEntry } from '../src/api/types'

function file(path: string, role: FileEntry['role'] = 'source'): FileEntry {
  return { path, language: 'python', role, content_sha256: '', size_bytes: 0, line_count: 0, symbol_count: 0 }
}

describe('buildFileTree', () => {
  it('目录排在文件前，同级按名排序', () => {
    const nodes = buildFileTree([file('z.py'), file('a/b.py'), file('m.py'), file('a/c.py')])
    expect(nodes.map((n) => n.name)).toEqual(['a', 'm.py', 'z.py'])
    const a = nodes[0]
    expect(a.kind).toBe('dir')
    expect((a.children ?? []).map((c) => c.name)).toEqual(['b.py', 'c.py'])
  })

  it('整目录 vendored → 折成一个节点，弱化显示', () => {
    const nodes = buildFileTree([file('src/a.py'), file('mobile_sam/x.py', 'vendored'), file('mobile_sam/deep/y.py', 'vendored')])
    const folded = nodes.find((n) => n.kind === 'folded')
    expect(folded?.name).toBe('mobile_sam/')
    expect(folded?.foldedCount).toBe(2)
    // 项目自己的代码正常展示
    expect(nodes.some((n) => n.path === 'src')).toBe(true)
  })

  it('目录里有项目自己的文件就不折（那里还有真实代码）', () => {
    const nodes = buildFileTree([file('lib/mine.py'), file('lib/third_party.py', 'vendored')])
    expect(nodes.some((n) => n.kind === 'folded')).toBe(false)
    const lib = nodes.find((n) => n.path === 'lib')
    expect((lib?.children ?? []).length).toBe(2)
  })

  it('isDeemphasizedRole 只认 vendored/generated', () => {
    expect(isDeemphasizedRole('vendored')).toBe(true)
    expect(isDeemphasizedRole('generated')).toBe(true)
    expect(isDeemphasizedRole('test')).toBe(false)
    expect(isDeemphasizedRole('source')).toBe(false)
  })
})

describe('filterTree', () => {
  const tree = buildFileTree([file('backend/core/chat.py'), file('backend/api/pet.py'), file('docs/readme.md')])

  it('按路径子串过滤，命中路径上的目录保留', () => {
    const filtered = filterTree(tree, 'chat')
    const paths = JSON.stringify(filtered)
    expect(paths).toContain('chat.py')
    expect(paths).not.toContain('pet.py')
  })

  it('无查询时原样返回', () => {
    expect(filterTree(tree, '  ')).toBe(tree)
  })

  it('目录名命中时保留整棵子树', () => {
    const filtered = filterTree(tree, 'docs')
    expect(JSON.stringify(filtered)).toContain('readme.md')
  })

  it('符号命中的文件即使路径不含查询词也保留', () => {
    // 搜索框写着"搜索文件或符号…"：符号名命中时，
    // 所在文件路径不含查询词也得留在树里。
    const filtered = filterTree(tree, 'orchestrate', new Set(['backend/api/pet.py']))
    const paths = JSON.stringify(filtered)
    expect(paths).toContain('pet.py')
    expect(paths).not.toContain('chat.py')
  })

  it('符号命中集合为空时行为与原来一致', () => {
    const filtered = filterTree(tree, 'chat', new Set())
    expect(JSON.stringify(filtered)).toContain('chat.py')
    expect(JSON.stringify(filtered)).not.toContain('pet.py')
  })
})
