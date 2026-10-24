/**
 * Monaco 真身（由 CodeViewer 懒加载，不进首屏 bundle）。
 * 只读；`startLine` 让行号对齐符号在文件里的真实位置。
 */
import Editor, { loader } from '@monaco-editor/react'
import type { Monaco } from '@monaco-editor/react'
import * as monaco from 'monaco-editor/editor/editor.api'
import EditorWorker from 'monaco-editor/editor/editor.worker.js?worker'
import 'monaco-editor/languages/definitions/python/register'
import 'monaco-editor/languages/definitions/javascript/register'
import 'monaco-editor/languages/definitions/typescript/register'
import 'monaco-editor/languages/definitions/sql/register'

// 代码阅读不依赖外部 CDN；整个编辑器模块仍由 CodeViewer 延迟加载。
self.MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })
const positions = new Map<string, { scrollTop: number; scrollLeft: number }>()

export default function MonacoViewer({
  code,
  language,
  startLine,
  highlightRanges,
  viewKey,
}: {
  viewKey?: string
  code: string
  language: string
  startLine: number
  highlightRanges: Array<[number, number]>
}) {
  const beforeMount = (monaco: Monaco) => {
    monaco.editor.defineTheme('ci-light', {
      base: 'vs',
      inherit: true,
      rules: [],
      colors: { 'editor.background': '#f8fafc' },
    })
  }

  const decorations = highlightRanges.map(([from, to], i) => ({
    id: `hl-${i}`,
    range: {
      startLineNumber: from,
      startColumn: 1,
      endLineNumber: Math.max(from, to),
      endColumn: 1,
    },
    options: { isWholeLine: true, className: 'bg-accent-soft/60' },
  }))

  return (
    <Editor
      height="280px"
      theme="ci-light"
      language={language}
      value={code}
      beforeMount={beforeMount}
      onMount={(editor) => {
        if (viewKey) {
          const saved = positions.get(viewKey)
          if (saved) editor.setScrollPosition(saved)
          editor.onDidScrollChange(() =>
            positions.set(viewKey, {
              scrollTop: editor.getScrollTop(),
              scrollLeft: editor.getScrollLeft(),
            }),
          )
        }
        editor.createDecorationsCollection(
          decorations.map((d) => ({
            range: d.range,
            options: d.options,
          })),
        )
      }}
      options={{
        readOnly: true,
        minimap: { enabled: false },
        fontSize: 11,
        lineNumbersMinChars: 4,
        scrollBeyondLastLine: false,
        renderLineHighlight: 'none',
        automaticLayout: true,
        // 片段是符号的局部：行号从 startLine 起数，与文件真实行号对齐。
        lineNumbers: (n) => String(startLine + n - 1),
      }}
      loading={<p className="p-3 text-xs text-slate-400">编辑器加载中…</p>}
    />
  )
}
