import { describe, expect, it, vi } from 'vitest'
import { hotState } from '../src/store/hotState'

describe('开发热更新状态', () => {
  it('同一个模块重新执行时保持容器和闭包身份，不重复创建订阅', () => {
    const hot = { data: {} }
    const factory = vi.fn(() => ({ count: 4, controller: new AbortController() }))
    const before = hotState(hot, 'projects', factory)
    before.count = 8
    const after = hotState(hot, 'projects', factory)
    expect(after).toBe(before)
    expect(after.count).toBe(8)
    expect(after.controller).toBe(before.controller)
    expect(factory).toHaveBeenCalledTimes(1)
  })
  it('不同模块相互隔离，生产环境不缓存模块外的状态', () => {
    const hot = { data: {} }
    expect(hotState(hot, 'a', () => 1)).toBe(1)
    expect(hotState(hot, 'b', () => 2)).toBe(2)
    expect(hotState(undefined, 'a', () => ({}))).not.toBe(hotState(undefined, 'a', () => ({})))
  })
})
