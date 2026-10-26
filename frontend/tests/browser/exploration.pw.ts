import { expect, test, type Page } from '@playwright/test'
import { resolve } from 'node:path'

async function ready(page: Page) {
  await page.goto('/')
  await expect(page.locator('.wb-center textarea')).toBeEnabled()
  await expect(page.getByRole('navigation', { name: '项目探索入口' })).toBeVisible()
}
async function explore(page: Page) {
  await ready(page)
  await page.getByRole('navigation', { name: '项目探索入口' }).getByRole('button').first().click()
  await expect(page.getByRole('navigation', { name: '接着探索' }).last()).toBeVisible()
}
test.beforeEach(async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
})

test('真实项目导览、编号来源、流程与直接追问保留草稿和关联', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await ready(page)
  await expect(page.locator('.project-guide-intro')).toContainText('SQLite')
  await expect(page.locator('.project-guide')).not.toContainText('混合检索')
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
  await page.getByTestId('tree-file').filter({ hasText: 'store.py' }).click()
  await expect(page.locator('.reading-context')).toContainText('store.py')
  const original = await page.locator('.reading-context').innerText()
  await page.locator('.wb-center textarea').fill('我的草稿还没有写完😀')
  await page.screenshot({ path: resolve('..', '.ci/browser/exploration-guide.png') })
  await page.getByRole('navigation', { name: '项目探索入口' }).getByRole('button').first().click()
  const next = page.getByRole('navigation', { name: '接着探索' }).last()
  // 首次回答还包含本地中文分词词典的冷启动，不以默认五秒判定功能失败。
  await expect(next).toBeVisible({ timeout: 15000 })
  await expect(page.locator('.wb-center textarea')).toHaveValue('我的草稿还没有写完😀')
  expect(await page.locator('.reading-context').innerText()).toBe(original)
  await expect(page.getByRole('button', { name: '[1]', exact: true })).toBeVisible()
  await expect(page.getByRole('region', { name: '局部流程' })).toContainText('包含')
  await page.screenshot({ path: resolve('..', '.ci/browser/exploration-answer.png') })
  const pending = page.waitForRequest(r => r.url().endsWith('/query/stream') && r.method() === 'POST')
  await next.getByRole('button', { name: /如果不提交会怎样/ }).click()
  expect((await pending).postDataJSON().action_origin.kind).toBe('answer')
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  await expect(page.locator('.wb-center textarea')).toHaveValue('我的草稿还没有写完😀')
  expect(await page.locator('.reading-context').innerText()).toBe(original)
  await page.getByRole('button', { name: '[1]', exact: true }).last().click()
  await expect(page.locator('#workspace-materials')).toContainText('store.py')
  expect(errors).toEqual([])
})

test('局部知识解读、全文、来源回合与刷新恢复', async ({ page }) => {
  await explore(page)
  const cid = new URL(page.url()).searchParams.get('conversation')!
  await page.getByRole('navigation', { name: '接着探索' }).last().getByRole('button', { name: /理解事务的提交与回滚/ }).click()
  const contextual = page.locator('.context-reading')
  await expect(contextual.getByRole('button', { name: '阅读全文', exact: true })).toBeVisible()
  await expect(contextual).toContainText('本回合已解释的要点')
  // 有效的新知识动作可以指向尚未注入正文的章节，仍应从已保存动作恢复。
  await page.route('**/api/projects/1/conversations/*/turns/*', async route => {
    const response = await route.fetch()
    const turn = await response.json()
    await route.fulfill({ response, json: { ...turn, answer: { ...turn.answer, knowledge_sources: [], learning_targets: [] } } })
  })
  await page.reload()
  await expect(page.locator('.context-reading')).toBeVisible()
  await expect(page.locator('.context-reading')).toContainText('对应的项目位置')
  await page.screenshot({ path: resolve('..', '.ci/browser/exploration-context.png') })
  await page.locator('.context-reading').getByRole('button', { name: '阅读全文', exact: true }).click()
  await expect(page.locator('.learning-article')).toBeVisible()
  await page.getByRole('button', { name: '返回上一处', exact: true }).click()
  await expect(page.locator('.context-reading')).toBeVisible()
  await page.getByRole('button', { name: '新建对话', exact: true }).click()
  await expect(page.locator('.context-reading')).toHaveCount(0)
  await page.locator(`[data-conversation-id="${cid}"]`).getByRole('button').first().click()
  await expect(page.locator('.context-reading')).toBeVisible()
  await page.locator('.exploration-trail summary').click()
  await expect(page.locator('.exploration-trail')).toContainText('写入先开启事务')
  await page.getByRole('button', { name: '清空脉络，保留对话' }).click()
  await expect(page.locator('.exploration-trail')).toHaveCount(0)
  await expect(page.getByRole('navigation', { name: '接着探索' })).toBeVisible()
})

test('旧索引动作禁用，导览失败可重试，窄窗口仍可探索', async ({ page }) => {
  await page.route('**/api/projects/1/overview', route => route.fulfill({ status: 503, contentType: 'application/json', body: JSON.stringify({ error: { code: 'internal_error', title: '离线失败', hint: '重试', detail: '' } }) }))
  await page.goto('/')
  await expect(page.locator('.project-guide')).toContainText('项目导览读取失败')
  await page.unroute('**/api/projects/1/overview')
  await page.locator('.project-guide').getByRole('button', { name: '重新读取' }).click()
  await expect(page.getByRole('navigation', { name: '项目探索入口' })).toBeVisible()
  for (const width of [900, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.getByRole('navigation', { name: '项目探索入口' }).getByRole('button').first().click()
  await expect(page.getByRole('navigation', { name: '接着探索' })).toBeVisible()
  await page.route('**/api/projects/1', async route => {
    const response = await route.fetch()
    const json = await response.json()
    await route.fulfill({ response, json: { ...json, index_epoch: json.index_epoch + 1 } })
  })
  await page.reload()
  await expect(page.getByRole('navigation', { name: '接着探索' })).toContainText('旧索引')
  await expect(page.getByRole('navigation', { name: '接着探索' }).getByRole('button').first()).toBeDisabled()
})
