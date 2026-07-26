import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  return {
    base: env.VITE_BASE || './',

    plugins: [
      vue(),
    ],

    server: {
      // 避免服务器无法提高 inotify 限制时出现 ENOSPC。
      watch: {
        usePolling: true,
        interval: 1000,
      },

      proxy: {
        '/api': {
          target:
            env.VITE_API_TARGET
            || 'http://127.0.0.1:8000',

          changeOrigin: true,
        },
      },
    },
  }
})