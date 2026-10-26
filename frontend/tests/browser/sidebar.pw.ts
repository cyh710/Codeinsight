import { expect, test, type Page } from '@playwright/test'
import { resolve } from 'node:path'

let projectId: number

test.beforeEach(async ({ page, request }) => {
  const source = await (await request.get('/api/projects/1')).json()
  const project = await (await request.post('/api/projects', { data: { root_path: source.root_path, name: '订单服务' } })).json()
  projectId = project.id
  await page.addInitScript(pid => localStorage.setItem('ci.projectId', String(pid)), projectId)
  await page.goto('/')
  await expect(page.locator('.wb-center textarea')).toBeEnabled()
  await expect(page.getByRole('button', { name: '选择项目', exact: true })).toContainText('订单服务')
})

test.afterEach(async ({ request }) => { await request.delete(`/api/projects/${projectId}`) })

async function removeDialog(page: Page) {
  await page.getByRole('button', { name: '项目操作', exact: true }).click()
  await page.getByRole('menuitem', { name: '移除项目…', exact: true }).click()
  return page.getByRole('dialog', { name: '移除项目', exact: true })
}

test('项目菜单、置顶分组与搜索筛选清楚可达，窄栏不溢出', async ({ page, request }) => {
  const pinned = await (await request.post(`/api/projects/${projectId}/conversations`)).json()
  await request.patch(`/api/projects/${projectId}/conversations/${pinned.id}`, { data: { title: '理解订单保存流程', pinned: true } })
  await page.reload()
  await expect(page.getByRole('region', { name: '置顶', exact: true })).toContainText('理解订单保存流程')
  await page.getByRole('button', { name: '对话筛选', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: '全部项目', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '对话筛选', exact: true }).click()
  await expect(page.getByRole('checkbox', { name: '全部项目', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '项目操作', exact: true }).click()
  await expect(page.getByRole('menuitem', { name: '复制项目路径', exact: true })).toBeVisible()
  await expect(page.getByRole('menuitem', { name: '重新定位源码', exact: true })).toBeVisible()
  await page.screenshot({ path: resolve('..', '.ci/browser/sidebar-project-menu.png'), animations: 'disabled' })
  await page.keyboard.press('Escape')
  await page.screenshot({ path: resolve('..', '.ci/browser/sidebar-conversations.png'), animations: 'disabled' })
  for (const width of [900, 1024, 1280, 1440]) {
    await page.setViewportSize({ width, height: 1000 })
    if (!(await page.getByRole('button', { name: '选择项目', exact: true }).isVisible())) await page.getByRole('button', { name: '项目与对话', exact: true }).click()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
  }
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
  await expect(page.getByTestId('tree-file').filter({ hasText: 'store.py' })).toBeVisible()
})

test('确认移除清理该项目缓存，其他项目和磁盘源码仍可用', async ({ page, request }) => {
  await page.evaluate(async pid => {
    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const req = indexedDB.open('codeinsight-workbench', 1)
      req.onsuccess = () => resolve(req.result); req.onerror = () => reject(req.error)
    })
    await new Promise<void>(resolve => {
      const tx = db.transaction('workspaces', 'readwrite')
      tx.objectStore('workspaces').put('删除范围内', `draft:${pid}:closed`)
      tx.objectStore('workspaces').put('另一个项目', 'draft:1:retained')
      tx.oncomplete = () => resolve()
    })
    db.close()
  }, projectId)
  let dialog = await removeDialog(page)
  await expect(dialog.getByRole('button', { name: '确认移除', exact: true })).toBeDisabled()
  await expect(dialog).toContainText('磁盘上的源码文件和内置教材会保留')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  expect((await request.get(`/api/projects/${projectId}`)).status()).toBe(200)
  dialog = await removeDialog(page)
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: '确认移除', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('button', { name: '选择项目', exact: true })).toContainText('example-main')
  expect((await request.get(`/api/projects/${projectId}`)).status()).toBe(404)
  expect((await request.get('/api/projects/1/code?path=store.py&start_line=1&end_line=6')).status()).toBe(200)
  const values = await page.evaluate(async pid => {
    const db = await new Promise<IDBDatabase>(resolve => { const req = indexedDB.open('codeinsight-workbench', 1); req.onsuccess = () => resolve(req.result) })
    const store = db.transaction('workspaces').objectStore('workspaces')
    const read = (key: string) => new Promise(resolve => { const req = store.get(key); req.onsuccess = () => resolve(req.result) })
    const result = await Promise.all([read(`draft:${pid}:closed`), read('draft:1:retained')]); db.close(); return result
  }, projectId)
  expect(values).toEqual([undefined, '另一个项目'])
})

test('移除失败保留当前项目和草稿；移除最后一个项目显示导入入口', async ({ page, request }) => {
  await page.locator('.wb-center textarea').fill('保留这份草稿')
  await page.route(`**/api/projects/${projectId}`, async route => {
    if (route.request().method() === 'DELETE') await route.fulfill({ status: 409, json: { error: { code: 'index_running', title: '项目正在处理任务', hint: '请等待回答结束', detail: '' } } })
    else await route.continue()
  })
  let dialog = await removeDialog(page)
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: '确认移除', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('项目正在处理任务')
  await expect(dialog.getByRole('alert')).toContainText('请等待回答结束')
  await dialog.getByRole('button', { name: '取消', exact: true }).click()
  await expect(page.locator('.wb-center textarea')).toHaveValue('保留这份草稿')
  await page.unroute(`**/api/projects/${projectId}`)
  const only = await (await request.get(`/api/projects/${projectId}`)).json()
  await page.route('**/api/projects', route => route.fulfill({ json: [only] }))
  await page.reload()
  dialog = await removeDialog(page)
  await dialog.getByRole('checkbox').check()
  await dialog.getByRole('button', { name: '确认移除', exact: true }).click()
  await expect(page.getByRole('button', { name: '导入第一个项目', exact: true })).toBeVisible()
  await expect(page.getByRole('button', { name: '新建对话', exact: true })).toBeDisabled()
})
