import { expect, test } from '@playwright/test'

for (const [width, rightWidth] of [[1440, 480], [1280, 720], [1100, 480], [1024, 480], [900, 480]]) {
  test(`${width}px 材料关闭按钮不误关左栏，项目与对话保持`, async ({ page, request }) => {
    const conversation = await (await request.post('/api/projects/1/conversations')).json()
    await page.setViewportSize({ width, height: 900 })
    await page.addInitScript(({ cid, rightWidth }) => {
      localStorage.setItem('ci.projectId', '1')
      localStorage.setItem('ci.activeConversation.1', cid)
      localStorage.setItem('ci.layout.v1', JSON.stringify({ left: true, right: false, leftWidth: 256, rightWidth, sidebar: 'conversations' }))
    }, { cid: conversation.id, rightWidth })
    await page.goto('/')
    await expect(page.locator('.wb-center textarea')).toBeEnabled()
    const left = page.locator('#workspace-left')
    const row = left.locator(`[data-conversation-id="${conversation.id}"]`)
    await expect(row).toBeVisible()
    const selector = left.getByRole('button', { name: '选择项目', exact: true })
    const selectedProject = await selector.innerText()
    await page.locator('[data-material-toggle]').click()
    const close = page.getByRole('button', { name: '隐藏材料区域' })
    await expect(close).toBeVisible()
    await expect.poll(() => page.locator('#workspace-materials').evaluate(element => element.getAnimations().filter(animation => animation.playState === 'running').length)).toBe(0)
    const bounds = (await close.boundingBox())!
    expect(await page.locator('.workbench-header').evaluate(element => element.getBoundingClientRect().height)).toBe(42)
    expect(await page.getByRole('separator', { name: '调整右栏宽度' }).evaluate(element => element.getBoundingClientRect().width)).toBe(1)
    const point = { x: bounds.x + bounds.width / 2, y: bounds.y + bounds.height / 2 }
    const target = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('button')?.getAttribute('aria-label'), point)
    expect(target).toBe('隐藏材料区域')
    if (width >= 1100) {
      const handle = (await page.getByRole('separator', { name: '调整右栏宽度' }).boundingBox())!
      const hit = await page.evaluate(({ x, y }) => document.elementFromPoint(x, y)?.closest('[role="separator"]')?.getAttribute('aria-label'), { x: handle.x + handle.width / 2, y: handle.y + handle.height / 2 })
      expect(hit).toBe('调整右栏宽度')
    }
    await page.mouse.click(point.x, point.y)
    await expect(page.locator('[data-material-toggle]')).toHaveAttribute('aria-expanded', 'false')
    await expect(page.getByRole('button', { name: '项目与对话', exact: true })).toHaveAttribute('aria-expanded', 'true')
    await expect(left).toBeVisible()
    await expect(row).toBeVisible()
    await expect(selector).toHaveText(selectedProject!)
    expect(new URL(page.url()).searchParams.get('conversation')).toBe(conversation.id)
    await page.locator('[data-material-toggle]').click()
    await page.locator('[data-material-toggle]').click()
    await expect(row).toBeVisible()
  })
}
