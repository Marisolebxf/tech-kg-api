import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, switchGraphSpace, waitFor } from './helpers'

// 阶段 5：前端 Schema 管理验证——切到 yunfei_test_1 后，目录里的 49 个 schema
// （16 实体 + 33 关系，control 库 kg_schema_definition）应全部列出。
// 列表为服务端分页（每页 10，ListPagination「共 N 条」）——验收看总数 + 翻页行数。

test.describe.serial('S5 Schema 管理验证', () => {
  test('S5 列出全部 49 个 schema（16 实体 + 33 关系）', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/schema')

    // 实体页签（默认）：首页 10 行 + 总数 16
    await page.locator('.schema-entity-table tbody tr').first().waitFor()
    await expect(page.locator('.list-pagination__summary')).toHaveText(/共 16 条/)
    expect(await page.locator('.schema-entity-table tbody tr').count()).toBe(10)
    // 翻到第 2 页补齐剩余 6 行（arco 分页项）
    await page.locator('.arco-pagination-item', { hasText: '2' }).first().click()
    await waitFor(
      async () => (await page.locator('.schema-entity-table tbody tr').count()) === 6,
      { timeout: 20_000, label: '实体第 2 页 6 行' },
    )
    await shot(page, 's5-1-schema-entities')

    // 关系页签：总数 33
    await page.locator('.schema-tabs button', { hasText: '关系' }).first().click()
    await waitFor(async () => (await page.locator('.schema-relation-table tbody tr').count()) > 0, {
      timeout: 20_000,
      label: '关系表首屏',
    })
    await expect(page.locator('.list-pagination__summary')).toHaveText(/共 33 条/)
    expect(await page.locator('.schema-relation-table tbody tr').count()).toBe(10)
    await shot(page, 's5-2-schema-relations')
  })
})
