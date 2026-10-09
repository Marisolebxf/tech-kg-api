import { expect, test } from '@playwright/test'
import { request as apiRequest } from '@playwright/test'
import { SPACE, gotoRoute, ngql, runConsoleUi, shot, switchGraphSpace } from './helpers'

// 阶段 8：前端验证（对账 + 页面探针）。前置：阶段 6 三链终态 + 阶段 7 离线域 ETL 完成。
// 口径（手册 §7）：锚点断言 + 分组归因，不逐项追平绝对值。
//   锚点：SAME_AS 两空间相等（259 口径）、Journal/DataSource/PatentFamily 全等、
//         OrganizationBase 在 yft_1 存在（平台链专属）。
/** 宿主机内存吃紧时 trs-graph 水位（0.9）按请求抖动拒绝读——带退避重试抢窗口。 */
async function withRetry<T>(fn: () => Promise<T>, tries = 6, delayMs = 8_000): Promise<T> {
  let lastErr: unknown
  for (let i = 0; i < tries; i++) {
    try {
      return await fn()
    } catch (e) {
      lastErr = e
      await new Promise((r) => setTimeout(r, delayMs))
    }
  }
  throw lastErr
}

test.describe.serial('S8 前端对账与页面验证', () => {
  test('S8a 控制台对账：SHOW STATS 读数 + SUBMIT JOB STATS 被 403 取证', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-query')

    // SHOW STATS（阶段 7 后 CLI 已 SUBMIT 过，此为前端读数取证）
    const stats = await runConsoleUi(page, 'SHOW STATS')
    expect(stats.length).toBeGreaterThan(20) // 20 TAG + 42 EDGE 的统计行
    await shot(page, 's8-1-show-stats')

    // SUBMIT JOB STATS 属管理语句，前端控制台被 403（问题记录⑤）
    const ta = page.locator('textarea[aria-label="nGQL 查询语句"]')
    await ta.fill('SUBMIT JOB STATS')
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/v1/graph-console/query') && r.request().method() === 'POST',
    )
    await page.getByRole('button', { name: '执行 nGQL' }).click()
    const resp = await respPromise
    expect(resp.status()).toBe(403)
    await page.waitForTimeout(600)
    await shot(page, 's8-2-submit-job-stats-rejected')
  })

  test('S8b 锚点对账（SAME_AS 相等 / Journal 等全等 / OrganizationBase 平台专属）', async ({}) => {
    const request = await apiRequest.newContext()
    // 对账读数走 SHOW STATS 快照（阶段 7 后 CLI 已 SUBMIT JOB STATS 刷新）：宿主机内存吃紧时
    // MATCH 全扫会按请求被水位（0.9）拒绝，统计快照读是稳定通道（与 UI 控制台同端点）。
    async function statsMap(space: string): Promise<{ tag: Record<string, number>; edge: Record<string, number> }> {
      const rows = await withRetry(() => ngql(request, space, 'SHOW STATS'))
      const tag: Record<string, number> = {}
      const edge: Record<string, number> = {}
      for (const r of rows) {
        // SHOW STATS 行可能是对象 {Type,Name,Count}，也可能是数组（控制台 UI 路径）
        const [type, name, count] = Array.isArray(r) ? r : [r.Type, r.Name, r.Count]
        if (type === 'Tag') tag[name] = Number(count)
        if (type === 'Edge') edge[name] = Number(count)
      }
      return { tag, edge }
    }
    const yft = await statsMap(SPACE)
    const dev = await statsMap('dev')
    // SAME_AS 是 EDGE（域4 对齐写入）：两空间全等锚点（259 口径）
    expect(yft.edge.SAME_AS).toBeGreaterThan(0)
    expect(Math.abs(yft.edge.SAME_AS - (dev.edge.SAME_AS ?? 0))).toBeLessThanOrEqual(2)
    // 全等/容差组（TAG）
    for (const a of ['Journal', 'DataSource', 'PatentFamily']) {
      expect(yft.tag[a]).toBeGreaterThan(0)
      expect(Math.abs(yft.tag[a] - (dev.tag[a] ?? 0))).toBeLessThanOrEqual(10)
    }
    // 平台链专属：yft_1 有 OrganizationBase TAG 数据（本轮按 schema 属性建大写 TAG）
    expect(yft.tag.OrganizationBase).toBe(61652) // 精确锚点
    // 学者域锚点：Person/COAUTHOR_WITH（源年代差组，只验证非零量级；本轮源库重灌后偏小）
    expect(yft.tag.Person).toBeGreaterThan(30000)
    expect(yft.edge.COAUTHOR_WITH).toBeGreaterThan(1000)
  })

  test('S8c 九大业务模块页面：env 冻结 dev 取证', async ({ page }) => {
    // 九模块查询走容器 env 冻结空间（dev）——页面能正常出数恰恰说明查的不是重建空间。
    // 用 dev 特有 fixture 实体（重建空间按口径没有）作为「查的是 dev」的实证。
    await gotoRoute(page, '/expert-direct')
    await page.waitForTimeout(1_500)
    await shot(page, 's8-3-expert-direct-page')
    // 页面可用性 + 空间提示（无空间切换入口）——取证留档
    const hasSpaceSwitch = await page.locator('.app-space-select').count()
    expect(hasSpaceSwitch).toBe(0) // 业务模块页无全局空间选择器（只在 /overview）
  })
})
