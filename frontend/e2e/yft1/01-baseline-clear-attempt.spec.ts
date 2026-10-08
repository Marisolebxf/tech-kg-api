import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, runConsoleUi, shot, switchGraphSpace } from './helpers'

// 阶段 0/1：基线取证 + 前端「清场」尝试（手册 §3 清场要求 DROP 图空间/向量库/水位）。
// 本阶段只做前端能做的事，并把做不到的当场取证，供问题记录引用截图。
// nGQL 控制台在 /graph-query（综合查询）页；全局图空间选择器只在 /overview 面包屑。
test.describe.serial('S0/S1 基线与前端清场尝试', () => {
  test('S0 工作台控制台基线：yunfei_test_1 在且有数据', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-query')

    const spaces = await runConsoleUi(page, 'SHOW SPACES')
    expect(spaces.some((r) => r.some((c) => c.includes(SPACE)))).toBeTruthy()
    await shot(page, 's0-1-show-spaces')

    const tags = await runConsoleUi(page, 'SHOW TAGS')
    expect(tags.length).toBeGreaterThanOrEqual(16) // 上轮重建预建口径：≥16 TAG
    await shot(page, 's0-2-show-tags')

    // SHOW STATS 读上次统计快照（SUBMIT JOB STATS 属管理语句，控制台禁执行——见问题记录）
    const stats = await runConsoleUi(page, 'SHOW STATS')
    expect(stats.length).toBeGreaterThan(0)
    await shot(page, 's0-3-show-stats')
  })

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
    await page.waitForTimeout(600) // 等 toast 渲染后截图取证
    await shot(page, 's1a-console-drop-space-rejected')
  })

  test('S1b 配置管理·图数据空间：无删除/清空入口', async ({ page }) => {
    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '图数据空间' }).click()
    await page.waitForTimeout(800)

    // 只有「新建/绑定」，无任何删除、解绑、清空类按钮
    await expect(page.getByRole('button', { name: '＋ 新建图数据空间' })).toBeVisible()
    const dangerButtons = await page
      .locator('.space-table button, .space-table a, .bind-nav button')
      .filter({ hasText: /删除|解绑|清空|销毁|DROP/ })
      .count()
    expect(dangerButtons).toBe(0)
    // 空间行内也没有任何操作按钮（表只展示）
    const rowButtons = await page.locator('.space-table tbody tr button').count()
    expect(rowButtons).toBe(0)
    await shot(page, 's1b-config-space-no-delete')
  })
})
