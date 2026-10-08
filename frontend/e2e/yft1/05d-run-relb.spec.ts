import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, sleep, switchGraphSpace } from './helpers'

// 阶段 6b-修复轮3：关系B（未运行态首次触发）。终态口径同 05c：
// 已完成（行级零失败）/ 运行异常（行级失败转审核）均算通过，运行失败=硬失败才算缺陷。
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

test.describe.serial('S6b-修复3 关系B触发', () => {
  test('触发关系B并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    const name = `还原-关系B@${SPACE}`
    const row = page.locator('table tbody tr', { hasText: name }).first()
    await expect(row.locator('td').nth(5)).toHaveText(/未运行/)
    await row.getByRole('button', { name: '执行', exact: true }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })

    const final = await waitTerminal(page, name, 45 * 60_000)
    expect(final).toMatch(/已完成|运行异常/)
    await shot(page, 's6-8b-relb-final')

    // 三链终态全家福 + 关系B 详情页取证
    await shot(page, 's6-9-all-chains-final')
    await row.locator('button', { hasText: '查看详情' }).click()
    await page.waitForURL(/\/graph-build\/jobs\//, { timeout: 20_000 })
    await page.waitForTimeout(2_500)
    await shot(page, 's6-10-relb-chain-detail')
  })
})
