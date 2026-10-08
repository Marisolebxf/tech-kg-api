import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, switchGraphSpace } from './helpers'

// 阶段 1：清场取证（CLI 清场在上一轮已记为问题①，本轮复取证保持记录自包含）。
// ① nGQL 控制台 DROP SPACE 被 DDL 禁令拒；② 配置管理图数据空间无删除/清空入口。
test.describe.serial('S1 前端清场取证', () => {
  test('S1a 控制台尝试 DROP SPACE → 被 DDL 禁令拒绝', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-query')

    const ta = page.locator('textarea[aria-label="nGQL 查询语句"]')
    await ta.scrollIntoViewIfNeeded()
    await ta.fill(`DROP SPACE IF EXISTS ${SPACE}`)
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/v1/graph-console/query') && r.request().method() === 'POST',
    )
    await page.getByRole('button', { name: '执行 nGQL' }).click()
    const resp = await respPromise
    expect(resp.status()).toBe(403)
    const body = await resp.json()
    expect(JSON.stringify(body)).toContain('禁止执行 DDL')
    await page.waitForTimeout(600)
    await shot(page, 'r2-s1a-console-drop-space-rejected')
  })

  test('S1b 配置管理·图数据空间：无删除/清空入口', async ({ page }) => {
    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '图数据空间' }).click()
    await page.waitForTimeout(800)

    await expect(page.getByRole('button', { name: '＋ 新建图数据空间' })).toBeVisible()
    const dangerButtons = await page
      .locator('.space-table button, .space-table a, .bind-nav button')
      .filter({ hasText: /删除|解绑|清空|销毁|DROP/ })
      .count()
    expect(dangerButtons).toBe(0)
    const rowButtons = await page.locator('.space-table tbody tr button').count()
    expect(rowButtons).toBe(0)
    await shot(page, 'r2-s1b-config-space-no-delete')
  })
})
