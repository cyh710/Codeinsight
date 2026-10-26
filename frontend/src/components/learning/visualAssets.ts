import type { KnowledgeAsset } from '../../api/types'

/** 图片只解析当前教材的受维护清单，未知地址不触发外部加载。 */
export function resolveVisualAsset(src: string | undefined, assets: KnowledgeAsset[]) {
  const id = /^\/knowledge\/assets\/([a-z][a-z0-9-]*)$/.exec(src ?? '')?.[1]
  const asset = assets.find(item => item.id === id)
  return asset && asset.href === `/knowledge/assets/${asset.id}/${asset.sha256}` &&
    /^[a-f0-9]{64}$/.test(asset.sha256) ? asset : undefined
}
