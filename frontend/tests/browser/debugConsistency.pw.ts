import { expect, test } from '@playwright/test'

test.beforeEach(async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => { localStorage.setItem('ci.projectId', '1'); localStorage.setItem('ci.activeConversation.1', cid) }, conversation.id)
})

test('新建对话的迟到响应不能切回旧项目或覆盖新项目草稿', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.wb-center textarea')).toBeEnabled()
  let release!: () => void, observed!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  const started = new Promise<void>(resolve => { observed = resolve })
  await page.route('**/api/projects/1/conversations', async route => {
    const response = await route.fetch()
    observed(); await gate
    await route.fulfill({ response })
  })
  await page.getByRole('button', { name: '新建对话', exact: true }).click()
  await started
  await page.evaluate(async () => { const { projectStore } = await import('/src/store/projectStore.ts' + ''); await projectStore.getState().selectProject(2) })
  await expect(page.locator('.wb-center textarea')).toBeEnabled()
  await page.locator('.wb-center textarea').fill('项目二的独立草稿')
  const completed = page.waitForResponse(r => r.url().endsWith('/projects/1/conversations') && r.request().method() === 'POST')
  release(); await completed
  await expect.poll(() => page.evaluate(async () => { const { chatStore } = await import('/src/store/chatStore.ts' + ''); return chatStore.getState().projectId })).toBe(2)
  await expect(page.locator('.wb-center textarea')).toHaveValue('项目二的独立草稿')
  expect(new URL(page.url()).searchParams.get('project')).toBe('2')
})

test('工作区首次补哈希不新增浏览器历史，一次返回即离开文件', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.wb-center textarea')).toBeEnabled()
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
  const before = await page.evaluate(() => history.length)
  await page.getByTestId('tree-file').filter({ hasText: 'store.py' }).click()
  await expect(page.locator('#workspace-materials .monaco-editor')).toBeVisible()
  await expect.poll(() => { const material = new URL(page.url()).searchParams.get('material'); return material ? Boolean(JSON.parse(material).contentSha) : false }).toBe(true)
  expect(await page.evaluate(() => history.length)).toBe(before + 1)
  await page.goBack()
  await expect.poll(() => { const material = new URL(page.url()).searchParams.get('material'); return material ? JSON.parse(material).mode : null }).toBe('evidence')
})
