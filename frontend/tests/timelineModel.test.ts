/**
 * 时间线纯函数：全量索引的「未知」不能被画成 0。
 */
import { describe, expect, it } from 'vitest'
import type { TimelineItem } from '../src/api/types'
import {
  fileCountsLabel,
  formatTimelineTime,
  modeLabel,
  shortCommit,
} from '../src/components/timeline/timelineModel'

function item(overrides: Partial<TimelineItem> = {}): TimelineItem {
  return {
    id: 'run-1',
    kind: 'index',
    mode: 'incremental',
    ok: true,
    at: '2026-10-21T09:00:00Z',
    base_commit: 'c0',
    head_commit: 'c1d2e3f4a5b6',
    summary: '',
    files: { added: 1, modified: 2, deleted: 3, total: 6 },
    symbols_changed: 4,
    symbols_added: 2,
    symbols_removed: 1,
    files_total: 10,
    source: 'git',
    stale_design_decisions: [],
    ...overrides,
  }
}

describe('timelineModel', () => {
  it('增量显示增删改；全量显示 null 而不是 0', () => {
    expect(fileCountsLabel(item())).toBe('+1 ~2 −3')
    expect(
      fileCountsLabel(
        item({ mode: 'full', files: { added: null, modified: null, deleted: null, total: 688 } }),
      ),
    ).toBeNull()
  })

  it('模式标签区分增量/全量/外部变更', () => {
    expect(modeLabel(item())).toBe('增量索引')
    expect(modeLabel(item({ mode: 'full' }))).toBe('全量索引')
    expect(modeLabel(item({ kind: 'change', mode: null }))).toBe('外部变更')
  })

  it('commit 截断到 7 位；缺失时明说未知', () => {
    expect(shortCommit('c1d2e3f4a5b6')).toBe('c1d2e3f')
    expect(shortCommit(null)).toBe('未知版本')
  })

  it('时间缺失或非法时不崩，也不显示假日期', () => {
    expect(formatTimelineTime(null)).toBe('时间未知')
    expect(formatTimelineTime('not-a-date')).toBe('not-a-date')
    expect(formatTimelineTime('2026-10-21T09:00:00Z')).toMatch(/^\d{2}-\d{2} \d{2}:\d{2}$/)
  })
})
