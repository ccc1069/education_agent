import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')
  const useMock = env.VITE_USE_MOCK === 'true'

  return {
    plugins: [react()],
    resolve: {
      alias: {
        '@': path.resolve(__dirname, 'src'),
      },
    },
    server: {
      port: 3000,
      // Mock 模式下不要把 /api 代理到真实后端，否则 MSW 未命中的请求会带着假 JWT 打到 :8000 → 401
      proxy: useMock
        ? undefined
        : {
            '/api': {
              target: 'http://localhost:8000',
              changeOrigin: true,
            },
            // Vite WS 代理用 http(s) target + ws:true 更稳;勿用 ws:// 作为 target
            '/ws': {
              target: 'http://localhost:8000',
              ws: true,
              changeOrigin: true,
            },
            '/health': 'http://localhost:8000',
            '/ready': 'http://localhost:8000',
            '/live': 'http://localhost:8000',
            '/metrics': 'http://localhost:8000',
          },
    },
  }
})
