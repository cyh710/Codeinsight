/** 地址只保存稳定目标；正文仍由 API 重新读取。 */
import { chatStore } from './chatStore'
import { projectStore } from './projectStore'
import { viewStore } from './viewStore'
import { workbenchStore } from './workbenchStore'
import type { RightPanel } from './types'
import { getKnowledgeTopic } from '../api/learning'

let restoring = false
export async function restoreLocation() {
  restoring = true
  const address = new URL(location.href), params = address.searchParams
  try {
    const project = Number(params.get('project'))
    if (project > 0 && projectStore.getState().currentProjectId !== project) await projectStore.getState().selectProject(project)
    const pid = projectStore.getState().currentProjectId
    const cid = params.get('conversation')
    if (pid && cid && chatStore.getState().conversationId !== cid) await chatStore.getState().openConversation(pid, cid)
    const view = params.get('view')
    if (view === 'chat' || view === 'graph' || view === 'timeline') viewStore.getState().setCenterTab(view)
    const material = params.get('material')
    if (material) {
      const panel: RightPanel = JSON.parse(material)
      const valid = panel && (
        (panel.mode === 'file' && typeof panel.path === 'string' && Number.isInteger(panel.lineno)) ||
        (panel.mode === 'symbol' && typeof panel.qualname === 'string') ||
        (panel.mode === 'knowledge' && typeof panel.target?.topic_id === 'string' && typeof panel.target?.version === 'string') ||
        (panel.mode === 'concept' && typeof panel.conceptId === 'string') || panel.mode === 'evidence' || panel.mode === 'knowledge-tree')
        || (panel?.mode === 'exploration' && panel.projectId === pid && typeof panel.conversationId === 'string' && typeof panel.requestId === 'string' && typeof panel.target?.topic_id === 'string')
      if (valid) workbenchStore.getState().openMaterial(panel)
    } else {
      const match = /^\/learn\/([a-z][a-z0-9-]*)$/.exec(address.pathname)
      if (match) {
        const topic = await getKnowledgeTopic(match[1])
        workbenchStore.getState().openKnowledge({ topic_id: topic.id, title: topic.title, version: topic.version,
          section_id: address.hash.slice(1) || null, href: address.pathname + address.hash })
      }
    }
  } catch { chatStore.setState({ error: '无法恢复这个位置，请从对话列表或教材目录重新打开。' }) }
  finally { restoring = false }
}
export function startNavigation() {
  let previous = ''
  const update = (replace = false) => {
    const chat = chatStore.getState(), project = projectStore.getState().currentProjectId
    if (restoring || chat.loading || !project || !chat.conversationId) return
    const panel = workbenchStore.getState().rightPanel
    const params = new URLSearchParams({ project: String(project), conversation: chat.conversationId,
      view: viewStore.getState().centerTab, material: JSON.stringify(panel) })
    const path = panel.mode === 'knowledge' ? `/learn/${panel.target.topic_id}` : '/'
    const hash = panel.mode === 'knowledge' && panel.target.section_id ? `#${panel.target.section_id}` : ''
    const next = `${path}?${params}${hash}`
    if (next === previous) return
    if (previous && panel.mode === 'file' && panel.indexEpoch !== undefined) {
      try {
        const prior = JSON.parse(new URL(previous, location.origin).searchParams.get('material') ?? 'null') as RightPanel | null
        // 首次读取后补齐版本身份属于同一位置，不能额外压入浏览器历史。
        if (prior?.mode === 'file' && prior.path === panel.path && prior.lineno === panel.lineno && prior.indexEpoch === undefined) replace = true
      } catch { /* 旧地址缺少有效材料身份时，保持普通导航。 */ }
    }
    previous = next
    history[replace ? 'replaceState' : 'pushState'](null, '', next)
  }
  update(true)
  const unsubs = [workbenchStore.subscribe(() => update()), viewStore.subscribe(() => update()), chatStore.subscribe(() => update())]
  const pop = () => { previous = location.pathname + location.search + location.hash; void restoreLocation() }
  addEventListener('popstate', pop)
  return () => { unsubs.forEach(fn => fn()); removeEventListener('popstate', pop) }
}
