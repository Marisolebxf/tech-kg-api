import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, runConsoleUi, shot, switchGraphSpace } from './helpers'

// S3b 复跑（S3a 已建空间成功，S3b 上次为 UI 时序偶发失败）。
test('S3b-重试 全局选择器切新空间 + 控制台验证 vid 口径', async ({ page }) => {
  await page.goto('/overview')
  await page.waitForLoadState('networkidle')
  await switchGraphSpace(page, SPACE)
  await gotoRoute(page, '/graph-query')

  const rows = await runConsoleUi(page, `SHOW CREATE SPACE ${SPACE}`)
  const flat = rows.map((r) => r.join(' ')).join('\n')
  expect(flat).toContain('FIXED_STRING(256)')
  await shot(page, 's3-3-show-create-space')

  const tags = await runConsoleUi(page, 'SHOW TAGS')
  // 新空间是空壳：预建 schema 由阶段 4 CLI 完成，此处应为 0
  expect(tags.length).toBe(0)
  await shot(page, 's3-4-empty-tags')
})
