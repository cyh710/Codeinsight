import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'
import type { ExecutionMetadata } from '../../src/api/types'

test('执行卡从恢复的回合读取计划，轮询到验收及学习卡', async ({ page, request }) => {
  // 驱动器与审批端点在后端离线测试验证；这里用接口夹具单独验证浏览器的状态投影。
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  const cid = conversation.id as string
  const response = await request.post('/api/query', { data: {
    project_id: 1, conversation_id: cid, request_id: 'execution-card-fixture', question: 'SQL 是什么',
  } })
  expect(response.ok()).toBe(true)
  const meta: ExecutionMetadata = {
    task_id: 'exec-ui-fixture', status: 'planned',
    plan: { intent: '修复保存逻辑', files: ['store.py'], approach: '核对提交步骤', risks: [] },
    progress: [], diff_summary: null, change_card: null, summary: '',
  }
  let polls = 0
  await page.route(`**/api/projects/1/conversations/${cid}/turns*`, async route => {
    const upstream = await route.fetch()
    const body = await upstream.json()
    for (const turn of body.items) {
      if (turn.request_id === 'execution-card-fixture') turn.answer.execution = { ...meta }
    }
    await route.fulfill({ response: upstream, json: body })
  })
  await page.route('**/api/projects/1/executions/exec-ui-fixture**', async route => {
    if (route.request().method() === 'POST') {
      if (route.request().url().endsWith('/approve')) meta.status = 'executing'
      if (route.request().url().endsWith('/merge')) meta.status = 'merged'
      polls = 0
    } else if (++polls >= 2) {
      if (meta.status === 'executing') {
        meta.status = 'review'
        meta.summary = '保存逻辑已调整，请验收。'
        meta.diff_summary = { files_changed: 1, insertions: 1, deletions: 1,
          files: [{ path: 'store.py', status: 'modified', add: 1, del: 1 }] }
      } else if (meta.status === 'merged') {
        meta.change_card = { facts: [], impacted: { modules: [], symbols: [] }, concept_ids: [] }
      }
    }
    await route.fulfill({ json: { ...meta } })
  })
  await page.addInitScript(value => localStorage.setItem('ci.activeConversation.1', value), cid)
  await page.goto('/')
  const card = page.getByTestId('execution-card')
  await expect(card).toHaveAttribute('data-status', 'planned')
  await card.getByRole('button', { name: '批准执行' }).click()
  await expect(card).toHaveAttribute('data-status', 'executing')
  await expect(card).toHaveAttribute('data-status', 'review')
  await card.getByRole('button', { name: '验收并合入' }).click()
  await expect(card).toHaveAttribute('data-status', 'merged')
  await expect(card.getByRole('region', { name: '变更学习卡' })).toBeVisible()
  await expect(card).toContainText('索引已更新')
  await page.screenshot({ path: resolve('../.ci/browser/executors-integration.png'), fullPage: true })
})
