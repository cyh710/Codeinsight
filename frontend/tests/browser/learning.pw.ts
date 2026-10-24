import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

test('真实 API 的知识阅读、续问、往返和项目隔离', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  const reader = page.locator('aside').last()
  await page.getByTestId('tree-file').filter({ hasText: 'store.py' }).click()
  await expect(reader.getByText('当前窗口最多 200 行', { exact: false })).toBeVisible()
  const input = page.getByRole('textbox').last()
  await input.fill('SQL 是什么')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'SQL', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: 'SQL', exact: true }).click()
  await expect(
    reader.getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列' }),
  ).toBeVisible()
  await expect(reader.getByRole('button').filter({ hasText: '组合证据' })).toBeVisible()
  await reader.getByRole('button', { name: '跟着例子理解', exact: true }).click()
  const scroll = reader.locator('[data-reading-scroll]')
  await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
  const request = page.waitForRequest(
    (r) => r.url().endsWith('/query/stream') && r.method() === 'POST',
  )
  await input.fill('这里是什么意思')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const body = (await request).postDataJSON()
  expect(body.reading_context.kind).toBe('knowledge')
  expect(body.reading_context.topic_id).toBe('sql-database')
  expect(body.reading_context.section_id).toBe('example')
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible()
  await scroll.evaluate((el) => {
    el.scrollTop = 1300
  })
  await page.waitForTimeout(100)
  const position = await scroll.evaluate((el) => el.scrollTop)
  await reader.getByRole('button', { name: 'SELECT：查询、筛选与排序', exact: true }).click()
  await expect(
    reader.getByRole('heading', {
      name: 'SELECT：查询、筛选与排序',
      exact: true,
    }),
  ).toBeVisible()
  await reader.getByRole('button', { name: '返回上一处', exact: true }).click()
  await expect(
    reader.getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列' }),
  ).toBeVisible()
  await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(position - 20)
  await page.screenshot({
    path: resolve('..', '.ci/browser/learning-workbench.png'),
    fullPage: true,
  })
  await reader.getByRole('button', { name: '回到代码', exact: true }).click()
  await expect(reader.getByText('当前窗口最多 200 行', { exact: false })).toBeVisible()
  const codeRequest = page.waitForRequest(
    (r) => r.url().endsWith('/query/stream') && r.method() === 'POST',
  )
  await input.fill('这里是什么意思')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  expect((await codeRequest).postDataJSON().reading_context).toMatchObject({
    kind: 'code',
    path: 'store.py',
    project_id: 1,
  })
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '选择项目', exact: true }).click()
  await page.getByRole('option', { name: /example-other/ }).click()
  await expect(page.getByText('结合代码 store.py:1 提问', { exact: false })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'SQL', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '选择项目', exact: true }).click()
  await page.getByRole('option', { name: /example-main/ }).click()
  await expect(page.getByRole('link', { name: 'SQL', exact: true }).first()).toBeVisible()
  expect(errors).toEqual([])
})

test('Provider 故障后教材仍能阅读，错误目标有可解释降级', async ({ page }) => {
  await page.goto('/learn/sql-database#removed-old-section')
  const reader = page.locator('aside').last()
  await expect(reader.getByText('原引用的教材或章节已更新', { exact: false })).toBeVisible()
  await page.getByRole('textbox').last().fill('__fixture_fail_provider__')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('alert').first()).toBeVisible()
  await expect(
    reader.getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列' }),
  ).toBeVisible()
  await reader.getByRole('button', { name: '知识目录', exact: true }).click()
  await reader.getByRole('textbox', { name: '搜索知识' }).fill('React state 是什么')
  await reader.getByRole('button', { name: '搜索章节', exact: true }).click()
  await expect(reader.getByRole('button').filter({ hasText: 'State' }).first()).toBeVisible()
})

test('真实项目实例、代码概念标签与 deep 降级形成往返', async ({ page }) => {
  const external: string[] = []
  page.on('request', (request) => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith('http://127.0.0.1:'))
      external.push(request.url())
  })
  await page.goto('/learn/sql-transactions')
  const reader = page.locator('aside').last()
  await reader.getByRole('button').filter({ hasText: '组合证据' }).click()
  await expect(reader.getByRole('heading', { name: /save/ })).toBeVisible()
  await expect(reader.locator('.monaco-editor')).toBeVisible()
  await reader.getByRole('button', { name: '了解 db-transaction', exact: true }).click()
  await reader.getByRole('tab', { name: '深入探索', exact: true }).click()
  await expect(reader.getByRole('status').filter({ hasText: '深入解释不可用' })).toBeVisible()
  await reader.getByRole('button', { name: '数据库事务：一致完成状态转换', exact: true }).click()
  await expect(
    reader.getByRole('heading', {
      name: '数据库事务：一致完成状态转换',
      exact: true,
    }),
  ).toBeVisible()
  await reader.getByRole('button', { name: '回到代码', exact: true }).click()
  await expect(reader.getByRole('heading', { name: /save/ })).toBeVisible()
  expect(external).toEqual([])
})
