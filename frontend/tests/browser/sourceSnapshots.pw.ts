import { expect, test } from '@playwright/test'
import { mkdtemp, writeFile, unlink, rmdir } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'

test('本地项目修改、更新和刷新后，旧页签仍打开同一份源码快照', async ({ page, request }) => {
  const root = await mkdtemp(join(tmpdir(), 'codeinsight-source-browser-'))
  const path = join(root, 'app.py')
  const name = root.split(/[\\/]/).at(-1)!
  try {
    await writeFile(path, 'def value():\n    return 1\n')
    const created = await (await request.post('/api/projects', { data: { root_path: root, name } })).json()
    const pid = created.project_id ?? created.id
    expect(pid).toBeTruthy()
    await expect.poll(async () => (await (await request.get(`/api/projects/${pid}`)).json()).status).toBe('ready')
    const conversation = await (await request.post(`/api/projects/${pid}/conversations`)).json()
    const address = (epoch: number) => `/?${new URLSearchParams({ project: String(pid), conversation: conversation.id, material: JSON.stringify({ mode: 'file', path: 'app.py', lineno: 1, indexEpoch: epoch }) })}`
    await page.goto(address(1))
    await expect(page.locator('#workspace-materials .monaco-editor')).toContainText('return 1')
    await writeFile(path, 'def value():\n    return 2\n')
    await page.reload()
    await expect(page.locator('#workspace-materials')).toContainText('磁盘文件已有修改')
    await expect(page.locator('#workspace-materials .monaco-editor')).toContainText('return 1')
    await request.post('/api/projects', { data: { root_path: root, name } })
    await expect.poll(async () => (await (await request.get(`/api/projects/${pid}`)).json()).index_epoch).toBe(2)
    await page.reload()
    await expect(page.locator('#workspace-materials .monaco-editor')).toContainText('return 1')
    await page.screenshot({ path: resolve('..', '.ci/browser/source-snapshot-history.png'), animations: 'disabled' })
    await page.goto(address(2))
    await expect(page.locator('#workspace-materials .monaco-editor')).toContainText('return 2')
  } finally {
    await unlink(path)
    await rmdir(root)
  }
})

test('后端需要重启时给出明确提示，保留输入与页面操作', async ({ page }) => {
  await page.route('**/api/health', async route => {
    const response = await route.fetch()
    const data = await response.json()
    await route.fulfill({ response, json: { ...data, runtime_revision: 'old-runtime', restart_required: true } })
  })
  await page.goto('/')
  await expect(page.getByText('后端需要重启以加载当前代码。', { exact: false })).toBeVisible()
  await page.locator('.wb-center textarea').fill('保留这个草稿')
  await page.getByRole('button', { name: '恢复布局', exact: true }).click()
  await expect(page.locator('.wb-center textarea')).toHaveValue('保留这个草稿')
})
