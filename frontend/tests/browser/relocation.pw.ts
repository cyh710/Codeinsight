import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

test.afterEach(async ({ page }) => {
  await page.unrouteAll({ behavior: 'wait' })
})

test('重新定位可取消，并保留当前对话、草稿与项目身份', async ({ page, request }) => {
  const project = await (await request.get('/api/projects/1')).json()
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => {
    localStorage.setItem('ci.projectId', '1')
    localStorage.setItem('ci.activeConversation.1', cid)
  }, conversation.id)
  let submitted = 0
  let selections = 0
  await page.route('**/api/projects/1', async route => {
    const response = await route.fetch()
    const detail = await response.json()
    await route.fulfill({ response, json: submitted ? detail : { ...detail, source_available: false, root_path: 'D:/old/missing-worktree' } })
  })
  await page.route('**/api/local/select-folder', async route => {
    selections++
    await route.fulfill({ json: { root_path: selections === 1 ? null : project.root_path } })
  })
  await page.route('**/api/projects/1/relocate', async route => {
    submitted++
    expect(route.request().postDataJSON()).toEqual({ root_path: project.root_path })
    await route.continue()
  })
  await page.goto('/')
  const input = page.locator('.wb-center textarea').first()
  await expect(input).toBeEnabled()
  await input.fill('重新定位后也要保留的草稿')
  await page.getByRole('button', { name: '重新定位', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '重新定位源码目录' })
  await expect(dialog.getByText('D:/old/missing-worktree')).toBeVisible()
  await expect(dialog).toHaveCSS('opacity', '1')
  await expect(page.locator('.modal-backdrop')).toHaveCSS('opacity', '1')
  await page.screenshot({ path: resolve('..', '.ci/browser/relocate-dialog.png') })
  await dialog.getByRole('button', { name: '选择文件夹', exact: true }).click()
  await expect(dialog.getByText('尚未选择新目录')).toBeVisible()
  expect(submitted).toBe(0)
  await dialog.getByRole('button', { name: '选择文件夹', exact: true }).click()
  await expect(dialog.getByText(project.root_path, { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  expect(submitted).toBe(0)
  await expect(input).toHaveValue('重新定位后也要保留的草稿')
  await page.getByRole('button', { name: '重新定位', exact: true }).click()
  await dialog.getByRole('button', { name: '选择文件夹', exact: true }).click()
  await dialog.getByRole('button', { name: '重新关联并重建索引', exact: true }).click()
  await expect(dialog).toBeHidden()
  await expect(page.getByRole('button', { name: '重新定位', exact: true })).toHaveCount(0)
  await expect(input).toHaveValue('重新定位后也要保留的草稿')
  expect(new URL(page.url()).searchParams.get('conversation')).toBe(conversation.id)
  expect(submitted).toBe(1)
  await page.reload()
  await expect(input).toHaveValue('重新定位后也要保留的草稿')
  expect(new URL(page.url()).searchParams.get('conversation')).toBe(conversation.id)
})
