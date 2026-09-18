import { expect, test } from '@playwright/test'
import { switchGraphSpace, waitFor } from './helpers'

// B. 图谱查询（/graph-query，PlatformWorkbenchView 的 query Tab）
// 参数模式已移除：查询页签收敛为「nGQL 模式 | 图算法」。
test.describe('B. 图谱查询', () => {
  test('B1 nGQL 模式执行（Ctrl+Enter + 按钮，两种结果态）', async ({ page }) => {
    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: 'nGQL 模式' }).click()

    // nGQL 面板内已无图空间控件：执行空间跟随顶栏全局选择器
    await expect(page.locator('.platform-ngql-input__space-field')).toHaveCount(0)
    await switchGraphSpace(page, 'dev2')

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

  test('B2 图算法 tab（mock 提交→轮询→PageRank 排名表全链路）', async ({ page }) => {
    // 作业三接口用 route mock（Spark 运行器未就绪，真实提交必然失败）：
    // 提交回 running，轮询第一轮 running、之后 succeeded，结果 2 行 csv。
    // metadata / engine 不 mock，走真实 dev2 接口（引擎徽标对 正常/不可用 均兼容）。
    // 排名表节点类型解析（nodes）同样 mock。
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
    // 排名表节点名称/类型解析：p1/p2 → Paper
    await page.route(/\/api\/v1\/graph-search\/nodes\/[^/]+(?:\?.*)?$/, async (route) => {
      const vid = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '')
      await route.fulfill({
        json: ok({
          id: vid,
          labels: ['Paper'],
          properties: { name: vid === 'p2' ? '高影响力论文' : '普通论文' },
        }),
      })
    })

    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')

    // 默认落在 nGQL 模式：结果区常驻（未执行时空数据占位）；切到图算法 tab 出面板
    await expect(page.getByRole('heading', { name: 'nGQL 执行结果' })).toBeVisible()
    await expect(page.getByText('暂无数据，执行 nGQL 语句后在此查看结果')).toBeVisible()
    // 图算法边类型/引擎状态按全局图空间加载：先切到 dev2 再进图算法面板
    await switchGraphSpace(page, 'dev2')
    await page.getByRole('button', { name: '图算法' }).click()
    // 面板无独立标题行：算法页签并入头部行，以「算法切换」导航可见作为出面板标志
    await expect(page.getByRole('navigation', { name: '算法切换' })).toBeVisible()

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

    // 业务输入保留，高级参数入口及执行提示已移除。
    await expect(page.locator('.platform-query-algo__labels')).toBeVisible()
    await expect(page.locator('.platform-query-algo__advanced')).toHaveCount(0)
    await expect(page.locator('.platform-query-algo__actions-hint')).toHaveCount(0)

    // 边类型多选（真实 metadata）：选 HAS_KEYWORD；dev2 边类型较多、弹层内需滚动，
    // Escape 不再收起（焦点停在选项上），点面板外区域关闭弹层
    await page.locator('.platform-query-algo__labels .arco-select-view').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'HAS_KEYWORD' }).first().click()
    await page.locator('.platform-query-algo__desc').click()

    // 提交 → 轮询（3s 间隔，两轮内到 succeeded）→ 节点重要性排名表
    await page.getByRole('button', { name: '提交算法作业' }).click()
    await waitFor(
      async () => (await page.getByRole('heading', { name: '节点重要性排名' }).isVisible().catch(() => false)),
      { label: '节点重要性排名面板' },
    )
    await expect(page.getByText('2 行记录')).toBeVisible()
    // 排名列（p2 分值 0.20 → 第 1 名在前）、节点名称与类型（经 nodes 接口解析）
    const rankTable = page.locator('table[aria-label="PageRank 节点重要性排名"]')
    await expect(rankTable).toContainText('高影响力论文')
    await waitFor(
      async () => (await rankTable.getByText('Paper').first().isVisible().catch(() => false)),
      { label: '排名表节点类型解析' },
    )
    await expect(rankTable).toContainText('0.15')
    // 结果区只保留排名表：图谱高亮面板已移除
    await expect(page.locator('.platform-query-algo__highlight')).toHaveCount(0)
    await expect(page.getByText('作业 job-e2e-1')).toBeVisible()

    // 切回 nGQL 模式恢复输入面板
    await page.getByRole('button', { name: 'nGQL 模式' }).click()
    await expect(page.locator('textarea[placeholder*="MATCH (v:专家)"]')).toBeVisible()
  })

  test('B3 Louvain 社区发现（mock 提交→节点→社区表）', async ({ page }) => {
    // 作业三接口 + 节点解析接口 route mock；Louvain 结果视图无子图查询。
    const ok = (data: unknown) => ({ code: 200, success: true, data, msg: 'success' })
    let pollCount = 0

    await page.route('**/api/v1/graph-algorithms/jobs', async (route) => {
      const request = route.request()
      if (request.method() !== 'POST') {
        await route.continue()
        return
      }
      const body = request.postDataJSON() as {
        algorithm: string
        labels: string[]
        params?: Record<string, number | string | boolean>
      }
      expect(body.algorithm).toBe('louvain')
      // 调优参数不在页面暴露：提交载荷不带 params，由服务端默认值兜底
      expect(body.params).toBeUndefined()
      await route.fulfill({ json: ok({ jobId: 'job-e2e-3', status: 'running' }) })
    })
    await page.route(/\/api\/v1\/graph-algorithms\/jobs\/job-e2e-3\/result(?:\?.*)?$/, async (route) => {
      await route.fulfill({
        json: ok({
          jobId: 'job-e2e-3',
          sink: 'csv',
          rows: [
            { vid: 'e1', louvain: '2' },
            { vid: 'e2', louvain: '2' },
            { vid: 'e3', louvain: '2' },
            { vid: 'p1', louvain: '5' },
          ],
          count: 4,
          truncated: false,
        }),
      })
    })
    await page.route(/\/api\/v1\/graph-algorithms\/jobs\/job-e2e-3(?:\?.*)?$/, async (route) => {
      pollCount += 1
      await route.fulfill({
        json: ok(
          pollCount === 1
            ? { jobId: 'job-e2e-3', status: 'running' }
            : { jobId: 'job-e2e-3', status: 'succeeded', finishedAt: '2026-09-17T09:00:10Z' },
        ),
      })
    })
    await page.route(/\/api\/v1\/graph-search\/nodes\/[^/]+(?:\?.*)?$/, async (route) => {
      const vid = decodeURIComponent(new URL(route.request().url()).pathname.split('/').pop() ?? '')
      const isExpert = vid.startsWith('e')
      await route.fulfill({
        json: ok({
          id: vid,
          labels: [isExpert ? 'Scholar' : 'Paper'],
          properties: { name: isExpert ? `专家${vid}` : `论文${vid}` },
        }),
      })
    })

    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, 'dev2')
    await page.getByRole('button', { name: '图算法' }).click()
    await page.getByRole('button', { name: 'Louvain算法' }).click()
    await expect(page.getByText('Louvain算法：', { exact: false })).toBeVisible()

    // 调优参数使用默认值，页面只展示关系类型。
    await expect(page.locator('.platform-query-algo__labels')).toBeVisible()
    await expect(page.locator('.platform-query-algo__advanced')).toHaveCount(0)

    // 选边类型并提交 → 轮询两轮到 succeeded → 社区发现结果
    await page.locator('.platform-query-algo__labels .arco-select-view').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'HAS_KEYWORD' }).first().click()
    await page.locator('.platform-query-algo__desc').click()
    await page.getByRole('button', { name: '提交算法作业' }).click()

    await waitFor(
      async () => (await page.getByRole('heading', { name: '社区发现结果' }).isVisible().catch(() => false)),
      { label: '社区发现结果面板' },
    )
    await expect(page.getByText('4 行记录')).toBeVisible()

    // 节点→社区表：按社区规模降序（社区 2 的三行在前），类型解析后显示 Scholar/Paper
    const table = page.locator('table[aria-label="Louvain 节点社区归属"]')
    await expect(table).toContainText('专家e1')
    await waitFor(
      async () => (await table.getByText('Scholar').first().isVisible().catch(() => false)),
      { label: '社区表节点类型解析' },
    )
    await expect(table).toContainText('2')
    await expect(table).toContainText('5')

    // 结果区只保留节点→社区表：社区图谱与社区列表已移除
    await expect(page.locator('.platform-query-algo__highlight')).toHaveCount(0)
    await expect(page.locator('.platform-query-algo__community-list')).toHaveCount(0)
  })
})
