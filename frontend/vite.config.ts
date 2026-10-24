import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { env } from 'node:process'

// 端口 8020 是 CodeInsight 后端（契约 §0.1）。与织忆同构：
// 浏览器一律走 /api 前缀，proxy 负责剥掉前缀转发。
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      input: {
        main: 'index.html',
      },
    },
  },
  server: {
    proxy: {
      '/api': {
        target: env.CI_API_TARGET || 'http://127.0.0.1:8020',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
        configure: (proxy) => {
          proxy.on('proxyRes', (proxyRes) => {
            // SSE 流不允许被缓冲（契约 §8.2）：没有这两个头，
            // 代理层会把增量攒成一坨，前端"边流边渲染"就废了。
            if (proxyRes.headers['content-type']?.includes('text/event-stream')) {
              proxyRes.headers['X-Accel-Buffering'] = 'no'
              proxyRes.headers['Cache-Control'] = 'no-cache'
            }
          })
        },
      },
    },
  },
})
