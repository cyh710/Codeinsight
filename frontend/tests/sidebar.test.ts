import { expect, it } from 'vitest'
import { conversationGroups } from '../src/components/chat/conversationGroups'
import type { Conversation } from '../src/api/types'

it('置顶独立于时间，今天、近七天和旧对话分组保持服务端顺序', () => {
  const now = new Date(2026, 9, 26, 12)
  const items = [
    { id: 'old-pin', pinned: true, updated_at: new Date(2026, 9, 1).toISOString() },
    { id: 'today', pinned: false, updated_at: new Date(2026, 9, 26, 8).toISOString() },
    { id: 'today2', pinned: false, updated_at: new Date(2026, 9, 26, 7).toISOString() },
    { id: 'week', pinned: false, updated_at: new Date(2026, 9, 23).toISOString() },
    { id: 'old', pinned: false, updated_at: new Date(2026, 9, 1).toISOString() },
  ] as Conversation[]
  expect(conversationGroups(items, now).map(g => [g.title, g.items.map(c => c.id)])).toEqual([
    ['置顶', ['old-pin']], ['今天', ['today', 'today2']], ['最近 7 天', ['week']], ['更早', ['old']],
  ])
})
