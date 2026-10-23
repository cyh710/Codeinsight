/*
 * 官方配色注册表（ADR 0013）：七套主题的唯一数据源。
 *
 * 纪律（继承 ADR 0009 并由 0013 扩充）：
 * - 任一时刻全站只有一个品牌强调色；本表不接受任意用户自定义 HEX。
 * - 六套新主题的渐变起止 HEX 为用户原表逐字符拷贝，不得按颜色名称
 *   "修正"撞色组合（雾蓝的浅绿起点、雾紫的深绿终点均为原始设计）。
 * - accent/accentHover 为白字实底色（≥4.5:1，验证记录见
 *   docs/tasks/2026-09-10-ui-color-palettes.md 与 tests/palettes.test.ts）；
 *   accentSoft 上以 accent 作文字（≥4.5:1）；accentBright 仅装饰
 *   （光晕/描边/渐变），不承载白字或关键指示；focusRing 取 accent 本身
 *   （对白底非文本对比度远高于 3:1）。
 * - 语义色（--color-danger/warning/success）不在此表，永不随主题变化。
 * - index.css @theme 中的经典值只是构建期首帧默认；运行期以本表为唯一
 *   目录，通过 themeStore 覆盖根节点内联 CSS 变量。
 */

export type PaletteId =
  | 'classic-sky'
  | 'sunset-orange'
  | 'cream-sky'
  | 'mist-blue'
  | 'mist-purple'
  | 'spring-peach'
  | 'forest-green'

export interface Palette {
  id: PaletteId
  name: string
  description: string
  /** 渐变起始色（用户原表原样保留） */
  start: string
  /** 渐变结束色（用户原表原样保留） */
  end: string
  /** 白字实底强调色（对白 ≥4.5:1） */
  accent: string
  /** 实底 hover（对白 ≥4.5:1，比 accent 深） */
  accentHover: string
  /** 浅色块：选中/悬停底，accent 文字在其上 ≥4.5:1 */
  accentSoft: string
  /** 点缀/描边/光晕：仅装饰，不承载白字 */
  accentBright: string
  /** 实底上的文字颜色（全部主题为白） */
  accentForeground: string
  /** 焦点指示（非文本 ≥3:1） */
  focusRing: string
  /** 无壁纸时的默认氛围背景（完整 CSS background 值） */
  ambientBackground: string
  /** 侧栏渐变顶部 RGB 通道（半透明，由 App 按透明度合成） */
  sidebarFrom: [number, number, number]
  /** 侧栏渐变基底 RGB 通道 */
  sidebarTo: [number, number, number]
}

export const DEFAULT_PALETTE_ID: PaletteId = 'classic-sky'

const PALETTE_IDS: readonly PaletteId[] = [
  'classic-sky',
  'sunset-orange',
  'cream-sky',
  'mist-blue',
  'mist-purple',
  'spring-peach',
  'forest-green',
]

/** 把 #RRGGBB 解析为 0-255 通道数组；非法输入返回 null（不猜测颜色）。 */
export function hexToRgbChannels(hex: string): [number, number, number] | null {
  const match = /^#([0-9a-fA-F]{6})$/.exec(hex)
  if (!match) return null
  const int = parseInt(match[1], 16)
  return [(int >> 16) & 255, (int >> 8) & 255, int & 255]
}

/** #RRGGBB → rgba() 字符串；仅用于装饰性渐变/氛围层的确定性派生。 */
export function hexToRgba(hex: string, alpha: number): string {
  const channels = hexToRgbChannels(hex)
  if (!channels) throw new Error(`Invalid hex color: ${hex}`)
  return `rgba(${channels[0]}, ${channels[1]}, ${channels[2]}, ${alpha})`
}

/** 新主题默认氛围背景：与经典天蓝同构（径向柔光 ×2 + 斜向基底）。 */
function buildAmbient(start: string, end: string): string {
  return [
    `radial-gradient(60rem 40rem at 12% -10%, ${hexToRgba(start, 0.2)}, transparent 60%)`,
    `radial-gradient(50rem 40rem at 100% 0%, ${hexToRgba(end, 0.14)}, transparent 55%)`,
    `linear-gradient(135deg, #f8fafc, ${hexToRgba(start, 0.16)} 55%, #f8fafc)`,
  ].join(', ')
}

export const PALETTES: Record<PaletteId, Palette> = {
  'classic-sky': {
    id: 'classic-sky',
    name: '经典天蓝',
    description: '经典默认方案',
    start: '#E0F2FE',
    end: '#0EA5E9',
    accent: '#0369A1',
    accentHover: '#075985',
    accentSoft: '#E0F2FE',
    accentBright: '#0EA5E9',
    accentForeground: '#FFFFFF',
    focusRing: '#0369A1',
    // 与 App.tsx 原实现逐字符一致：切换主题后再切回，默认氛围不变。
    ambientBackground:
      'radial-gradient(60rem 40rem at 12% -10%, rgba(14, 165, 233, 0.18), transparent 60%), ' +
      'radial-gradient(50rem 40rem at 100% 0%, rgba(45, 212, 191, 0.10), transparent 55%), ' +
      'linear-gradient(135deg, #f8fafc, #eef2ff 55%, #f8fafc)',
    sidebarFrom: [238, 242, 255],
    sidebarTo: [237, 243, 248],
  },
  'sunset-orange': {
    id: 'sunset-orange',
    name: '落日橘暖渐变',
    description: '元气暖调',
    start: '#FBE693',
    end: '#FE8E28',
    accent: '#C2410C',
    accentHover: '#9A3412',
    accentSoft: '#FFEDD5',
    accentBright: '#FB923C',
    accentForeground: '#FFFFFF',
    focusRing: '#C2410C',
    ambientBackground: buildAmbient('#FBE693', '#FE8E28'),
    sidebarFrom: [255, 243, 224],
    sidebarTo: [253, 242, 235],
  },
  'cream-sky': {
    id: 'cream-sky',
    name: '奶黄晴空渐变',
    description: '温柔干净',
    start: '#F4DC84',
    end: '#79BEDF',
    accent: '#1C5D99',
    accentHover: '#164C7E',
    accentSoft: '#EAF4FB',
    accentBright: '#79BEDF',
    accentForeground: '#FFFFFF',
    focusRing: '#1C5D99',
    ambientBackground: buildAmbient('#F4DC84', '#79BEDF'),
    sidebarFrom: [250, 246, 228],
    sidebarTo: [235, 244, 250],
  },
  'mist-blue': {
    id: 'mist-blue',
    name: '雾蓝清透渐变',
    description: '清冷高级',
    start: '#C9DDC4',
    end: '#1F5CAC',
    accent: '#1F5CAC',
    accentHover: '#17488A',
    accentSoft: '#E3ECF8',
    accentBright: '#4A7BC8',
    accentForeground: '#FFFFFF',
    focusRing: '#1F5CAC',
    ambientBackground: buildAmbient('#C9DDC4', '#1F5CAC'),
    sidebarFrom: [233, 240, 232],
    sidebarTo: [230, 239, 249],
  },
  'mist-purple': {
    id: 'mist-purple',
    name: '雾紫低饱和渐变',
    description: '小众氛围感',
    start: '#B8A9C6',
    end: '#2B693F',
    accent: '#5B4B8A',
    accentHover: '#4A3D72',
    accentSoft: '#EDE9F4',
    accentBright: '#9C8CBC',
    accentForeground: '#FFFFFF',
    focusRing: '#5B4B8A',
    ambientBackground: buildAmbient('#B8A9C6', '#2B693F'),
    sidebarFrom: [240, 236, 245],
    sidebarTo: [236, 242, 238],
  },
  'spring-peach': {
    id: 'spring-peach',
    name: '春日桃绿渐变',
    description: '甜系柔和',
    start: '#E4F6AA',
    end: '#FF81A6',
    accent: '#B23A60',
    accentHover: '#96304F',
    accentSoft: '#FCE7EF',
    accentBright: '#FF81A6',
    accentForeground: '#FFFFFF',
    focusRing: '#B23A60',
    ambientBackground: buildAmbient('#E4F6AA', '#FF81A6'),
    sidebarFrom: [244, 250, 226],
    sidebarTo: [253, 238, 243],
  },
  'forest-green': {
    id: 'forest-green',
    name: '森系青绿渐变',
    description: '清新治愈',
    start: '#80E484',
    end: '#2B693F',
    accent: '#2B693F',
    accentHover: '#215733',
    accentSoft: '#E1F2E5',
    accentBright: '#55B06A',
    accentForeground: '#FFFFFF',
    focusRing: '#2B693F',
    ambientBackground: buildAmbient('#80E484', '#2B693F'),
    sidebarFrom: [228, 244, 230],
    sidebarTo: [232, 243, 235],
  },
}

/** 展示顺序（设置页选择器使用）。 */
export const PALETTE_ORDER: readonly PaletteId[] = PALETTE_IDS

export function isPaletteId(value: unknown): value is PaletteId {
  return typeof value === 'string' && PALETTE_IDS.includes(value as PaletteId)
}

/** 未知/过时 ID 一律安全回退默认主题，不抛错。 */
export function normalizePaletteId(value: unknown): PaletteId {
  return isPaletteId(value) ? value : DEFAULT_PALETTE_ID
}

export function getPalette(id: PaletteId): Palette {
  return PALETTES[id]
}

/**
 * 主题写入根节点的 CSS 变量集合（纯函数，测试直接断言）。
 * 只含品牌强调与主题装饰；语义色/中性色/透明度契约不在其中。
 */
export function paletteCssVars(palette: Palette): Record<string, string> {
  return {
    '--color-accent': palette.accent,
    '--color-accent-hover': palette.accentHover,
    '--color-accent-soft': palette.accentSoft,
    '--color-accent-bright': palette.accentBright,
    '--color-accent-foreground': palette.accentForeground,
    '--color-focus-ring': palette.focusRing,
    '--theme-gradient': `linear-gradient(135deg, ${palette.start}, ${palette.end})`,
    '--theme-gradient-soft': `linear-gradient(135deg, ${hexToRgba(palette.start, 0.5)}, ${hexToRgba(palette.end, 0.35)})`,
    '--theme-ambient-background': palette.ambientBackground,
  }
}
