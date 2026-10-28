import { expect, test } from '@playwright/test'
import { resolve } from 'node:path'

test.beforeEach(async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
})

test('真实 API 的知识阅读、续问、往返和项目隔离', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/')
  await page.getByRole('navigation', { name: '左栏内容' }).getByRole('button', { name: '文件', exact: true }).click()
  const reader = page.locator('aside').last()
  await page.getByTestId('tree-file').filter({ hasText: 'store.py' }).click()
  await expect(reader.getByText('只读源码窗口', { exact: false })).toBeVisible()
  const input = page.locator('.wb-center textarea').first()
  await input.fill('SQL 是什么')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('button', { name: '停止生成', exact: true })).toBeVisible()
  await expect(page.getByRole('link', { name: 'SQL', exact: true })).toHaveCount(0)
  await page.getByRole('link', { name: 'SQL', exact: true }).click()
  await expect(
    reader.getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列' }),
  ).toBeVisible()
  await expect(reader.getByRole('button').filter({ hasText: '组合证据' })).toBeVisible()
  const topic = await (await page.request.get('/api/knowledge/topics/sql-database')).json()
  const example = topic.sections.find((s: { id: string }) => s.id === 'example')
  await reader.getByText('本篇目录', { exact: false }).click()
  await reader
    .getByRole('navigation', { name: '章节目录' })
    .getByRole('button', { name: example.title, exact: false })
    .click()
  const scroll = reader.locator('[data-reading-scroll]')
  await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(0)
  const request = page.waitForRequest(
    (r) => r.url().endsWith('/query/stream') && r.method() === 'POST',
  )
  await input.fill('这里是什么意思')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const body = (await request).postDataJSON()
  expect(body.reading_context.kind).toBe('knowledge')
  expect(body.reading_context.topic_id).toBe('sql-database')
  expect(body.reading_context.section_id).toBe('example')
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible()
  await scroll.evaluate((el) => {
    el.scrollTop = 1300
  })
  await page.waitForTimeout(100)
  const position = await scroll.evaluate((el) => el.scrollTop)
  await reader.getByRole('button', { name: 'SELECT：查询、筛选与排序', exact: true }).click()
  await expect(
    reader.getByRole('heading', {
      name: 'SELECT：查询、筛选与排序',
      exact: true,
    }),
  ).toBeVisible()
  await reader.getByRole('button', { name: '返回上一处', exact: true }).click()
  await expect(
    reader.getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列' }),
  ).toBeVisible()
  await expect.poll(() => scroll.evaluate((el) => el.scrollTop)).toBeGreaterThan(position - 20)
  await page.screenshot({
    path: resolve('..', '.ci/browser/learning-workbench.png'),
    fullPage: true,
  })
  await reader.getByRole('button', { name: '回到代码', exact: true }).click()
  await expect(reader.getByText('只读源码窗口', { exact: false })).toBeVisible()
  const codeRequest = page.waitForRequest(
    (r) => r.url().endsWith('/query/stream') && r.method() === 'POST',
  )
  await input.fill('这里是什么意思')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  expect((await codeRequest).postDataJSON().reading_context).toMatchObject({
    kind: 'code',
    path: 'store.py',
    project_id: 1,
  })
  await expect(page.getByRole('button', { name: '发送', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '选择项目', exact: true }).click()
  await page.getByRole('option', { name: /example-other/ }).click()
  await expect(page.getByText('结合代码 store.py:1 提问', { exact: false })).toHaveCount(0)
  await expect(page.getByRole('link', { name: 'SQL', exact: true })).toHaveCount(0)
  await page.getByRole('button', { name: '选择项目', exact: true }).click()
  await page.getByRole('option', { name: /example-main/ }).click()
  await expect(page.getByRole('link', { name: 'SQL', exact: true }).first()).toBeVisible()
  expect(errors).toEqual([])
})

test('Provider 故障后教材仍能阅读，错误目标有可解释降级', async ({ page }) => {
  await page.goto('/learn/sql-database#removed-old-section')
  const reader = page.locator('aside').last()
  await expect(reader.getByText('原引用的教材或章节已更新', { exact: false })).toBeVisible()
  await page.getByRole('textbox').last().fill('__fixture_fail_provider__')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  await expect(page.getByRole('alert').first()).toBeVisible()
  await expect(
    reader.getByRole('heading', { name: 'SQL 是什么：数据库、表、行与列' }),
  ).toBeVisible()
  await reader.getByRole('button', { name: '教材目录', exact: true }).click()
  await reader.getByRole('textbox', { name: '搜索知识' }).fill('React state 是什么')
  await reader.getByRole('button', { name: '搜索章节', exact: true }).click()
  await expect(reader.getByRole('button').filter({ hasText: 'State' }).first()).toBeVisible()
})

test('真实项目实例、代码概念标签与 deep 降级形成往返', async ({ page }) => {
  const external: string[] = []
  page.on('request', (request) => {
    if (/^https?:/.test(request.url()) && !request.url().startsWith('http://127.0.0.1:'))
      external.push(request.url())
  })
  await page.goto('/learn/sql-transactions')
  const reader = page.locator('aside').last()
  await reader.getByRole('button').filter({ hasText: '组合证据' }).click()
  await expect(reader.getByRole('heading', { name: /save/ })).toBeVisible()
  await expect(reader.locator('.monaco-editor')).toBeVisible()
  await expect(reader.getByRole('button', { name: '了解 db-transaction', exact: true })).toBeVisible()
  await page.screenshot({ path: resolve('..', '.ci/browser/debug-code-concepts.png'), animations: 'disabled' })
  await reader.getByRole('button', { name: '了解 db-transaction', exact: true }).click()
  await reader.getByRole('tab', { name: '深入探索', exact: true }).click()
  await expect(reader.getByRole('status').filter({ hasText: '深入解释不可用' })).toBeVisible()
  await reader.getByRole('button', { name: '数据库事务：一致完成状态转换', exact: true }).click()
  await expect(
    reader.getByRole('heading', {
      name: '数据库事务：一致完成状态转换',
      exact: true,
    }),
  ).toBeVisible()
  await reader.getByRole('button', { name: '回到代码', exact: true }).click()
  await expect(reader.getByRole('heading', { name: /save/ })).toBeVisible()
  expect(external).toEqual([])
})

test('长回答保留代码与阅读入口，顶栏切换后对话仍在', async ({ page }) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.goto('/learn/sql-database')
  const topic = await (await page.request.get('/api/knowledge/topics/sql-database')).json()
  const target = {
    topic_id: topic.id,
    title: topic.title,
    version: topic.version,
    section_id: 'overview',
    href: '/learn/sql-database#overview',
  }
  const code = `SELECT name, price FROM products WHERE name = '${'example_'.repeat(24)}';`
  const text = [
    '## SQL，把需求写成查询',
    'SQL 是用来与数据库交流的语言。先理解[表](/learn/sql-database#overview)，再试着查询需要的数据。以下是教学示例。',
    '### 从一张商品表开始',
    '1. **表**把一类数据组织在一起。\n2. **行**是一条记录。\n3. **列**描述记录的一个属性。',
    '| name | price |\n| --- | --- |\n| 笔记本 | 12.00 |\n| 钢笔 | 35.00 |',
    '### 用 SELECT 说清你需要什么',
    '```sql\nSELECT name, price\nFROM products\nWHERE price < 20;\n```',
    '这句查询只返回价格低于 `20` 的商品。它描述需要的结果，数据库决定怎样执行。',
    '```sql\n' + code + '\n```',
  ].join('\n\n')
  await page.route('**/api/query/stream', async (route) => {
    const events = [
      ['meta', { conversation_id: 'visual-offline-fixture' }],
      [
        'answer',
        {
          text,
          facts: [],
          inferences: [],
          citations: [],
          abstained: false,
          learning_entries: [target],
          learning_targets: [target],
        },
      ],
      ['done', { abstained: false }],
    ]
    await route.fulfill({
      status: 200,
      contentType: 'text/event-stream',
      body: events
        .map(([event, data]) => `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`)
        .join(''),
    })
  })
  await page.getByRole('textbox').last().fill('SQL 是什么？可以举个例子吗？')
  await page.getByRole('button', { name: '发送', exact: true }).click()
  const heading = page.getByRole('heading', { name: 'SQL，把需求写成查询', exact: true })
  await expect(heading).toBeVisible()
  const prose = page.locator('.learning-prose').first()
  await expect(prose.locator('pre').last()).toHaveText(code)
  await expect(prose.getByRole('table')).toBeVisible()
  await prose.getByRole('link', { name: '表', exact: true }).click()
  await expect(
    page.locator('aside').last().getByRole('heading', { name: topic.title, exact: true }),
  ).toBeVisible()
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true)
  await heading.scrollIntoViewIfNeeded()
  await page.screenshot({
    path: resolve('..', '.ci/browser/frontend-refined-1440.png'),
    fullPage: true,
  })
  await page.setViewportSize({ width: 1280, height: 900 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
    .toBe(true)
  await heading.scrollIntoViewIfNeeded()
  await page.screenshot({
    path: resolve('..', '.ci/browser/frontend-refined-1280.png'),
    fullPage: true,
  })
  const nav = page.getByRole('navigation', { name: '工作台视图' })
  await nav.getByRole('button', { name: '关系图', exact: true }).click()
  await expect(page.getByRole('textbox', { name: '搜索关系图中心符号' })).toBeVisible()
  await nav.getByRole('button', { name: '时间线', exact: true }).click()
  await expect(page.getByRole('heading', { name: '演进时间线', exact: true })).toBeVisible()
  await nav.getByRole('button', { name: '对话', exact: true }).click()
  await expect(heading).toBeVisible()
  await prose.getByRole('link', { name: '表', exact: true }).click()
  await expect(
    page.locator('aside').last().getByRole('heading', { name: topic.title, exact: true }),
  ).toBeVisible()
  expect(errors).toEqual([])
})
