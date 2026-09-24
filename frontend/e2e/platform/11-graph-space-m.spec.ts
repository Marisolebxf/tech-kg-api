import { expect, test } from '@playwright/test'
import {
  api,
  apiMust,
  describeColumns,
  dropGraphEdge,
  dropGraphTag,
  graphCount,
  graphWrite,
  gotoRoute,
  mysql,
  selectArcoScrolled,
  switchGraphSpace,
  waitFor,
} from './helpers'

// M. 图空间维度横切：一切图相关操作可选图空间（schema 展示/创建/关系/查询/抽取写入）；
// 空间统一由平台总览页的全局选择器切换，业务页联动重载
test.describe.serial('M. 图空间横切', () => {
  const SPACE_B = 'e2e_verify_space'

  test.beforeAll(async ({ request }) => {
    // 清理 M 组历史残留（目录 + 图库 TAG/EDGE），保证 e2e_verify_space 空态
    const schemas = await apiMust<any>(
      request,
      'GET',
      `/schema-management/schemas?graphSpace=${SPACE_B}&pageSize=100&includeDetails=true`,
      undefined,
      `列 ${SPACE_B} schema`,
    )
    for (const item of schemas.items ?? []) {
      await api(request, 'DELETE', `/schema-management/schemas/${item.id}`)
    }
    const dev2 = await apiMust<any>(
      request,
      'GET',
      '/schema-management/schemas?graphSpace=dev2&pageSize=100&includeDetails=true',
      undefined,
      '列 dev2 schema',
    )
    for (const item of dev2.items ?? []) {
      if (item.name === 'E2eDevOnly' || item.name === 'E2eSpaceWidget') {
        await api(request, 'DELETE', `/schema-management/schemas/${item.id}`)
      }
    }
    await dropGraphEdge('E2E_SPACE_RELATES', SPACE_B)
    await dropGraphTag('E2eSpaceWidget', SPACE_B)
    await dropGraphTag('E2eDevOnly')
    // 选择器列表已收敛为「默认+本人绑定」（对所有用户生效）：M 组要切的两个
    // 目标空间先绑定到测试账号（bind 幂等）；D5 结束时会解绑 e2e_verify_space
    await api(request, 'POST', `/graph-spaces/${SPACE_B}/bind`, {})
    await api(request, 'POST', '/graph-spaces/algo_test/bind', {})
  })

  test('M1 Schema 管理页：全局图空间切换与按空间过滤', async ({ page, request }) => {
    // 全局空间默认 dev2（免登录模式无用户维度不落盘、选择器仅平台总览页渲染，
    // 以页面实际请求的 graphSpace 参数核对）
    const dev2Load = page.waitForRequest(
      (r) => r.url().includes('/schema-management/schemas') && /[?&]graphSpace=dev2(&|$)/.test(r.url()),
    )
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    await dev2Load

    // 切到 e2e_verify_space（空）→ 空态而非报错
    await switchGraphSpace(page, SPACE_B)
    await waitFor(
      async () => (await page.locator('tbody tr').count()) === 0,
      { label: '空空间列表为空' },
    )
    await expect(page.getByText('暂无实体 Schema', { exact: false }).first()).toBeVisible({ timeout: 15_000 })

    // 切回 dev2 → 非空，与 API 一致
    await switchGraphSpace(page, 'dev2')
    await waitFor(
      async () => (await page.locator('tbody tr').count()) > 0,
      { label: 'dev2 列表恢复' },
    )
    const dev2List = await apiMust<any>(request, 'GET', '/schema-management/schemas?graphSpace=dev2&pageSize=100', undefined, 'dev2 API')
    expect((dev2List.items ?? []).length).toBeGreaterThan(0)
  })

  test('M2 在指定图空间创建实体 Schema（双向隔离）', async ({ page, request }) => {
    // e2e_verify_space 建 e2e_SpaceWidget（UI 全流程；空间取全局选择器当前值）
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE_B)
    await expect(page.getByText('暂无实体 Schema', { exact: false }).first()).toBeVisible({ timeout: 15_000 })

    await page.getByRole('button', { name: '＋ 增加' }).click()
    let modal = page.locator('.schema-create-modal')
    await expect(modal).toBeVisible()
    await modal.locator('input[placeholder="Gadget"]').fill('E2eSpaceWidget')
    await modal.locator('input[placeholder="如：技术"]').fill('E2E空间挂件')
    await modal.getByRole('button', { name: '预览并创建' }).click()
    const ddl = await modal.locator('pre').first().innerText()
    expect(ddl).toContain('CREATE TAG')
    await modal.getByRole('button', { name: '确认创建' }).click()
    await expect(page.locator('tbody tr', { hasText: 'E2eSpaceWidget' }).first()).toBeVisible({ timeout: 30_000 })
    // 弹窗已无图空间字段：落库归属改为按目录数据断言（graphSpace=当前全局空间）
    const bSchemas = await apiMust<any>(
      request,
      'GET',
      `/schema-management/schemas?graphSpace=${SPACE_B}&pageSize=100`,
      undefined,
      `列 ${SPACE_B} schema`,
    )
    const spaceWidget = (bSchemas.items ?? []).find((s: any) => s.name === 'E2eSpaceWidget')
    expect(spaceWidget?.graphSpace).toBe(SPACE_B)

    // dev2 建 e2e_DevOnly
    await switchGraphSpace(page, 'dev2')
    await waitFor(async () => (await page.locator('tbody tr').count()) > 0, { label: 'dev2 列表' })
    await page.getByRole('button', { name: '＋ 增加' }).click()
    modal = page.locator('.schema-create-modal')
    await expect(modal).toBeVisible()
    await modal.locator('input[placeholder="Gadget"]').fill('E2eDevOnly')
    await modal.locator('input[placeholder="如：技术"]').fill('E2E独有实体')
    await modal.getByRole('button', { name: '预览并创建' }).click()
    await modal.getByRole('button', { name: '确认创建' }).click()
    await expect(page.locator('tbody tr', { hasText: 'E2eDevOnly' }).first()).toBeVisible({ timeout: 30_000 })

    // 双向隔离：e2e_verify_space 看不到 e2e_DevOnly；dev2 看不到 e2e_SpaceWidget（目录）
    await switchGraphSpace(page, SPACE_B)
    await expect(page.locator('tbody tr', { hasText: 'E2eDevOnly' })).toHaveCount(0)
    await switchGraphSpace(page, 'dev2')
    await expect(page.locator('tbody tr', { hasText: 'E2eSpaceWidget' })).toHaveCount(0)

    // 图库复核：TAG 只在各自空间存在
    const bCols = await describeColumns(request, SPACE_B, 'TAG', 'E2eSpaceWidget')
    expect(bCols.length).toBeGreaterThan(0)
    const devOnly = await describeColumns(request, 'dev2', 'TAG', 'E2eDevOnly')
    expect(devOnly.length).toBeGreaterThan(0)
    const wrongB = await api<any>(request, 'POST', '/graph-console/query', {
      space: SPACE_B,
      statement: 'DESCRIBE TAG E2eDevOnly',
    })
    expect(wrongB.ok).toBe(false)
  })

  test('M3 构建关系：不同空间可选择的实体不一样', async ({ page, request }) => {
    // e2e_verify_space 新建关系：起点下拉可见 e2e_SpaceWidget、不可见 e2e_DevOnly
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE_B)
    await waitFor(
      async () => (await page.locator('tbody tr', { hasText: 'E2eSpaceWidget' }).count()) > 0,
      { label: '空间 B 实体就绪' },
    )
    await page.locator('[aria-label="Schema 类型切换"]').getByText('关系').click()
    await waitFor(async () => (await page.locator('tbody tr').count()) >= 0, { label: '关系列表' })
    await page.getByRole('button', { name: '＋ 增加' }).click()
    let modal = page.locator('.schema-create-modal')
    await expect(modal).toBeVisible()
    await modal.locator('input[placeholder="USES_TECHNOLOGY"]').fill('E2E_SPACE_RELATES')
    await modal.locator('input[placeholder="如：技术"]').fill('E2E空间关系')
    await modal.locator('.create-field', { hasText: '起点实体' }).locator('.arco-select-view-single').click()
    const srcOpts = await page.locator('li.arco-select-option').allTextContents()
    expect(srcOpts.join()).toContain('E2eSpaceWidget')
    expect(srcOpts.join()).not.toContain('E2eDevOnly')
    await selectArcoScrolled(page, modal.locator('.create-field', { hasText: '起点实体' }).locator('.arco-select-view-single'), 'E2eSpaceWidget')
    await selectArcoScrolled(page, modal.locator('.create-field', { hasText: '终点实体' }).locator('.arco-select-view-single'), 'E2eSpaceWidget')
    await modal.getByRole('button', { name: '预览并创建' }).click()
    const ddl = await modal.locator('pre').first().innerText()
    expect(ddl).toContain('CREATE EDGE')
    await modal.getByRole('button', { name: '确认创建' }).click()
    await expect(page.locator('tbody tr', { hasText: 'E2E_SPACE_RELATES' }).first()).toBeVisible({ timeout: 30_000 })

    const edgeCols = await describeColumns(request, SPACE_B, 'EDGE', 'E2E_SPACE_RELATES')
    expect(edgeCols.length).toBeGreaterThan(0)

    // dev2 的关系新建下拉正好相反（可见 e2e_DevOnly，不可见 e2e_SpaceWidget）
    await switchGraphSpace(page, 'dev2')
    await waitFor(async () => (await page.locator('tbody tr').count()) >= 0, { label: 'dev2 关系列表' })
    await page.getByRole('button', { name: '＋ 增加' }).click()
    modal = page.locator('.schema-create-modal')
    await expect(modal).toBeVisible()
    await modal.locator('.create-field', { hasText: '起点实体' }).locator('.arco-select-view-single').click()
    const devOpts = await page.locator('li.arco-select-option').allTextContents()
    expect(devOpts.join()).not.toContain('E2eSpaceWidget')
    await page.keyboard.press('Escape')
    await modal.locator('header button').click()
  })

  test('M4 任务中心 schemaId 下拉按空间联动', async ({ page }) => {
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')

    // 全局切 e2e_verify_space → 弹窗按该空间拉可抽取 schema（该空间 schema 无脚本/来源）
    await switchGraphSpace(page, SPACE_B)
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    let dialog = page.locator('[class*="job-launch"]').filter({ hasText: '新建任务' }).first()
    await expect(dialog).toBeVisible()
    await expect(dialog.getByText('暂无可抽取 Schema——请先在 Schema 管理页上传抽取脚本并绑定来源表')).toBeVisible({ timeout: 30_000 })

    // 关弹窗切回 dev2 再开 → E2EWidget 出现（有脚本+来源）
    await dialog.getByRole('button', { name: '取消' }).click()
    await switchGraphSpace(page, 'dev2')
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    dialog = page.locator('[class*="job-launch"]').filter({ hasText: '新建任务' }).first()
    await expect(dialog).toBeVisible()
    await dialog.locator('input[placeholder="选择要抽取的实体/关系"]').click()
    const widgetOpt = page.locator('li.arco-select-option:visible', { hasText: 'E2EWidget' }).first()
    await waitFor(async () => (await widgetOpt.isVisible().catch(() => false)), { label: 'dev2 下拉出现 E2EWidget' })
  })

  test('M5 查询与实体列表空间切换（回归）', async ({ page }) => {
    // nGQL 模式：换全局空间后执行（面板自身已无空间控件）
    await page.goto('/graph-query')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: 'nGQL 模式' }).click()
    await switchGraphSpace(page, 'algo_test')
    const ta = page.locator('textarea[placeholder*="MATCH (v:专家)"]')
    await ta.fill('MATCH (v) RETURN count(v) AS c')
    await page.getByRole('button', { name: '执行 nGQL' }).click()
    await expect(page.getByText(/行记录/).first()).toBeVisible({ timeout: 30_000 })

    // 实体列表切空间 + 关键词搜索
    await page.goto('/graph-query/entities')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, 'dev2')
    await waitFor(
      async () => /空间 dev2/.test(await page.locator('body').innerText()),
      { label: '实体列表切回 dev2' },
    )
    await page.locator('input[placeholder*="输入实体名称"]').fill('挂件')
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await waitFor(
      async () => {
        const t = await page.locator('body').innerText()
        return t.includes('检索模式：关键词') || t.includes('检索模式：混合') || t.includes('未找到匹配') ? t : null
      },
      { timeout: 60_000, label: '实体列表跨空间搜索完成' },
    )
  })

  test('M6 抽取写入指定图空间', async ({ request }) => {
    test.setTimeout(420_000)
    // 前置：e2e_verify_space 建 E2EWidget TAG（列结构对齐 dev2）
    const cols = await describeColumns(request, 'dev2', 'TAG', 'E2EWidget')
    const colDefs = cols.map((c) => `${c} string NULL`).join(', ')
    await graphWrite(`CREATE TAG IF NOT EXISTS E2EWidget(${colDefs})`, SPACE_B)
    // Nebula DDL 有传播延迟：等 TAG 可查
    await waitFor(
      async () => {
        const r = await api<any>(request, 'POST', '/graph-console/query', {
          space: SPACE_B,
          statement: 'DESCRIBE TAG E2EWidget',
        })
        return r.ok ? true : null
      },
      { timeout: 60_000, interval: 3_000, label: 'E2EWidget TAG 在目标空间可见' },
    )

    const dev2Before = await graphCount(request, 'dev2', '(v:E2EWidget)')
    // 水位与空间无关（按 schema+来源绑定共享）：推水位保证本次有行可读
    await mysql(
      "UPDATE techkg_e2e.widgets SET name='挂件一号', update_time=NOW() WHERE id='w1'; " +
        "UPDATE techkg_e2e.widgets SET name='挂件二号', update_time=NOW() WHERE id='w2';",
    )
    // 触发抽取（graphSpace=e2e_verify_space，走 API 与 UI 同端点）
    const schemas = await apiMust<any>(request, 'GET', '/schema-management/schemas?graphSpace=dev2&pageSize=100', undefined, '列 schema')
    const widget = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidget')
    test.skip(!widget, '无 E2EWidget schema')
    const trig = await apiMust<any>(
      request,
      'POST',
      `/schema-management/schemas/${widget.id}/extract`,
      { graphSpace: SPACE_B, batchSize: 2 },
      '定向空间抽取',
    )
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/executions/${trig.executionId}`)
        return ['COMPLETED', 'FAILED'].includes(detail.data?.status) ? detail.data : null
      },
      { timeout: 300_000, label: '定向空间抽取完成' },
    )
    // 目标空间 count 增加；dev2 不变
    const bAfter = await graphCount(request, SPACE_B, '(v:E2EWidget)')
    const dev2After = await graphCount(request, 'dev2', '(v:E2EWidget)')
    expect(bAfter).toBeGreaterThanOrEqual(2)
    expect(dev2After).toBe(dev2Before)
    // 执行详情记录图空间
    const execDetail = await apiMust<any>(request, 'GET', `/workflow-system/executions/${trig.executionId}`, undefined, '执行详情')
    expect(String((execDetail.payload || {}).graphSpace || '')).toContain(SPACE_B)
  })

  test('D5 图数据空间绑定/解绑（选择器联动）', async ({ page, request }) => {
    // beforeAll 已绑定 SPACE_B 供 M1-M6 切换；先 API 解绑复位，再走 UI 完整绑定/解绑
    await api(request, 'DELETE', `/graph-spaces/${SPACE_B}`)
    await page.goto('/configurations')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '图数据空间', exact: false }).first().click()

    // 绑定 e2e_verify_space（admin 区 .bind-nav 内「绑定已有图数据空间」select + 绑定按钮）
    await page.locator('.bind-nav .arco-select-view-single').click()
    await page.locator('li.arco-select-option:visible', { hasText: SPACE_B }).first().click()
    await page.locator('.bind-nav button', { hasText: '绑定' }).click()
    await waitFor(
      async () => {
        const spaces = await apiMust<any>(request, 'GET', '/graph-spaces', undefined, '图空间列表')
        return (spaces.items ?? spaces).find((s: any) => s.name === SPACE_B)?.bound === true ? true : null
      },
      { label: 'API bound=true' },
    )
    // 绑定对所有用户生效：store ensureLoaded 强刷后，平台总览页的全局图空间
    // 选择器可选列表立即出现 SPACE_B
    await gotoRoute(page, '/overview')
    await page.locator('.app-breadcrumb .app-space-select .arco-select-view-single').click()
    await expect(page.locator('li.arco-select-option:visible', { hasText: SPACE_B }).first()).toBeVisible({
      timeout: 15_000,
    })
    await page.keyboard.press('Escape')

    // 解绑：配置页图数据空间列表已无「解除绑定」操作列（绑定关系由管理员维护），
    // 走 API 解除后断言 bound=false，继续覆盖选择器列表同步移除
    await gotoRoute(page, '/configurations')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '图数据空间', exact: false }).first().click()
    await expect(page.getByRole('button', { name: '解除绑定' })).toHaveCount(0)
    await apiMust(request, 'DELETE', `/graph-spaces/${SPACE_B}`, undefined, '解除绑定')
    await waitFor(
      async () => {
        const spaces = await apiMust<any>(request, 'GET', '/graph-spaces', undefined, '图空间列表')
        return (spaces.items ?? spaces).find((s: any) => s.name === SPACE_B)?.bound === false ? true : null
      },
      { label: 'API bound=false' },
    )
    // 选择器列表同步移除该空间（后续 N 组如需切换会在自己的 beforeAll 重新绑定）
    await gotoRoute(page, '/overview')
    await page.locator('.app-breadcrumb .app-space-select .arco-select-view-single').click()
    await expect(page.locator('li.arco-select-option:visible', { hasText: SPACE_B })).toHaveCount(0)
  })
})
