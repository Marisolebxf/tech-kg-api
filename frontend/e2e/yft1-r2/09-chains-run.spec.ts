import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, sleep, switchGraphSpace } from './helpers'

// 阶段 9：前端依次触发三链并等终态（手册 §5 顺序：实体 → 关系A → 关系B，
// 串行依赖——边脚本读图内既有实体做端点匹配）。
// 终态口径：接受 已完成|运行异常（ABNORMAL = 行级失败转人工审核，手册 §5 预期），
// 出现 运行失败 即硬失败，用例报错。
// 轮询方式：周期 reload 任务中心读状态列（纯读操作；触发本身经 UI 执行按钮）。
const TERMINAL = /运行异常|已完成|运行失败/
const HARD_FAIL = /运行失败/
const CHAIN_NAMES = [`还原2-实体@${SPACE}`, `还原2-关系A@${SPACE}`, `还原2-关系B@${SPACE}`]

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

/** 触发一条链并等终态；可续跑（研磨重试，⑫ 水位期常态）：
 *  - 已完成/运行异常 → 本轮已过账直接返回（已完成无重跑入口，问题②）；
 *  - 运行失败 → 「重新执行」（a36e70e7，重跑=水位增量续抽）；
 *  - 未运行 → 「执行」。 */
async function runChain(page: Page, name: string, shotPrefix: string): Promise<string> {
  const row = page.locator('table tbody tr', { hasText: name }).first()
  const state0 = ((await row.locator('td').nth(5).innerText().catch(() => '')) || '').trim()
  if (!/已完成|运行异常/.test(state0)) {
    expect(/未运行/.test(state0) || TERMINAL.test(state0), `${name} 初始态「${state0}」不可触发`).toBe(true)
    await row.getByRole('button', { name: /^(执行|重新执行)$/ }).first().click()
    await expect(row.locator('td').nth(5)).toHaveText(/运行中/, { timeout: 60_000 })
    await shot(page, `${shotPrefix}-running`)
  }
  const final = await waitTerminal(page, name, 45 * 60_000)
  expect(HARD_FAIL.test(final), `${name} 终态「${final}」`).toBe(false)
  await shot(page, `${shotPrefix}-final`)
  return final
}

test.describe.serial('S9 三链执行', () => {
  test('S9a 触发实体链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    await runChain(page, CHAIN_NAMES[0], 'r2-s9-1-entity-chain')
    // 详情页取证（行内「查看详情」按钮 → /graph-build/jobs/:jobId）
    const row = page.locator('table tbody tr', { hasText: CHAIN_NAMES[0] }).first()
    await row.locator('button', { hasText: '查看详情' }).click()
    await page.waitForURL(/\/graph-build\/jobs\//, { timeout: 20_000 })
    await page.waitForTimeout(2_500)
    await shot(page, 'r2-s9-3-entity-chain-detail')
  })

  test('S9b 触发关系A链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    await runChain(page, CHAIN_NAMES[1], 'r2-s9-4-rela-chain')
  })

  test('S9c 触发关系B链并等终态', async ({ page }) => {
    test.setTimeout(50 * 60_000)
    await openBuild(page)
    await runChain(page, CHAIN_NAMES[2], 'r2-s9-5-relb-chain')
  })
})
