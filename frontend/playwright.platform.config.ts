import { defineConfig } from '@playwright/test'

// dev2 全功能线 E2E：宿主机 Playwright → 容器化 web 根路径实例(8091) + api(8002)。
// 门户前缀实例在 8089（/bkg_zpt），e2e 走根路径实例避免改动全部用例路径。
// 串行执行（workers=1）：场景间存在造数依赖链（C 组 schema → E/F 任务 → G/H），
// 文件名数字前缀决定执行顺序。
export default defineConfig({
  testDir: './e2e/platform',
  fullyParallel: false,
  workers: 1,
  timeout: 180_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [
    ['list'],
    ['json', { outputFile: '../artifacts/playwright-platform/report.json' }],
    ['html', { outputFolder: '../artifacts/playwright-platform/html', open: 'never' }],
  ],
  use: {
    baseURL: 'http://localhost:8091',
    browserName: 'chromium',
    headless: true,
    // 1280 默认宽度命中响应式断点会隐藏 hero 徽标/部分操作列，统一用宽视口
    viewport: { width: 1600, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 15_000,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  },
  outputDir: '../artifacts/playwright-platform/test-results',
})
