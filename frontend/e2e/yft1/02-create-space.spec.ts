import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, runConsoleUi, shot, switchGraphSpace, waitFor } from './helpers'

// 阶段 3：前端「新建图数据空间」建 yunfei_test_1（阶段 2 已 CLI 兜底清场）。
// 验收：空间创建成功 + vid 类型 FIXED_STRING(256)（GRAPH_SPACE_VID_LENGTH 默认 256 口径）。
test.describe.serial('S3 前端建空间', () => {
  test('S3a 配置管理→新建图数据空间 yunfei_test_1', async ({ page }) => {
    await gotoRoute(page, '/configurations')
    await page.getByRole('button', { name: '图数据空间' }).click()
    await page.waitForTimeout(800)

    await page.getByRole('button', { name: '＋ 新建图数据空间' }).click()
    await page.locator('input[aria-label="仅字母、数字、下划线，以字母或下划线开头"]').waitFor()
    await page.locator('input[aria-label="仅字母、数字、下划线，以字母或下划线开头"]').fill(SPACE)
    await shot(page, 's3-1-create-space-dialog')
    await page.getByRole('button', { name: '创建', exact: true }).click()

    // 表格出现 yunfei_test_1 行
    await waitFor(
      async () => (await page.getByText(SPACE, { exact: true }).first().isVisible().catch(() => false)),
      { timeout: 30_000, interval: 1_500, label: '空间列表出现 yunfei_test_1' },
    )
    await shot(page, 's3-2-space-created')
  })

  test('S3b 全局选择器切到新空间 + 控制台验证 vid 口径', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-query')

    const rows = await runConsoleUi(page, `SHOW CREATE SPACE ${SPACE}`)
    const flat = rows.map((r) => r.join(' ')).join('\n')
    expect(flat).toContain('FIXED_STRING(256)')
    await shot(page, 's3-3-show-create-space')
  })
})
