import { defineConfig } from '@playwright/test'

// yunfei_test_1 前端全流程 e2e（2026-10-08）：宿主机 Playwright → yunfei3 栈
// web 根路径实例(8093) + api(8004)。目标：按 backend/docs/yunfei_test全量重建文档.md
// 的全量重建流程，把每一步尽量通过前端 UI 完成，前端做不到的记录为问题。
// 串行执行（workers=1）：阶段间有严格先后依赖（清场→建空间→链→验证）。
export default defineConfig({
  testDir: './',
  fullyParallel: false,
  workers: 1,
  timeout: 300_000,
  expect: { timeout: 20_000 },
  retries: 0,
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:8093',
    browserName: 'chromium',
    headless: true,
    viewport: { width: 1600, height: 900 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
    actionTimeout: 20_000,
    locale: 'zh-CN',
    timezoneId: 'Asia/Shanghai',
  },
  outputDir: '../../../artifacts/yft1-frontend-e2e/test-results',
})
