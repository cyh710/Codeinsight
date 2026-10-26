import { useEffect, useRef, useState } from 'react'
import type { KnowledgeAsset } from '../../api/types'
import { BASE } from '../../api/client'

/** 图只来自同版本教材清单；原生模态框关闭时恢复焦点及下方阅读位置。 */
export default function KnowledgeFigure({ asset, caption, sourceMap }: {
  asset: KnowledgeAsset
  caption: string
  sourceMap?: string
}) {
  const [failed, setFailed] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const dialog = useRef<HTMLDialogElement>(null)
  const titleId = `figure-title-${asset.id}`
  const src = `${BASE}${asset.href}${attempt ? `?retry=${attempt}` : ''}`
  useEffect(() => () => dialog.current?.close(), [])
  return (
    <figure className="knowledge-figure">
      {failed ? (
        <div className="knowledge-figure-fallback" style={{ aspectRatio: `${asset.width}/${asset.height}` }}>
          <strong>图示暂未加载</strong>
          <p>{asset.description}</p>
          <button type="button" onClick={() => { setFailed(false); setAttempt(n => n + 1) }}>重试图片</button>
        </div>
      ) : (
        <button className="knowledge-figure-open" type="button" aria-label={`放大图示：${asset.title}`}
          onClick={() => dialog.current?.showModal()}>
          <img src={src} alt={asset.title} width={asset.width} height={asset.height}
            loading="lazy" decoding="async" onError={() => setFailed(true)} />
          <span className="knowledge-figure-zoom">放大查看</span>
        </button>
      )}
      <figcaption><span data-source-map={sourceMap}>{caption}</span></figcaption>
      <dialog ref={dialog} className="knowledge-figure-dialog" aria-labelledby={titleId}>
        <div className="knowledge-figure-dialog-header">
          <strong id={titleId}>{asset.title}</strong>
          <button type="button" autoFocus onClick={() => dialog.current?.close()}>关闭图示</button>
        </div>
        <div className="knowledge-figure-scroll">
          <img src={src} alt={asset.description} width={asset.width} height={asset.height} />
        </div>
        <p>{asset.description}</p>
        <small>图示：{asset.author} · {asset.license}</small>
      </dialog>
    </figure>
  )
}
