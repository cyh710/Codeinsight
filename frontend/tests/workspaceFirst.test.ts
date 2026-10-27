import { afterEach, expect, it } from 'vitest'
import { workbenchStore, materialKey } from '../src/store/workbenchStore'
import { openCode } from '../src/components/exploration/actions'

afterEach(() => workbenchStore.getState().resetProject())

it('默认打开当前文件不继承旧索引版本，首次读取按哈希绑定且不增加材料历史', () => {
  const s = workbenchStore.getState()
  s.setIndexVersion('old-commit')
  s.selectFile('new.py')
  expect(workbenchStore.getState().rightPanel).toEqual({ mode: 'file', path: 'new.py', lineno: 1 })
  const length = workbenchStore.getState().history.length
  s.bindFileVersion('new.py', 1, null, undefined, 'workspace', 'first')
  expect(workbenchStore.getState().rightPanel).toMatchObject({ sourceKind: 'workspace', contentSha: 'first' })
  expect(workbenchStore.getState().history).toHaveLength(length)
  expect(workbenchStore.getState().tabs).toHaveLength(2)
})

it('同文件不同工作区版本不覆盖，来源跳转保留实际版本', () => {
  const s = workbenchStore.getState()
  openCode({ kind: 'code', project_id: 1, path: 'score.txt', lineno: 1, source_kind: 'workspace', content_sha256: 'old' })
  const previous = workbenchStore.getState().activeTab
  s.selectFile('score.txt', 1, null, undefined, 'workspace', 'new')
  expect(workbenchStore.getState().activeTab).not.toBe(previous)
  s.activateTab(previous)
  expect(workbenchStore.getState().rightPanel).toMatchObject({ contentSha: 'old' })
  expect(materialKey({ mode: 'file', path: 'score.txt', lineno: 1, indexEpoch: 1 })).not.toBe(previous)
})
