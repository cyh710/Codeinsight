/** 可控的图响应验证交互语义；真实仓库画面另行核对，不调用模型。 */
import { expect, test } from '@playwright/test'
import type { GraphNode, GraphResponse } from '../../src/api/types'

test.beforeEach(async ({ page, request }) => {
  const conversation = await (await request.post('/api/projects/1/conversations')).json()
  await page.addInitScript(cid => localStorage.setItem('ci.activeConversation.1', cid), conversation.id)
})

function node(id: number, name: string, path = 'helpers.py'): GraphNode {
  return {
    id,
    name,
    qualname: name === 'save' ? 'store.save' : `helpers.${name}`,
    path,
    lineno: id === 1 ? 3 : id,
    end_lineno: id + 20,
    kind: 'function',
    is_async: false,
    is_private: false,
    in_degree: 0,
    out_degree: 0,
    concept_ids: [],
    depth: 1,
  }
}
const nodes = [
  node(1, 'save', 'store.py'),
  node(2, 'web_entry', 'web.py'),
  node(3, 'test_save_a', 'tests/test_store.py'),
  node(4, 'test_save_b', 'tests/test_store.py'),
  ...['one', 'two', 'three', 'four', 'five', 'six'].map((name, index) =>
    node(index + 10, `helper_${name}`),
  ),
]
function response(qualname: string | null): GraphResponse {
  const center = nodes.find((item) => item.qualname === qualname)
  return {
    mode: center ? 'focus' : 'overview',
    center: center ? { qualname: center.qualname, path: center.path, lineno: center.lineno } : null,
    depth: center ? 1 : null,
    kinds: ['call'],
    nodes,
    truncated: true,
    edges: [
      { src: 2, dst: 1, kind: 'call', lineno: 21, confidence: 1, uncertain: false },
      { src: 3, dst: 1, kind: 'call', lineno: 31, confidence: 1, uncertain: false },
      { src: 4, dst: 1, kind: 'call', lineno: 41, confidence: 1, uncertain: false },
      ...nodes
        .slice(4)
        .map((item) => ({
          src: 1,
          dst: item.id,
          kind: 'call' as const,
          lineno: 4,
          confidence: item.id === 10 ? 0.6 : 1,
          uncertain: item.id === 10,
        })),
    ],
  }
}

test('局部阅读分清方向、折叠测试、展开关系、验证调用位置与换中心，并保留高级图', async ({
  page,
}) => {
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  await page.route('**/api/projects/*/graph?**', async (route) => {
    const url = new URL(route.request().url())
    await route.fulfill({ json: response(url.searchParams.get('qualname')) })
  })
  await page.goto('/')
  await page
    .getByRole('navigation', { name: '工作台视图' })
    .getByRole('button', { name: '关系图', exact: true })
    .click()
  await expect(page.getByRole('heading', { name: '先选一处你想读懂的代码' })).toBeVisible()
  await expect(page.locator('.react-flow__node')).toHaveCount(0)
  await page.getByRole('textbox', { name: '搜索关系图中心符号' }).fill('save')
  await page.locator('li button').filter({ hasText: 'store.save' }).click()
  await expect(page.getByRole('heading', { name: 'save 的调用关系', exact: true })).toBeVisible()
  const incoming = page.getByRole('region', { name: '谁调用它', exact: true })
  const outgoing = page.getByRole('region', { name: '它调用什么', exact: true })
  await expect(incoming.getByRole('button', { name: 'web_entry', exact: true })).toBeVisible()
  await expect(outgoing.getByRole('button', { name: 'web_entry', exact: true })).toHaveCount(0)
  await expect(incoming.getByRole('button', { name: 'test_save_a', exact: true })).toBeHidden()
  await incoming.locator('summary').filter({ hasText: '测试中的调用' }).click()
  await expect(incoming.getByRole('button', { name: 'test_save_a', exact: true })).toBeVisible()
  await incoming.locator('summary').filter({ hasText: '测试中的调用' }).click()
  await expect(outgoing.getByRole('button', { name: 'helper_six', exact: true })).toHaveCount(0)
  await outgoing.getByRole('button', { name: '展开其余 2 项', exact: true }).click()
  await expect(outgoing.getByRole('button', { name: 'helper_six', exact: true })).toBeVisible()
  await expect(page.getByRole('status').filter({ hasText: '当前仅返回部分关系' })).toBeVisible()
  const one = outgoing
    .locator('article')
    .filter({ has: page.getByRole('button', { name: 'helper_one', exact: true }) })
  await expect(one.getByText('可能的调用', { exact: true })).toBeVisible()
  await one.locator('summary').filter({ hasText: '调用依据' }).click()
  await one.getByRole('button', { name: 'store.py:4 · 待核对 60%', exact: true }).click()
  await expect(
    page.locator('aside').last().getByText('只读源码窗口', { exact: false }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: 'save 的调用关系', exact: true })).toBeVisible()
  await one.getByRole('button', { name: '以此为中心', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: 'helper_one 的调用关系', exact: true }),
  ).toBeVisible()
  await page.getByRole('button', { name: '返回上一个关系中心', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'save 的调用关系', exact: true })).toBeVisible()
  await page.getByRole('button', { name: '高级全图', exact: true }).click()
  await expect(page.getByRole('group', { name: '跳数', exact: true })).toBeVisible()
  await expect.poll(() => page.locator('.react-flow__node').count()).toBeGreaterThan(0)
  await page.getByRole('button', { name: '局部阅读', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'save 的调用关系', exact: true })).toBeVisible()
  await page.setViewportSize({ width: 1024, height: 800 })
  await expect
    .poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    .toBe(true)
  await page.getByRole('button', { name: '回到关系图', exact: true }).click()
  await expect(
    page
      .getByRole('region', { name: '当前代码', exact: true })
      .getByRole('heading', { name: 'save', exact: true }),
  ).toBeInViewport()
  expect(errors).toEqual([])
})

test('读取失败可重试；没有已定位调用时不生成假关系', async ({ page }) => {
  let failed = true
  await page.route('**/api/projects/*/graph?**', async (route) => {
    const q = new URL(route.request().url()).searchParams.get('qualname')
    if (q && failed)
      return route.fulfill({
        status: 503,
        json: { detail: { code: 'unavailable', title: '测试：关系读取失败', hint: '稍后重试' } },
      })
    const data = response(q)
    if (q) {
      data.nodes = [nodes[0]]
      data.edges = []
      data.truncated = false
    }
    await route.fulfill({ json: data })
  })
  await page.goto('/')
  await page
    .getByRole('navigation', { name: '工作台视图' })
    .getByRole('button', { name: '关系图', exact: true })
    .click()
  await page.getByRole('textbox', { name: '搜索关系图中心符号' }).fill('save')
  await page.locator('li button').filter({ hasText: 'store.save' }).click()
  await expect(page.getByRole('alert')).toBeVisible()
  failed = false
  await page.getByRole('button', { name: '重新读取', exact: true }).click()
  await expect(page.getByRole('heading', { name: 'save 的调用关系', exact: true })).toBeVisible()
  await expect(page.getByText('当前返回的关系中没有非测试调用者。', { exact: true })).toBeVisible()
  await expect(
    page.getByText('当前返回的关系中没有非测试调用目标。', { exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('button', { name: '以此为中心', exact: true })).toHaveCount(0)
})
