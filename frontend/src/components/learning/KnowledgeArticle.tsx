import { openSource } from '../exploration/actions'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { useStore } from 'zustand'
import { getKnowledgeTopic, getTopicInstances } from '../../api/learning'
import { isMockMode } from '../../api/dataSource'
import type { ConceptInstance, KnowledgeTopic, LearningTarget } from '../../api/types'
import { projectStore } from '../../store/projectStore'
import { panelKey, workbenchStore } from '../../store/workbenchStore'
import LearningMarkdown from './LearningMarkdown'
import { selectedKnowledge } from './selection'
import { layoutStore } from '../../store/layoutStore'
import { viewStore } from '../../store/viewStore'

export default function KnowledgeArticle({ target }: { target: LearningTarget }) {
  const readingMode = useStore(workbenchStore, s => s.readingMode)
  const [selectionError, setSelectionError] = useState('')
  const [state, setState] = useState<{ topic: KnowledgeTopic } | null>(null)
  const [error, setError] = useState('')
  const projectId = useStore(projectStore, (s) => s.currentProjectId)
  const [instanceResult, setInstanceResult] = useState<{
    items: ConceptInstance[]
    status: string
  } | null>(null)
  const instances = instanceResult?.items ?? []
  const [instancesError, setInstancesError] = useState('')
  const articleRef = useRef<HTMLElement>(null)
  useEffect(() => {
    let alive = true
    getKnowledgeTopic(target.topic_id)
      .then((topic) => {
        if (alive) setState({ topic })
      })
      .catch((e) => {
        if (alive) setError(String(e))
      })
    return () => {
      alive = false
    }
  }, [target.topic_id])
  useEffect(() => {
    if (projectId === null || isMockMode) return
    let alive = true
    getTopicInstances(projectId, target.topic_id)
      .then((r) => {
        if (alive) setInstanceResult(r)
      })
      .catch((e) => {
        if (alive) setInstancesError(String(e))
      })
    return () => {
      alive = false
    }
  }, [projectId, target.topic_id])
  const topic = state?.topic
  const contentReady = Boolean(
    topic && (projectId === null || isMockMode || instanceResult !== null || instancesError),
  )
  useLayoutEffect(() => {
    if (!topic || topic.version !== target.version) return
    const section =
      target.section_id && topic.sections.some((s) => s.id === target.section_id)
        ? target.section_id
        : topic.sections[0]?.id
    workbenchStore.getState().setReading({
      kind: 'knowledge',
      topic_id: topic.id,
      section_id: section,
      version: topic.version,
      title: topic.title,
      section_title: topic.sections.find(s => s.id === section)?.title,
    })
  }, [topic, target.section_id, target.version, readingMode])
  useLayoutEffect(() => {
    if (!topic || !contentReady) return
    const container = articleRef.current?.closest('[data-reading-scroll]') as HTMLElement | null
    const key = panelKey(workbenchStore.getState().rightPanel)
    const saved = workbenchStore.getState().scrollPositions[key]
    const section =
      target.section_id && topic.sections.some((s) => s.id === target.section_id)
        ? target.section_id
        : 'overview'
    if (container) {
      if (saved !== undefined) container.scrollTop = saved
      else if (target.section_id) {
        const anchor = articleRef.current?.querySelector(`[data-section-id="${section}"]`)
        if (anchor)
          container.scrollTop +=
            anchor.getBoundingClientRect().top - container.getBoundingClientRect().top - 10
      }
    }
  }, [topic, target.section_id, contentReady])
  if (error)
    return (
      <p role="alert" className="text-xs leading-6 text-danger">
        {error}
      </p>
    )
  if (!topic) return <p className="text-xs text-slate-400">读取完整章节…</p>
  if (topic.version !== target.version) return <div role="alert" className="text-xs leading-6 text-amber-700">这个教材页签引用的版本已更新，原来的提问关联没有被替换。<button className="wb-button ml-2" onClick={() => workbenchStore.getState().openKnowledge({ ...target, version: topic.version, title: topic.title })}>打开当前版本</button></div>
  const open = (t: LearningTarget) => workbenchStore.getState().openKnowledge(t)
  return (
    <article
      ref={articleRef}
      data-reading-ready={contentReady || undefined}
      className="learning-article space-y-7 pb-8"
    >
        <div className="article-selection-toolbar">
          <button className="wb-primary" type="button" onPointerDown={e => e.preventDefault()} onClick={() => {
            try {
              workbenchStore.getState().fixReading(selectedKnowledge(articleRef.current!, topic))
              setSelectionError('')
              viewStore.getState().setCenterTab('chat')
              layoutStore.setState({ full: false, ...(layoutStore.getState().viewport < 1100 ? { right: false } : {}) })
              requestAnimationFrame(() => document.querySelector<HTMLTextAreaElement>('.wb-center textarea')?.focus())
            } catch (error) { setSelectionError(String(error)) }
          }}>问选中段落</button>
          {selectionError && <p role="alert" className="w-full text-xs text-danger">{selectionError}</p>}
        </div>
      <header className="article-heading">
        <p className="text-[10px] font-semibold tracking-widest text-accent">{topic.group}</p>
        <h2 className="mt-2 text-lg font-semibold leading-8 tracking-tight text-slate-800">
          {topic.title}
        </h2>
        {/* 摘要就是正文首段，不再重复渲染一次。目录卡片里仍然显示摘要。 */}
        {(target.version !== topic.version ||
          (target.section_id && !topic.sections.some((s) => s.id === target.section_id))) && (
          <p
            role="status"
            className="mt-2 rounded-lg bg-warning/10 p-2 text-xs leading-6 text-warning"
          >
            原引用的教材或章节已更新；当前显示最新内容，继续提问也将使用此版本。
          </p>
        )}
        {topic.dialect && (
          <p className="mt-2 text-[11px] text-slate-400">SQL 方言：{topic.dialect}</p>
        )}
        <details className="article-toc">
          <summary className="cursor-pointer text-xs font-medium text-slate-500">
            本篇目录{' '}
            <span className="ml-1 font-normal text-slate-400">· {topic.sections.length} 节</span>
          </summary>
          <nav
            aria-label="章节目录"
            className="mt-2 flex flex-col border-t border-slate-200/70 pt-2"
          >
            {topic.sections.map((s, index) => (
              <button
                key={s.id}
                onClick={() =>
                  open({
                    topic_id: topic.id,
                    title: topic.title,
                    section_id: s.id,
                    version: topic.version,
                    href: `/learn/${topic.id}#${s.id}`,
                  })
                }
                className="flex items-baseline gap-2 rounded-md px-2 py-1.5 text-left text-xs text-slate-500 hover:bg-accent-soft hover:text-accent"
              >
                <span className="w-4 shrink-0 font-mono text-[10px] text-slate-400">
                  {String(index + 1).padStart(2, '0')}
                </span>
                {s.title}
              </button>
            ))}
          </nav>
        </details>
      </header>
      {topic.prerequisite_targets.length > 0 && (
        <section className="border-l-2 border-accent/30 pl-3">
          <p className="text-[10px] font-semibold text-slate-400">可以先了解</p>
          <div className="mt-1 flex flex-wrap gap-2">
            {topic.prerequisite_targets.map((t) => (
              <button
                key={t.href}
                className="text-xs leading-6 text-accent hover:underline"
                onClick={() => open(t)}
              >
                {t.title}
              </button>
            ))}
          </div>
        </section>
      )}
      {topic.sections
        .filter((s) => s.id !== 'sources' && s.id !== 'related')
        .map((section) => (
          <section key={section.id} data-section-id={section.id} className="scroll-mt-4">
            <h3 className="mb-3 text-[15px] font-semibold leading-7 text-slate-800">
              {section.title}
            </h3>
            <div className="text-sm text-slate-600">
              <LearningMarkdown text={section.content} targets={topic.learning_targets} assets={topic.assets} selectable />
            </div>
          </section>
        ))}
      <section className="rounded-xl border border-slate-200 p-3" aria-label="项目实例">
        <h3 className="text-xs font-semibold text-slate-600">这个概念在当前项目里</h3>
        {instancesError && (
          <p role="alert" className="mt-2 text-xs text-danger">
            {instancesError}
          </p>
        )}
        {instances.map((i) => (
          <button
            key={i.id}
            className="mt-2 block w-full rounded-lg bg-slate-50 p-2 text-left hover:bg-accent-soft/40"
            onClick={() => openSource(i)}
          >
            <span className="font-mono text-[11px] text-accent">
              {i.path}:{i.lineno}
            </span>
            <span className="mt-1 block text-[11px] leading-5 text-slate-500">
              {i.confidence < 0.8 ? '待核对 · ' : ''}
              {i.evidence}
            </span>
          </button>
        ))}
        {!instances.length && !instancesError && (
          <p className="mt-2 text-[11px] leading-6 text-slate-400">
            {projectId === null
              ? '导入项目后，可查看索引中有证据支持的对应实例。'
              : isMockMode
                ? '当前为快照模式，未关联真实项目实例。'
                : instanceResult === null
                  ? '正在核对项目索引中的关联实例…'
                  : instanceResult.status === 'not_indexed'
                    ? '该项目尚未完成索引，暂时无法查询项目实例。'
                    : '没有在索引里找到直接用到它的地方。'}
          </p>
        )}
        {instances.length >= 50 && (
          <p className="mt-2 text-[11px] text-slate-400">这里展示前 50 项，不代表完整召回结果。</p>
        )}
      </section>
      <section data-section-id="related" className="border-t border-slate-200 pt-3">
        <h3 className="text-xs font-semibold text-slate-500">继续探索</h3>
        <div className="mt-2 flex flex-wrap gap-2">
          {topic.related_targets.map((t) => (
            <button
              key={t.href}
              onClick={() => open(t)}
              className="rounded-lg bg-accent-soft/50 px-2 py-1 text-[11px] leading-5 text-accent hover:bg-accent-soft"
            >
              {t.title}
            </button>
          ))}
        </div>
      </section>
      <details
        data-section-id="sources"
        open={target.section_id === 'sources' || undefined}
        className="text-[11px] leading-6 text-slate-400"
      >
        <summary className="cursor-pointer">来源与许可</summary>
        {topic.sources.map((s) => (
          <p key={s.id} className="mt-2">
            <a href={s.url} target="_blank" rel="noreferrer" className="text-accent">
              {s.title}
            </a>{' '}
            · {s.author}
            <br />
            {s.version} ·{' '}
            <a href={s.license_url} target="_blank" rel="noreferrer">
              {s.license}
            </a>
          </p>
        ))}
      </details>
    </article>
  )
}
