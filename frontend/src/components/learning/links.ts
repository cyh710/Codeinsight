import type { LearningTarget } from '../../api/types'

export function resolveLearningLink(
  href: string | undefined,
  targets: readonly LearningTarget[],
  streaming = false,
) {
  if (streaming || !href || !/^\/learn\/[a-z][a-z0-9-]*(?:#[a-z][a-z0-9-]*)?$/.test(href))
    return null
  return targets.find((target) => target.href === href) ?? null
}
