import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: './e2e',
  reporter: [['html', { outputFolder: '../artifacts/playwright-api/html-report', open: 'never' }], ['list']],
  use: { browserName: 'chromium', headless: true, screenshot: 'only-on-failure' },
  outputDir: '../artifacts/playwright-api/test-results',
})
