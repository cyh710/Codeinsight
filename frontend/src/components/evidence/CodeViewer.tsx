/**
 * 只读代码查看器（Monaco，**必须懒加载**——它有 ~5MB，进首屏会白屏，
 * 违背"用户不需要逐个打开文件阅读"的初衷）。fallback 是带行号的 pre。
 */
import { lazy, Suspense } from 'react'
const MonacoViewer = lazy(() => import('./MonacoViewer'))

export default function CodeViewer({
  code,
  language,
  startLine = 1,
  highlightLines,
  viewKey,
}: {
  viewKey?: string
  code: string
  language: string
  startLine?: number
  highlightLines?: Array<[number, number]>
}) {
  const lines = code.split('\n')
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
      <Suspense
        fallback={
          <pre className="max-h-72 overflow-auto px-3 py-2 font-mono text-[11px] leading-relaxed text-slate-600">
            {lines.map((line, i) => (
              <div key={i}>
                <span className="mr-2 inline-block w-8 select-none text-right text-slate-300">
                  {startLine + i}
                </span>
                {line}
              </div>
            ))}
          </pre>
        }
      >
        <MonacoViewer
          viewKey={viewKey}
          code={code}
          language={language}
          startLine={startLine}
          highlightRanges={highlightLines ?? []}
        />
      </Suspense>
    </div>
  )
}
