/**
 * 概念卡：本体字段（summary/principles/tradeoffs/alternatives——来自
 * 人工策展的 YAML，不是模型生成的）+ 三级深度解释（quick 不调 LLM）。
 *
 * `quick` 直接读本体的 summary；`project`/`deep` 走 explain 端点。
 * 解释的 facts 与 inferences 也分栏渲染（ADR 0007）。
 */
import { useEffect, useState } from 'react'
import { Ban, BookOpen } from 'lucide-react'
import { api } from '../../api/dataSource'
import type {
  ConceptDepth,
  ConceptDetail,
  ConceptExplanation,
  ConceptInstance,
} from '../../api/types'
import { projectStore } from '../../store/projectStore'
import { workbenchStore } from '../../store/workbenchStore'
import { chatStore } from '../../store/chatStore'
import { viewStore } from '../../store/viewStore'
import { layoutStore } from '../../store/layoutStore'
import { useStore } from 'zustand'
import LearningMarkdown from '../learning/LearningMarkdown'

const DEPTHS: Array<{ id: ConceptDepth; label: string; hint: string }> = [
  { id: 'quick', label: '快速理解', hint: '读本体的 summary，瞬时' },
  { id: 'project', label: '结合项目', hint: '本项目里的位置与关系，<1s' },
  { id: 'deep', label: '深入探索', hint: '原理与权衡，可慢' },
]

export default function ConceptCard({ conceptId }: { conceptId: string }) {
  const projectId = useStore(projectStore, s => s.currentProjectId)
  const streaming = useStore(chatStore, s => s.streaming)
  const origin = useStore(workbenchStore, s => s.history.slice(0, s.historyIndex + 1).reverse().find(h => h.reading?.kind === 'code')?.reading)
  const [depth, setDepth] = useState<ConceptDepth>('quick')
  // 状态带键（属于哪个 concept/depth）：换目标或换深度时旧值自然失效，
  // 避免 effect 里同步清空的级联渲染。
  const [state, setState] = useState<{
    for: string
    detail: ConceptDetail
  } | null>(null)
  const [explanation, setExplanation] = useState<{
    for: string
    data: ConceptExplanation
  } | null>(null)
  const [failed, setFailed] = useState<{
    for: string
    title: string
    hint: string
  } | null>(null)

  useEffect(() => {
    let alive = true
    if (projectId === null) return
    api
      .getConcept(projectId, conceptId)
      .then((d) => alive && setState({ for: conceptId, detail: d }))
      .catch(
        (e) =>
          alive &&
          setFailed({
            for: conceptId,
            title: e instanceof Error ? e.message : '概念加载失败',
            hint: '当前数据源里没有这个概念（mock 快照暂无概念数据）。',
          }),
      )
    return () => {
      alive = false
    }
  }, [projectId, conceptId])

  useEffect(() => {
    let alive = true
    if (projectId === null || depth === 'quick') return
    api
      .explainConcept(projectId, conceptId, depth)
      .then((d) => alive && setExplanation({ for: `${conceptId}:${depth}`, data: d }))
      .catch(
        (e) =>
          alive &&
          setFailed({
            for: `${conceptId}:${depth}`,
            title: e instanceof Error ? e.message : '解释生成失败',
            hint: '稍后重试。',
          }),
      )
    return () => {
      alive = false
    }
  }, [projectId, conceptId, depth])

  // 实例列表（双向导航的"概念 → 代码"侧）：点击跳回符号/文件。
  // 概念本体可能存在但本项目还没有实例——空列表也是合法状态，不算错误。
  const [instances, setInstances] = useState<{
    for: string
    items: ConceptInstance[]
  } | null>(null)
  useEffect(() => {
    let alive = true
    if (projectId === null) return
    api
      .listConceptInstances(projectId, conceptId)
      .then((r) => alive && setInstances({ for: conceptId, items: r.items }))
      .catch(() => {
        // 概念本体不存在时 instances 也 404；详情请求会给出错误卡，这里静默。
      })
    return () => {
      alive = false
    }
  }, [projectId, conceptId])

  const detail = state?.for === conceptId ? state.detail : null
  useEffect(() => {
    const target =
      detail?.learning_targets?.find((t) => t.topic_id === conceptId) ??
      detail?.learning_targets?.[0]
    if (target)
      workbenchStore.getState().setReading({
        kind: 'knowledge',
        topic_id: target.topic_id,
        section_id: target.section_id,
        version: target.version,
      })
  }, [detail, conceptId])
  const error = failed?.for === conceptId || failed?.for === `${conceptId}:${depth}` ? failed : null

  if (error) {
    return (
      <div className="rounded-xl border border-warning/30 bg-warning/[0.05] px-3 py-3" role="alert">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-warning">
          <Ban size={13} strokeWidth={1.8} />
          {error.title}
        </div>
        <p className="mt-1 text-[11px] leading-relaxed text-slate-600">{error.hint}</p>
      </div>
    )
  }
  if (!detail) {
    return <p className="px-1 py-6 text-center text-xs text-slate-400">读取概念…</p>
  }

  const loadedExplanation = explanation?.for === `${conceptId}:${depth}` ? explanation.data : null
  const summaryText =
    depth === 'quick' ? detail.summary : (loadedExplanation?.summary ?? detail.summary)
  const reliable = instances?.for === conceptId ? instances.items.filter(i => i.confidence >= 0.8 && i.evidence) : []
  const exact = origin?.kind === 'code' ? reliable.find(i => i.path === origin.path && i.lineno >= origin.lineno && i.lineno <= (origin.end_lineno ?? origin.lineno)) : undefined
  const nearby = origin?.kind === 'code' ? reliable.find(i => i.path === origin.path) : undefined
  const primary = exact ?? nearby ?? reliable[0]

  return (
    <article className="space-y-2.5">
      <header>
        <p className="font-mono text-[11px] text-slate-400">#{detail.concept_id}</p>
        <h3 className="mt-0.5 flex items-center gap-1.5 text-sm font-semibold text-slate-800">
          <BookOpen size={14} strokeWidth={1.7} className="text-accent/70" />
          {detail.name}
          <span className="rounded bg-accent-soft px-1.5 py-px font-mono text-[10px] text-accent">
            {detail.category}
          </span>
        </h3>
        <p className="mt-0.5 text-[10.5px] text-slate-400">本项目实例 {detail.instance_count} 个</p>
      </header>

      <section className="context-excerpt">
        <p className="exploration-section-label">{exact ? '当前阅读范围中的实例' : nearby ? '同文件中的实例' : '先看项目中的可靠实例'}</p>
        {primary ? <><button className="text-left text-sm text-accent" onClick={() => workbenchStore.getState().selectFile(primary.path, primary.lineno)}>{primary.path}:{primary.lineno}</button><p className="mt-2 text-sm leading-7">{primary.evidence}</p>
          <button className="wb-button mt-2" disabled={streaming} onClick={() => { viewStore.getState().setCenterTab('chat'); layoutStore.setState({ full: false, ...(layoutStore.getState().viewport < 1100 ? { right: false } : {}) }); void chatStore.getState().sendMessage(projectId!, `请结合 ${primary.path} 第 ${primary.lineno} 行解释 ${detail.name} 在这里解决什么问题，核对实际实现后再讨论取舍。`, { preserveDraft: true, reading: { kind: 'code', project_id: projectId!, path: primary.path, lineno: primary.lineno } }) }}>追问：解释它在这里的作用</button>
        </> : <p className="exploration-muted">{instances?.for === conceptId ? '未找到可靠的项目实例，下面仍可阅读通用说明。' : '正在核对项目实例…'}</p>}
      </section>
      <div className="flex gap-1" role="tablist" aria-label="解释深度">
        {DEPTHS.map((d) => (
          <button
            key={d.id}
            type="button"
            role="tab"
            aria-selected={depth === d.id}
            title={d.hint}
            onClick={() => setDepth(d.id)}
            className={`rounded-lg px-2.5 py-1 text-[11px] font-medium transition-colors ${
              depth === d.id
                ? 'bg-accent text-accent-foreground'
                : 'bg-slate-100 text-slate-500 hover:bg-accent-soft hover:text-accent'
            }`}
          >
            {d.label}
          </button>
        ))}
      </div>

      <div className="rounded-lg bg-slate-50 px-2.5 py-2 text-xs leading-relaxed text-slate-700">
        <LearningMarkdown
          text={summaryText || '（本体未写 summary）'}
          targets={loadedExplanation?.learning_targets ?? detail.learning_targets}
        />
      </div>
      {detail.learning_targets && detail.learning_targets.length > 0 && (
        <section className="space-y-2 border-l-2 border-accent/25 pl-3">
          <h4 className="text-[11px] font-semibold text-slate-500">阅读原理与教学示例</h4>
          {detail.learning_targets.map((t) => (
            <button
              type="button"
              key={t.href}
              className="block text-left text-xs leading-6 text-accent hover:underline"
              onClick={() => workbenchStore.getState().openKnowledge(t)}
            >
              {t.title}
            </button>
          ))}
        </section>
      )}

      {depth !== 'quick' && !loadedExplanation && !error && (
        <p className="px-1 text-[11px] text-slate-400">生成解释中…</p>
      )}

      {loadedExplanation && (
        <>
          {loadedExplanation.error && (
            <p role="status" className="text-[11px] leading-6 text-warning">
              {loadedExplanation.error}
            </p>
          )}
          {loadedExplanation.facts.length > 0 && (
            <section className="rounded-xl border border-success/25 bg-success/[0.04] px-3 py-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-success">
                事实（带代码出处）
              </h4>
              <ul className="mt-1 space-y-1.5">
                {loadedExplanation.facts.map((f, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-[11px] leading-relaxed text-slate-700"
                  >
                    <span className="shrink-0 rounded bg-accent-soft/70 px-1.5 py-px font-mono text-[10px] text-accent">
                      {f.citation.path}:{f.citation.lineno}
                    </span>
                    <span className="min-w-0">{f.text}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {loadedExplanation.inferences.length > 0 && (
            <section className="rounded-xl border border-warning/25 bg-warning/[0.04] px-3 py-2">
              <h4 className="text-[10px] font-semibold uppercase tracking-wider text-warning">
                推断（模型判断）
              </h4>
              <ul className="mt-1 space-y-1.5">
                {loadedExplanation.inferences.map((inf, i) => (
                  <li
                    key={i}
                    className="flex items-start gap-2 text-[11px] leading-relaxed text-slate-600"
                  >
                    <span className="shrink-0 rounded bg-warning/10 px-1 py-px font-mono text-[10px] text-warning">
                      {Math.round(inf.confidence * 100)}%
                    </span>
                    <span className="min-w-0">{inf.text}</span>
                  </li>
                ))}
              </ul>
            </section>
          )}
          {loadedExplanation.llm_used && (
            <p className="text-[10px] text-slate-400">本层解释由模型生成，事实栏均可回代码验证。</p>
          )}
        </>
      )}

      {instances?.for === conceptId && instances.items.length > 0 && (
        <section>
          <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            本项目实例（{instances.items.length}）·点击跳回代码
          </h4>
          <ul className="mt-1 space-y-1">
            {instances.items.map((inst) => (
              <li key={inst.id}>
                <button
                  type="button"
                  onClick={() =>
                    inst.qualname
                      ? workbenchStore
                          .getState()
                          .selectSymbol(inst.qualname, inst.path, inst.lineno)
                      : workbenchStore.getState().selectFile(inst.path, inst.lineno)
                  }
                  className="flex w-full items-start gap-1.5 rounded px-1.5 py-1 text-left text-[11px] transition-colors hover:bg-accent-soft/50"
                  title={`跳到 ${inst.path}:${inst.lineno}`}
                >
                  <span className="shrink-0 rounded bg-accent-soft/70 px-1.5 py-px font-mono text-[10px] text-accent">
                    {inst.path}:{inst.lineno}
                  </span>
                  <span className="min-w-0 truncate text-slate-600">{inst.evidence}</span>
                  {inst.confidence < 1 && (
                    <span className="ml-auto shrink-0 text-[10px] text-warning">
                      {Math.round(inst.confidence * 100)}%
                    </span>
                  )}
                </button>
              </li>
            ))}
          </ul>
        </section>
      )}

      {depth === 'deep' && detail.principles && (
        <section className="space-y-1.5">
          {[
            ['原理', detail.principles],
            ['权衡', detail.tradeoffs],
            ['其他做法', detail.alternatives],
          ]
            .filter(([, text]) => text)
            .map(([label, text]) => (
              <div key={label}>
                <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
                  {label}
                </h4>
                <p className="mt-0.5 text-[11px] leading-relaxed text-slate-600">{text}</p>
              </div>
            ))}
        </section>
      )}

      {detail.references.length > 0 && (
        <div>
          <h4 className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">
            参考
          </h4>
          <ul className="mt-0.5 space-y-0.5">
            {detail.references.map((url) => (
              <li key={url}>
                <a
                  href={url}
                  target="_blank"
                  rel="noreferrer"
                  className="break-all text-[10.5px] text-accent hover:underline"
                >
                  {url}
                </a>
              </li>
            ))}
          </ul>
        </div>
      )}
    </article>
  )
}
