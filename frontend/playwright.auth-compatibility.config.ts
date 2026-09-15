import { defineConfig } from '@playwright/test'
import compatibility from './playwright.compatibility.config'

export default defineConfig({
  ...compatibility,
  testMatch: 'login-responsive.spec.ts',
  outputDir: './.tmp/playwright-auth-compatibility',
  use: { ...compatibility.use, baseURL: 'http://127.0.0.1:5298' },
  projects: compatibility.projects?.map(project => ({
    ...project,
    use: { ...project.use, hasTouch: true },
  })),
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5298 --strictPort',
    url: 'http://127.0.0.1:5298',
    env: { VITE_AUTH_ENABLED: 'true' },
    timeout: 120_000,
  },
})
