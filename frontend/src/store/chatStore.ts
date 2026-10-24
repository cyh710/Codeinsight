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
import { workbenchStore } from './workbenchStore'

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

export function createChatActions(set: Set, get: Get) {
  let activeProject: number | null = null
  const saved = new Map<number, { messages: ChatMessage[]; conversationId: string }>()
  return {
    switchProject: (projectId: number) => {
      if (activeProject === projectId) return
      const s = get()
      if (activeProject !== null)
        saved.set(activeProject, {
          messages: s.messages.map((m) =>
            m.streaming
              ? {
                  ...m,
                  streaming: false,
                  error: {
                    code: 'aborted',
                    title: '切换项目后已停止这次回答',
                    hint: '原对话已保留，可以继续提问。',
                  },
                }
              : m,
          ),
          conversationId: s.conversationId,
        })
      s._abortController?.abort()
      activeProject = projectId
      set({
        messages: saved.get(projectId)?.messages ?? [],
        conversationId: saved.get(projectId)?.conversationId ?? '',
        streaming: false,
        _abortController: null,
      })
    },
    sendMessage: async (projectId: number, question: string) => {
      if (activeProject === null) activeProject = projectId
      const state = get()
      if (state.streaming) return
      const assistantId = `assistant-${Date.now()}`
      const controller = new AbortController()
      const conversationId = state.conversationId || `project-${projectId}-${crypto.randomUUID()}`
      const reading = workbenchStore.getState().reading

      set({
        messages: [
          ...state.messages,
          {
            id: `user-${Date.now()}`,
            role: 'user',
            text: question,
            timestamp: new Date().toISOString(),
          },
          {
            id: assistantId,
            role: 'assistant',
            text: '',
            streaming: true,
            timestamp: new Date().toISOString(),
          },
        ],
        streaming: true,
        _abortController: controller,
        conversationId,
      })

      const result = await api.streamQuery(
        {
          project_id: projectId,
          question,
          conversation_id: conversationId,
          ...(reading ? { reading_context: reading } : {}),
        },
        (event) => {
          if (get()._abortController !== controller || activeProject !== projectId) return
          if (event.event === 'meta') {
            // meta 的 conversation_id 是后端的权威值
            set((s) => ({ conversationId: event.data.conversation_id || s.conversationId }))
          }
          set((s) => ({ messages: applySseEvent(s.messages, assistantId, event) }))
        },
        controller.signal,
      )
      if (get()._abortController !== controller || activeProject !== projectId) return

      // 收尾：流结束（正常 done / watchdog / 网络）都走这里，不留 streaming=true。
      set((s) => ({
        messages: s.messages.map((m) =>
          m.id === assistantId
            ? {
                ...m,
                streaming: false,
                ...(result.error && !m.error
                  ? {
                      error: {
                        code: result.error.code,
                        title: result.error.title,
                        hint: result.error.hint,
                      },
                    }
                  : {}),
                ...(result.aborted && !m.text && !m.error
                  ? { error: { code: 'aborted', title: '已停止', hint: '这次回答没有完成。' } }
                  : {}),
              }
            : m,
        ),
        streaming: false,
        _abortController: null,
      }))
    },

    stopStreaming: () => {
      get()._abortController?.abort()
    },

    reset: () =>
      set({ messages: [], streaming: false, conversationId: '', _abortController: null }),
  }
}

export const chatStore = createStore<ChatStore>((set, get) => ({
  messages: [],
  streaming: false,
  conversationId: '',
  _abortController: null,
  ...createChatActions(set, get),
}))
