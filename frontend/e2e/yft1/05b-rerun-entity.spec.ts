import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, sleep, switchGraphSpace } from './helpers'

// 阶段 6b-修复轮：实体链首轮因 OrganizationBase TAG 大小写硬失败（dev 现网 TAG 已小写化，
// 平台链按 schema 名大写写图 → No schema found → retry 耗尽整链 FAILED）。
// CLI 已按 schema 属性建大写 TAG；本用例走前端「重新执行」按钮（运行失败态提供入口）
// 重跑整链——已跑环水位顶到头只抽增量，OrganizationBase 环（水位已清）全量补抽。
const TERMINAL = /运行异常|已完成|运行失败/

async function waitTerminal(page: import('@playwright/test').Page, name: string, timeoutMs: number): Promise<string> {
  const deadline = Date.now() + timeoutMs
  let last = ''
  while (Date.now() < deadline) {
    const row = page.locator('table tbody tr', { hasText: name }).first()
    if (await row.isVisible().catch(() => false)) {
      last = (await row.locator('td').nth(5).innerText().catch(() => '')) || ''
      if (TERMINAL.test(last)) return last.trim()
    }
    await sleep(30_000)
    await page.reload()
    await page.locator('table tbody tr').first().waitFor().catch(() => {})
  }
  throw new Error(`等待任务终态超时: ${name} 最后状态「${last}」`)
}

test.describe.serial('S6b-修复 实体链重跑', () => {
  test('重新执行实体链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-build')
    await page.locator('table tbody tr').first().waitFor()

    const name = `还原-实体@${SPACE}`
    const row = page.locator('table tbody tr', { hasText: name }).first()
    await expect(row.locator('td').nth(5)).toHaveText(/运行失败/)
    await row.getByRole('button', { name: '重新执行', exact: true }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })
    await shot(page, 's6-4b-entity-rerun-running')

    const final = await waitTerminal(page, name, 45 * 60_000)
    expect(final, '修复后应到达 ABNORMAL/COMPLETED，而非硬失败').toMatch(/运行异常|已完成/)
    await shot(page, 's6-5b-entity-rerun-final')

    await row.locator('button', { hasText: '查看详情' }).click()
    await page.waitForURL(/\/graph-build\/jobs\//, { timeout: 20_000 })
    await page.waitForTimeout(2_500)
    await shot(page, 's6-6b-entity-chain-detail')
  })

  test('触发关系A链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-build')
    await page.locator('table tbody tr').first().waitFor()

    const name = `还原-关系A@${SPACE}`
    const row = page.locator('table tbody tr', { hasText: name }).first()
    await expect(row.locator('td').nth(5)).toHaveText(/未运行/)
    await row.getByRole('button', { name: '执行', exact: true }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })

    const final = await waitTerminal(page, name, 45 * 60_000)
    expect(final).toBe('运行异常')
    await shot(page, 's6-7-rela-chain-final')
  })

  test('触发关系B链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-build')
    await page.locator('table tbody tr').first().waitFor()

    const name = `还原-关系B@${SPACE}`
    const row = page.locator('table tbody tr', { hasText: name }).first()
    await expect(row.locator('td').nth(5)).toHaveText(/未运行/)
    await row.getByRole('button', { name: '执行', exact: true }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })

    const final = await waitTerminal(page, name, 45 * 60_000)
    expect(final).toBe('运行异常')
    await shot(page, 's6-8-relb-chain-final')
  })
})
