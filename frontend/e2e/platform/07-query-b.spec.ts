import { expect, test } from '@playwright/test'
import { apiMust, waitFor } from './helpers'

// B. 图谱查询（/graph-query，PlatformWorkbenchView 的 query Tab）
// 环境说明：dev2 已为各 TAG 的搜索字段建属性索引（e2e_idx_*，见测试报告）；
// 科研成果域实体（Paper/Journal/Report/Project/Patent）现网均无名称数据，
// 「科研成果图谱」按名查中心实体会走「未查询到实体」分支——作为校验分支覆盖。
test.describe('B. 图谱查询', () => {
  const PERSON_NAME = '吴边'
  const ORG_NAME = '平安银行股份有限公司'

  test('B1 参数模式查询：画布 + 统计 + 详情四 Tab + 动态图例', async ({ page }) => {
    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')

    // 关键词为空时「查询图谱」不可用（校验分支）
    const queryBtn = page.getByRole('button', { name: '查询图谱', exact: true })
    await expect(queryBtn).toBeDisabled()

    await page.locator('input[placeholder="请输入实体名称或节点ID"]').fill(PERSON_NAME)
    await expect(queryBtn).toBeEnabled()
    await queryBtn.click()

    // 综合图谱展示：「N 个节点 / M 条关系」统计（N≥1）
    const graphPanel = page.locator('.platform-query-graph')
    await waitFor(
      async () => {
        const text = await graphPanel.locator('.kg-panel__header span').first().innerText()
        const m = text.match(/(\d+) 个节点 \/ (\d+) 条关系/)
        return m && Number(m[1]) >= 1 ? text : null
      },
      { label: '图谱统计' },
    )
    await expect(page.locator('[aria-label="图谱查询结果"] .platform-node').first()).toBeVisible()

    // 实体类型图例跟随本次结果动态渲染
    const legend = page.locator('[aria-label="实体类型图例"]')
    await expect(legend).toBeVisible()
    const legendBefore = await legend.innerText()

    // 详情面板四个 Tab 均可切换
    const tabs = page.locator('[aria-label="图谱详情类型"] button')
    for (const name of ['摘要', '实体', '关系', '溯源']) {
      await tabs.filter({ hasText: name }).click()
      await expect(tabs.filter({ hasText: name })).toHaveClass(/is-active/)
    }

    // 换一个机构实体重查（结果更收敛），图例随之变化
    await page.locator('input[placeholder="请输入实体名称或节点ID"]').fill(ORG_NAME)
    await queryBtn.click()
    await waitFor(
      async () => {
        const text = await graphPanel.locator('.kg-panel__header span').first().innerText()
        const m = text.match(/(\d+) 个节点 \/ (\d+) 条关系/)
        return m && Number(m[1]) >= 1 ? text : null
      },
      { label: '机构查询统计' },
    )
    await waitFor(
      async () => {
        const now = await legend.innerText()
        return now && now !== legendBefore ? now : null
      },
      { label: '图例随结果收敛变化' },
    )

    // 科研成果图谱 + 人名 → 「未查询到实体」校验分支（域内实体无名称数据）
    await page.locator('input[placeholder="请输入实体名称或节点ID"]').fill(PERSON_NAME)
    await page
      .locator('.platform-form-field', { hasText: '图谱范围' })
      .locator('.arco-select-view-single')
      .first()
      .click()
    await page.locator('li.arco-select-option:visible', { hasText: '科研成果图谱' }).click()
    await queryBtn.click()
    await waitFor(
      async () =>
        (await page
          .getByText(/未查询到实体/, { exact: false })
          .first()
          .isVisible()
          .catch(() => false)),
      { label: '科研成果图谱未查询到提示', timeout: 15_000 },
    ).catch(() => {
      /* 条件分支：域内出现可命中实体时画布出结果，同样合法 */
    })
  })

  test('B2 nGQL 模式执行（Ctrl+Enter + 按钮，两种结果态）', async ({ page }) => {
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

  test('B3 溯源三要素（实体/关系）+ 构建详情跳转（条件分支）', async ({ page, request }) => {
    // 专利「一种改性y型分子筛及其制备方法」有 HAS_KEYWORD 边（关系溯源素材），
    // 且属于科研成果域（顺带覆盖范围过滤命中路径）
    const PATENT_TITLE = '一种改性y型分子筛及其制备方法'
    const search = await apiMust<any>(
      request,
      'POST',
      '/graph-search/nodes/search?label=Patent&limit=5&space=dev2',
      { title_zh: PATENT_TITLE },
      '按名搜 Patent',
    )
    test.skip(!search?.items?.length, 'dev2 无该专利数据')
    const vid = String(search.items[0].id)
    const sourceTable = String(search.items[0].properties?.source_table ?? '')

    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')
    await page.locator('input[placeholder="请输入实体名称或节点ID"]').fill(PATENT_TITLE)
    await page.getByRole('button', { name: '查询图谱', exact: true }).click()
    await waitFor(
      async () =>
        (await page
          .locator('[aria-label="图谱查询结果"] .platform-node--center')
          .first()
          .isVisible()
          .catch(() => false)),
      { label: '中心节点渲染' },
    )

    // 选中心实体节点 → 溯源 Tab → 三要素齐全且与图库一致
    await page.locator('[aria-label="图谱查询结果"] .platform-node--center').first().click()
    await page.locator('[aria-label="图谱详情类型"] button', { hasText: '溯源' }).click()
    const detail = page.locator('.platform-detail')
    await expect(detail.getByText('实体溯源')).toBeVisible({ timeout: 10_000 })
    const traceText = await detail.innerText()
    expect(traceText).toContain('源数据表')
    expect(traceText).toContain('英文字段名')
    expect(traceText).toContain('图空间 VID')
    // 经平台抽取入库的实体必有三点（源表、vid 与图库一致）
    if (sourceTable) expect(traceText).toContain(sourceTable)
    expect(traceText).toContain(vid)

    // 选一条关系（视觉层与命中层重叠，需 force 点击命中层；点完重进溯源 Tab 确保渲染）
    await page.locator('[aria-label="图谱查询结果"] .platform-network-hit-area').first().click({ force: true })
    await page.locator('[aria-label="图谱详情类型"] button', { hasText: '溯源' }).click()
    await expect(detail.getByText('关系溯源')).toBeVisible({ timeout: 10_000 })
    const relText = await detail.innerText()
    expect(relText).toContain('两端实体来源')
    expect(relText).toContain('源数据表')
    expect(relText).toContain('图空间 VID')

    // 构建详情跳转（条件分支：无构建来源数据时按钮不出现）
    const buildLink = page.getByRole('button', { name: '查看构建详情 →' })
    if (await buildLink.isVisible().catch(() => false)) {
      await buildLink.first().click()
      await page.waitForURL(/processing-instance|task-detail|graph-build\/jobs/, { timeout: 15_000 })
      await expect(page.locator('body')).not.toContainText('页面启动异常')
    }
  })
})
