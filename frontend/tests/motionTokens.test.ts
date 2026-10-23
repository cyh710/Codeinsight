import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'
import { staggerDelayMs } from '../src/components/common/motion'

/**
 * 系统动效契约（docs/tasks/2026-09-10-system-motion.md §1/§13/§9）。
 * Node 环境无 DOM：令牌与关键动画 class 靠读 index.css 源文钉住。
 */

function readSource(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

const indexCss = readSource('../src/index.css')

describe('motion tokens (§1)', () => {
  it('defines the five canonical duration tokens with spec values', () => {
    expect(indexCss).toMatch(/--motion-instant:\s*80ms/)
    expect(indexCss).toMatch(/--motion-fast:\s*150ms/)
    expect(indexCss).toMatch(/--motion-base:\s*220ms/)
    expect(indexCss).toMatch(/--motion-slow:\s*320ms/)
    expect(indexCss).toMatch(/--motion-ambient:\s*500ms/)
  })

  it('defines the four canonical easing tokens', () => {
    expect(indexCss).toMatch(/--ease-standard:\s*cubic-bezier\(0\.2,\s*0,\s*0,\s*1\)/)
    expect(indexCss).toMatch(/--ease-enter:\s*cubic-bezier\(0\.16,\s*1,\s*0\.3,\s*1\)/)
    expect(indexCss).toMatch(/--ease-exit:\s*cubic-bezier\(0\.4,\s*0,\s*1,\s*1\)/)
    expect(indexCss).toMatch(/--ease-emphasized:\s*cubic-bezier\(0\.2,\s*0\.8,\s*0\.2,\s*1\)/)
  })

  it('keeps legacy token names as aliases pointing at the new tokens', () => {
    expect(indexCss).toMatch(/--duration-fast:\s*var\(--motion-fast\)/)
    expect(indexCss).toMatch(/--duration-base:\s*var\(--motion-base\)/)
    expect(indexCss).toMatch(/--ease-out-emphasized:\s*var\(--ease-enter\)/)
  })

  it('keeps reduced-motion coverage including stagger delays', () => {
    expect(indexCss).toMatch(/prefers-reduced-motion:\s*reduce/)
    expect(indexCss).toMatch(/animation-delay:\s*0ms\s*!important/)
    expect(indexCss).toMatch(/transition-delay:\s*0ms\s*!important/)
  })
})

describe('shared motion classes (§13)', () => {
  it('provides the public motion-* animation classes', () => {
    for (const cls of [
      '.motion-fade',
      '.motion-rise',
      '.motion-scale',
      '.motion-slide-left',
      '.motion-slide-right',
      '.motion-press',
      '.motion-pop-in',
      '.motion-nudge-x',
      '.motion-pulse-soft',
      '.motion-width',
      '.motion-image-in',
    ]) {
      expect(indexCss, `missing ${cls}`).toContain(cls)
    }
  })

  it('provides the modal exit, drawer, crossfade and stagger classes', () => {
    for (const cls of [
      '.modal-backdrop.modal-exiting',
      '.modal-panel-drawer-left',
      '.modal-panel-drawer-right',
      '.bg-layer-in',
      '.chat-swap-in',
      '.stagger-item',
      '.asr-ring',
      '.asr-success-glow',
    ]) {
      expect(indexCss, `missing ${cls}`).toContain(cls)
    }
  })

  it('keeps message entrance distance restrained at 6px (§4)', () => {
    const block = indexCss.match(/@keyframes bubble-in\s*\{[\s\S]*?\n\}/)
    expect(block).not.toBeNull()
    expect(block?.[0]).toContain('translateY(6px)')
    expect(block?.[0]).not.toContain('translateY(12px)')
  })
})

describe('list stagger cap (§9)', () => {
  it('staggers the first six cards by 25ms and zeroes everything after', () => {
    expect(staggerDelayMs(0)).toBe(0)
    expect(staggerDelayMs(1)).toBe(25)
    expect(staggerDelayMs(5)).toBe(125)
    expect(staggerDelayMs(6)).toBe(0)
    expect(staggerDelayMs(20)).toBe(0)
  })

  it('rejects invalid indices and honours custom step/cap', () => {
    expect(staggerDelayMs(-1)).toBe(0)
    expect(staggerDelayMs(1.5)).toBe(0)
    expect(staggerDelayMs(2, 40)).toBe(80)
    expect(staggerDelayMs(3, 25, 3)).toBe(0)
  })
})

describe('modal exit via presence (§3)', () => {
  it('plays the exit animation before unmount and keeps the stack contract', () => {
    const modal = readSource('../src/components/common/Modal.tsx')
    // 退出走 Presence 原语，animationend 后才真正卸载
    expect(modal).toContain('usePresence')
    expect(modal).toContain('modal-exiting')
    expect(modal).toContain('finishExit')
    // animationend 必须过滤子元素动画冒泡
    expect(modal).toContain('event.target !== event.currentTarget')
    // ESC/模态栈/滚动锁行为保留
    expect(modal).toContain("event.key === 'Escape'")
    expect(modal).toContain('modalStack')
    expect(modal).toContain("document.body.style.overflow = 'hidden'")
  })

  it('supports per-purpose motion variants (drawer-left / drawer-right)', () => {
    const modal = readSource('../src/components/common/Modal.tsx')
    expect(modal).toContain('drawer-left')
    expect(modal).toContain('drawer-right')
  })
})

// CodeInsight 适配：§6/§7（氛围背景双层 crossfade）与 §9（角色列表/作品墙
// stagger）断言的是织忆业务组件（sidebar / creation），未随基建复制，整块移除。
// §10 的创作向导进度条、§11 的 PetSettings 调用方与 MessageBubble 成功勾
// 同理移除；通用件与 index.css 的动效契约断言全部原样保留。

describe('creation status transitions (§10)', () => {
  it('RetryableImage reveals with a blur-in instead of a bare fade', () => {
    const image = readSource('../src/components/common/RetryableImage.tsx')
    expect(image).toContain('motion-image-in')
    expect(image).toContain('motion-image-in--pending')
    expect(image).not.toContain('duration-150')
  })
})

describe('toast / success unification (§11)', () => {
  it('provides the toast motion classes with spec values', () => {
    expect(indexCss).toContain('.motion-toast')
    expect(indexCss).toContain('.motion-toast-exit')
    const toastIn = indexCss.match(/@keyframes toast-in\s*\{[\s\S]*?\n\}/)
    expect(toastIn?.[0]).toContain('translateY(-6px)')
    const toastOut = indexCss.match(/@keyframes toast-out\s*\{[\s\S]*?\n\}/)
    expect(toastOut?.[0]).toContain('translateY(-4px)')
  })

  it('keeps the notice on the shared Toast primitive', () => {
    const toast = readSource('../src/components/common/Toast.tsx')
    expect(toast).toContain('usePresence')
    expect(toast).toContain('role="status"')
    // CodeInsight 适配：PetSettings 调用方断言移除（未随基建复制）。
  })
})

describe('button press feedback (§2)', () => {
  it('wires the press class into Button and Chip', () => {
    const button = readSource('../src/components/common/Button.tsx')
    const chip = readSource('../src/components/common/Chip.tsx')
    expect(button).toContain('motion-press')
    expect(chip).toContain('motion-press')
    // 纯展示 chip 不参与按压
    expect(chip).toMatch(/interactive \? 'motion-press' : 'transition-colors'/)
  })

  it('press is soft: 80ms down / 150ms release via tokens, no bounce keyframes', () => {
    const press = indexCss.match(/\.motion-press[\s\S]*?\.motion-press:active:not\(:disabled\)\s*\{[^}]*\}/)
    expect(press).not.toBeNull()
    expect(press?.[0]).toContain('scale(0.98)')
    expect(press?.[0]).toContain('var(--motion-instant)')
    expect(indexCss).not.toMatch(/@keyframes[^{]*(bounce|spring|wobble)/)
  })

  it('lift is reserved for the primary variant only', () => {
    const button = readSource('../src/components/common/Button.tsx')
    expect(button).toContain("variant === 'primary' ? 'motion-press-lift '")
  })
})
