import { expect, test, type Page } from '@playwright/test'

async function ready(page: Page) {
  await page.goto('/learn/sql-database')
  await expect(page.locator('.wb-center textarea')).toBeEnabled()
  await expect(page.locator('.learning-article [data-source-map]').first()).toBeVisible()
  await expect.poll(() => page.locator('#workspace-materials').evaluate(e => e.getBoundingClientRect().width)).toBe(480)
}

test.beforeEach(async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
})

test('侧栏有中间过渡帧，快速反向开关保留阅读，拖动不滞后', async ({ page }) => {
  await ready(page)
  const panel = page.locator('#workspace-materials')
  const scroll = panel.locator('[data-reading-scroll]')
  await page.locator('.wb-center textarea').fill('动画不能清空这份草稿')
  await scroll.evaluate(e => { e.scrollTop = 450 })
  // 在浏览器内暂停真实宽度过渡并检查中点，避免跨进程调用延迟错过整个动画。
  const middle = await panel.evaluate(e => new Promise<{ width: number; inert: boolean }>(resolve => {
    const sample = (event: Event) => {
      if ((event as TransitionEvent).propertyName !== 'width' || event.target !== e) return
      e.removeEventListener('transitionrun', sample)
      const animation = e.getAnimations().find(a => (a as CSSTransition).transitionProperty === 'width')!
      animation.pause()
      animation.currentTime = Number(animation.effect!.getTiming().duration) / 2
      requestAnimationFrame(() => {
        const result = { width: e.getBoundingClientRect().width, inert: (e as HTMLElement).inert }
        animation.play()
        resolve(result)
      })
    }
    e.addEventListener('transitionrun', sample)
    document.querySelector<HTMLButtonElement>('[data-material-toggle]')!.click()
  }))
  expect(middle.width).toBeGreaterThan(0)
  expect(middle.width).toBeLessThan(480)
  expect(middle.inert).toBe(true)
  await page.getByRole('button', { name: '打开材料', exact: true }).click()
  await expect.poll(() => panel.evaluate(e => e.getBoundingClientRect().width)).toBe(480)
  await expect.poll(() => scroll.evaluate(e => e.scrollTop)).toBe(450)
  await expect(page.locator('.wb-center textarea')).toHaveValue('动画不能清空这份草稿')
  const separator = page.getByRole('separator', { name: '调整右栏宽度', exact: true })
  const box = (await separator.boundingBox())!
  await page.mouse.move(box.x + 3, box.y + 160); await page.mouse.down()
  await page.mouse.move(box.x - 77, box.y + 160)
  await expect(page.locator('.wb-app')).toHaveAttribute('data-resizing', 'true')
  expect(await panel.evaluate(e => getComputedStyle(e).transitionDuration)).toBe('0s')
  expect(await panel.evaluate(e => e.getBoundingClientRect().width)).toBe(560)
  await page.mouse.up()
  await expect(page.locator('.wb-app')).not.toHaveAttribute('data-resizing')
})

test('菜单有进出动画，退出时不可操作，快速重开取消旧退出', async ({ page }) => {
  await ready(page)
  const trigger = page.getByRole('button', { name: '材料操作', exact: true })
  await trigger.click()
  await expect(page.getByRole('menu', { name: '材料操作' })).toBeVisible()
  expect(await page.locator('.wb-action-menu').evaluate(e => getComputedStyle(e).animationName)).toBe('wb-menu-in')
  await page.keyboard.press('Escape')
  await expect(trigger).toBeFocused()
  await expect(page.getByRole('menu', { name: '材料操作' })).toHaveCount(0)
  await trigger.click()
  await expect(page.getByRole('menu', { name: '材料操作' })).toBeVisible()
  await expect(page.getByRole('menuitemcheckbox').first()).toBeFocused()
  await page.keyboard.press('Escape')
  await expect(page.locator('.wb-action-menu')).toHaveCount(0)
})

test('运行时开启减少动态效果后面板和菜单立即关闭，弹窗仍能使用', async ({ page }) => {
  await ready(page)
  await page.emulateMedia({ reducedMotion: 'reduce' })
  const trigger = page.getByRole('button', { name: '材料操作', exact: true })
  await trigger.click()
  expect(await page.locator('.wb-action-menu').evaluate(e => getComputedStyle(e).animationName)).toBe('none')
  await page.keyboard.press('Escape')
  expect(await page.locator('.wb-action-menu').count()).toBe(0)
  await page.getByRole('button', { name: '隐藏材料', exact: true }).click()
  await expect(page.locator('#workspace-materials')).toBeHidden()
  expect(await page.locator('#workspace-materials').getAttribute('data-panel-state')).toBe('closed')
  await page.getByRole('button', { name: '导入项目并建索引', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '导入项目并建索引' })
  await expect(dialog).toBeVisible()
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  expect(await page.getByRole('dialog').count()).toBe(0)
})
