import { defineConfig } from '@playwright/test'

// yunfei_test_1 前端全流程 e2e 第二轮（2026-10-08 r2）：与第一轮同栈（web 8093 根路径 +
// api 8004），差异是建实体/关系目录、绑脚本、抽数据全部经前端 UI 重建（第一轮 CLI 预建 DDL）。
// 串行执行（workers=1）：阶段间有严格先后依赖（清场→建空间→删目录→建目录→绑→跑链→验证）。
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
  outputDir: '../../../artifacts/yft1-frontend-e2e-r2/test-results',
})
