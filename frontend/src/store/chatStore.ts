/**
 * 对话 store + SSE 事件规约。
 *
 * `applySseEvent` 是唯一的流事件入口：真实流（fetch 解析）与 mock 回放
 * 喂同一种事件，走同一段规约——保证两种模式下 UI 行为一致，也让规约
 * 本身可以脱离网络做单元测试。
 *
 * 收尾只认 `done`（契约 §8.3：error 之后 done 仍必发）。
 */
import { createStore } from 'zustand'
import { api } from '../api/dataSource'
import type { SseEvent } from '../api/types'
import type { ChatMessage, ChatStore, ToolTimelineItem } from './types'
import { activateWorkbench, suspendWorkbench, workbenchStore } from './workbenchStore'
import * as conversationsApi from '../api/conversations'
import { isMockMode } from '../api/dataSource'
import type { Conversation, ConversationTurn, ReadingContext } from '../api/types'
import { readLocal, writeLocal } from './persistence'
import { hotState } from './hotState'

type Set = (partial: Partial<ChatStore> | ((s: ChatStore) => Partial<ChatStore>)) => void
type Get = () => ChatStore

/** 把一条 SSE 事件规约到目标 assistant 消息上。导出供测试直接喂事件。 */
export function applySseEvent(
  messages: ChatMessage[],
  assistantId: string,
  event: SseEvent,
): ChatMessage[] {
  const patch = (fn: (m: ChatMessage) => ChatMessage) =>
    messages.map((m) => (m.id === assistantId ? fn(m) : m))

  switch (event.event) {
    case 'meta':
      // conversation_id 由后端权威分配：记住它，下一轮追问带上。
      return messages
    case 'delta':
      return patch((m) => ({ ...m, text: m.text + event.data.text }))
    case 'tool': {
      const item: ToolTimelineItem = {
        name: event.data.name,
        status: event.data.status,
        summary: event.data.summary,
      }
      return patch((m) => {
        const tools = [...(m.tools ?? [])]
        // 同名工具 running → ok/error：更新最后一行而不是追加，
        // 否则时间线一行变两行。
        const last = tools[tools.length - 1]
        if (
          last &&
          last.name === item.name &&
          last.status === 'running' &&
          item.status !== 'running'
        ) {
          tools[tools.length - 1] = item
        } else {
          tools.push(item)
        }
        return { ...m, tools }
      })
    }
    case 'evidence':
      return patch((m) => ({
        ...m,
        evidence: [
          ...(m.evidence ?? []),
          {
            path: event.data.path,
            lineno: event.data.lineno,
            end_lineno: event.data.end_lineno,
            qualname: event.data.qualname,
            snippet: event.data.snippet,
            lanes: event.data.lanes,
            concepts: event.data.concepts,
          },
        ],
      }))
    case 'answer':
      return patch((m) => ({
        ...m,
        text: event.data.text ?? m.text,
        facts: event.data.facts,
        inferences: event.data.inferences,
        citations: event.data.citations,
        abstained: event.data.abstained,
        incomplete: event.data.incomplete,
        abstentionReason: event.data.reason,
        knowledgeSources: event.data.knowledge_sources ?? [],
        learningEntries: event.data.learning_entries ?? [],
        learningTargets: event.data.learning_targets ?? [],
        knowledgeError: event.data.knowledge_error,
        sourceHeadCommit: event.data.source_head_commit,
        exploration: event.data.exploration,
        rawText: event.data.raw_text,
        responseKind: event.data.response_kind,
        evidenceReview: event.data.evidence_review,
      }))
    case 'error':
      // 只记录，不中断：契约保证 done 仍会来，由 done 统一收尾。
      return patch((m) => ({
        ...m,
        error: { code: event.data.code, title: event.data.title, hint: event.data.hint },
      }))
    case 'done':
      return patch((m) => ({
        ...m,
        streaming: false,
        abstained: event.data.abstained,
        abstentionReason: event.data.reason || m.abstentionReason,
      }))
  }
}

export function turnMessages(turn: ConversationTurn): ChatMessage[] {
  const user: ChatMessage = { id: `user-${turn.request_id}`, role: 'user', text: turn.question,
    requestId: turn.request_id, timestamp: turn.created_at, readingContext: turn.reading_context }
  const message: ChatMessage = { id: `assistant-${turn.request_id}`, role: 'assistant', text: turn.answer.text ?? '',
    requestId: turn.request_id, timestamp: turn.created_at, streaming: turn.status === 'running', legacy: turn.legacy,
    readingContext: turn.reading_context, error: turn.answer.error,
    tools: turn.answer.tools, evidence: turn.answer.evidence?.map(item => ({ ...item, concepts: item.concepts ?? item.concept_ids ?? [], lanes: item.lanes ?? [] })) }
  const event = { event: 'answer' as const, data: { facts: [], inferences: [], citations: [],
    abstained: false, reason: '', incomplete: false, ...turn.answer, evidence: undefined } }
  return [user, ...applySseEvent([message], message.id, event)]
}
interface Client {
  title: string; archived: boolean
  pid: number; cid: string; messages: ChatMessage[]; streaming: boolean; draft: string
  controller: AbortController | null; taskId: string | null; cursor: number | null
  retry?: { rid: string; question: string; reading: ReadingContext | null }
}
const browserApi = () => typeof window !== 'undefined' && !isMockMode
export function createChatActions(set: Set, get: Get) {
  const clients = new Map<string, Client>()
  let active: Client | null = null
  let generation = 0
  let searchGeneration = 0
  const key = (pid: number, cid: string) => `${pid}:${cid}`
  const sync = (client: Client) => {
    if (active === client) set({ messages: client.messages, streaming: client.streaming, currentTitle: client.title, currentArchived: client.archived,
      conversationId: client.cid, draft: client.draft, taskId: client.taskId,
      _abortController: client.controller, turnsCursor: client.cursor })
  }
  const clientFor = (pid: number, cid: string) => {
    let client = clients.get(key(pid, cid))
    if (!client) {
      const meta = get().conversations.find(c => c.id === cid && c.project_id === pid)
      client = { pid, cid, title: meta?.title ?? '新对话', archived: meta?.archived ?? false, messages: [], streaming: false, draft: '', controller: null, taskId: null, cursor: null }
      clients.set(key(pid, cid), client)
    }
    return client
  }
  const remember = (pid: number, cid: string) => {
    if (typeof localStorage !== 'undefined') {
      try { localStorage.setItem(`ci.activeConversation.${pid}`, cid) } catch { /* 工作区 IndexedDB 错误由统一提示呈现。 */ }
    }
  }
  return {
    projectId: null, currentTitle: '新对话', currentArchived: false, listLoading: false, draft: '', error: '', loading: browserApi(), conversations: [] as Conversation[],
    nextCursor: null, turnsCursor: null, taskId: null, search: '', allProjects: false,
    archived: false, find: '', focusRequest: null,
    setDraft: (draft: string) => {
      if (!active) return
      active.draft = draft; set({ draft })
      void writeLocal(`draft:${key(active.pid, active.cid)}`, draft)
    },
    setFind: (find: string) => set({ find }),
    searchConversations: (search: string, allProjects = false, archived = false) => {
      set({ search, allProjects, archived, conversations: [], nextCursor: null }); void get().refreshConversations()
    },
    refreshConversations: async (more = false) => {
      if (!browserApi() || get().projectId === null) return
      const token = ++searchGeneration
      set({ listLoading: true })
      const s = get(), params = new URLSearchParams({ q: s.search, archived: String(s.archived), cursor: String(more ? s.nextCursor ?? 0 : 0) })
      if (!more) params.set('limit', String(Math.min(100, Math.max(30, s.conversations.length))))
      if (!s.allProjects) params.set('project_id', String(s.projectId))
      try {
        const result = await conversationsApi.listConversations(params)
        if (token === searchGeneration) {
          const meta = result.items.find(c => c.id === active?.cid && c.project_id === active?.pid)
          if (active && meta) { active.title = meta.title; active.archived = meta.archived; sync(active) }
          set({ conversations: more ? [...get().conversations, ...result.items] : result.items, nextCursor: result.next_cursor, error: '' })
        }
      } catch (error) { if (token === searchGeneration) set({ error: String(error) }) }
      finally { if (token === searchGeneration) set({ listLoading: false }) }
    },
    openConversation: async (pid: number, cid: string, focusRequest?: string) => {
      const token = ++generation
      const client = clientFor(pid, cid)
      active = client
      set({ projectId: pid, loading: browserApi(), error: '', find: '', focusRequest: focusRequest ?? null })
      sync(client); remember(pid, cid)
      if (!browserApi()) return
      await activateWorkbench(key(pid, cid))
      if (token !== generation) return
      const draft = await readLocal<string>(`draft:${key(pid, cid)}`)
      const pending = await readLocal<{ rid: string; question: string; reading: ReadingContext | null; preserveDraft?: boolean }>(`pending:${key(pid, cid)}`)
      if (draft !== undefined && !client.draft) client.draft = draft
      sync(client)
      try {
        if (!client.controller) {
          const [result, meta] = await Promise.all([conversationsApi.getTurns(pid, cid), conversationsApi.getConversation(pid, cid)])
          client.title = meta.title; client.archived = meta.archived
          client.messages = result.items.flatMap(turnMessages)
          client.streaming = result.items.some(t => t.status === 'running')
          client.taskId = result.items.find(t => t.status === 'running')?.task_id ?? null
          client.cursor = result.next_cursor
          if (pending) {
            if (!client.messages.some(message => message.requestId === pending.rid)) {
              client.retry = pending
              if (!client.draft && !pending.preserveDraft) { client.draft = pending.question; void writeLocal(`draft:${key(pid, cid)}`, client.draft) }
              if (!pending.preserveDraft && active === client && client.draft === pending.question) { if (pending.reading) workbenchStore.getState().fixReading(pending.reading); else workbenchStore.getState().setReading(null) }
            }
            void writeLocal(`pending:${key(pid, cid)}`, null)
          }
          if (focusRequest) {
            while (client.cursor !== null && !client.messages.some(m => m.requestId === focusRequest)) {
              const older = await conversationsApi.getTurns(pid, cid, client.cursor)
              client.messages = [...older.items.flatMap(turnMessages), ...client.messages]; client.cursor = older.next_cursor
            }
          }
        }
        if (token === generation) { sync(client); set({ loading: false }); void conversationsApi.patchConversation(pid, cid, { mark_read: true }).catch(() => {}) }
      } catch (error) { if (token === generation) set({ loading: false, error: String(error) }) }
      if (token === generation) void get().refreshConversations()
    },
    newConversation: async (pid: number) => {
      try {
        const cid = browserApi() ? (await conversationsApi.createConversation(pid)).id : `conv-${crypto.randomUUID()}`
        await get().openConversation(pid, cid)
        await get().refreshConversations()
      } catch (error) { set({ error: String(error) }) }
    },
    updateConversation: async (cid: string, patch: Record<string, unknown>, pid = get().projectId!) => {
      try { const meta = await conversationsApi.patchConversation(pid, cid, patch); const client = clients.get(key(pid, cid)); if (client) { client.title = meta.title; client.archived = meta.archived; sync(client) }; await get().refreshConversations() }
      catch (error) { set({ error: String(error) }) }
    },
    loadMore: async () => {
      const client = active
      if (!client || client.cursor === null || !browserApi()) return
      try {
        const result = await conversationsApi.getTurns(client.pid, client.cid, client.cursor)
        client.messages = [...result.items.flatMap(turnMessages), ...client.messages]; client.cursor = result.next_cursor; sync(client)
      } catch (error) { set({ error: String(error) }) }
    },
    pollRunning: async () => {
      const client = active
      if (!client || client.controller || !client.streaming || !browserApi()) return
      try {
        const result = await conversationsApi.getTurns(client.pid, client.cid)
        if (client.controller) return
        client.messages = result.items.flatMap(turnMessages)
        client.streaming = result.items.some(t => t.status === 'running')
        client.taskId = result.items.find(t => t.status === 'running')?.task_id ?? null
        client.cursor = result.next_cursor
        sync(client)
      } catch (error) { if (active === client) set({ error: String(error) }) }
    },
    switchProject: async (pid: number) => {
      if (active?.pid === pid) return
      if (browserApi()) suspendWorkbench()
      let cid: string | null = null
      try { cid = typeof localStorage !== 'undefined' ? localStorage.getItem(`ci.activeConversation.${pid}`) : null } catch { /* 读取失败采用项目列表回退。 */ }
      if (!browserApi()) {
        const previous = [...clients.values()].find(c => c.pid === pid)
        active = previous ?? clientFor(pid, `project-${pid}-${crypto.randomUUID()}`)
        set({ projectId: pid }); sync(active); return
      }
      const token = ++generation
      active = null; set({ projectId: pid, messages: [], streaming: false, conversationId: '', draft: '', loading: true, error: '' })
      try {
        const result = await conversationsApi.listConversations(new URLSearchParams({ project_id: String(pid) }))
        if (token !== generation) return
        set({ conversations: result.items, nextCursor: result.next_cursor })
        cid = result.items.some(c => c.id === cid) ? cid : result.items[0]?.id ?? null
        if (cid) await get().openConversation(pid, cid)
        else await get().newConversation(pid)
      } catch (error) { if (token === generation) set({ loading: false, error: String(error) }) }
    },
    sendMessage: async (pid: number, question: string, options?: { preserveDraft?: boolean; reading?: import('../api/types').ReadingContext | null; origin?: import('../api/types').ActionOrigin }) => {
      if (!active || active.pid !== pid) {
        active = clientFor(pid, get().conversationId || `project-${pid}-${crypto.randomUUID()}`)
        set({ projectId: pid }); sync(active)
      }
      const client = active
      if (client.streaming) return
      const reading = options && 'reading' in options ? options.reading ?? null : workbenchStore.getState().reading
      const requestId = client.retry?.question === question && JSON.stringify(client.retry.reading) === JSON.stringify(reading) ? client.retry.rid : crypto.randomUUID()
      const aid = `assistant-${requestId}`
      const controller = new AbortController()
      client.controller = controller; client.streaming = true; client.taskId = null
      if (!options?.preserveDraft) { client.draft = ''; void writeLocal(`draft:${key(pid, client.cid)}`, '') }
      client.messages = [...client.messages.filter(message => message.requestId !== requestId),
        { id: `user-${requestId}`, role: 'user', text: question, timestamp: new Date().toISOString(), requestId, readingContext: reading },
        { id: aid, role: 'assistant', text: '', streaming: true, timestamp: new Date().toISOString(), requestId, readingContext: reading }]
      sync(client)
      if (browserApi()) await writeLocal(`pending:${key(pid, client.cid)}`, { rid: requestId, question, reading, preserveDraft: options?.preserveDraft })
      let acknowledged = false
      const result = await api.streamQuery({ project_id: pid, question, conversation_id: client.cid,
        request_id: requestId, ...(options?.origin ? { action_origin: options.origin } : {}), ...(reading ? { reading_context: reading } : {}) }, event => {
        if (client.controller !== controller) return
        if (event.event === 'meta') { acknowledged = true; client.taskId = event.data.task_id; client.retry = undefined; void writeLocal(`pending:${key(pid, client.cid)}`, null) }
        client.messages = applySseEvent(client.messages, aid, event)
        if ((event.event === 'evidence' || event.event === 'answer') && active === client) workbenchStore.getState().notifyEvidence()
        sync(client)
      }, controller.signal)
      if (client.controller !== controller) return
      client.messages = client.messages.map(m => m.id !== aid ? m : ({ ...m, streaming: false,
        ...(result.error && !m.error ? { error: result.error } : {}),
        ...(result.aborted && !result.error && !m.error ? { error: { code: 'aborted', title: '回答已中断', hint: '已保留现有内容，可以恢复问题后重试。' } } : {}) }))
      client.streaming = false; client.controller = null; sync(client)
      if (!acknowledged && result.error) {
        client.retry = { rid: requestId, question, reading }
        if (!client.draft && !options?.preserveDraft) { client.draft = question; void writeLocal(`draft:${key(pid, client.cid)}`, question); sync(client) }
      }
      void get().refreshConversations()
    },
    stopStreaming: () => {
      if (!active) return
      if (active.taskId && browserApi()) void conversationsApi.cancelTask(active.pid, active.taskId).catch(error => set({ error: String(error) }))
      active.controller?.abort()
    },
    restoreQuestion: (message: ChatMessage) => {
      const user = get().messages.find(m => m.role === 'user' && m.requestId === message.requestId)
      if (!user) return
      get().setDraft(user.text)
      if (user.readingContext) workbenchStore.getState().fixReading(user.readingContext)
      else workbenchStore.getState().setReading(null)
    },
    reset: () => { active = null; generation++; set({ messages: [], streaming: false, conversationId: '', draft: '', _abortController: null }) },
  }
}
export const chatStore = hotState(import.meta.hot, 'chat', () => createStore<ChatStore>((set, get) => ({
  messages: [], streaming: false, conversationId: '', _abortController: null,
  ...createChatActions(set, get),
})))
