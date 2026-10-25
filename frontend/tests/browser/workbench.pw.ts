import { expect, test, type Page } from '@playwright/test'
import { resolve } from 'node:path'

const input = (page: Page) => page.locator('.wb-center textarea').first()
const reader = (page: Page) => page.locator('#workspace-materials')
async function ready(page: Page, path = '/') {
  await page.goto(path)
  await expect(input(page)).toBeEnabled()
  await expect.poll(() => new URL(page.url()).searchParams.get('conversation')).toBeTruthy()
}
test.beforeEach(async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
})

test('布局调宽、阅读展开、隐藏重开和草稿刷新恢复', async ({ page }) => {
  const errors: string[] = []; page.on('pageerror', e => errors.push(e.message))
  await ready(page, '/learn/sql-database')
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  await input(page).fill('这份草稿在切视图和刷新后都应该保留\n还有第二行')
  const nav = page.getByRole('navigation', { name: '工作台视图' })
  await nav.getByRole('button', { name: '关系图', exact: true }).click()
  await nav.getByRole('button', { name: '对话', exact: true }).click()
  await expect(input(page)).toHaveValue(/这份草稿/)
  const separator = page.getByRole('separator', { name: '调整右栏宽度' })
  const before = await reader(page).evaluate(e => e.getBoundingClientRect().width)
  await separator.focus(); await page.keyboard.press('ArrowLeft')
  await expect.poll(() => reader(page).evaluate(e => e.getBoundingClientRect().width)).toBe(before + 20)
  const handle = (await separator.boundingBox())!
  await page.mouse.move(handle.x + 3, handle.y + 30); await page.mouse.down()
  await page.mouse.move(handle.x - 27, handle.y + 30); await page.mouse.up()
  await expect.poll(() => reader(page).evaluate(e => e.getBoundingClientRect().width)).toBe(before + 50)
  const scroll = reader(page).locator('[data-reading-scroll]')
  await scroll.evaluate(e => { e.scrollTop = 400 })
  await expect.poll(() => scroll.evaluate(e => e.scrollTop)).toBe(400)
  await reader(page).getByRole('button', { name: '隐藏材料区域' }).click()
  await expect(reader(page)).toBeHidden()
  await page.getByRole('button', { name: '打开材料', exact: true }).click()
  await expect.poll(() => scroll.evaluate(e => e.scrollTop)).toBe(400)
  await reader(page).getByRole('button', { name: '展开阅读', exact: true }).click()
  await expect(page.locator('.wb-center')).toBeHidden()
  await reader(page).getByRole('button', { name: '回到对话', exact: true }).click()
  await expect(input(page)).toBeVisible()
  await expect(page.getByText('正在保存工作区…', { exact: true })).toHaveCount(0)
  await page.reload(); await expect(input(page)).toBeEnabled()
  await expect(input(page)).toHaveValue(/这份草稿/)
  await expect.poll(() => scroll.evaluate(e => e.scrollTop)).toBe(400)
  await expect.poll(() => reader(page).evaluate(e => e.getBoundingClientRect().width)).toBe(before + 50)
  await page.screenshot({ path: resolve('..', '.ci/browser/workbench-1440.png'), fullPage: true })
  for (const width of [1280, 1024, 900]) {
    await page.setViewportSize({ width, height: 1000 })
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
    if (width < 1100) {
      await expect(reader(page)).toBeVisible(); await expect(page.locator('.wb-center')).toBeHidden()
      await reader(page).getByRole('button', { name: '回到对话', exact: true }).click()
      await expect(input(page)).toBeVisible()
      await page.getByRole('button', { name: '打开材料', exact: true }).click()
    }
  }
  await page.screenshot({ path: resolve('..', '.ci/browser/workbench-900.png'), fullPage: true })
  expect(errors).toEqual([])
})

test('每会话保存自己的页签、草稿和阅读目标，支持关闭重开', async ({ page }) => {
  await ready(page, '/learn/sql-database')
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  const first = new URL(page.url()).searchParams.get('conversation')!
  await input(page).fill('只属于 SQL 会话的草稿')
  await page.getByRole('button', { name: '新建对话', exact: false }).click()
  await expect(input(page)).toHaveValue('')
  await expect.poll(() => new URL(page.url()).searchParams.get('conversation')).not.toBe(first)
  const second = new URL(page.url()).searchParams.get('conversation')!
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
  await page.getByTestId('tree-file').filter({ hasText: 'store.py' }).click()
  await expect(reader(page).getByText('只读源码窗口', { exact: false })).toBeVisible()
  await input(page).fill('只属于代码会话的草稿')
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '对话', exact: true }).click()
  await page.locator(`[data-conversation-id="${first}"]`).getByRole('button').first().click()
  await expect(input(page)).toHaveValue('只属于 SQL 会话的草稿')
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  const tab = reader(page).getByRole('tab', { name: 'SQL 是什么：数据库、表、行与列', exact: true })
  await reader(page).getByRole('button', { name: '关闭页签 SQL 是什么：数据库、表、行与列', exact: true }).click()
  await expect(tab).toHaveCount(0)
  await reader(page).getByRole('button', { name: '材料操作', exact: true }).click()
  await page.getByRole('menuitem', { name: '重新打开已关闭页签', exact: true }).click()
  await expect(tab).toBeVisible()
  await page.locator(`[data-conversation-id="${second}"]`).getByRole('button').first().click()
  await expect(input(page)).toHaveValue('只属于代码会话的草稿')
  await expect(tab).toHaveCount(0)
  await expect(page.locator('.reading-context')).toContainText('store.py')
})

test('教材连续选区由服务端重读，取消后切材料不恢复关联', async ({ page, request }) => {
  await ready(page, '/learn/sql-database')
  const topic = await (await request.get('/api/knowledge/topics/sql-database')).json()
  await expect(reader(page).locator('[data-source-map]').first()).toBeVisible()
  const chosen = await reader(page).evaluate(root => {
    const sections = [...root.querySelectorAll<HTMLElement>('[data-section-id]')].filter(e => e.querySelector('[data-source-map]'))
    const begin = sections[0].querySelector<HTMLElement>('[data-source-map]')!
    const end = sections[1].querySelector<HTMLElement>('[data-source-map]')!
    const range = document.createRange(); range.setStart(begin.firstChild!, 0); range.setEnd(end.firstChild!, end.firstChild!.textContent!.length)
    const selection = getSelection()!; selection.removeAllRanges(); selection.addRange(range)
    return selection.toString()
  })
  await reader(page).getByRole('button', { name: '问选中段落', exact: true }).click()
  await expect(page.locator('.reading-context')).toContainText('已固定')
  const pending = page.waitForRequest(r => r.url().endsWith('/query/stream') && r.method() === 'POST')
  await input(page).fill('SQL 这里是什么意思'); await page.getByRole('button', { name: '发送', exact: true }).click()
  const body = (await pending).postDataJSON()
  expect(body.reading_context.preview).toBe(chosen)
  expect(body.reading_context.selection.ranges).toHaveLength(2)
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const turns = await (await request.get(`/api/projects/1/conversations/${body.conversation_id}/turns`)).json()
  const final = turns.items.find((t: { request_id: string }) => t.request_id === body.request_id)
  expect(final.answer.reading_status).toBe('ok')
  for (const range of body.reading_context.selection.ranges) {
    const source = topic.sections.find((s: { id: string }) => s.id === range.section_id).content
    expect(final.answer.knowledge_sources.some((hit: { snippet: string }) => hit.snippet === source.slice(range.start_offset, range.end_offset))).toBe(true)
  }
  await page.getByRole('button', { name: '取消关联', exact: true }).click()
  await reader(page).locator('[data-reading-scroll]').evaluate(e => { e.scrollTop = 900 })
  await reader(page).getByRole('button', { name: '教材目录', exact: true }).click()
  await expect(page.locator('.reading-context')).toContainText('未关联')
})

test('代码选区保留源码版本并通过服务端校验', async ({ page, request }) => {
  await ready(page)
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
  await page.getByTestId('tree-file').filter({ hasText: 'store.py' }).click()
  await expect(reader(page).locator('.monaco-editor')).toBeVisible()
  await reader(page).locator('.monaco-editor .view-lines').click()
  await page.keyboard.press('Control+Home'); await page.keyboard.press('Control+Shift+End')
  await reader(page).getByRole('button', { name: '问选中代码', exact: true }).click()
  await expect(page.locator('.reading-context')).toContainText('已固定')
  const pending = page.waitForRequest(r => r.url().endsWith('/query/stream') && r.method() === 'POST')
  await input(page).fill('这里是什么意思'); await page.getByRole('button', { name: '发送', exact: true }).click()
  const body = (await pending).postDataJSON()
  expect(body.reading_context.selection.start_column).toBe(1)
  expect(body.reading_context.head_commit).toBeTruthy(); expect(body.reading_context.content_sha256).toBeTruthy()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const turns = await (await request.get(`/api/projects/1/conversations/${body.conversation_id}/turns`)).json()
  expect(turns.items.find((t: { request_id: string }) => t.request_id === body.request_id).answer.reading_status).toBe('ok')
})

test('跨项目切换时原回答继续，结果与来源不会串台', async ({ page, request }) => {
  await request.post('/api/projects/2/conversations')
  await ready(page)
  const first = new URL(page.url()).searchParams.get('conversation')!
  await input(page).fill('SQL 是什么 __fixture_slow__'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '选择项目', exact: true }).click(); await page.getByRole('option', { name: /example-other/ }).click()
  await expect(input(page)).toBeEnabled(); await expect(input(page)).toHaveValue('')
  await input(page).fill('SQL 是什么 第二个项目'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const second = new URL(page.url()).searchParams.get('conversation')!
  await expect.poll(async () => (await (await request.get(`/api/projects/1/conversations/${first}/turns`)).json()).items[0]?.status).toBe('completed')
  const a = await (await request.get(`/api/projects/1/conversations/${first}/turns`)).json()
  const b = await (await request.get(`/api/projects/2/conversations/${second}/turns`)).json()
  expect(a.items[0].question).toContain('__fixture_slow__'); expect(b.items[0].question).toContain('第二个项目')
  await expect(page.locator('.wb-center')).not.toContainText('__fixture_slow__')
})

test('会话命名、置顶、内容搜索和归档恢复', async ({ page }) => {
  await ready(page)
  const cid = new URL(page.url()).searchParams.get('conversation')!
  await input(page).fill('SQL 是什么'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const row = page.locator(`[data-conversation-id="${cid}"]`)
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: /对话操作/ }).click()
  await page.getByRole('menuitem', { name: '改名', exact: true }).click()
  await row.getByRole('textbox', { name: '对话名称' }).fill('我的数据库学习')
  await row.getByRole('button', { name: '保存', exact: true }).click()
  await expect(row).toContainText('我的数据库学习')
  await row.getByRole('button', { name: /对话操作/ }).click()
  await page.getByRole('menuitem', { name: '置顶', exact: true }).click()
  await expect(row).toContainText('◆')
  await page.getByRole('textbox', { name: '搜索历史对话' }).fill('查询和管理')
  await expect(row).toBeVisible()
  await expect(row).toContainText('查询和管理')
  await row.getByRole('button', { name: /对话操作/ }).click()
  await page.getByRole('menuitem', { name: '归档', exact: true }).click()
  await expect(row).toHaveCount(0)
  await page.getByRole('checkbox', { name: '已归档', exact: true }).check()
  await expect(row).toBeVisible()
  await row.getByRole('button', { name: /对话操作/ }).click()
  await page.getByRole('menuitem', { name: '恢复归档', exact: true }).click()
  await expect(row).toHaveCount(0)
  await page.getByRole('checkbox', { name: '已归档', exact: true }).uncheck()
  await expect(row).toBeVisible()
  await page.getByRole('textbox', { name: '搜索历史对话' }).fill('不存在的随机词__no_match__')
  await expect(page.getByText('没有找到匹配的对话。', { exact: true })).toBeVisible()
})

test('第二标签页只读取运行状态，不重复发起回答，并能停止原任务', async ({ page, context, request }) => {
  await ready(page)
  const cid = new URL(page.url()).searchParams.get('conversation')!
  await input(page).fill('SQL 是什么 __fixture_cancel__'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toBeVisible()
  await expect.poll(async () => (await (await request.get(`/api/projects/1/conversations/${cid}/turns`)).json()).items[0]?.task_id).toBeTruthy()
  const peer = await context.newPage()
  try {
    await ready(peer, page.url())
    await expect(peer.getByRole('button', { name: '停止生成', exact: true })).toBeVisible()
    const conflict = await request.post('/api/query/stream', { data: { project_id: 1, conversation_id: cid, request_id: 'other-tab-request', question: '不该启动第二次生成' } })
    expect(conflict.status()).toBe(409)
    await peer.getByRole('button', { name: '停止生成', exact: true }).click()
    await expect.poll(async () => (await (await request.get(`/api/projects/1/conversations/${cid}/turns`)).json()).items[0].status).toBe('interrupted')
    const turns = await (await request.get(`/api/projects/1/conversations/${cid}/turns`)).json()
    expect(turns.items).toHaveLength(1)
    expect(turns.items[0].answer.text).toBeTruthy()
    await expect(page.getByText('回答已中断', { exact: false }).first()).toBeVisible()
  } finally { await peer.close() }
})

test('浏览器前后回到同一材料；保存失败有明确提示', async ({ page }) => {
  await ready(page, '/learn/sql-database')
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  await reader(page).getByRole('button', { name: 'SELECT：查询、筛选与排序', exact: true }).click()
  await expect(reader(page).getByRole('heading', { name: 'SELECT：查询、筛选与排序', exact: true })).toBeVisible()
  await page.goBack()
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  await page.goForward()
  await expect(reader(page).getByRole('heading', { name: 'SELECT：查询、筛选与排序', exact: true })).toBeVisible()
  await page.addInitScript(() => { indexedDB.open = () => { throw new DOMException('offline storage failure fixture', 'SecurityError') } })
  await page.reload(); await expect(input(page)).toBeEnabled()
  await input(page).fill('存储受限时仍能编辑，但不能声称保存成功')
  await expect(page.getByRole('alert').filter({ hasText: /本地保存失败|无法读取本地工作区/ })).toBeVisible()
  await expect(page.getByText('本地保存异常', { exact: true })).toBeVisible()
})

test('大文件可以继续阅读和跳行，同文件复用页签', async ({ page }) => {
  await ready(page)
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
  await page.getByTestId('tree-file').filter({ hasText: 'large.py' }).click()
  await expect(reader(page).getByText('1–200 / 451 行', { exact: true })).toBeVisible()
  await reader(page).getByRole('button', { name: '后 200 行', exact: true }).click()
  await expect(reader(page).getByText('201–400 / 451 行', { exact: true })).toBeVisible()
  await reader(page).getByRole('spinbutton', { name: '跳到行号', exact: true }).fill('401')
  await reader(page).getByRole('button', { name: '跳行', exact: true }).click()
  await expect(reader(page).getByText('401–451 / 451 行', { exact: true })).toBeVisible()
  await expect(reader(page).getByRole('tab', { name: 'large.py', exact: true })).toHaveCount(1)
})

test('会话搜索失败展示原因并可重试', async ({ page }) => {
  await ready(page)
  await page.route('**/api/conversations?**', async route => route.fulfill({ status: 503, json: { error: { code: 'internal_error', title: '离线搜索故障夹具', hint: '请重试', detail: '' } } }))
  await page.getByRole('textbox', { name: '搜索历史对话' }).fill('SQL')
  await expect(page.getByRole('region', { name: '对话列表' }).getByRole('alert')).toContainText('离线搜索故障夹具')
  await page.unroute('**/api/conversations?**')
  await page.getByRole('region', { name: '对话列表' }).getByRole('button', { name: '重试', exact: true }).click()
  await expect(page.getByRole('region', { name: '对话列表' }).getByRole('alert')).toHaveCount(0)
})

test('连接在确认前失败时恢复问题，刷新后的重试复用请求 ID', async ({ page, request }) => {
  await ready(page)
  const cid = new URL(page.url()).searchParams.get('conversation')!
  let firstRequest = ''
  await page.route('**/api/query/stream', async route => { firstRequest = route.request().postDataJSON().request_id; await route.abort('failed') })
  await input(page).fill('SQL 是什么'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  await expect(input(page)).toHaveValue('SQL 是什么')
  await expect(page.getByText('正在保存工作区…', { exact: true })).toHaveCount(0)
  await page.reload(); await expect(input(page)).toBeEnabled(); await expect(input(page)).toHaveValue('SQL 是什么')
  await page.unroute('**/api/query/stream')
  const next = page.waitForRequest(r => r.url().endsWith('/query/stream') && r.method() === 'POST')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  expect((await next).postDataJSON().request_id).toBe(firstRequest)
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const turns = await (await request.get(`/api/projects/1/conversations/${cid}/turns`)).json()
  expect(turns.items).toHaveLength(1)
})

test('切项目后丢弃旧文件函数列表的迟到响应', async ({ page }) => {
  await ready(page)
  let release!: () => void
  const gate = new Promise<void>(resolve => { release = resolve })
  await page.route('**/api/projects/1/symbols?**', async route => {
    if (new URL(route.request().url()).searchParams.get('path') !== 'store.py') { await route.continue(); return }
    await gate
    await route.fulfill({ json: { items: [{ name: 'forbidden_old_project_symbol', qualname: 'store.forbidden_old_project_symbol', path: 'store.py', kind: 'function', lineno: 3, end_lineno: 6 }], total: 1 } })
  })
  try {
    await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
    const old = page.waitForRequest(r => r.url().includes('/projects/1/symbols?') && new URL(r.url()).searchParams.get('path') === 'store.py')
    await page.getByRole('button', { name: '展开 store.py 的函数', exact: true }).click(); await old
    await page.getByRole('button', { name: '选择项目', exact: true }).click(); await page.getByRole('option', { name: /example-other/ }).click()
    await expect(input(page)).toBeEnabled()
    await page.getByRole('button', { name: '展开 store.py 的函数', exact: true }).click()
    const response = page.waitForResponse(r => r.url().includes('/projects/1/symbols?') && new URL(r.url()).searchParams.get('path') === 'store.py')
    release(); await response
    await expect(page.getByText('forbidden_old_project_symbol', { exact: true })).toHaveCount(0)
    await expect(page.locator('#workspace-left').getByText('save', { exact: true })).toBeVisible()
  } finally { release() }
})

test('刷新恢复长对话的中间阅读位置，不强制跳到底部', async ({ page }) => {
  await ready(page)
  await input(page).fill('SQL 是什么 __fixture_long__'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const scroll = page.locator('[data-chat-scroll]')
  await scroll.evaluate(e => { e.scrollTop = 500 })
  await expect.poll(() => scroll.evaluate(e => e.scrollTop)).toBe(500)
  await expect(page.getByText('正在保存工作区…', { exact: true })).toHaveCount(0)
  await page.reload(); await expect(input(page)).toBeEnabled()
  await expect.poll(() => scroll.evaluate(e => e.scrollTop)).toBe(500)
})

async function dragSide(page: Page, label: string, x: number) {
  const handle = (await page.getByRole('separator', { name: label, exact: true }).boundingBox())!
  await page.mouse.move(handle.x + handle.width / 2, handle.y + 180)
  await page.mouse.down()
  await page.mouse.move(x, handle.y + 180, { steps: 8 })
  await page.mouse.up()
}

test('导入通过选择文件夹提交路径，取消和失败不丢失已有选择', async ({ page }) => {
  const folder = 'D:\\中文项目\\demo with spaces'
  let selection = 0
  let imports = 0
  await page.route('**/api/local/select-folder', async route => {
    selection++
    if (selection === 4) {
      await route.fulfill({ status: 404, json: { error: {
        code: 'project_not_found', title: 'Not Found', hint: '', detail: '',
      } } })
    } else if (selection === 3) {
      await route.fulfill({ status: 503, json: { error: {
        code: 'internal_error', title: '无法打开系统文件夹选择框', hint: '请重试。', detail: '',
      } } })
    } else await route.fulfill({ json: { root_path: selection === 1 ? null : folder } })
  })
  await page.route('**/api/projects', async route => {
    if (route.request().method() !== 'POST') { await route.continue(); return }
    imports++
    expect(route.request().postDataJSON()).toEqual({ root_path: folder })
    await route.fulfill({ status: 400, json: { error: {
      code: 'bad_request', title: '所选文件夹不是 Git 仓库', hint: '请更换文件夹。', detail: '',
    } } })
  })
  await ready(page)
  await page.getByRole('button', { name: '导入项目并建索引', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '导入项目并建索引' })
  const submit = dialog.getByRole('button', { name: '导入并建索引', exact: true })
  await expect(submit).toBeDisabled()
  await dialog.getByRole('button', { name: '选择文件夹', exact: true }).click()
  await expect(dialog.getByRole('button', { name: '选择文件夹', exact: true })).toBeEnabled()
  await expect(submit).toBeDisabled()
  await dialog.getByRole('button', { name: '选择文件夹', exact: true }).click()
  await expect(dialog.getByText(folder, { exact: true })).toBeVisible()
  await expect(submit).toBeEnabled()
  expect(imports).toBe(0)
  await dialog.getByRole('button', { name: '更换文件夹', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('无法打开系统文件夹选择框')
  await expect(dialog.getByText(folder, { exact: true })).toBeVisible()
  await dialog.getByRole('button', { name: '更换文件夹', exact: true }).click()
  await expect(dialog.getByRole('alert')).toContainText('请重启 CodeInsight 后端后重试')
  await submit.click()
  await expect(dialog.getByRole('alert')).toContainText('所选文件夹不是 Git 仓库')
  await expect(dialog.getByRole('button', { name: '更换文件夹', exact: true })).toBeEnabled()
  expect(imports).toBe(1)
})

test('拖动侧栏直接收起并从边缘展开，保留阅读和草稿', async ({ page }) => {
  await ready(page, '/learn/sql-database')
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  await input(page).fill('拖动收起后保留这份草稿')
  await reader(page).locator('[data-reading-scroll]').evaluate(e => { e.scrollTop = 400 })
  await dragSide(page, '调整左栏宽度', 20)
  await expect(page.locator('#workspace-left')).toBeHidden()
  await dragSide(page, '拖动打开左栏', 120)
  await expect(page.locator('#workspace-left')).toBeVisible()
  await dragSide(page, '调整右栏宽度', 1420)
  await expect(reader(page)).toBeHidden()
  await expect(input(page)).toHaveValue('拖动收起后保留这份草稿')
  await dragSide(page, '拖动打开右栏', 1310)
  await expect(reader(page)).toBeVisible()
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  await expect.poll(() => reader(page).locator('[data-reading-scroll]').evaluate(e => e.scrollTop)).toBe(400)
  const handle = (await page.getByRole('separator', { name: '调整右栏宽度', exact: true }).boundingBox())!
  const width = await reader(page).evaluate(e => e.getBoundingClientRect().width)
  await page.mouse.move(handle.x + 3, handle.y + 150); await page.mouse.down()
  await page.mouse.move(1420, handle.y + 150)
  await expect(reader(page)).toBeHidden()
  await page.getByRole('separator', { name: '拖动打开右栏', exact: true }).dispatchEvent('pointercancel')
  await page.mouse.up()
  await expect(reader(page)).toBeVisible()
  await expect.poll(() => reader(page).evaluate(e => e.getBoundingClientRect().width)).toBe(width)
})

test('拖动侧栏在单区阅读和专注阅读中也能开关', async ({ page }) => {
  await page.setViewportSize({ width: 1024, height: 900 })
  await ready(page, '/learn/sql-database')
  await expect(reader(page).getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列', exact: true })).toBeVisible()
  await dragSide(page, '调整右栏宽度', 120)
  await expect(reader(page)).toBeHidden()
  await expect(input(page)).toBeVisible()
  await dragSide(page, '拖动打开右栏', 900)
  await expect(reader(page)).toBeVisible()
  await dragSide(page, '拖动打开左栏', 120)
  await expect(page.locator('#workspace-left')).toBeVisible()
  await dragSide(page, '调整左栏宽度', 20)
  await expect(page.locator('#workspace-left')).toBeHidden()
  await page.setViewportSize({ width: 1440, height: 1000 })
  await reader(page).getByRole('button', { name: '展开阅读', exact: true }).click()
  await dragSide(page, '调整右栏宽度', 120)
  await expect(input(page)).toBeVisible()
  await expect(reader(page)).toBeHidden()
})

test('材料菜单不被正文遮挡，选段从关系图回到输入框', async ({ page }) => {
  await ready(page, '/learn/sql-database')
  await expect(reader(page).locator('[data-source-map]').first()).toBeVisible()
  const section = reader(page).locator('[data-section-id]').filter({ has: page.locator('[data-source-map]') }).nth(2)
  const title = await section.locator('h3').innerText()
  await section.scrollIntoViewIfNeeded()
  await expect(page.locator('.reading-context')).toContainText(title)
  const menu = reader(page).getByRole('button', { name: '材料操作', exact: true })
  await menu.click()
  await page.getByRole('menuitem', { name: '关闭其他页签', exact: true }).click()
  await expect(page.getByRole('menu', { name: '材料操作' })).toHaveCount(0)
  await menu.click(); await page.keyboard.press('Escape')
  await expect(menu).toBeFocused()
  await menu.click(); await page.getByRole('heading', { name: 'CodeInsight', exact: true }).click()
  await expect(page.getByRole('menu', { name: '材料操作' })).toHaveCount(0)
  await input(page).fill('切图后保留草稿')
  await page.getByRole('navigation', { name: '工作台视图' }).getByRole('button', { name: '关系图', exact: true }).click()
  await reader(page).locator('[data-reading-scroll]').evaluate(e => { e.scrollTop = 0 })
  await reader(page).locator('[data-source-map]').first().evaluate(e => {
    const range = document.createRange(); range.selectNodeContents(e)
    const selection = getSelection()!; selection.removeAllRanges(); selection.addRange(range)
  })
  await reader(page).getByRole('button', { name: '问选中段落', exact: true }).click()
  await expect(input(page)).toBeVisible()
  await expect(input(page)).toBeFocused()
  await expect(input(page)).toHaveValue('切图后保留草稿')
})

test('恢复旧问题先保护草稿，并支持在会话内逐条查找', async ({ page }) => {
  await ready(page)
  await input(page).fill('SQL 是什么'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  await input(page).fill('尚未发送的重要草稿')
  const restore = page.getByRole('button', { name: '恢复问题到草稿', exact: true }).first()
  await restore.click()
  const dialog = page.getByRole('dialog', { name: '替换当前草稿？' })
  await dialog.getByRole('button', { name: '保留草稿', exact: true }).click()
  await expect(input(page)).toHaveValue('尚未发送的重要草稿')
  await restore.click(); await dialog.getByRole('button', { name: '替换草稿', exact: true }).click()
  await expect(input(page)).toHaveValue('SQL 是什么')
  await page.getByRole('button', { name: '查找当前对话', exact: true }).click()
  await page.getByRole('textbox', { name: '查找当前对话', exact: true }).fill('SQL')
  await expect(page.locator('.chat-toolbar')).toContainText('1/2 条')
  await page.getByRole('button', { name: '下一条匹配消息' }).click()
  await expect(page.locator('.chat-toolbar')).toContainText('2/2 条')
  await page.getByRole('button', { name: '关闭对话查找' }).click()
  await expect(input(page)).toHaveValue('SQL 是什么')
})

test('来源卡片携带真实行号和回答版本打开源码', async ({ page, request }) => {
  await ready(page)
  await input(page).fill('SQL 是什么'); await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toHaveCount(0)
  const project = await (await request.get('/api/projects/1')).json()
  await page.route('**/conversations/*/turns?*', async route => {
    const response = await route.fetch(); const body = await response.json()
    body.items[0].answer.source_head_commit = project.head_commit
    body.items[0].answer.evidence = [{ path: 'large.py', lineno: 210, end_lineno: 213,
      qualname: null, snippet: '固定离线来源投影', lanes: [], concepts: [] }]
    await route.fulfill({ json: body })
  })
  await page.reload(); await expect(input(page)).toBeEnabled()
  await page.getByRole('button', { name: '查看来源', exact: true }).first().click()
  await reader(page).getByRole('button').filter({ hasText: 'large.py:210' }).click()
  await expect(reader(page).getByText('210–409 / 451 行', { exact: true })).toBeVisible()
  expect(JSON.parse(new URL(page.url()).searchParams.get('material')!).version).toBe(project.head_commit)
})

test('索引已接受时关闭导入弹窗，后台轮询不阻塞工作台', async ({ page, request }) => {
  await ready(page)
  const project = await (await request.get('/api/projects/1')).json()
  await page.route('**/api/local/select-folder', route => route.fulfill({ json: { root_path: 'D:/fixture' } }))
  await page.route('**/api/projects/1', route => route.fulfill({ json: { ...project, status: 'indexing' } }))
  await page.route('**/api/projects', async route => {
    if (route.request().method() === 'POST') await route.fulfill({ status: 202, json: { ...project, status: 'indexing' } })
    else await route.continue()
  })
  await page.getByRole('button', { name: '导入项目并建索引', exact: true }).click()
  const dialog = page.getByRole('dialog', { name: '导入项目并建索引' })
  await dialog.getByRole('button', { name: '选择文件夹', exact: true }).click()
  await dialog.getByRole('button', { name: '导入并建索引', exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(page.getByRole('status').filter({ hasText: /索引/ })).toBeVisible()
  await expect(input(page)).toBeEnabled()
  await input(page).fill('索引过程中也能写草稿')
})
