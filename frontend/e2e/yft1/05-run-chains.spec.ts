import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, sleep, switchGraphSpace } from './helpers'

// 阶段 6b：前端依次触发三链并等终态（手册 §5 顺序：实体 → 关系A → 关系B，
// 串行依赖——边引用点，必须等前一条终态）。预期终态「运行异常」（ABNORMAL =
// 行级失败转人工审核），硬失败才是「运行失败」。
// 轮询方式：周期 reload 任务中心读状态列（纯读操作；触发本身经 UI 执行按钮）。

const TERMINAL = /运行异常|已完成|运行失败/
const CHAIN_NAMES = [`还原-实体@${SPACE}`, `还原-关系A@${SPACE}`, `还原-关系B@${SPACE}`]

async function openBuild(page: Page): Promise<void> {
  await page.goto('/overview')
  await page.waitForLoadState('networkidle')
  await switchGraphSpace(page, SPACE)
  await gotoRoute(page, '/graph-build')
  await page.locator('table tbody tr').first().waitFor()
}

/** 轮询某任务行状态列（第 6 列）直到终态；返回终态文本。 */
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

test.describe.serial('S6b 三链执行', () => {
  test('触发实体链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    const row = page.locator('table tbody tr', { hasText: CHAIN_NAMES[0] }).first()
    await expect(row.locator('td').nth(5)).toHaveText(/未运行/)
    await row.locator('button.primary', { hasText: '执行' }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })
    await shot(page, 's6-4-entity-chain-running')

    const final = await waitTerminal(page, CHAIN_NAMES[0], 45 * 60_000)
    expect(final).toBe('运行异常') // ABNORMAL 预期口径
    await shot(page, 's6-5-entity-chain-final')
    // 详情页取证（行内「查看详情」按钮 → /graph-build/jobs/:jobId）
    await row.locator('button', { hasText: '查看详情' }).click()
    await page.waitForURL(/\/graph-build\/jobs\//, { timeout: 20_000 })
    await page.waitForTimeout(2_500)
    await shot(page, 's6-6-entity-chain-detail')
  })

  test('触发关系A链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    const row = page.locator('table tbody tr', { hasText: CHAIN_NAMES[1] }).first()
    await row.locator('button.primary', { hasText: '执行' }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })

    const final = await waitTerminal(page, CHAIN_NAMES[1], 45 * 60_000)
    expect(final).toBe('运行异常')
    await shot(page, 's6-7-rela-chain-final')
  })

  test('触发关系B链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    const row = page.locator('table tbody tr', { hasText: CHAIN_NAMES[2] }).first()
    await row.locator('button.primary', { hasText: '执行' }).click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })

    const final = await waitTerminal(page, CHAIN_NAMES[2], 45 * 60_000)
    expect(final).toBe('运行异常')
    await shot(page, 's6-8-relb-chain-final')
  })
})
