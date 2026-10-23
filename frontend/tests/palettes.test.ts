import { describe, expect, it } from 'vitest'
import {
  DEFAULT_PALETTE_ID,
  PALETTES,
  PALETTE_ORDER,
  getPalette,
  hexToRgbChannels,
  isPaletteId,
  normalizePaletteId,
  paletteCssVars,
  type Palette,
} from '../src/theme/palettes'

// WCAG 2.x 相对亮度与对比度（与 docs/tasks/2026-09-10-ui-color-palettes.md
// 的验证脚本同一套公式；阈值即验收契约）。
function luminance(hex: string): number {
  const channels = hexToRgbChannels(hex)
  if (!channels) throw new Error(`Invalid hex color: ${hex}`)
  const [r, g, b] = channels.map((v) => {
    const s = v / 255
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4)
  })
  return 0.2126 * r + 0.7152 * g + 0.0722 * b
}

function contrast(a: string, b: string): number {
  const la = luminance(a)
  const lb = luminance(b)
  return (Math.max(la, lb) + 0.05) / (Math.min(la, lb) + 0.05)
}

const HEX_RE = /^#[0-9a-fA-F]{6}$/

// 用户确认的官方色表（HEX 必须逐字符一致，不得按颜色名称"修正"撞色组合）。
const USER_TABLE: Array<[string, string, string]> = [
  ['sunset-orange', '#FBE693', '#FE8E28'],
  ['cream-sky', '#F4DC84', '#79BEDF'],
  ['mist-blue', '#C9DDC4', '#1F5CAC'],
  ['mist-purple', '#B8A9C6', '#2B693F'],
  ['spring-peach', '#E4F6AA', '#FF81A6'],
  ['forest-green', '#80E484', '#2B693F'],
]

describe('palette registry', () => {
  it('has exactly seven unique palette ids with classic-sky as default', () => {
    expect(PALETTE_ORDER).toHaveLength(7)
    expect(new Set(PALETTE_ORDER).size).toBe(7)
    expect(PALETTE_ORDER[0]).toBe('classic-sky')
    expect(DEFAULT_PALETTE_ID).toBe('classic-sky')
    for (const id of PALETTE_ORDER) expect(PALETTES[id].id).toBe(id)
  })

  it('keeps the six user gradients byte-for-byte, including the clashing combos', () => {
    for (const [id, start, end] of USER_TABLE) {
      const palette = PALETTES[id as keyof typeof PALETTES]
      expect(palette.start, `${id}.start`).toBe(start)
      expect(palette.end, `${id}.end`).toBe(end)
    }
    // 雾蓝浅绿起点 / 雾紫深绿终点：原始设计，禁止"按名称改色"
    expect(PALETTES['mist-blue'].start).toBe('#C9DDC4')
    expect(PALETTES['mist-purple'].end).toBe('#2B693F')
  })

  it('preserves the classic sky functional colors as the default design', () => {
    const classic = PALETTES['classic-sky']
    expect(classic.accent).toBe('#0369A1')
    expect(classic.accentHover).toBe('#075985')
    expect(classic.accentSoft).toBe('#E0F2FE')
    expect(classic.accentBright).toBe('#0EA5E9')
  })

  it('only accepts valid hex colors for every color field', () => {
    for (const palette of Object.values(PALETTES)) {
      const fields: Array<keyof Palette> = [
        'start', 'end', 'accent', 'accentHover', 'accentSoft', 'accentBright', 'accentForeground', 'focusRing',
      ]
      for (const field of fields) {
        expect(typeof palette[field], `${palette.id}.${String(field)}`).toBe('string')
        expect(palette[field] as string, `${palette.id}.${String(field)}`).toMatch(HEX_RE)
      }
      expect(palette.sidebarFrom).toHaveLength(3)
      expect(palette.sidebarTo).toHaveLength(3)
      for (const channel of [...palette.sidebarFrom, ...palette.sidebarTo]) {
        expect(channel).toBeGreaterThanOrEqual(0)
        expect(channel).toBeLessThanOrEqual(255)
      }
    }
  })

  it('meets the contrast thresholds for text, solid fills and focus rings', () => {
    for (const palette of Object.values(PALETTES)) {
      const id = palette.id
      // 白字实底（普通文字 ≥4.5:1）
      expect(contrast('#FFFFFF', palette.accent), `${id} white/accent`).toBeGreaterThanOrEqual(4.5)
      expect(contrast('#FFFFFF', palette.accentHover), `${id} white/hover`).toBeGreaterThanOrEqual(4.5)
      // accent 文字压 soft 底 / 应用底（普通文字 ≥4.5:1）
      expect(contrast(palette.accent, palette.accentSoft), `${id} accent/soft`).toBeGreaterThanOrEqual(4.5)
      expect(contrast(palette.accent, '#F8FAFC'), `${id} accent/bg`).toBeGreaterThanOrEqual(4.5)
      // 焦点环（关键非文本 ≥3:1）
      expect(contrast(palette.focusRing, '#FFFFFF'), `${id} focus/white`).toBeGreaterThanOrEqual(3)
      // 实底文字色统一为白
      expect(palette.accentForeground).toBe('#FFFFFF')
    }
  })

  it('keeps the classic default ambient background identical to the previous App implementation', () => {
    const classicAmbient =
      'radial-gradient(60rem 40rem at 12% -10%, rgba(14, 165, 233, 0.18), transparent 60%), ' +
      'radial-gradient(50rem 40rem at 100% 0%, rgba(45, 212, 191, 0.10), transparent 55%), ' +
      'linear-gradient(135deg, #f8fafc, #eef2ff 55%, #f8fafc)'
    expect(PALETTES['classic-sky'].ambientBackground).toBe(classicAmbient)
    // 侧栏通道也保持原值
    expect(PALETTES['classic-sky'].sidebarFrom).toEqual([238, 242, 255])
    expect(PALETTES['classic-sky'].sidebarTo).toEqual([237, 243, 248])
  })
})

describe('palette helpers', () => {
  it('normalizes unknown or stale ids back to classic-sky', () => {
    expect(normalizePaletteId('sunset-orange')).toBe('sunset-orange')
    expect(normalizePaletteId('pink-unicorn')).toBe('classic-sky')
    expect(normalizePaletteId(undefined)).toBe('classic-sky')
    expect(normalizePaletteId(42)).toBe('classic-sky')
    expect(isPaletteId('mist-blue')).toBe(true)
    expect(isPaletteId('')).toBe(false)
  })

  it('refuses to guess malformed hex', () => {
    expect(hexToRgbChannels('#2B693F')).toEqual([43, 105, 63])
    expect(hexToRgbChannels('#2B693')).toBeNull()
    expect(hexToRgbChannels('green')).toBeNull()
    expect(() => hexToRgba('nope', 0.5)).toThrow()
  })

  it('exposes theme css vars without semantic colors', () => {
    const vars = paletteCssVars(getPalette('sunset-orange'))
    expect(vars['--color-accent']).toBe('#C2410C')
    expect(vars['--color-accent-hover']).toBe('#9A3412')
    expect(vars['--theme-gradient']).toContain('#FBE693')
    expect(vars['--theme-gradient']).toContain('#FE8E28')
    expect(vars['--theme-ambient-background']).toContain('radial-gradient')
    // 语义色不属于主题变量：绝不随品牌主题变化
    for (const key of Object.keys(vars)) {
      expect(key.startsWith('--color-danger')).toBe(false)
      expect(key.startsWith('--color-warning')).toBe(false)
      expect(key.startsWith('--color-success')).toBe(false)
    }
  })
})
