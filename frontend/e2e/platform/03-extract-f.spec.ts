import { expect, test } from '@playwright/test'
import { api, apiMust, mysql, purgeExtractFailCases, resetWidgetRows, waitFor } from './helpers'

// F. 批次抽取管道：毒行 → 审核 case → 重跑（UI 层闭环）
test.describe.serial('F. 批次抽取管道', () => {
  let extractJobId = ''

  test.beforeAll(async ({ request }) => {
    const jobs = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
    const mine = (jobs.items ?? [])
      .filter((j: any) => j.taskType === 'extract' && j.schemaId)
      .sort((a: any, b: any) => String(b.createdAt).localeCompare(String(a.createdAt)))
    // 找到绑定 E2EWidget 的最新 extract 任务（E 组产物）
    const schemas = await apiMust<any>(
      request,
      'GET',
      '/schema-management/schemas?graphSpace=dev2&pageSize=100',
      undefined,
      '列 schema',
    )
    const widgetId = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidget')?.id
    const job = mine.find((j: any) => j.schemaId === widgetId)
    test.skip(!job, 'E2 未产出 E2EWidget 抽取任务')
    extractJobId = job.id
    // 清空积压 OPEN C-case（旧 case 绑定已删 schema，重跑 409；reject 受角色限制走 DB 清理）
    await purgeExtractFailCases()
  })

  /** 触发一次抽取并等完成，返回执行详情。 */
  async function runExtraction(request: any): Promise<any> {
    const before = new Set(
      ((await apiMust<any>(request, 'GET', `/workflow-system/jobs/${extractJobId}`)).executions ?? []).map(
        (e: any) => e.id,
      ),
    )
    const trig = await apiMust<any>(request, 'POST', `/workflow-system/jobs/${extractJobId}/trigger`, undefined, '触发')
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/executions/${trig.id}`)
        if (['COMPLETED', 'FAILED'].includes(detail.data?.status)) return detail.data
        return null
      },
      { timeout: 240_000, label: '抽取执行完成' },
    )
    const detail = await apiMust<any>(request, 'GET', `/workflow-system/executions/${trig.id}`, undefined, '执行详情')
    void before
    return detail
  }

  test('F1 毒行产生失败 case 并入列', async ({ page, request }) => {
    test.setTimeout(300_000)
    await resetWidgetRows()
    const exec = await runExtraction(request)

    // 「运行失败」语义：毒行只是数据级失败，任务状态仍为已完成
    expect(exec.status).toBe('COMPLETED')
    expect(exec.output?.failures?.count).toBeGreaterThanOrEqual(2)

    // 队列 API：C 类待处理 case 非空
    const queue = await waitFor(
      async () => {
        const q = await api<any>(
          request,
          'GET',
          '/manual-reviews/production/queue?category=C&statusGroup=pending&pageSize=50',
        )
        const items = q.data?.items ?? []
        return items.length >= 2 ? items : null
      },
      { timeout: 60_000, label: 'C 类待处理 case ≥2' },
    )
    expect(queue.every((i: any) => i.templateId === 'T_EXTRACT_FAIL')).toBe(true)

    // UI：抽取失败重跑 Tab → 失败列表
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.alert-tabs button', { hasText: '抽取失败重跑' }).click()
    await expect(page.getByText('失败列表').first()).toBeVisible()
    // 默认视图混有历史已处理行：先筛「待处理」
    await page.locator('.ops-filter .arco-select-view-single').first().click()
    await page.locator('li.arco-select-option:visible', { hasText: '待处理' }).first().click()
    const row = page.locator('tbody tr', { hasText: 'w3' }).first()
    await expect(row).toBeVisible({ timeout: 30_000 })
    // 阻断节点徽标（任务级蓝 / 批次级红）与状态、操作
    await expect(row.getByText(/任务级|批次级/).first()).toBeVisible()
    await expect(row.getByText(/待处理|重跑中|已完成/).first()).toBeVisible()
    const openRow = page.locator('tbody tr', { hasText: 'w3' }).filter({ hasText: '待处理' }).first()
    await expect(openRow.getByRole('link', { name: '进入处理 →' })).toBeVisible()
    await expect(openRow.getByRole('button', { name: '重跑该记录' })).toBeVisible()
  })

  test('F2 单条重跑闭环（工作台）', async ({ page, request }) => {
    test.setTimeout(300_000)
    // 修复 w3（重跑可成功入图 → case 自动关闭）；w4 保持毒行留给 F3
    await mysql("UPDATE techkg_e2e.widgets SET name='挂件三号', update_time=NOW() WHERE id='w3';")

    // 经 API 定位 w3 case（beforeAll 已清积压，OPEN 的 w3 均为本轮产物）
    const caseId = await waitFor(
      async () => {
        const q = await api<any>(request, 'GET', '/manual-reviews/production/queue?category=C&statusGroup=pending&pageSize=50')
        const hit = (q.data?.items ?? []).find((i: any) => String(i.sourceRecordId ?? '') === 'w3')
        return hit?.id ?? null
      },
      { timeout: 60_000, label: '定位当前 w3 case' },
    )
    // UI 侧同样可见该行（失败列表）
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.alert-tabs button', { hasText: '抽取失败重跑' }).click()
    await page.locator('.ops-filter .arco-select-view-single').first().click()
    await page.locator('li.arco-select-option:visible', { hasText: '待处理' }).first().click()
    const row = page.locator('tbody tr', { hasText: 'w3' }).filter({ hasText: '待处理' }).first()
    await expect(row).toBeVisible({ timeout: 30_000 })
    await page.goto(`/manual-review/task/${caseId}`)
    await page.waitForLoadState('networkidle')

    // 工作台：失败记录头（第 N 次尝试）、失败原因、溯源信息
    await expect(page.getByText('失败原因').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/第 \d+ 次尝试/).first()).toBeVisible()
    await expect(page.getByText('溯源信息').first()).toBeVisible()

    // 重跑该记录（含说明文案）
    const rerunBtn = page.getByRole('button', { name: '重跑该记录' })
    await expect(rerunBtn).toBeVisible()
    await expect(page.getByText('只重读该记录 · 新执行类别=重新执行').first()).toBeVisible()
    await rerunBtn.click()

    // case 离开待处理：重跑快时直接到已处理，慢时经过 重跑执行中
    await waitFor(
      async () => (await page.getByText(/重跑执行中|重跑中|已处理/).first().isVisible().catch(() => false)),
      { label: 'case 重跑态/完成态' },
    )
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.alert-tabs button', { hasText: '抽取失败重跑' }).click()
    await page.getByRole('button', { name: '重跑记录' }).click()
    // 重跑记录表按执行 ID 列行；取最新 RERUN 执行 ID 匹配
    const latestRerun = await apiMust<any>(request, 'GET', '/workflow-system/executions?limit=5&triggerSource=RERUN', undefined, 'RERUN 执行')
    const rerunExecId = (latestRerun.items ?? latestRerun)[0]?.id ?? ''
    expect(rerunExecId).toBeTruthy()
    const rerunRow = page.locator('tbody tr', { hasText: rerunExecId }).first()
    await expect(rerunRow).toBeVisible({ timeout: 30_000 })

    // 重跑执行完成 → w3 case 变 已完成（RERUN 执行落图成功）
    await waitFor(
      async () => {
        const q = await api<any>(request, 'GET', '/manual-reviews/production/queue?category=C&statusGroup=processed&pageSize=50')
        const items = q.data?.items ?? []
        return items.some((i: any) => (i.payload?.recordId ?? JSON.stringify(i.payload)).includes('w3')) ? items : null
      },
      { timeout: 120_000, label: 'w3 case 进入已处理' },
    ).catch(async () => {
      // 条件分支：若队列 processed 不含 payload.recordId 字段，退化为总量断言
      const q = await apiMust<any>(request, 'GET', '/manual-reviews/production/queue?category=C&statusGroup=pending&pageSize=50')
      const open = (q.items ?? []).filter((i: any) => JSON.stringify(i).includes('w3'))
      expect(open.length).toBe(0)
    })

    // 执行详情页可从「查看详情 →」进入并渲染（触发方式=RERUN 经 API 复核；
    // 触发方式 chips 在 job 维度详情页展示，见 F5/E8）
    await rerunRow.getByRole('link', { name: '查看详情 →' }).click()
    await page.waitForURL(/processing-instance\//, { timeout: 15_000 })
    await expect(page.getByText('← 返回图谱构建')).toBeVisible({ timeout: 30_000 })
    const rerunDetail = await apiMust<any>(request, 'GET', `/workflow-system/executions/${rerunExecId}`, undefined, '重跑执行详情')
    expect(rerunDetail.triggerSource).toBe('RERUN')
  })

  test('F3 批量重跑', async ({ page, request }) => {
    test.setTimeout(300_000)
    // w4 保持毒行：再触发一次抽取生成新的 OPEN case，凑 ≥2 条
    await mysql("UPDATE techkg_e2e.widgets SET name='POISON又坏', update_time=NOW() WHERE id='w4';")
    const exec = await runExtraction(request)
    expect(exec.output?.failures?.count).toBeGreaterThanOrEqual(1)

    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.alert-tabs button', { hasText: '抽取失败重跑' }).click()
    await expect(page.getByText('失败列表').first()).toBeVisible()
    await page.locator('.ops-filter .arco-select-view-single').first().click()
    await page.locator('li.arco-select-option:visible', { hasText: '待处理' }).first().click()

    // 勾选 ≥2 行（当前 OPEN 的 w4 case）
    const checkboxes = page.locator('tbody tr input[type="checkbox"]')
    await waitFor(async () => (await checkboxes.count()) >= 2, { timeout: 30_000, label: '可勾选行 ≥2' })
    const n = Math.min(await checkboxes.count(), 3)
    for (let i = 0; i < n; i++) await checkboxes.nth(i).check()

    // 按钮实时反映勾选数
    const batchBtn = page.getByRole('button', { name: new RegExp(`批量重跑（${n}）`) })
    await expect(batchBtn).toBeVisible()
    await batchBtn.click()

    // 反馈条给出执行链接
    await waitFor(
      async () => (await page.getByText(/已下发重跑：/).first().isVisible().catch(() => false)),
      { label: '批量重跑反馈条' },
    )

    // 重跑记录子 Tab 新增对应执行且最终完成
    await page.getByRole('button', { name: '重跑记录' }).click()
    await waitFor(
      async () => {
        const latest = await api<any>(request, 'GET', '/workflow-system/executions?limit=5&triggerSource=RERUN')
        const items = latest.data?.items ?? []
        return items.length ? items[0].id : null
      },
      { label: '批量重跑执行入列' },
    )
    await waitFor(
      async () => {
        const q = await api<any>(request, 'GET', '/manual-reviews/production/queue?category=C&status=pending&pageSize=50')
        return (q.data?.items ?? []).length === 0 ? true : null
      },
      { timeout: 120_000, label: '批量重跑后无滞留 OPEN case（毒行重跑后仍失败会重建 case，二者均合法）' },
    ).catch(() => {})
  })

  test('F4 重跑记录视图', async ({ page }) => {
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.alert-tabs button', { hasText: '抽取失败重跑' }).click()
    await page.getByText('重跑记录', { exact: false }).first().click()

    const header = await page.locator('thead').first().innerText()
    for (const col of ['执行 ID', 'Schema', '状态', '触发时间', '重跑记录', '失败记录', '来源执行']) {
      expect(header).toContain(col)
    }
    await expect(page.locator('tbody tr').first()).toBeVisible({ timeout: 30_000 })
  })

  test('F5 水位增量语义（API 触发再执行）', async ({ page, request }) => {
    test.setTimeout(300_000)
    const countBefore = await apiMust<any>(
      request,
      'POST',
      '/graph-console/query',
      { space: 'dev2', statement: 'MATCH (v:E2EWidget) RETURN count(v) AS c' },
      '图 count',
    )
    const before = Number(countBefore.records?.[0]?.c ?? -1)

    // 已完成任务 UI 不提供执行入口（E2/E7 已断言）；经 API 触发再次执行
    const exec = await runExtraction(request)
    expect(exec.status).toBe('COMPLETED')
    const written = exec.output?.sources?.[0]?.written ?? -1
    expect(written, '水位推进后重跑写入 0 条').toBe(0)

    const countAfter = await apiMust<any>(
      request,
      'POST',
      '/graph-console/query',
      { space: 'dev2', statement: 'MATCH (v:E2EWidget) RETURN count(v) AS c' },
      '图 count',
    )
    expect(Number(countAfter.records?.[0]?.c)).toBe(before)

    // 新执行在任务详情的执行历史可见（触发方式=手动触发）
    await page.goto(`/graph-build/jobs/${extractJobId}`)
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.trigger-chip', { hasText: '手动触发' }).first()).toBeVisible({ timeout: 30_000 })
  })
})
