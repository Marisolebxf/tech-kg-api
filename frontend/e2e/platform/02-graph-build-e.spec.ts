import { expect, test } from '@playwright/test'
import {
  API_BASE,
  api,
  apiMust,
  autoAcceptConfirms,
  graphCount,
  mysql,
  resetWidgetRows,
  runId,
  switchGraphSpace,
  waitFor,
} from './helpers'

const ECHO_SCRIPT = `"""e2e echo workflow"""
from typing import Any, Mapping


def workflow(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "echo": str(payload.get("hello", ""))}
`

/** E3 素材：第二个可抽取 Schema 的转换脚本（与 WIDGET_SCRIPT 同形，tag 不同） */
const WIDGET_B_SCRIPT = `"""E2EWidgetB 转换脚本：出实体 + 写图。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities = []
    for row in rows:
        entities.append({"id": "widgetb_" + str(row["id"]), "props": {"id": str(row["id"]), "name": str(row.get("name") or "")}})
    return {"entities": entities, "failures": []}
`

// E. 任务中心（/graph-build）
test.describe.serial('E. 任务中心', () => {
  const suffix = runId()
  let extractJobId = ''
  let chainJobId = ''
  let singleJobId = ''
  let uploadJobId = ''

  test.beforeAll(async ({ request }) => {
    // E2 前置：E2EWidget schema（C 组产物）；推水位让本次抽取有新数据可写
    const schemas = await apiMust<any>(
      request,
      'GET',
      '/schema-management/schemas?graphSpace=dev2&pageSize=100&includeDetails=true',
      undefined,
      '列 schema',
    )
    const widget = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidget')
    test.skip(!widget, 'C 组未产出 E2EWidget')
  })

  test('E1 任务列表 + 标题 + 汇总卡 + 筛选', async ({ page, request }) => {
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')

    // 页面左上角标题为「图谱构建」（不是「任务中心」）；设计规范改版移除 h1 后标题在面包屑
    await expect(page.locator('.app-breadcrumb__current', { hasText: '图谱构建' })).toBeVisible()

    // 四个汇总卡
    for (const label of ['运行中', '已完成', '运行失败', '已暂停']) {
      await expect(page.locator('article', { hasText: label }).first()).toBeVisible()
    }

    // 列头齐全 + 现网历史任务存在
    const header = await page.locator('thead').first().innerText()
    for (const col of ['任务名', '类型', '图空间', '调度', '状态', '最近执行', '操作']) {
      expect(header).toContain(col)
    }
    const jobs = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
    const names = (jobs.items ?? []).map((j: any) => String(j.name))
    expect(names.some((n: string) => n.includes('e2e抽取') || n.includes('e2e任务')), '现网历史 e2e 任务存在').toBe(true)

    // 名称筛选
    await page.locator('#graph-build-filter-name input').fill('e2e')
    await waitFor(
      async () => {
        const rows = page.locator('tbody tr')
        const n = await rows.count()
        return n > 0 ? n : null
      },
      { label: '名称筛选收敛' },
    )
    await page.locator('#graph-build-filter-name input').fill('')
  })

  test('E2 新建一次性「数据抽取」任务并立即执行', async ({ page, request }) => {
    test.setTimeout(300_000)
    const jobName = `e2e任务-抽取-${suffix}`
    // 推水位（幂等重跑也保证本次执行有新行可写）；实体 upsert 语义下图 count 不
    // 随重写增长，写入数改由执行输出核对
    await mysql(
      "UPDATE techkg_e2e.widgets SET name='挂件一号', update_time=NOW() WHERE id='w1'; " +
        "UPDATE techkg_e2e.widgets SET name='挂件二号', update_time=NOW() WHERE id='w2';",
    )

    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    // 弹窗内已无图空间选择：可抽取 Schema 按全局选择器当前空间拉取
    await switchGraphSpace(page, 'dev2')
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    const dialog = page.locator('[class*="job-launch"], .arco-modal, [class*="modal"]').filter({ hasText: '新建任务' }).first()
    await expect(dialog).toBeVisible()

    await dialog.locator('input[placeholder="如：论文-专家抽取"]').fill(jobName)
    // 任务类型已是静态「数据抽取」（D2/D4 下线其余通道后弹窗只建抽取任务），无需选择
    await dialog.locator('input[placeholder="选择要抽取的实体/关系"]').click()
    const widgetOpt = page.locator('li.arco-select-option:visible', { hasText: 'E2EWidget' }).first()
    await waitFor(async () => (await widgetOpt.isVisible().catch(() => false)), { label: 'E2EWidget 选项出现' })
    await widgetOpt.click()
    // 批大小 2
    await dialog.locator('input[type="number"]').first().fill('2')
    // 一次性 + 创建后立即执行（默认勾选）
    await expect(dialog.getByText('创建后立即执行')).toBeVisible()
    await dialog.getByRole('button', { name: '创建任务' }).click()

    await waitFor(
      async () => (await page.getByText(`任务「${jobName}」已创建并触发执行`).first().isVisible().catch(() => false)),
      { label: '创建并触发 toast' },
    )

    // 行出现 → 状态终态
    const jobs = await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        return (list.items ?? []).find((j: any) => j.name === jobName) ?? null
      },
      { label: '任务入列' },
    )
    extractJobId = jobs.id
    const doneExec = await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${extractJobId}`)
        const execs = detail.data?.executions ?? []
        if (!execs.length) return null
        const done = execs.find((e: any) => ['COMPLETED', 'FAILED'].includes(e.status))
        if (!done) return null
        return done.status === 'COMPLETED' ? done : null
      },
      { timeout: 240_000, label: '抽取执行完成' },
    )
    // 写入计数（IO 输出）：本次执行实写 2 行（w1/w2）
    const execDetail = await apiMust<any>(request, 'GET', `/workflow-system/executions/${doneExec.id}`, undefined, '执行详情')
    const written = execDetail.output?.sources?.[0]?.written ?? -1
    expect(written).toBeGreaterThanOrEqual(1)

    // 调度列显示 单次；图库 count 增加；行内无「执行」入口
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: jobName }).first()
    await expect(row).toBeVisible()
    await expect(row.getByText('单次')).toBeVisible()
    await expect(row.getByRole('button', { name: '执行', exact: true })).toHaveCount(0)
    await expect(row.getByRole('button', { name: '重新执行' })).toHaveCount(0)

    const countNow = await graphCount(request, 'dev2', '(v:E2EWidget)')
    expect(countNow).toBeGreaterThanOrEqual(2)

    // 详情页执行历史：一条 MANUAL 记录 + IO 输出写入计数
    await row.getByRole('button', { name: '查看详情' }).click()
    await page.waitForURL(/graph-build\/jobs\//, { timeout: 15_000 })
    await expect(page.getByText('手动触发').first()).toBeVisible({ timeout: 30_000 })
  })

  test('E3 新建「多脚本串行」任务（chain）', async ({ page, request }) => {
    test.setTimeout(300_000)
    const jobName = `e2e任务-串行-${suffix}`

    // ---- 前置：两个可抽取 Schema（E2EWidget 来自 C 组；E2EWidgetB 现场造：建目录 → 传脚本 → 绑来源）
    const schemas = await apiMust<any>(
      request,
      'GET',
      '/schema-management/schemas?graphSpace=dev2&pageSize=100&includeDetails=true',
      undefined,
      '列 schema',
    )
    const widget = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidget')
    test.skip(!widget, 'C 组未产出 E2EWidget')
    const widgetB = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidgetB')
    if (!widgetB) {
      const created = await apiMust<any>(
        request,
        'POST',
        '/schema-management/schemas/entities',
        {
          schemaKey: 'e2e_widget_b',
          name: 'E2EWidgetB',
          label: 'E2E测试挂件B',
          description: 'e2e chain 串行素材',
          identityKey: 'id',
          properties: [
            { name: 'id', dataType: 'string', required: true, rule: '', category: 'required' },
            { name: 'name', dataType: 'string', required: true, rule: '', category: 'required' },
          ],
          graphSpace: 'dev2',
        },
        '建 E2EWidgetB',
      )
      widgetB.id = created.id
    }
    // 幂等重跑：脚本与来源绑定每次都重放（上次中断也能补齐）
    const scriptResp = await request.put(`${API_BASE}/schema-management/schemas/${widgetB.id}/script`, {
      multipart: {
        script: {
          name: 'e2e_widget_b_extract.py',
          mimeType: 'text/x-python',
          buffer: Buffer.from(WIDGET_B_SCRIPT, 'utf-8'),
        },
      },
    })
    expect(scriptResp.ok(), `上传 E2EWidgetB 脚本: HTTP ${scriptResp.status()}`).toBeTruthy()
    const ds = await apiMust<any>(request, 'GET', '/mysql-datasources', undefined, '列数据源')
    const dsList = Array.isArray(ds) ? ds : (ds.items ?? [])
    const e2eDs = dsList.find((d: any) => d.name === 'e2e-mysql-src' && d.host === 'temporal-mysql-dev2')
    expect(e2eDs, 'e2e-mysql-src 数据源存在').toBeTruthy()
    await apiMust<any>(
      request,
      'PUT',
      `/schema-management/schemas/${widgetB.id}/sources`,
      { sources: [{ datasourceId: e2eDs.id, databaseName: 'techkg_e2e', tableName: 'widgets' }] },
      '绑来源',
    )
    // 推水位：两环都有新行可写
    await resetWidgetRows()

    // ---- UI：新建 chain 任务
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    const dialog = page.locator('[class*="job-launch"], .arco-modal, [class*="modal"]').filter({ hasText: '新建任务' }).first()
    await expect(dialog).toBeVisible()
    await dialog.locator('input[placeholder="如：论文-专家抽取"]').fill(jobName)
    await dialog.locator('[aria-label="任务类型"]').click()
    await page.locator('li.arco-select-option:visible', { hasText: '多脚本串行' }).first().click()

    // 先选图空间（M4 联动：chain 队列同样按空间过滤）
    await dialog.locator('.arco-select-view-single:has(input[placeholder="默认空间"])').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'dev2' }).first().click()

    // 添加第一个 Schema：仅 1 个时被拦（创建按钮禁用 + 提示文案）
    const pick = dialog.locator('input[placeholder="搜索并添加 Schema"]')
    await pick.click()
    const optA = page.locator('li.arco-select-option:visible', { hasText: 'E2EWidgetB' }).first()
    await waitFor(async () => (await optA.isVisible().catch(() => false)), { label: 'E2EWidgetB 选项' })
    await optA.click()
    await expect(dialog.getByText('多脚本串行任务至少选择 2 个 Schema')).toBeVisible()
    await expect(dialog.getByRole('button', { name: '创建任务' })).toBeDisabled()
    await expect(dialog.locator('.chain-steps li')).toHaveCount(1)

    // 追加第二个 Schema（chain 选择后输入框自动清空，直接再开下拉）。
    // 'E2EWidget' 是 'E2EWidgetB' 的子串——用右括号锚定精确匹配 E2EWidget
    await pick.click()
    const optB = page.locator('li.arco-select-option:visible', { hasText: '· E2EWidget）' }).first()
    await waitFor(async () => (await optB.isVisible().catch(() => false)), { label: 'E2EWidget 选项' })
    await optB.click()
    await expect(dialog.locator('.chain-steps li')).toHaveCount(2)
    // 顺序可调：把第 2 项上移成第 1 项（E2EWidget 打头）
    await dialog.locator('.chain-steps li').nth(1).getByRole('button', { name: '上移' }).click()
    await expect(dialog.getByRole('button', { name: '创建任务' })).toBeEnabled()
    await dialog.getByRole('button', { name: '创建任务' }).click()
    await waitFor(
      async () => (await page.getByText(`任务「${jobName}」已创建并触发执行`).first().isVisible().catch(() => false)),
      { label: 'chain 创建 toast' },
    )

    const jobs = await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        const job = (list.items ?? []).find((j: any) => j.name === jobName) ?? null
        return job?.schemaIds?.length === 2 ? job : null
      },
      { label: 'chain 任务入列（带 schemaIds）' },
    )
    chainJobId = jobs.id
    expect(jobs.schemaLabels.join('→')).toContain('E2E')
    const exec = await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${chainJobId}`)
        const execs = detail.data?.executions ?? []
        const done = execs.find((e: any) => ['COMPLETED', 'FAILED'].includes(e.status))
        return done?.status === 'COMPLETED' ? done : null
      },
      { timeout: 240_000, label: 'chain 执行完成' },
    )
    // 两环串行都写了图（w1/w2 各写一份）；output 在执行详情端点（同 E2 的取法）
    const execDetail = await apiMust<any>(
      request,
      'GET',
      `/workflow-system/executions/${exec.id}`,
      undefined,
      'chain 执行详情',
    )
    const written = (execDetail.output?.steps ?? {}) as Record<string, any>
    const writtenTotal = Object.values(written).reduce((sum, s) => sum + (s.written ?? 0), 0)
    expect(writtenTotal).toBeGreaterThanOrEqual(2)

    // ---- 详情页：每个 Schema 一个抽屉，展开是脚本内转换步
    await page.goto(`/graph-build/jobs/${chainJobId}`)
    await page.waitForLoadState('networkidle')
    const stepBtns = page.locator('.process-step')
    await waitFor(async () => (await stepBtns.count()) >= 2, { label: '两个 Schema 阶段' })
    expect(await page.locator('.process-step.is-成功').count()).toBeGreaterThanOrEqual(2)
    // 抽屉展开：点击第一个 Schema 阶段 → 内层转换步（单 transform 聚合为 1 条，name=函数名）
    await stepBtns.first().click()
    const substep = page.locator('.process-substep', { hasText: 'transform' }).first()
    await expect(substep).toBeVisible()
    await expect(substep.getByText(/行 · 写图/)).toBeVisible()
    expect(exec.status).toBe('COMPLETED')
  })

  test('E4 新建「单脚本抽取」任务', async ({ page, request }) => {
    test.skip(true, 'single 建任务 UI 已随 D2/D4 下线（2026-09-14），待按新任务中心形态重写')
    test.setTimeout(300_000)
    const jobName = `e2e任务-单脚本-${suffix}`
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    const dialog = page.locator('[class*="job-launch"], .arco-modal, [class*="modal"]').filter({ hasText: '新建任务' }).first()
    await dialog.locator('input[placeholder="如：论文-专家抽取"]').fill(jobName)
    await dialog.locator('[aria-label="任务类型"]').click()
    await page.locator('li.arco-select-option:visible', { hasText: '单脚本抽取' }).first().click()
    const pick = dialog.locator('input[placeholder="搜索并选择脚本"]')
    await pick.click()
    const opt = page.locator('li.arco-select-option:visible', { hasText: `e2e-echo-a-${suffix}` }).first()
    await waitFor(async () => (await opt.isVisible().catch(() => false)), { label: 'echo 选项' })
    await opt.click()
    await dialog.getByRole('button', { name: '创建任务' }).click()

    const jobs = await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        return (list.items ?? []).find((j: any) => j.name === jobName) ?? null
      },
      { label: 'single 任务入列' },
    )
    singleJobId = jobs.id
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${singleJobId}`)
        const done = (detail.data?.executions ?? []).find((e: any) =>
          ['COMPLETED', 'FAILED'].includes(e.status),
        )
        return done?.status === 'COMPLETED' ? done : null
      },
      { timeout: 240_000, label: 'single 执行完成' },
    )
  })

  test('E5 新建「上传脚本」任务', async ({ page, request }) => {
    test.skip(true, 'upload 建任务 UI 已随 D2/D4 下线（2026-09-14），待按新任务中心形态重写')
    test.setTimeout(300_000)
    const jobName = `e2e任务-上传-${suffix}`
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    const dialog = page.locator('[class*="job-launch"], .arco-modal, [class*="modal"]').filter({ hasText: '新建任务' }).first()
    await dialog.locator('input[placeholder="如：论文-专家抽取"]').fill(jobName)
    await dialog.locator('[aria-label="任务类型"]').click()
    await page.locator('li.arco-select-option:visible', { hasText: '上传脚本' }).first().click()
    await dialog.getByRole('button', { name: '选择 .py 文件' }).click()
    await page.locator('input[type="file"][accept=".py"]').setInputFiles({
      name: 'e2e_echo_job.py',
      mimeType: 'text/x-python',
      buffer: Buffer.from(ECHO_SCRIPT, 'utf-8'),
    })
    await dialog.getByRole('button', { name: '创建任务' }).click()

    const jobs = await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        return (list.items ?? []).find((j: any) => j.name === jobName) ?? null
      },
      { label: 'upload 任务入列' },
    )
    uploadJobId = jobs.id
    const exec = await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${uploadJobId}`)
        const done = (detail.data?.executions ?? []).find((e: any) =>
          ['COMPLETED', 'FAILED'].includes(e.status),
        )
        return done?.status === 'COMPLETED' ? done : null
      },
      { timeout: 240_000, label: 'upload 执行完成' },
    )

    // IO Tab 输出含 echo 内容
    await page.goto(`/graph-build/jobs/${uploadJobId}`)
    await page.waitForLoadState('networkidle')
    await page.locator('.detail-tabs button', { hasText: '输入输出' }).click()
    await expect(page.getByText('"status": "ok"').first()).toBeVisible({ timeout: 30_000 })
    expect(exec.status).toBe('COMPLETED')
  })

  test('E6 周期性任务 + 暂停调度', async ({ page, request }) => {
    test.skip(true, 'upload 建任务 UI 已随 D2/D4 下线（2026-09-14）；暂停调度链路待改用 extract 周期任务重写')
    const jobName = `e2e任务-周期-${suffix}`
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    const dialog = page.locator('[class*="job-launch"], .arco-modal, [class*="modal"]').filter({ hasText: '新建任务' }).first()
    await dialog.locator('input[placeholder="如：论文-专家抽取"]').fill(jobName)
    await dialog.locator('[aria-label="任务类型"]').click()
    await page.locator('li.arco-select-option:visible', { hasText: '上传脚本' }).first().click()
    await dialog.getByRole('button', { name: '选择 .py 文件' }).click()
    await page.locator('input[type="file"][accept=".py"]').setInputFiles({
      name: 'e2e_echo_job.py',
      mimeType: 'text/x-python',
      buffer: Buffer.from(ECHO_SCRIPT, 'utf-8'),
    })
    // 执行模式 = 周期性，频率每12小时（不点立即执行）
    await dialog.getByText('周期性', { exact: false }).first().click()
    await dialog.locator('.arco-select-view-single:has(input)').nth(0).click().catch(async () => {
      await dialog.getByText('每天', { exact: false }).first().click()
    })
    const freqSelect = dialog.locator('.arco-select-view-single').filter({ hasText: /每天|每12小时|每6小时|每周/ }).first()
    if (await freqSelect.count()) {
      await freqSelect.click()
      await page.locator('li.arco-select-option:visible', { hasText: '每12小时' }).first().click()
    }
    await dialog.getByRole('button', { name: '创建任务' }).click()

    const jobs = await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        return (list.items ?? []).find((j: any) => j.name === jobName) ?? null
      },
      { label: '周期任务入列' },
    )
    // 锚点语义：每12小时 + 默认首次执行时间 02:00 → cron `0 2,14 * * *`（02:00、14:00 各一次）
    expect(jobs.schedule?.cron).toBe('0 2,14 * * *')
    // 调度列人话化展示（cron 原文收进 title）
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: jobName }).first()
    await expect(row).toBeVisible()
    await expect(row.getByText(/每12小时 · 02:00、14:00/)).toBeVisible()

    // 「暂停调度」入口只对 已完成+cron 的任务展示（未运行没有）：API 触发一次使其完成
    await apiMust<any>(request, 'POST', `/workflow-system/jobs/${jobs.id}/trigger`, undefined, '首跑')
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${jobs.id}`)
        const done = (detail.data?.executions ?? []).find((e: any) =>
          ['COMPLETED', 'FAILED'].includes(e.status),
        )
        return done?.status === 'COMPLETED' ? done : null
      },
      { timeout: 240_000, label: '周期任务首跑完成' },
    )
    await page.reload()
    await page.waitForLoadState('networkidle')
    const rowAfter = page.locator('tbody tr', { hasText: jobName }).first()
    await expect(rowAfter).toBeVisible()

    // 暂停调度 → 按钮翻转
    await rowAfter.getByRole('button', { name: '暂停调度' }).click()
    await waitFor(
      async () => (await rowAfter.getByRole('button', { name: '恢复', exact: true }).isVisible().catch(() => false)),
      { label: '调度暂停按钮翻转' },
    )
    // API：schedule paused 生效
    const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${jobs.id}`)
    expect(detail.ok).toBe(true)

    // 清理：删除该任务（confirm 含「执行历史将保留」）
    autoAcceptConfirms(page)
    await rowAfter.getByRole('button', { name: '删除' }).click()
    await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        return (list.items ?? []).some((j: any) => j.id === jobs.id) ? null : true
      },
      { label: '周期任务删除' },
    )
  })

  test('E7 任务行状态操作：统一状态模型 + 删除保留执行历史', async ({ page, request }) => {
    test.skip(!singleJobId, 'E4 未产出')
    autoAcceptConfirms(page)

    // 已完成任务：操作列无「执行」「暂停」
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    const singleName = `e2e任务-单脚本-${suffix}`
    const row = page.locator('tbody tr', { hasText: singleName }).first()
    await expect(row).toBeVisible()
    await expect(row.getByRole('button', { name: '执行', exact: true })).toHaveCount(0)
    await expect(row.getByRole('button', { name: '暂停', exact: true })).toHaveCount(0)
    await expect(row.getByRole('button', { name: '查看详情' })).toBeVisible()

    // 删除任务前抓一个执行 ID
    const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${singleJobId}`)
    const execId = detail.data?.executions?.[0]?.id ?? ''
    expect(execId).toBeTruthy()

    // 删除（confirm 已由 autoAcceptConfirms 接受；文案断言见 E6 场景内的 confirm 约定）
    await row.getByRole('button', { name: '删除' }).click()
    await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        return (list.items ?? []).some((j: any) => j.id === singleJobId) ? null : true
      },
      { label: '任务删除' },
    )

    // 执行历史仍可访问
    const exec = await api<any>(request, 'GET', `/workflow-system/executions/${execId}`)
    expect(exec.ok).toBe(true)
    await page.goto(`/processing-instance/${execId}`)
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('← 返回图谱构建')).toBeVisible({ timeout: 30_000 })
  })

  test('E8 任务详情页：配置 + 触发方式 chips + IO（过渡断言）', async ({ page, request }) => {
    test.skip(!extractJobId, 'E2 未产出')
    await page.goto(`/graph-build/jobs/${extractJobId}`)
    await page.waitForLoadState('networkidle')

    // 配置区：图空间=dev2
    await expect(page.locator('.job-config-panel').getByText('dev2').first()).toBeVisible({ timeout: 30_000 })
    // 触发方式 chips（手动触发）
    await expect(page.locator('.trigger-chip', { hasText: '手动触发' }).first()).toBeVisible()
    // 执行历史表
    await expect(page.getByText('执行历史')).toBeVisible()
    // 步骤侧栏：D3 删除静态 7 步模板后，单 transform 抽取无 stages 输出 → 空态文案；
    // STEPS 多步脚本才渲染分步。两者取其一
    await expect(page.locator('.process-step.is-成功, .process-empty').first()).toBeVisible({ timeout: 60_000 })
    // IO Tab：输入/输出 JSON（实际访问资源卡仅在脚本上报 access 时渲染）
    await page.locator('.detail-tabs button', { hasText: '输入输出' }).click()
    await expect(page.getByText(/实际访问资源|输入数据|输出结果|阶段真实输入输出/).first()).toBeVisible()
    const ioText = await page.locator('.step-detail').innerText()
    expect(ioText.length).toBeGreaterThan(0)
  })

  test('E9 任务列表按当前图空间过滤 + 「全部空间」开关', async ({ page, request }) => {
    test.setTimeout(120_000)
    // 造一个别的空间的任务（admin 绕过绑定校验，直接落 algo_test 空间；不触发执行）
    const jobName = `e2e任务-跨空间-${suffix}`
    const schemas = await apiMust<any>(
      request,
      'GET',
      '/schema-management/schemas?graphSpace=dev2&pageSize=100',
      undefined,
      '列 schema',
    )
    const widget = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidget')
    test.skip(!widget, '无 E2EWidget schema')
    const otherJob = await apiMust<any>(
      request,
      'POST',
      '/workflow-system/jobs',
      {
        name: jobName,
        taskType: 'extract',
        schemaId: widget.id,
        schedule: { kind: 'once' },
        graphSpace: 'algo_test',
        batchSize: 2,
      },
      '建跨空间任务',
    )
    try {
      await page.goto('/graph-build')
      await page.waitForLoadState('networkidle')
      // 默认跟随当前全局空间（dev2）：跨空间任务不可见
      await expect(page.locator('tbody tr', { hasText: jobName })).toHaveCount(0)
      // 打开「全部空间」→ 任务可见，图空间列显示 algo_test
      await page.locator('.gb-space-toggle').click()
      const row = page.locator('tbody tr', { hasText: jobName }).first()
      await expect(row).toBeVisible({ timeout: 15_000 })
      await expect(row.getByText('algo_test')).toBeVisible()
      // 关闭开关 → 回到当前空间过滤（隐藏）
      await page.locator('.gb-space-toggle').click()
      await expect(page.locator('tbody tr', { hasText: jobName })).toHaveCount(0)
    } finally {
      await api(request, 'DELETE', `/workflow-system/jobs/${otherJob.id}`)
    }
  })
})
