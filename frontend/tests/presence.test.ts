import { describe, expect, it } from 'vitest'
import { presenceTransition, type PresencePhase } from '../src/components/common/Presence'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

/**
 * Presence 原语契约（docs/tasks/2026-09-10-system-motion.md §3）。
 * Node 环境无 DOM/测试渲染器：状态机用纯函数钉住，接线行为用源文契约钉住。
 */

function readSource(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

function step(prev: PresencePhase, open: boolean): PresencePhase {
  return presenceTransition(prev, open)
}

describe('presence state machine', () => {
  it('enters from closed to open', () => {
    expect(step('closed', true)).toBe('open')
  })

  it('stays closed while closed', () => {
    expect(step('closed', false)).toBe('closed')
  })

  it('moves open to exiting on close (exit animation window)', () => {
    expect(step('open', false)).toBe('exiting')
  })

  it('does not restart the exit while already exiting', () => {
    expect(step('exiting', false)).toBe('exiting')
  })

  it('cancels the exit when reopened during the exit window', () => {
    expect(step('exiting', true)).toBe('open')
  })
})

describe('presence wiring contract', () => {
  it('usePresence exposes mounted/exiting/finishExit and a fallback timer', () => {
    const presence = readSource('../src/components/common/Presence.tsx')
    expect(presence).toContain('finishExit')
    expect(presence).toContain('window.setTimeout')
    // 兜底计时器只在退出期存在，进入/打开时不得留下常驻定时器
    expect(presence).toMatch(/if \(phase !== 'exiting'\) return/)
  })
})
