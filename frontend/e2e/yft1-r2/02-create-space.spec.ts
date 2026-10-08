import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, runConsoleUi, shot, switchGraphSpace, waitFor } from './helpers'

// 阶段 2：CLI 兜底清场（DROP SPACE / Milvus / 水位，问题①口径）之后，
// 前端「新建图数据空间」重建 yunfei_test_1，验收 vid FIXED_STRING(256)。
test.describe.serial('S2 前端建空间', () => {
  test('S2a 配置管理→新建图数据空间 yunfei_test_1', async ({ page }) => {
    await gotoRoute(page, '/configurations')
    await page.getByRole('button', { name: '图数据空间' }).click()
    await page.waitForTimeout(800)

    await page.getByRole('button', { name: '＋ 新建图数据空间' }).click()
    await page.locator('input[aria-label="仅字母、数字、下划线，以字母或下划线开头"]').waitFor()
    await page.locator('input[aria-label="仅字母、数字、下划线，以字母或下划线开头"]').fill(SPACE)
    await shot(page, 'r2-s2-1-create-space-dialog')
    await page.getByRole('button', { name: '创建', exact: true }).click()

    await waitFor(
      async () => (await page.getByText(SPACE, { exact: true }).first().isVisible().catch(() => false)),
      { timeout: 30_000, interval: 1_500, label: '空间列表出现 yunfei_test_1' },
    )
    await shot(page, 'r2-s2-2-space-created')
  })

  test('S2b 切到新空间 + 控制台验证 vid 口径与空目录', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-query')

    const rows = await runConsoleUi(page, `SHOW CREATE SPACE ${SPACE}`)
    const flat = rows.map((r) => r.join(' ')).join('\n')
    expect(flat).toContain('FIXED_STRING(256)')
    await shot(page, 'r2-s2-3-show-create-space')

    const tags = await runConsoleUi(page, 'SHOW TAGS')
    expect(tags.length).toBe(0) // 空壳：本目录由前端新建（阶段 4/5）
    const edges = await runConsoleUi(page, 'SHOW EDGES')
    expect(edges.length).toBe(0)
    await shot(page, 'r2-s2-4-empty-tags')
  })
})
