import { describe, expect, it } from 'vitest'
import { projectStatusView } from '../src/components/tree/projectStatusView'

describe('projectStatusView', () => {
  it('ready 静默（tone=none，不显示徽标）', () => {
    expect(projectStatusView('ready').tone).toBe('none')
    expect(projectStatusView('ready').label).toBe('')
  })

  it('indexing → info；failed → danger；stale → warning', () => {
    expect(projectStatusView('indexing').tone).toBe('info')
    expect(projectStatusView('failed').tone).toBe('danger')
    expect(projectStatusView('stale').tone).toBe('warning')
    expect(projectStatusView('stale').label).toContain('过期')
  })

  it('未知状态兜底为静默（不白屏、不显示乱码）', () => {
    expect(projectStatusView('weird-unknown').tone).toBe('none')
  })
})
