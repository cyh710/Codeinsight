/**
 * 时间线的纯函数部分（可单测，不依赖浏览器）。
 */
import type { TimelineItem } from '../../api/types'

/** `at` 是后端统一过的 ISO-8601 UTC；这里按本地时区显示。 */
export function formatTimelineTime(at: string | null): string {
  if (!at) return '时间未知'
  const date = new Date(at)
  if (Number.isNaN(date.getTime())) return at
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(
    date.getMinutes(),
  )}`
}

/**
 * 全量索引只有「扫描了多少文件」，没有增删改；返回 null，
 * 调用方改显示文件总数——不把未知画成 0。
 */
export function fileCountsLabel(item: TimelineItem): string | null {
  if (item.files.added === null) return null
  const modified = item.files.modified ?? 0
  const deleted = item.files.deleted ?? 0
  return `+${item.files.added} ~${modified} −${deleted}`
}

export function modeLabel(item: TimelineItem): string {
  if (item.kind === 'change') return '外部变更'
  return item.mode === 'incremental' ? '增量索引' : '全量索引'
}

/** 短 commit：7 位足够在本仓库内识别。 */
export function shortCommit(sha: string | null): string {
  return sha ? sha.slice(0, 7) : '未知版本'
}
