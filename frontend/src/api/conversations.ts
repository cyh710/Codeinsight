import { jsonRequest } from './client'
import type { Conversation, ConversationTurn, Page } from './types'

const route = (pid: number, cid: string) => `/projects/${pid}/conversations/${encodeURIComponent(cid)}`
export const listConversations = (params: URLSearchParams) =>
  jsonRequest<Page<Conversation>>(`/conversations?${params}`)
export const createConversation = (pid: number) =>
  jsonRequest<Conversation>(`/projects/${pid}/conversations`, { method: 'POST' })
export const getConversation = (pid: number, cid: string) => jsonRequest<Conversation>(route(pid, cid))
export const patchConversation = (pid: number, cid: string, data: Record<string, unknown>) =>
  jsonRequest<Conversation>(route(pid, cid), { method: 'PATCH', body: JSON.stringify(data) })
export const getTurns = (pid: number, cid: string, cursor = 0) =>
  jsonRequest<Page<ConversationTurn>>(`${route(pid, cid)}/turns?cursor=${cursor}`)
export const cancelTask = (pid: number, task: string) =>
  jsonRequest(`/projects/${pid}/tasks/${encodeURIComponent(task)}/cancel`, { method: 'POST' })
