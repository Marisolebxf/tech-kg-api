import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, sleep, switchGraphSpace } from './helpers'

// 阶段 6b-修复轮2：关系A 首轮因 dev 瘦化 EDGE 缺治理列（update_time 等）硬失败；
// CLI 已按 schema 属性补齐 48 个 TAG/EDGE 缺列。走前端「重新执行」重跑关系A→关系B。
const TERMINAL = /运行异常|已完成|运行失败/

async function waitTerminal(page: Page, name: string, timeoutMs: number): Promise<string> {
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

async function openBuild(page: Page): Promise<void> {
  await page.goto('/overview')
  await page.waitForLoadState('networkidle')
  await switchGraphSpace(page, SPACE)
  await gotoRoute(page, '/graph-build')
  await page.locator('table tbody tr').first().waitFor()
}

test.describe.serial('S6b-修复2 关系链重跑', () => {
  test('重新执行关系A并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    const name = `还原-关系A@${SPACE}`
    const row = page.locator('table tbody tr', { hasText: name }).first()
    await expect(row.locator('td').nth(5)).toHaveText(/运行失败/)
    await row.locator('button.primary', { hasText: '重新执行' }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })

    const final = await waitTerminal(page, name, 45 * 60_000)
    // 终态口径：行级零失败=已完成；有行级失败转审核=运行异常。本轮小源库实测直接 COMPLETED。
    expect(final).toMatch(/已完成|运行异常/)
    await shot(page, 's6-7b-rela-rerun-final')
  })
})
