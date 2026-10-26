import { defineConfig } from '@playwright/test'
import { env } from 'node:process'

export default defineConfig({
  testDir: './tests/browser',
  testMatch: '*.pw.ts',
  workers: 1,
  // 本地真实 API 包含冷启动与 2.5 秒跨标签页轮询，避免用单元测试级等待误判。
  timeout: 60000,
  expect: { timeout: 15000 },
  outputDir: '../.ci/browser-results',
  use: {
    baseURL: 'http://127.0.0.1:15174',
    channel: 'msedge',
    headless: true,
    viewport: { width: 1440, height: 1000 },
  },
  webServer: [
    {
      command: `"${env.CI_TEST_PYTHON || 'python'}" ../tests/browser_server.py`,
      url: 'http://127.0.0.1:18021/health',
      reuseExistingServer: false,
      timeout: 60000,
    },
    {
      command: 'npm run dev -- --host 127.0.0.1 --port 15174 --strictPort',
      url: 'http://127.0.0.1:15174',
      env: { CI_API_TARGET: 'http://127.0.0.1:18021', VITE_CI_MOCK: '0' },
      reuseExistingServer: false,
    },
  ],
})
