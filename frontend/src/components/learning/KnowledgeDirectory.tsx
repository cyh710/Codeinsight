import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { BookOpen, Search } from 'lucide-react'
import { getKnowledgeTree, searchKnowledge } from '../../api/learning'
import type { KnowledgeSearch, KnowledgeTree, LearningTarget } from '../../api/types'
import { panelKey, workbenchStore } from '../../store/workbenchStore'

export default function KnowledgeDirectory() {
  const [tree, setTree] = useState<KnowledgeTree | null>(null)
  const [initialQuery] = useState(workbenchStore.getState().directoryQuery)
  const [query, setQuery] = useState(initialQuery)
  const [result, setResult] = useState<KnowledgeSearch | null>(null)
  const [error, setError] = useState('')
  const [searching, setSearching] = useState(Boolean(initialQuery))
  const root = useRef<HTMLDivElement>(null)
  const sequence = useRef(0)
  const aliveRef = useRef(false)
  useEffect(() => {
    let alive = true
    aliveRef.current = true
    getKnowledgeTree()
      .then((r) => {
        if (alive) setTree(r)
      })
      .catch((e) => {
        if (alive) setError(String(e))
      })
    if (initialQuery)
      searchKnowledge(initialQuery)
        .then((r) => {
          if (alive) setResult(r)
        })
        .catch((e) => {
          if (alive) setError(String(e))
        })
        .finally(() => {
          if (alive) setSearching(false)
        })
    return () => {
      alive = false
      aliveRef.current = false
    }
  }, [initialQuery])
  useLayoutEffect(() => {
    const scroll = root.current?.closest('[data-reading-scroll]') as HTMLElement | null
    if (scroll)
      scroll.scrollTop =
        workbenchStore.getState().scrollPositions[panelKey(workbenchStore.getState().rightPanel)] ??
        0
  }, [tree, result])
  const open = (target: LearningTarget) => workbenchStore.getState().openKnowledge(target)
  const search = async () => {
    const request = ++sequence.current
    workbenchStore.getState().setDirectoryQuery(query)
    if (!query.trim()) {
      setResult(null)
      setSearching(false)
      return
    }
    setSearching(true)
    setError('')
    try {
      const r = await searchKnowledge(query)
      if (aliveRef.current && request === sequence.current) setResult(r)
    } catch (e) {
      if (aliveRef.current && request === sequence.current) setError(String(e))
    } finally {
      if (aliveRef.current && request === sequence.current) setSearching(false)
    }
  }
  return (
    <div ref={root} data-reading-ready={tree || result ? true : undefined} className="space-y-5">
      <div className="border-b border-slate-200 pb-4">
        <div className="flex items-center gap-2 text-accent">
          <BookOpen size={18} />
          <h3 className="text-sm font-semibold">从一个问题，读懂一个概念</h3>
        </div>
        <p className="mt-2 text-xs leading-6 text-slate-500">
          围绕代码按需阅读。先看定义，再跟着例子理解；阅读时可以回到对话继续问。
        </p>
        <form
          className="mt-3 flex gap-2"
          onSubmit={(e) => {
            e.preventDefault()
            void search()
          }}
        >
          <input
            aria-label="搜索知识"
            placeholder="SQL、函数参数、React state…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="min-w-0 flex-1 rounded-lg border border-slate-200 bg-transparent px-3 py-2 text-xs outline-none focus:border-accent"
          />
          <button
            aria-label="搜索章节"
            disabled={searching}
            className="rounded-lg bg-accent px-3 text-accent-foreground disabled:opacity-50"
          >
            <Search size={14} />
          </button>
        </form>
      </div>
      {error && (
        <p role="alert" className="text-xs leading-6 text-danger">
          {error}
        </p>
      )}
      {searching && <p className="text-xs text-slate-400">正在查找章节…</p>}
      {result ? (
        <div className="space-y-2">
          <div className="flex justify-between text-xs text-slate-500">
            <span>找到 {result.total} 个章节</span>
            <button
              className="text-accent"
              onClick={() => {
                sequence.current++
                setResult(null)
                setQuery('')
                workbenchStore.getState().setDirectoryQuery('')
              }}
            >
              返回目录
            </button>
          </div>
          {result.items.map((hit) => (
            <button
              key={hit.target.href}
              onClick={() => open(hit.target)}
              className="w-full rounded-lg border border-slate-200/70 p-3 text-left hover:bg-accent-soft/40"
            >
              <p className="text-xs font-semibold text-slate-700">{hit.target.title}</p>
              <p className="mt-1 line-clamp-3 whitespace-pre-line text-[11px] leading-6 text-slate-500">
                {hit.snippet}
              </p>
            </button>
          ))}
          {!result.total && (
            <p className="py-4 text-xs text-slate-400">没有匹配章节，请换个术语或浏览目录。</p>
          )}
        </div>
      ) : tree ? (
        tree.groups.map((group) => (
          <section key={group.title}>
            <h4 className="mb-2 flex items-center gap-2 text-xs font-semibold text-slate-500">
              {group.title}
              <span className="font-mono text-[10px] font-normal text-slate-400">
                {group.topics.length}
              </span>
            </h4>
            <div className="divide-y divide-slate-100 border-y border-slate-100">
              {group.topics.map((topic, index) => (
                <button
                  key={topic.id}
                  onClick={() =>
                    open({
                      topic_id: topic.id,
                      title: topic.title,
                      version: topic.version,
                      href: topic.href,
                      section_id: null,
                    })
                  }
                  className="group flex w-full gap-3 px-1 py-3 text-left hover:bg-accent-soft/30"
                >
                  <span className="pt-0.5 font-mono text-[10px] text-slate-300">
                    {String(index + 1).padStart(2, '0')}
                  </span>
                  <span>
                    <span className="block text-xs font-medium text-slate-700 group-hover:text-accent">
                      {topic.title}
                    </span>
                    <span className="mt-1 block line-clamp-2 text-[11px] leading-5 text-slate-400">
                      {topic.summary}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </section>
        ))
      ) : (
        !error && <p className="text-xs text-slate-400">读取知识目录…</p>
      )}
    </div>
  )
}
