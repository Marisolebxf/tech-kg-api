import { expect, test } from '@playwright/test'
import { apiMust } from './helpers'

const RUNNING = new Set(['RUNNING'])
const FAILED = new Set(['FAILED', 'CANCELED', 'TERMINATED', 'TIMED_OUT'])

/** 与前端 deriveJobUnifiedStatus 同口径（workflowOperations.ts:469）。 */
function deriveUnified(job: { status?: string; lastExecutionStatus?: string }): string {
  if (job.lastExecutionStatus && RUNNING.has(job.lastExecutionStatus)) return '运行中'
  if (job.status === '暂停') return '已暂停'
  if (job.lastExecutionStatus === 'COMPLETED') return '已完成'
  if (job.lastExecutionStatus && FAILED.has(job.lastExecutionStatus)) return '运行失败'
  return '未运行'
}

test.describe('A. 平台总览 /overview', () => {
  test('A1 总览真实数据卡加载（hero/资产/构建胶囊/审核面板与 API 一致）', async ({ page, request }) => {
    const overview = await apiMust<any>(request, 'GET', '/platform/overview', undefined, '总览')
    const jobsData = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
    const jobs: any[] = jobsData.items ?? []
    const counts: Record<string, number> = { 未运行: 0, 运行中: 0, 已暂停: 0, 已完成: 0, 运行失败: 0 }
    for (const job of jobs) counts[deriveUnified(job)] = (counts[deriveUnified(job)] ?? 0) + 1

    await page.goto('/overview')
    await page.waitForLoadState('networkidle')

    // hero：平台状态 · N 个批次待处理 · 实时/降级徽标
    await expect(page.getByRole('heading', { name: '亿级科技知识图谱平台' })).toBeVisible()
    const badge = page.locator('.platform-hero__actions span').first()
    await expect(badge).toBeVisible()
    const badgeText = await badge.innerText()
    expect(badgeText).toContain('个批次待处理')
    expect(
      ['实时数据', '部分实时', '降级数据', '正在加载平台状态'].some((t) => badgeText.includes(t)),
      `hero 徽标应含实时/降级状态之一，实际：${badgeText}`,
    ).toBe(true)
    expect(badgeText).toContain(String(overview.pendingBatchCount))

    // 当前图谱资产面板：数字非空（总量与 API 一致）
    const assetPanel = page.locator('section.platform-structure-overview')
    await expect(assetPanel).toBeVisible()
    const assetText = await assetPanel.innerText()
    expect(assetText).toContain('实体分类占比')
    for (const group of overview.assetOverviewGroups ?? []) {
      if (group.total && group.total !== '--') expect(assetText).toContain(group.total)
    }

    // 图谱构建四胶囊与 API 计数一致
    const buildPanel = page.locator('.platform-jobs-panel')
    await expect(buildPanel).toBeVisible()
    for (const label of ['运行中', '已完成', '运行失败', '已暂停']) {
      const pill = buildPanel.locator('article', { hasText: label }).first()
      await expect(pill).toBeVisible()
      const value = Number((await pill.innerText()).replace(/[^\d]/g, ' ').trim().split(/\s+/)[0] ?? '-1')
      expect(Number.isFinite(value) && value >= 0, `胶囊 ${label} 计数非负`).toBe(true)
      expect(value, `胶囊 ${label} 与 /jobs 推导计数一致`).toBe(counts[label] ?? 0)
    }

    // 人工审核面板：队列数据或空态，不报错
    const reviewPanel = page.locator('.platform-review-panel')
    await expect(reviewPanel).toBeVisible()
    const reviewText = await reviewPanel.innerText()
    expect(
      ['待处理', '当前没有待审核任务', '审核队列加载中', '审核队列暂不可用', '暂无审核权限'].some((t) =>
        reviewText.includes(t),
      ),
      '审核面板应有队列数据或空态文案',
    ).toBe(true)
  })

  test('A2 今日图谱数据变化弹窗可开可关', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    const btn = page.getByRole('button', { name: '查看今日新增 →' }).first()
    await btn.click()
    // 抽屉标题为 span（非 heading role）：今日图谱数据变化 + 动态 h2 明细
    await expect(page.locator('.asset-change-drawer').getByText('今日图谱数据变化')).toBeVisible()
    await expect(page.locator('.asset-change-drawer h2').first()).toBeVisible()
    // 关闭（点抽屉头部 ×；mask 层会被抽屉拦截指针事件）
    await page.locator('.asset-change-drawer header button').click()
    await expect(page.locator('.asset-change-drawer')).toBeHidden()
  })

  test('A3 三个跳转入口（查看任务/查看全部任务/查看处理队列）', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')

    await page.getByRole('link', { name: '查看任务' }).first().click()
    await page.waitForURL('**/graph-build')
    await expect(page.getByRole('heading', { name: '图谱构建' })).toBeVisible()

    await page.goBack()
    await page.waitForLoadState('networkidle')
    await page.getByRole('link', { name: '查看全部任务 →' }).first().click()
    await page.waitForURL('**/graph-build')
    await expect(page.getByRole('heading', { name: '图谱构建' })).toBeVisible()

    await page.goBack()
    await page.waitForLoadState('networkidle')
    await page.getByRole('link', { name: '查看处理队列 →' }).first().click()
    await page.waitForURL('**/manual-review')
    await expect(page.getByText('入库决策').first()).toBeVisible()
  })
})
