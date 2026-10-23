import { useState, type ReactNode } from 'react'

interface RetryableImageProps {
  src?: string | null
  alt: string
  /** Layout classes applied to the image area, including its reserved size. */
  className?: string
  /** Classes applied to the actual image element. */
  imageClassName?: string
  fallbackLabel?: ReactNode
  retryLabel?: string
  /** Make the healthy image a button without nesting a retry button. */
  onActivate?: () => void
  activateLabel?: string
}

interface ImageState {
  src: string | null | undefined
  failed: boolean
  loaded: boolean
  attempt: number
}

/**
 * A stable image surface for local/generated assets.
 *
 * The wrapper keeps the caller's layout box when an image fails, and retries
 * with a cache-busting query so a browser-cached 404 does not stay stuck.
 */
export default function RetryableImage({
  src,
  alt,
  className = '',
  imageClassName = 'max-h-full max-w-full object-contain',
  fallbackLabel = '图片暂时无法加载',
  retryLabel = '重新加载',
  onActivate,
  activateLabel,
}: RetryableImageProps) {
  const [state, setState] = useState<ImageState>({ src, failed: false, loaded: false, attempt: 0 })

  // Reset a previous failure when the caller switches to another asset. This
  // render-phase adjustment avoids a one-frame stale error placeholder.
  if (state.src !== src) {
    setState({ src, failed: false, loaded: false, attempt: 0 })
  }

  if (!src) {
    return (
      <div className={`flex items-center justify-center text-center text-xs text-slate-500 ${className}`} role="status">
        {fallbackLabel}
      </div>
    )
  }

  const imageSrc = state.attempt > 0 ? addRetryParam(src, state.attempt) : src
  if (state.failed) {
    return (
      <div className={`flex flex-col items-center justify-center gap-2 text-center text-xs text-slate-500 ${className}`} role="status" aria-live="polite">
        <span>{fallbackLabel}</span>
        <button
          type="button"
          onClick={() => setState((current) => ({ ...current, failed: false, loaded: false, attempt: current.attempt + 1 }))}
          className="rounded-md border border-slate-300 bg-white px-2.5 py-1.5 text-xs font-semibold text-accent transition hover:border-accent-bright hover:bg-accent-soft/60"
        >
          {retryLabel}
        </button>
      </div>
    )
  }

  const image = (
    <>
      {!state.loaded && (
        <span className="absolute inset-0 flex items-center justify-center text-xs text-slate-400" role="status">
          加载中…
        </span>
      )}
      {/* motion §10：生成图 blur-in（blur 2px + 透明 → 清晰，220ms）；
          布局框由外层容器保证，不跳高。 */}
      <img
        key={`${src}:${state.attempt}`}
        src={imageSrc}
        alt={alt}
        className={`${imageClassName} motion-image-in ${state.loaded ? '' : 'motion-image-in--pending'}`}
        onLoad={() => setState((current) => current.src === src ? { ...current, loaded: true, failed: false } : current)}
        onError={() => setState((current) => current.src === src ? { ...current, loaded: false, failed: true } : current)}
      />
    </>
  )
  if (onActivate) {
    return (
      <button
        type="button"
        onClick={onActivate}
        aria-label={activateLabel}
        aria-busy={!state.loaded}
        className={`relative flex items-center justify-center ${className}`}
      >
        {image}
      </button>
    )
  }
  return <div className={`relative flex items-center justify-center ${className}`} aria-busy={!state.loaded}>{image}</div>
}

function addRetryParam(src: string, attempt: number): string {
  if (src.startsWith('data:') || src.startsWith('blob:')) return src
  // Query parameters must be inserted before a URL fragment; appending after
  // ``#hash`` would leave the cache-buster invisible to the server.
  const hashIndex = src.indexOf('#')
  const base = hashIndex >= 0 ? src.slice(0, hashIndex) : src
  const hash = hashIndex >= 0 ? src.slice(hashIndex) : ''
  return `${base}${base.includes('?') ? '&' : '?'}__retry=${attempt}${hash}`
}

// Kept exported for the node-based frontend contract tests without requiring
// a DOM test runner.
// eslint-disable-next-line react-refresh/only-export-components
export function retryImageUrl(src: string, attempt: number): string {
  return addRetryParam(src, attempt)
}
