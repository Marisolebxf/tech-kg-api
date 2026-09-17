import { expect, test } from '@playwright/test'
import { waitFor } from './helpers'

// B. 图谱查询（/graph-query，PlatformWorkbenchView 的 query Tab）
// 参数模式已移除：查询页签收敛为「nGQL 模式 | 图算法」。
test.describe('B. 图谱查询', () => {
  test('B1 nGQL 模式执行（Ctrl+Enter + 按钮，两种结果态）', async ({ page }) => {
    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: 'nGQL 模式' }).click()

    // nGQL 面板内图空间选 dev2
    await page.locator('.platform-ngql-input__space-field .arco-select-view-single').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'dev2' }).first().click()

    const textarea = page.locator('textarea[placeholder*="MATCH (v:专家)"]')
    // 第一条：5 行记录（Ctrl+Enter 提交）
    await textarea.fill('MATCH (v:Paper) RETURN id(v) AS vid LIMIT 5')
    await textarea.press('Control+Enter')
    await waitFor(
      async () => (await page.getByText('5 行记录').first().isVisible().catch(() => false)),
      { label: 'nGQL 5 行记录' },
    )
    await expect(page.getByRole('heading', { name: 'nGQL 执行结果' })).toBeVisible()

    // 第二条：执行成功无返回记录（按钮提交）
    await textarea.fill('MATCH (v:Paper) WHERE v.Paper.name == "__none__" RETURN v')
    await page.getByRole('button', { name: '执行 nGQL' }).click()
    await waitFor(
      async () => (await page.getByText('语句执行成功，无返回记录').first().isVisible().catch(() => false)),
      { label: 'nGQL 空结果文案' },
    )
  })

  test('B2 图算法 tab（mock 提交→轮询→结果全链路）', async ({ page }) => {
    // 作业三接口用 route mock（Spark 运行器未就绪，真实提交必然失败）：
    // 提交回 running，轮询第一轮 running、之后 succeeded，结果 2 行 csv。
    // metadata / engine 不 mock，走真实 dev2 接口（引擎徽标对 正常/不可用 均兼容）。
    const ok = (data: unknown) => ({ code: 200, success: true, data, msg: 'success' })
    let pollCount = 0

    await page.route('**/api/v1/graph-algorithms/jobs', async (route) => {
      const request = route.request()
      if (request.method() !== 'POST') {
        await route.continue()
        return
      }
      const body = request.postDataJSON() as { algorithm: string; labels: string[] }
      expect(body.algorithm).toBe('pagerank')
      expect(body.labels).toContain('HAS_KEYWORD')
      await route.fulfill({ json: ok({ jobId: 'job-e2e-1', status: 'running' }) })
    })
    // 注意：GET 带查询串（?space=…），glob 按「含查询串的完整 URL」匹配会漏，
    // 必须用正则并显式兼容尾部查询串。
    await page.route(/\/api\/v1\/graph-algorithms\/jobs\/job-e2e-1\/result(?:\?.*)?$/, async (route) => {
      await route.fulfill({
        json: ok({
          jobId: 'job-e2e-1',
          sink: 'csv',
          rows: [
            { vid: 'p1', pagerank: '0.15' },
            { vid: 'p2', pagerank: '0.20' },
          ],
          count: 2,
          truncated: false,
        }),
      })
    })
    await page.route(/\/api\/v1\/graph-algorithms\/jobs\/job-e2e-1(?:\?.*)?$/, async (route) => {
      pollCount += 1
      await route.fulfill({
        json: ok(
          pollCount === 1
            ? { jobId: 'job-e2e-1', status: 'running' }
            : { jobId: 'job-e2e-1', status: 'succeeded', finishedAt: '2026-09-17T08:00:10Z' },
        ),
      })
    })

    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')

    // 默认落在 nGQL 模式：结果区常驻（未执行时空数据占位）；切到图算法 tab 出面板
    await expect(page.getByRole('heading', { name: 'nGQL 执行结果' })).toBeVisible()
    await expect(page.getByText('暂无数据，执行 nGQL 语句后在此查看结果')).toBeVisible()
    await page.getByRole('button', { name: '图算法' }).click()
    await expect(page.getByRole('heading', { name: '图算法' })).toBeVisible()

    // 引擎徽标必渲染（Spark 未就绪时为「不可用」，就绪后为「正常」，均为通过态）
    await waitFor(
      async () => (await page.getByText(/^算法引擎(正常|不可用)$/).isVisible().catch(() => false)),
      { label: '算法引擎状态徽标' },
    )

    // 三个算法页签（对齐人工审核「抽取失败重跑」二级子页签样式）：默认 PageRank，切换后描述联动
    await expect(page.getByRole('button', { name: 'PageRank算法' })).toBeVisible()
    await expect(page.getByText('PageRank算法：', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: 'Louvain算法' }).click()
    await expect(page.getByText('Louvain算法：', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: 'Degree算法' }).click()
    await expect(page.getByText('Degree算法：', { exact: false })).toBeVisible()
    await page.getByRole('button', { name: 'PageRank算法' }).click()

    // 边类型多选（真实 metadata）：选 HAS_KEYWORD
    await page.locator('.platform-query-algo__labels .arco-select-view').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'HAS_KEYWORD' }).first().click()
    await page.keyboard.press('Escape')

    // 提交 → 轮询（3s 间隔，两轮内到 succeeded）→ 结果表
    await page.getByRole('button', { name: '提交算法作业' }).click()
    await waitFor(
      async () => (await page.getByRole('heading', { name: '算法执行结果' }).isVisible().catch(() => false)),
      { label: '算法执行结果面板' },
    )
    await expect(page.getByText('2 行记录')).toBeVisible()
    await expect(page.locator('table[aria-label="图算法执行结果"]')).toContainText('0.15')
    await expect(page.getByText('作业 job-e2e-1')).toBeVisible()

    // 切回 nGQL 模式恢复输入面板
    await page.getByRole('button', { name: 'nGQL 模式' }).click()
    await expect(page.locator('textarea[placeholder*="MATCH (v:专家)"]')).toBeVisible()
  })
})
