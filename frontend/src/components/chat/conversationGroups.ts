import type { Conversation } from '../../api/types'

/** 日期只负责导航分组，不改变服务端会话身份或顺序。 */
export function conversationGroups(items: Conversation[], now = new Date()) {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
  const groups = ['置顶', '今天', '最近 7 天', '更早'].map(title => ({ title, items: [] as Conversation[] }))
  for (const item of items) {
    const time = new Date(item.updated_at).getTime()
    const index = item.pinned ? 0 : time >= today ? 1 : time >= today - 6 * 86400000 ? 2 : 3
    groups[index].items.push(item)
  }
  return groups.filter(group => group.items.length)
}
