import { expect, test } from '@playwright/test'
import {
  api,
  apiMust,
  autoAcceptConfirms,
  graphCount,
  mysql,
  runId,
  waitFor,
} from './helpers'

const ECHO_SCRIPT = `"""e2e echo workflow"""
from typing import Any, Mapping


def workflow(payload: Mapping[str, Any]) -> dict[str, Any]:
    return {"status": "ok", "echo": str(payload.get("hello", ""))}
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
    // E3 前置：上传两个 echo python 定义（链式任务素材）
    for (const name of [`e2e-echo-a-${suffix}`, `e2e-echo-b-${suffix}`]) {
      const form = new FormData()
      form.append('file', new Blob([ECHO_SCRIPT], { type: 'text/x-python' }), `${name}.py`)
      form.append('function_name', 'workflow')
      form.append('name', name)
      await request.post('http://localhost:8002/api/v1/workflow-system/definitions/python', {
        multipart: form,
        headers: { 'X-User-Id': 'local-dev' },
      })
    }
  })

  test('E1 任务列表 + 标题 + 汇总卡 + 筛选', async ({ page, request }) => {
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')

    // 页面左上角标题为「图谱构建」（不是「任务中心」）
    await expect(page.getByRole('heading', { name: '图谱构建' })).toBeVisible()

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
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    const dialog = page.locator('[class*="job-launch"], .arco-modal, [class*="modal"]').filter({ hasText: '新建任务' }).first()
    await expect(dialog).toBeVisible()

    await dialog.locator('input[placeholder="如：论文-专家抽取"]').fill(jobName)
    // 任务类型 = 数据抽取
    await dialog.locator('[aria-label="任务类型"]').click()
    await page.locator('li.arco-select-option:visible', { hasText: '数据抽取' }).first().click()
    // 先选图空间再选 Schema（M4 联动：换空间会清空已选 schemaId 并按空间重查）
    await dialog.locator('.arco-select-view-single:has(input[placeholder="默认空间"])').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'dev2' }).first().click()
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
    await page.goto('/graph-build')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '＋ 新建任务' }).click()
    const dialog = page.locator('[class*="job-launch"], .arco-modal, [class*="modal"]').filter({ hasText: '新建任务' }).first()
    await expect(dialog).toBeVisible()
    await dialog.locator('input[placeholder="如：论文-专家抽取"]').fill(jobName)
    await dialog.locator('[aria-label="任务类型"]').click()
    await page.locator('li.arco-select-option:visible', { hasText: '多脚本串行' }).first().click()

    // 仅选 1 个时被拦（创建按钮禁用 + 提示文案）；chain 的选择器占位符与 single 不同
    const pick = dialog.locator('input[placeholder="搜索并添加脚本"]')
    await pick.click()
    const optA = page.locator('li.arco-select-option:visible', { hasText: `e2e-echo-a-${suffix}` }).first()
    await waitFor(async () => (await optA.isVisible().catch(() => false)), { label: 'echo-a 选项' })
    await optA.click()
    await expect(dialog.getByText('多脚本串行任务至少选择 2 个脚本')).toBeVisible()
    await expect(dialog.getByRole('button', { name: '创建任务' })).toBeDisabled()

    // 追加第二个脚本（chain 选择后输入框自动清空，直接再开下拉）
    await pick.click()
    const optB = page.locator('li.arco-select-option:visible', { hasText: `e2e-echo-b-${suffix}` }).first()
    await waitFor(async () => (await optB.isVisible().catch(() => false)), { label: 'echo-b 选项' })
    await optB.click()
    await dialog.getByRole('button', { name: '创建任务' }).click()
    await waitFor(
      async () => (await page.getByText(`任务「${jobName}」已创建并触发执行`).first().isVisible().catch(() => false)),
      { label: 'chain 创建 toast' },
    )

    const jobs = await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
        return (list.items ?? []).find((j: any) => j.name === jobName) ?? null
      },
      { label: 'chain 任务入列' },
    )
    chainJobId = jobs.id
    const exec = await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${chainJobId}`)
        const execs = detail.data?.executions ?? []
        const done = execs.find((e: any) => ['COMPLETED', 'FAILED'].includes(e.status))
        return done?.status === 'COMPLETED' ? done : null
      },
      { timeout: 240_000, label: 'chain 执行完成' },
    )

    // 详情页：步骤侧栏两个脚本级子步骤（成功 ✓）
    await page.goto(`/graph-build/jobs/${chainJobId}`)
    await page.waitForLoadState('networkidle')
    const steps = page.locator('.process-step')
    await waitFor(async () => (await steps.count()) >= 2, { label: '两个脚本步骤' })
    expect(await page.locator('.process-step.is-成功').count()).toBeGreaterThanOrEqual(2)
    // IO Tab：输入/输出 JSON（echo 脚本不访问外部资源，无「实际访问资源」卡）
    await page.locator('.detail-tabs button', { hasText: '输入输出' }).click()
    await expect(page.getByText(/实际访问资源|输入数据|输出结果|阶段真实输入输出/).first()).toBeVisible()
    expect(exec.status).toBe('COMPLETED')
  })

  test('E4 新建「单脚本抽取」任务', async ({ page, request }) => {
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
    // 步骤侧栏 ✓ 状态
    await expect(page.locator('.process-step.is-成功').first()).toBeVisible({ timeout: 60_000 })
    // IO Tab：输入/输出 JSON（实际访问资源卡仅在脚本上报 access 时渲染）
    await page.locator('.detail-tabs button', { hasText: '输入输出' }).click()
    await expect(page.getByText(/实际访问资源|输入数据|输出结果|阶段真实输入输出/).first()).toBeVisible()
    const ioText = await page.locator('.step-detail').innerText()
    expect(ioText.length).toBeGreaterThan(0)
  })
})
