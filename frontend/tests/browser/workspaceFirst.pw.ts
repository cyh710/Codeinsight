import { expect, test } from '@playwright/test'
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve, sep } from 'node:path'

test('新增实验文件无需更新索引即可问答，来源、分页和刷新固定已读版本', async ({ page, request }) => {
  const root = await mkdtemp(join(tmpdir(), 'codeinsight-workspace-browser-'))
  try {
    await writeFile(join(root, 'main.py'), 'def run():\n    return 1\n')
    const created = await (await request.post('/api/projects', { data: { root_path: root, name: root.split(/[\\/]/).at(-1)! } })).json()
    const pid = created.project_id ?? created.id
    await expect.poll(async () => (await (await request.get(`/api/projects/${pid}`)).json()).status).toBe('ready')
    await mkdir(join(root, 'experiments'))
    const file = join(root, 'experiments', 'score_output.txt')
    await writeFile(file, 'MRR=0.75\n' + 'sample\n'.repeat(250))
    const conversation = await (await request.post(`/api/projects/${pid}/conversations`)).json()
    await page.addInitScript(({ pid, cid }) => { localStorage.setItem('ci.projectId', String(pid)); localStorage.setItem(`ci.activeConversation.${pid}`, cid) }, { pid, cid: conversation.id })
    const restored = page.waitForResponse(response => response.url().includes(`/projects/${pid}/conversations/${conversation.id}/turns`) && response.ok())
    await page.goto(`/?project=${pid}&conversation=${conversation.id}`)
    await restored
    await expect(page.locator('.wb-center textarea')).toBeEnabled()
    await page.locator('.wb-center textarea').fill('看看新增实验的成绩 __fixture_workspace__')
    await page.getByRole('button', { name: '发送', exact: true }).click()
    const link = page.locator('.assistant-answer').getByRole('link', { name: 'score_output.txt:1', exact: true })
    await expect(link).toBeVisible()
    const material = JSON.parse(new URL((await link.getAttribute('href'))!, 'http://127.0.0.1:15174').searchParams.get('material')!)
    expect(material.sourceKind).toBe('workspace')
    expect(material.contentSha).toHaveLength(64)
    expect(material.indexEpoch).toBeUndefined()
    await writeFile(file, 'MRR=0.99\n' + 'changed\n'.repeat(250))
    await link.click()
    const reader = page.locator('#workspace-materials')
    await expect(reader.locator('.monaco-editor')).toContainText('MRR=0.75')
    await reader.getByRole('button', { name: '后 200 行', exact: true }).click()
    await expect(reader.locator('.monaco-editor')).toContainText('sample')
    await expect(reader.locator('.monaco-editor')).not.toContainText('changed')
    await page.reload()
    await expect(reader.locator('.monaco-editor')).toContainText('sample')
    await reader.getByRole('button', { name: '查看当前文件', exact: true }).click()
    await expect(reader.locator('.monaco-editor')).toContainText('changed')
    await reader.getByRole('button', { name: '前 200 行', exact: true }).click()
    await expect(reader.locator('.monaco-editor')).toContainText('MRR=0.99')
    expect((await (await request.get(`/api/projects/${pid}`)).json()).index_epoch).toBe(1)
    await page.screenshot({ path: resolve('../.ci/browser/workspace-first.png'), animations: 'disabled' })
    await page.getByRole('button', { name: '文件', exact: true }).click()
    await page.getByPlaceholder('搜索文件或符号…').fill('score_output')
    await expect(page.getByTestId('tree-file').filter({ hasText: 'score_output.txt' })).toBeVisible()
    // 工作区树从实际目录载入，不要求索引存在这个文件。
    const files = await (await request.get(`/api/projects/${pid}/files?source_kind=workspace`)).json()
    expect(files.some((item: { path: string }) => item.path === 'experiments/score_output.txt')).toBe(true)
  } finally {
    expect(resolve(root).startsWith(resolve(tmpdir()) + sep + 'codeinsight-workspace-browser-')).toBe(true)
    await rm(root, { recursive: true, force: true })
  }
})
