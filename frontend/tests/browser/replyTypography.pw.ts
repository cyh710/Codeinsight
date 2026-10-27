import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

test('回复排版、范围引用、旧回答和右侧版本定位', async ({ page, request, context }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => {
    localStorage.setItem('ci.projectId', '1')
    localStorage.setItem('ci.activeConversation.1', cid)
    Object.defineProperty(navigator, 'clipboard', { value: { writeText: async (text: string) => {
      sessionStorage.setItem('fixture.copiedCode', text)
    } } })
  }, conversation.id)
  await page.goto('/')
  const input = page.locator('.wb-center textarea')
  await expect(input).toBeEnabled()
  await input.fill('解释这段查询 __fixture_reply_rendering__')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const answer = page.locator('.assistant-answer')
  const citation = answer.getByRole('link', { name: 'hybrid.py:19–23', exact: true })
  await expect(citation).toBeVisible()
  await expect(citation).toHaveAttribute('title', 'wattbot-nlp/src/dense/hybrid.py:19')
  const href = await citation.getAttribute('href')
  const address = new URL(href!, 'http://127.0.0.1:15174')
  expect(address.searchParams.get('project')).toBe('1')
  expect(address.searchParams.get('conversation')).toBe(conversation.id)
  expect(JSON.parse(address.searchParams.get('material')!)).toMatchObject({
    mode: 'file', path: 'wattbot-nlp/src/dense/hybrid.py', lineno: 19, sourceKind: 'workspace',
  })
  await expect(answer.locator('table')).toBeVisible()
  expect(await answer.locator('.learning-prose--answer').evaluate(el => getComputedStyle(el).fontSize)).toBe('16px')
  await answer.getByRole('button', { name: '复制代码', exact: true }).click()
  await expect(answer.getByRole('button', { name: '复制代码', exact: true })).toContainText('已复制')
  expect(await page.evaluate(() => sessionStorage.getItem('fixture.copiedCode'))).toBe('query = "保存 结果"\nterms = query.split()\nprint(terms)\n')
  const hide = page.getByRole('button', { name: '隐藏材料', exact: true })
  if (await hide.isVisible()) await hide.click()
  for (const width of [900, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1050 })
    await expect(citation).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.screenshot({ path: resolve('../.ci/browser/reply-typography-1440.png') })
  await citation.click()
  const reader = page.locator('#workspace-materials')
  await expect(reader.locator('.monaco-editor')).toBeVisible()
  await expect(reader.getByRole('spinbutton', { name: '跳到行号', exact: true })).toHaveValue('19')
  await page.screenshot({ path: resolve('../.ci/browser/reply-source-1440.png') })
  // 旧回合没有探索元数据仍可链接，不依赖另一个附加功能提供跳转资格。
  await page.route(`**/api/projects/1/conversations/${conversation.id}/turns*`, async route => {
    const response = await route.fetch(), body = await response.json()
    for (const turn of body.items) delete turn.answer.exploration
    await route.fulfill({ response, json: body })
  })
  await page.reload()
  await expect(citation).toBeVisible()
  await citation.focus()
  await page.keyboard.press('Enter')
  await expect(reader.locator('.monaco-editor')).toBeVisible()
  const other = await context.newPage()
  await other.goto(address.href)
  await expect(other.locator('#workspace-materials .monaco-editor')).toBeVisible()
  await expect(other.locator('#workspace-materials').getByRole('spinbutton', { name: '跳到行号', exact: true })).toHaveValue('19')
  await other.close()
})
