/**
 * Monaco 真身（由 CodeViewer 懒加载，不进首屏 bundle）。
 * 只读；`startLine` 让行号对齐符号在文件里的真实位置。
 */
import Editor, { loader } from '@monaco-editor/react'
import type { Monaco } from '@monaco-editor/react'
// 默认行为是从 jsDelivr 拉 Monaco 的 loader —— 内网/离线环境会永远停在
// 「编辑器加载中…」。这里改用 npm 包里自带的 monaco，随懒加载 chunk 一起发。
// 用 `editor.api`（精简入口）而不是整个 monaco-editor：后者会把所有语言
// 的语法/语言服务一并打进 chunk，体积差一个量级。
import * as monaco from 'monaco-editor/editor/editor.api'
// 包 exports 把 `monaco-editor/*.js` 映到 `esm/vs/*.js`，所以这里不要再写 esm/vs。
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
