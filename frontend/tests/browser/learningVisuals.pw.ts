import { expect, test, type Page } from '@playwright/test'
import { resolve } from 'node:path'

async function ready(page: Page, path: string) {
  await page.goto(path)
  await expect(page.locator('.wb-center textarea')).toBeEnabled()
  await expect.poll(() => new URL(page.url()).searchParams.get('conversation')).toBeTruthy()
  await expect(page.locator('.learning-article')).toHaveAttribute('data-reading-ready', 'true')
}

test.beforeEach(async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
})

test('图示真实加载、放大关闭不改阅读目标，图注可精确追问', async ({ page, request }) => {
  const errors: string[] = []
  page.on('pageerror', e => errors.push(e.message))
  await ready(page, '/learn/python-functions#example')
  const article = page.locator('.learning-article')
  const figure = article.locator('.knowledge-figure').first()
  const open = figure.getByRole('button', { name: /放大图示/ })
  await open.scrollIntoViewIfNeeded()
  await expect.poll(() => figure.locator('.knowledge-figure-open img').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(440)
  const target = await page.locator('.reading-context').innerText()
  const scroll = page.locator('[data-reading-scroll]')
  const position = await scroll.evaluate(el => el.scrollTop)
  await open.click()
  await expect(page.getByRole('dialog')).toBeVisible()
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog')).not.toBeVisible()
  await expect(open).toBeFocused()
  expect(await scroll.evaluate(el => el.scrollTop)).toBeCloseTo(position, 0)
  expect(await page.locator('.reading-context').innerText()).toBe(target)
  await page.screenshot({ path: resolve('..', '.ci/browser/learning-python-visuals.png') })

  const preview = await figure.locator('figcaption span').evaluate(span => {
    const range = document.createRange()
    range.selectNodeContents(span)
    const selection = getSelection()!
    selection.removeAllRanges(); selection.addRange(range)
    return selection.toString()
  })
  await article.getByRole('button', { name: '问选中段落', exact: true }).click()
  await expect(page.locator('.reading-context')).toContainText('已选择具体段落')
  const pending = page.waitForRequest(r => r.url().endsWith('/query/stream') && r.method() === 'POST')
  await page.locator('.wb-center textarea').fill('SQL 请解释这段图注')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const body = (await pending).postDataJSON()
  const topic = await (await request.get('/api/knowledge/topics/python-functions')).json()
  const range = body.reading_context.selection.ranges[0]
  const original = topic.sections.find((s: { id: string }) => s.id === range.section_id).content
  expect(original.slice(range.start_offset, range.end_offset)).toBe(preview)
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const turns = await (await request.get(`/api/projects/1/conversations/${body.conversation_id}/turns`)).json()
  const result = turns.items.find((t: { request_id: string }) => t.request_id === body.request_id)
  expect(result.answer.reading_status).toBe('ok')
  expect(errors).toEqual([])
})

test('缺图时正文与图意可读，重试后恢复；返回材料恢复位置', async ({ page }) => {
  await page.route('**/api/knowledge/assets/**', route => route.fulfill({ status: 404, body: 'missing fixture' }))
  await ready(page, '/learn/sql-database#relationships')
  const article = page.locator('.learning-article')
  const figure = article.locator('.knowledge-figure').first()
  await figure.scrollIntoViewIfNeeded()
  await expect(figure.getByText('图示暂未加载')).toBeVisible()
  await page.locator('[data-reading-scroll]').evaluate(el => { el.scrollTop += 8 })
  await expect(figure.getByText('图示暂未加载')).toBeVisible()
  await expect(figure).toContainText('101 和 102')
  await expect(article.getByRole('heading', { name: '一笔订单为什么只记商品编号' })).toBeVisible()
  await page.unroute('**/api/knowledge/assets/**')
  await figure.getByRole('button', { name: '重试图片' }).click()
  await expect.poll(() => figure.locator('.knowledge-figure-open img').evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(440)
  const scroll = page.locator('[data-reading-scroll]')
  await page.screenshot({ path: resolve('..', '.ci/browser/learning-sql-visuals.png') })
  const link = article.getByRole('link', { name: '关联查询', exact: true }).first()
  // 点击会先滚动到链接；返回应恢复离开时的位置，而非更早的图示位置。
  await link.scrollIntoViewIfNeeded()
  const position = await scroll.evaluate(async el => {
    await new Promise(requestAnimationFrame)
    return el.scrollTop
  })
  await link.click()
  await expect(page.locator('.learning-article h2')).toContainText('关联')
  await page.getByRole('button', { name: '返回上一处', exact: true }).click()
  await expect(page.locator('.learning-article h2')).toContainText('SQL 是什么')
  await expect.poll(() => scroll.evaluate((el, expected) => Math.abs(el.scrollTop - expected), position)).toBeLessThan(20)
})

test('窄栏与单区阅读中图示可见，状态样章有层级树和图文', async ({ page }) => {
  await ready(page, '/learn/state-lifecycle#ownership')
  const separator = page.getByRole('separator', { name: '调整右栏宽度', exact: true })
  for (const target of [360, 720, 480]) {
    let current = Number(await separator.getAttribute('aria-valuenow'))
    while (current !== target) {
      await separator.press(current < target ? 'ArrowLeft' : 'ArrowRight')
      current = Number(await separator.getAttribute('aria-valuenow'))
    }
    const image = page.locator('.knowledge-figure-open img').first()
    await image.scrollIntoViewIfNeeded()
    await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(440)
    expect(await image.evaluate(el => el.getBoundingClientRect().width)).toBeGreaterThan(250)
  }
  for (const width of [1440, 1280, 1024, 900]) {
    await page.setViewportSize({ width, height: 1000 })
    const image = page.locator('.knowledge-figure-open img').first()
    await image.scrollIntoViewIfNeeded()
    await expect.poll(() => image.evaluate((img: HTMLImageElement) => img.naturalWidth)).toBe(440)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.setViewportSize({ width: 1440, height: 1000 })
  await page.locator('.knowledge-figure').first().scrollIntoViewIfNeeded()
  await page.screenshot({ path: resolve('..', '.ci/browser/learning-state-visuals.png') })
})
