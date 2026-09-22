import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  testMatch: 'business-service-responsive.spec.ts',
  fullyParallel: true,
  workers: 2,
  reporter: 'list',
  outputDir: './.tmp/playwright-compatibility',
  use: {
    baseURL: 'http://127.0.0.1:5191',
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 5191 --strictPort',
    url: 'http://127.0.0.1:5191',
    env: { VITE_AUTH_ENABLED: 'false' },
    timeout: 120_000,
  },
})
