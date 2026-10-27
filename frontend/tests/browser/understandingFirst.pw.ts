import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

test('稀疏引用仍有查阅材料与探索脉络，刷新后保留且不补满推荐', async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
  await page.goto('/')
  await page.locator('.wb-center textarea').fill('我想了解已有策略与成绩 __fixture_understanding_sparse__')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const answer = page.locator('.assistant-answer').last()
  await expect(answer).toContainText('当前材料没有可比较的实验成绩')
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  await expect(answer.locator('.reply-citation')).toHaveCount(0)
  await expect(answer.getByRole('navigation', { name: '接着探索' })).toHaveCount(0)
  await expect(answer).not.toContainText('未核实')
  await answer.getByText('来源与查阅过程', { exact: true }).click()
  await answer.getByRole('button', { name: '查看来源', exact: true }).click()
  await expect(page.locator('#workspace-materials')).toContainText('本轮查阅')
  await expect(page.locator('#workspace-materials')).toContainText('store.py:1')
  await expect(page.locator('#workspace-materials')).toContainText('sqlite3')
  for (const width of [900, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.screenshot({ path: resolve('..', '.ci/browser/understanding-first-sources.png'), animations: 'disabled' })
  const detail = await (await request.get(`/api/projects/1/conversations/${conversation.id}`)).json()
  expect(detail.exploration_state.items[0].text).toContain('保存操作')
  await page.reload()
  await expect(page.locator('.assistant-answer')).toContainText('当前材料没有可比较的实验成绩')
  await expect(page.locator('#workspace-materials')).toContainText('本轮查阅')
})

test('旧概念独有解读作为普通正文保留，项目位置可打开而无分类和百分比', async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.route('**/api/projects/1/concepts/jwt', route => route.fulfill({ json: {
    concept_id: 'jwt', name: 'JWT', category: 'security', summary: '签名验证保护声明的完整性。',
    principles: null, tradeoffs: null, alternatives: null, references: [], instance_count: 0, instance_paths: [],
  } }))
  await page.route('**/api/projects/1/concepts/jwt/instances', route => route.fulfill({ json: { items: [], total: 0 } }))
  await page.route('**/api/projects/1/concepts/jwt/explain', route => route.fulfill({ json: {
    concept_id: 'jwt', depth: 'deep', summary: '签名验证保护声明的完整性。',
    facts: [{ text: '这是用于验证旧记录阅读的夹具位置。', citation: { path: 'store.py', lineno: 3, end_lineno: 3, qualname: null, snippet: '' } }],
    inferences: [{ text: '签名验证保护声明的完整性。', confidence: 0.5 }, { text: '过期检查还需核对调用参数。', confidence: 0.6 }],
    instances: [], llm_used: true,
  } }))
  await page.goto(`/?${new URLSearchParams({ project: '1', conversation: conversation.id, material: JSON.stringify({ mode: 'concept', conceptId: 'jwt' }) })}`)
  const card = page.locator('#workspace-materials')
  await card.getByRole('tab', { name: '深入探索' }).click()
  await expect(card).toContainText('过期检查还需核对调用参数')
  await expect(card.getByText('签名验证保护声明的完整性。', { exact: true })).toHaveCount(1)
  await expect(card).not.toContainText('模型判断')
  await expect(card).not.toContainText('60%')
  await card.getByText('项目位置', { exact: true }).click()
  await card.getByRole('button', { name: 'store.py:3', exact: true }).click()
  await expect(page.locator('#workspace-materials .monaco-editor')).toBeVisible()
})

test('明确知识动作的解读不依赖逐句代码引用，刷新后仍能继续读', async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
  await page.route('**/api/projects/1/conversations/*/turns/*', async route => {
    const response = await route.fetch()
    const turn = await response.json()
    await route.fulfill({ response, json: { ...turn, answer: { ...turn.answer, citations: [] } } })
  })
  await page.goto('/')
  await page.getByRole('navigation', { name: '项目探索入口' }).getByRole('button').first().click()
  await page.getByRole('navigation', { name: '接着探索' }).last().getByRole('button', { name: /理解事务的提交与回滚/ }).click()
  const context = page.locator('.context-reading')
  await expect(context.locator('.context-excerpt')).toContainText('写入先开启事务')
  await expect(context).not.toContainText('没有项目代码依据')
  await expect(context.locator('.context-project-sources')).toHaveCount(0)
  await page.reload()
  await expect(page.locator('.context-reading .context-excerpt')).toContainText('写入先开启事务')
  await page.locator('.context-reading').getByRole('button', { name: '阅读全文', exact: true }).click()
  await expect(page.locator('.learning-article')).toBeVisible()
})
