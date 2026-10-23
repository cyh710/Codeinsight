import { readFileSync } from 'node:fs'
import { describe, expect, it } from 'vitest'

function readSource(path: string): string {
  return readFileSync(new URL(path, import.meta.url), 'utf8')
}

/**
 * 弹层层级契约：应用设置弹窗与桌宠工作台都是 z-[80] 宿主。历史上 Modal /
 * ConfirmDialog 默认 z-50，凡调用方忘传 zClass 的弹层在宿主里会被整个盖住
 * （用户视角＝"按钮按了没反应"）。默认层现在必须高于宿主层。
 */
describe('modal layering contract', () => {
  it('Modal 默认层高于 z-80 宿主，ConfirmDialog 默认压过普通弹窗', () => {
    expect(readSource('../src/components/common/Modal.tsx')).toContain("zClass = 'z-[90]'")
    expect(readSource('../src/components/common/ConfirmDialog.tsx')).toContain("zClass = 'z-[100]'")
  })
})

// CodeInsight 适配：织忆的 z-80 宿主（SettingsDialog / PetStudioDialog）与
// 创作向导未随基建复制，它们专属的源码断言随之移除；
// 通用件（Modal / ConfirmDialog）的层级契约断言原样保留。
