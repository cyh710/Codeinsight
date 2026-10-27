import { expect, test, type Page, type APIRequestContext } from '@playwright/test'
import { resolve } from 'node:path'

test.afterEach(async ({ page }) => { await page.unrouteAll({ behavior: 'wait' }) })
const input = (page: Page) => page.locator('.wb-center textarea').first()
const notice = (page: Page) => page.getByTestId('project-index-status')

async function setup(page: Page, request: APIRequestContext) {
  const project = await (await request.get('/api/projects/2')).json()
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => {
    localStorage.setItem('ci.projectId', '1')
    localStorage.setItem('ci.activeConversation.1', cid)
  }, conversation.id)
  const state = { phase: 'ready', posts: 0, failFirst: false, delay: false, accept: () => {}, requests: [] as unknown[] }
  await page.route('**/api/local/select-folder', route => route.fulfill({ json: { root_path: project.root_path } }))
  await page.route('**/api/projects/2', route => state.phase === 'offline'
    ? route.fulfill({ status: 503, json: { error: { code: 'internal_error', title: '连接暂时中断', hint: '请恢复检查。', detail: '' } } })
    : route.fulfill({ json: { ...project, status: state.phase, index_error: state.phase === 'failed' ? '仓库读取失败，请检查目录。' : null } }))
  await page.route('**/api/projects', async route => {
    if (route.request().method() !== 'POST') { await route.continue(); return }
    state.posts++
    state.requests.push(route.request().postDataJSON())
    if (state.delay) await new Promise<void>(resolve => { state.accept = resolve })
    state.phase = state.failFirst ? state.posts === 1 ? 'failed' : 'ready' : 'indexing'
    await route.fulfill({ status: 202, json: { ...project, status: 'indexing' } })
  })
  await page.goto('/')
  await expect(input(page)).toBeEnabled()
  return { state, project }
}

async function submit(page: Page, ref?: string) {
  await page.getByRole('button', { name: '导入项目并建索引', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '导入项目并建索引' })
  await dialog.getByRole('button', { name: '选择文件夹', exact: true }).click()
  if (ref) {
    await dialog.getByText('更多选项', { exact: true }).click()
    await dialog.getByPlaceholder('缺省 = 当前 HEAD').fill(ref)
  }
  await dialog.getByRole('button', { name: '导入并建索引', exact: true }).click()
  return dialog
}

test('提交有反馈，后台索引可刷新恢复，状态检查断线不重复提交', async ({ page, request }) => {
  const { state, project } = await setup(page, request)
  state.delay = true
  try {
    const dialog = await submit(page)
    await expect(dialog.getByRole('status').filter({ hasText: '正在提交导入请求' })).toBeVisible()
    await expect(dialog.getByRole('button', { name: '提交中…', exact: true })).toBeDisabled()
    await expect.poll(() => state.posts).toBe(1)
    state.accept(); state.delay = false
    await expect(dialog).toBeHidden()
    await expect(notice(page)).toContainText(`正在为 ${project.name} 建立索引`)
    await expect(input(page)).toBeEnabled()
    await input(page).fill('索引等待期间保留的草稿')
    await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
    await expect(page.getByLabel('正在准备项目文件')).toBeVisible()
    await expect(page.getByText('没有匹配的文件。', { exact: true })).toHaveCount(0)
    await expect(notice(page)).toContainText('已等待')
    await page.getByRole('button', { name: '项目与对话', exact: true }).click()
    await expect(page.locator('#workspace-left')).toBeHidden()
    await expect(notice(page)).toBeVisible()
    await page.screenshot({ path: resolve('..', '.ci/browser/project-indexing.png') })
    await page.reload()
    await expect(notice(page)).toContainText('建立索引')
    await expect(input(page)).toHaveValue('索引等待期间保留的草稿')
    expect(state.posts).toBe(1)
    state.phase = 'offline'
    await expect(notice(page)).toContainText('状态暂不可读')
    await expect(page.locator('.sidebar-project-select')).not.toContainText('索引中')
    expect(state.posts).toBe(1)
    state.phase = 'ready'
    // 网络恢复后由原检查自动继续，不依赖用户再点一次，也不重复导入。
    await expect(notice(page)).toContainText('索引已就绪')
    await expect(notice(page)).toContainText(`${project.files.toLocaleString()} 个文件`)
    await expect(notice(page)).toContainText(`${project.symbols.toLocaleString()} 个符号`)
    await notice(page).getByRole('button', { name: '查看文件' }).click()
    await expect(page.locator('#workspace-left')).toBeVisible()
    await expect.poll(() => page.locator('#workspace-left').evaluate(element => element.getAnimations().filter(animation => animation.playState === 'running').length)).toBe(0)
    await expect(page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true })).toHaveAttribute('aria-pressed', 'true')
    await expect(input(page)).toHaveValue('索引等待期间保留的草稿')
    await page.screenshot({ path: resolve('..', '.ci/browser/project-indexed.png') })
    await notice(page).getByRole('button', { name: '关闭索引提示' }).click()
    await expect(notice(page)).toBeHidden()
  } finally { state.accept() }
})

test('真正失败后明确说明原因，只有用户点击才按原 ref 重试', async ({ page, request }) => {
  const { state } = await setup(page, request)
  state.failFirst = true
  await submit(page, 'agent-v1')
  await expect(notice(page)).toContainText('索引未完成')
  await expect(notice(page)).toContainText('仓库读取失败')
  expect(state.posts).toBe(1)
  await notice(page).getByRole('button', { name: '重试索引', exact: true }).click()
  await expect(notice(page)).toContainText('索引已就绪')
  expect(state.posts).toBe(2)
  expect(state.requests[1]).toEqual(state.requests[0])
  expect(state.requests[1]).toMatchObject({ ref: 'agent-v1' })
})

test('切到其他项目后，后台完成不抢走草稿或当前项目', async ({ page, request }) => {
  const { state, project } = await setup(page, request)
  await submit(page)
  await expect(notice(page)).toContainText('建立索引')
  await expect(input(page)).toBeEnabled()
  await page.getByRole('button', { name: '选择项目', exact: true }).click()
  await page.getByRole('option').filter({ hasText: 'example-main' }).click()
  await expect(input(page)).toBeEnabled()
  await input(page).fill('另一个项目的草稿')
  state.phase = 'ready'
  await expect(notice(page)).toContainText(`${project.name} 索引已就绪`)
  expect(new URL(page.url()).searchParams.get('project')).toBe('1')
  await expect(input(page)).toHaveValue('另一个项目的草稿')
  await expect(notice(page).getByRole('button', { name: '返回项目' })).toBeVisible()
})
