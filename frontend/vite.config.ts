import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    plugins: [vue()],
    server: {
      proxy: {
        '/api': {
          target: env.VITE_API_TARGET || 'http://127.0.0.1:8002',
          changeOrigin: true,
          // 本地后端路由挂在 /api/v1，保留 /api 前缀，不做 rewrite
        },
      },
    },
  }
})
