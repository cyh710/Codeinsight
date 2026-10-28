import { openSource } from '../exploration/actions'
/**
 * 编排执行三态卡（契约 §16.2 / ADR 0035）。
 *
 * planned：计划卡 + 批准/拒绝/转为普通问答；executing：进度时间线 + 中止；
 * review：diff 摘要 + 合入/放弃；merged/rejected/aborted/failed：终态摘要，
 * merged 附变更学习卡（事实带 file:line 跳右栏，概念 chips 链概念卡）。
 *
 * 动作都打后端端点（契约 §16.3），返回新状态后本地更新——不自造状态。
 */
import { useEffect, useState } from 'react'
import { useStore } from 'zustand'
import {
  AlertTriangle,
  Check,
  CircleX,
  FileDiff,
  GitMerge,
  Loader2,
  Play,
  Sparkles,
  Square,
} from 'lucide-react'
import { executionAction, getExecution } from '../../api/executions'
import type { ChatMessage } from '../../store/types'
import { chatStore } from '../../store/chatStore'
import { workbenchStore } from '../../store/workbenchStore'
import type { Citation, ExecutionStatus } from '../../api/types'

const STATUS_LABEL: Record<ExecutionStatus, string> = {
  planned: '待批准',
  executing: '执行中',
  review: '待验收',
  merged: '已合入',
  rejected: '已拒绝',
  aborted: '已中止',
  failed: '执行失败',
}

const STATUS_TONE: Record<ExecutionStatus, string> = {
  planned: 'bg-accent-soft text-accent',
  executing: 'bg-accent-soft text-accent',
  review: 'bg-warning/10 text-warning',
  merged: 'bg-success/10 text-success',
  rejected: 'bg-slate-100 text-slate-500',
  aborted: 'bg-slate-100 text-slate-500',
  failed: 'bg-danger-soft text-danger',
}

function useExecutionActions(message: ChatMessage) {
  const meta = message.execution!
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [pollError, setPollError] = useState('')
  const projectId = useStore(chatStore, state => state.projectId)
  const conversationId = useStore(chatStore, state => state.conversationId)
  const taskId = meta.task_id
  const status = meta.status
  const hasCard = Boolean(meta.change_card)
  useEffect(() => {
    if (projectId === null || !conversationId) return
    let active = true
    let timer: ReturnType<typeof setTimeout> | undefined
    const started = Date.now()
    const poll = async () => {
      try {
        const next = await getExecution(projectId, taskId)
        if (!active) return
        chatStore.getState().updateExecution(projectId, conversationId, message.id, next)
        setPollError('')
        if (['planned', 'executing', 'review'].includes(next.status)
          || (next.status === 'merged' && !next.change_card && !next.error && Date.now() - started < 60_000)) {
          timer = setTimeout(() => void poll(), 2000)
        }
      } catch (cause) {
        if (!active) return
        setPollError(`状态更新失败：${cause instanceof Error ? cause.message : String(cause)}`)
        timer = setTimeout(() => void poll(), 5000)
      }
    }
    void poll()
    return () => { active = false; clearTimeout(timer) }
  }, [projectId, conversationId, message.id, taskId, status, hasCard])
  const run = async (action: 'approve' | 'reject' | 'abort' | 'merge') => {
    if (busy) return
    setBusy(true)
    setError('')
    try {
      if (projectId === null) throw new Error('没有当前项目')
      const next = await executionAction(projectId, meta.task_id, action)
      // 本地更新这条消息的执行卡（后端是权威，这里只是投影）。
      chatStore.getState().updateExecution(projectId, conversationId, message.id, next)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }
  return { meta, busy, error: error || pollError, run }
}

function ActionButton({ onClick, disabled, tone, icon, label }: {
  onClick: () => void
  disabled?: boolean
  tone: 'primary' | 'danger' | 'neutral'
  icon: React.ReactNode
  label: string
}) {
  const cls =
    tone === 'primary'
      ? 'bg-accent text-accent-foreground hover:bg-accent-hover'
      : tone === 'danger'
        ? 'border border-danger/40 text-danger hover:bg-danger-soft'
        : 'border border-slate-300 text-slate-600 hover:bg-slate-50'
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`inline-flex items-center gap-1.5 rounded-lg px-2.5 py-1.5 text-[11px] font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-45 ${cls}`}
    >
      {icon}
      {label}
    </button>
  )
}

function ProgressList({ progress }: { progress: import('../../api/types').ExecutionProgress[] }) {
  if (progress.length === 0) {
    return <p className="text-[11px] text-slate-400">启动执行 agent 中…</p>
  }
  return (
    <ul className="max-h-44 space-y-1 overflow-y-auto" aria-label="执行进度">
      {progress.slice(-30).map((p, i) => (
        <li key={i} className="flex items-center gap-1.5 text-[11px] text-slate-600">
          {p.kind === 'tool' ? (
            <>
              <span className="rounded bg-slate-100 px-1 py-px font-mono text-[10px]">{p.tool}</span>
              {p.file && <span className="truncate font-mono text-[10.5px]">{p.file}</span>}
              {p.detail && <span className="truncate text-slate-400">{p.detail}</span>}
            </>
          ) : (
            <span className="truncate">{p.detail || p.kind}</span>
          )}
        </li>
      ))}
    </ul>
  )
}

function ChangeCard({ card }: { card: NonNullable<import('../../api/types').ExecutionMetadata['change_card']> }) {
  const onOpenCitation = (c: Citation) => {
    openSource(c)
  }
  return (
    <section className="mt-3 border-t border-slate-200/60 pt-3" aria-label="变更学习卡">
      <p className="mb-2 flex items-center gap-1.5 text-[11px] font-semibold text-slate-500">
        <Sparkles size={12} strokeWidth={1.8} className="text-accent" />
        这次改动学到了什么
      </p>
      <ul className="space-y-1.5">
        {card.facts.slice(0, 6).map((f, i) => (
          <li key={i} className="flex flex-wrap items-baseline gap-x-2 text-xs leading-relaxed">
            <button
              type="button"
              onClick={() => onOpenCitation(f.citation)}
              className="rounded bg-accent-soft/70 px-1.5 py-px font-mono text-[10px] text-accent hover:bg-accent-soft"
            >
              {f.citation.path}:{f.citation.lineno}
            </button>
            <span className="min-w-0 text-slate-700">{f.text}</span>
          </li>
        ))}
      </ul>
      {card.impacted.symbols.length > 0 && (
        <p className="mt-2 text-[11px] text-slate-500">
          影响 {card.impacted.symbols.length} 个下游符号
          {card.impacted.modules.length > 0 && ` · ${card.impacted.modules.slice(0, 3).join('、')}`}
        </p>
      )}
      {card.concept_ids.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {card.concept_ids.slice(0, 5).map((c) => (
            <button
              key={c}
              type="button"
              onClick={() => workbenchStore.getState().openConcept(c)}
              className="rounded bg-warning/10 px-1.5 py-px text-[10px] text-warning hover:bg-warning/20"
              title="打开概念卡"
            >
              #{c}
            </button>
          ))}
        </div>
      )}
    </section>
  )
}

export default function ExecutionCard({ message }: { message: ChatMessage }) {
  const { meta, busy, error, run } = useExecutionActions(message)
  const status = meta.status

  return (
    <section
      className="mt-2 rounded-xl border border-slate-200/80 bg-white/70 px-3.5 py-3"
      aria-label={`执行任务 ${meta.task_id}`}
      data-testid="execution-card"
      data-status={status}
    >
      <header className="flex items-center gap-2">
        <span className={`rounded px-1.5 py-px text-[10px] font-semibold ${STATUS_TONE[status]}`}>
          {STATUS_LABEL[status]}
        </span>
        <span className="font-mono text-[10px] text-slate-300">{meta.task_id}</span>
        {status === 'executing' && <Loader2 size={12} className="animate-spin text-accent" />}
      </header>

      {/* 计划（planned / review 及之后都可见，验收时对照计划） */}
      <div className="mt-2 space-y-1 text-xs leading-relaxed text-slate-700">
        <p>
          <span className="text-slate-400">意图：</span>
          {meta.plan.intent}
        </p>
        {meta.plan.approach && (
          <p>
            <span className="text-slate-400">思路：</span>
            {meta.plan.approach}
          </p>
        )}
        {meta.plan.files.length > 0 && (
          <p>
            <span className="text-slate-400">文件：</span>
            <span className="font-mono text-[11px]">{meta.plan.files.join('、')}</span>
          </p>
        )}
        {meta.plan.risks.length > 0 && (
          <p className="text-warning">
            <span className="opacity-70">风险：</span>
            {meta.plan.risks.join('；')}
          </p>
        )}
      </div>

      {/* 执行进度 */}
      {status === 'executing' && (
        <div className="mt-2.5">
          <ProgressList progress={meta.progress} />
        </div>
      )}

      {/* 验收：diff 摘要 */}
      {(status === 'review' || status === 'merged') && meta.diff_summary && (
        <div className="mt-2.5 flex items-center gap-2 text-[11px] text-slate-600">
          <FileDiff size={13} strokeWidth={1.7} className="shrink-0 text-slate-400" />
          <span>
            {meta.diff_summary.files_changed} 个文件 ·{' '}
            <span className="text-success">+{meta.diff_summary.insertions}</span>{' '}
            <span className="text-danger">−{meta.diff_summary.deletions}</span>
          </span>
          <details className="min-w-0">
            <summary className="cursor-pointer text-slate-400">明细</summary>
            <ul className="mt-1 max-h-32 space-y-0.5 overflow-y-auto">
              {meta.diff_summary.files.map((f) => (
                <li key={f.path} className="flex gap-2 font-mono text-[10.5px]">
                  <span className="w-14 shrink-0 text-slate-400">{f.status}</span>
                  <span className="min-w-0 truncate text-slate-600">{f.path}</span>
                  <span className="ml-auto shrink-0">
                    <span className="text-success">+{f.add}</span>{' '}
                    <span className="text-danger">−{f.del}</span>
                  </span>
                </li>
              ))}
            </ul>
          </details>
        </div>
      )}

      {meta.summary && (status === 'merged' || status === 'review') && (
        <p className="mt-2 rounded-lg bg-slate-50 px-2.5 py-2 text-[11px] leading-relaxed text-slate-600">
          {meta.summary}
        </p>
      )}

      {/* 终态错误 */}
      {(status === 'failed' || status === 'aborted' || status === 'merged') && meta.error && (
        <p className="mt-2 flex items-start gap-1.5 text-[11px] text-danger" role="alert">
          <AlertTriangle size={12} strokeWidth={1.8} className="mt-0.5 shrink-0" />
          {meta.error}
        </p>
      )}

      {/* 变更学习卡（merged 后） */}
      {status === 'merged' && meta.change_card && <ChangeCard card={meta.change_card} />}

      {/* 动作区 */}
      {error && (
        <p className="mt-2 text-[11px] text-danger" role="alert">
          {error}
        </p>
      )}
      <div className="mt-2.5 flex flex-wrap gap-2">
        {status === 'planned' && (
          <>
            <ActionButton
              tone="primary"
              icon={<Play size={12} strokeWidth={1.9} />}
              label="批准执行"
              disabled={busy}
              onClick={() => void run('approve')}
            />
            <ActionButton
              tone="neutral"
              icon={<CircleX size={12} strokeWidth={1.8} />}
              label="拒绝"
              disabled={busy}
              onClick={() => void run('reject')}
            />
          </>
        )}
        {status === 'executing' && (
          <ActionButton
            tone="danger"
            icon={<Square size={11} strokeWidth={2} />}
            label="中止"
            disabled={busy}
            onClick={() => void run('abort')}
          />
        )}
        {status === 'review' && (
          <>
            <ActionButton
              tone="primary"
              icon={<GitMerge size={12} strokeWidth={1.9} />}
              label="验收并合入"
              disabled={busy}
              onClick={() => void run('merge')}
            />
            <ActionButton
              tone="danger"
              icon={<CircleX size={12} strokeWidth={1.8} />}
              label="放弃（删除隔离分支）"
              disabled={busy}
              onClick={() => void run('abort')}
            />
          </>
        )}
        {status === 'merged' && (
          <span className="flex items-center gap-1 text-[11px] text-success">
            <Check size={12} strokeWidth={2} />
            {meta.change_card ? '已合入当前分支，索引已更新' : meta.error ? '已合入，学习资料更新失败' : '已合入，正在更新索引与学习卡'}
          </span>
        )}
      </div>
    </section>
  )
}
