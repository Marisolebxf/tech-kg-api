import { expect, test } from '@playwright/test'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { api, apiMust, mysql, purgeExtractFailCases, runId, waitFor } from './helpers'

const execFileAsync = promisify(execFile)

async function execDocker(sql: string): Promise<void> {
  await execFileAsync(
    'docker',
    ['exec', 'tech-kg-api-dev2', '.venv/bin/python', '-c',
     'from infra.mysql import get_session_factory; from sqlalchemy import text; '
     + 's = get_session_factory()(); s.execute(text(' + JSON.stringify(sql) + ')); s.commit(); s.close()'],
    { timeout: 30_000 },
  )
}

// G. 人工审核（A 类：入库决策）
// 造数：POST /internal/manual-reviews（worker 同款入口）注入 T_DIRECT 合成 case。
test.describe.serial('G. 人工审核（A 类）', () => {
  const suffix = runId()
  const directNames = [`e2e直入库甲${suffix}`, `e2e直入库乙${suffix}`]
  let caseA = ''
  let caseB = ''


  /** 真实通道造数：python workflow 返回 pendingReview → 平台入队 T_DIRECT case。 */
  async function seedDirectCasesViaWorkflow(request: any): Promise<void> {
    const pending = directNames.map((name) => ({
      templateId: 'T_DIRECT',
      kind: 'entity',
      nodeLabel: 'E2EWidget',
      objectId: `e2e_obj_${suffix}_${name}`,
      objectName: name,
      reason: 'LLM 输出 confidence = 0.42 < 0.85，未达自动入库线',
      confidence: 0.42,
      sourceTable: 'techkg_e2e.widgets',
      sourceRecordId: `e2e_src_${name}`,
      candidate: {
        _kind: 'entity',
        _nodeLabel: 'E2EWidget',
        id: `e2e_direct_${suffix}_${name}`,
        name,
        confidence: 0.42,
      },
    }))
    const docquote = String.fromCharCode(34, 34, 34)
    const script = (
      docquote + 'e2e T_DIRECT pendingReview seeder' + docquote + '\n' +
      'from typing import Any, Mapping\n\n\n' +
      'PENDING = ' + JSON.stringify(pending) + '\n\n\n' +
      'def seed(payload: Mapping[str, Any], ctx: Mapping[str, Any]) -> dict[str, Any]:\n' +
      '    return {"status": "ok", "pendingReview": PENDING}\n'
    )
    const defName = `e2e-direct-steps-${suffix}`
    // kg.custom.steps 流水线定义：execute_pipeline_step 才会消费 pendingReview
    // （single=kg.custom.python 与 chain 均原样存 output）
    const form = new FormData()
    form.append('file', new Blob([script], { type: 'text/x-python' }), `${defName}.py`)
    form.append('steps', JSON.stringify([{ id: 'seed', name: '造数', functionName: 'seed' }]))
    form.append('name', defName)
    const defResp = await request.post('http://localhost:8002/api/v1/workflow-system/definitions/steps', {
      multipart: form,
      headers: { 'X-User-Id': 'local-dev' },
    })
    const def = await defResp.json()
    const definitionId = def?.data?.id
    const job = await apiMust<any>(
      request,
      'POST',
      '/workflow-system/jobs',
      {
        name: `e2e任务-审核造数-${suffix}`,
        taskType: 'single',
        definitionId,
        schedule: { kind: 'once' },
        runNow: true,
        graphSpace: 'dev2',
      },
      '建造数任务',
    )
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/jobs/${job.id}`)
        const done = (detail.data?.executions ?? []).find((e: any) =>
          ['COMPLETED', 'FAILED'].includes(e.status),
        )
        return done?.status === 'COMPLETED' ? done : null
      },
      { timeout: 240_000, label: '造数任务完成' },
    )
    await waitFor(
      async () => {
        const q = await api<any>(request, 'GET', '/manual-reviews/production/queue?category=A&statusGroup=pending&pageSize=50')
        const items = q.data?.items ?? []
        const a = items.find((i: any) => i.objectName === directNames[0])
        const b = items.find((i: any) => i.objectName === directNames[1])
        if (a && b) {
          caseA = a.id
          caseB = b.id
          return true
        }
        return null
      },
      { timeout: 60_000, label: 'T_DIRECT case 入队' },
    )
  }

  test.beforeAll(async ({ request }) => {
    await purgeExtractFailCases()
    await seedDirectCasesViaWorkflow(request)
  })
  test('G1 队列与筛选', async ({ page, request }) => {
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    // 入库决策 Tab（默认 A 类）；队列按创建时间升序，新 case 可能不在首页——
    // 用关键词防抖搜索收敛定位
    await page.locator('.review-search-input input').fill(directNames[0])
    await expect(page.getByText(directNames[0]).first()).toBeVisible({ timeout: 30_000 })
    // 清空筛选：列表恢复非空（新 case 按时间升序可能不在首页，不做点名断言）
    await page.getByRole('button', { name: '清空筛选' }).click()
    await waitFor(
      async () => (await page.locator('tbody tr').count()) >= 1,
      { label: '清空后恢复' },
    )

    // 表格与 queue API 一致
    const q = await apiMust<any>(request, 'GET', '/manual-reviews/production/queue?category=A&statusGroup=pending&pageSize=50', undefined, 'A 队列')
    expect((q.items ?? []).length).toBeGreaterThanOrEqual(2)
  })

  test('G2 T_DIRECT 五段式处理：修正后入库', async ({ page, request }) => {
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.review-search-input input').fill(directNames[0])
    const row = page.locator('tbody tr', { hasText: directNames[0] }).first()
    await expect(row).toBeVisible({ timeout: 30_000 })
    await row.getByRole('link', { name: '进入处理 →' }).click()
    await page.waitForURL(/manual-review\/task\//, { timeout: 15_000 })

    // 五段式（专用工作台）
    await expect(page.getByText('① 候选').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('② 为什么需要你确认').first()).toBeVisible()
    await expect(page.getByText(/0\.42/).first()).toBeVisible()
    await expect(page.getByText('③ 原始记录').first()).toBeVisible()
    await expect(page.getByText('④ 抽取推理过程').first()).toBeVisible()
    await expect(page.getByText('⑤ 决策').first()).toBeVisible()

    // 编辑字段（name + 后缀）→ 出现「修正后入库」；未改字段时其提示为“请先在①候选中修改字段”
    await page.getByRole('button', { name: '编辑字段' }).click()
    const fixBtn = page.getByRole('button', { name: '修正后入库' })
    await expect(fixBtn).toBeVisible()
    await expect(page.getByText('请先在①候选中修改字段').first()).toBeVisible()
    const nameInput = page.locator('.direct-fields input').last()
    await nameInput.fill(`${directNames[0]}修正`)
    await fixBtn.click()
    await waitFor(
      async () => (await page.getByText(/已决策|已处理/).first().isVisible().catch(() => false)),
      { label: '决策完成' },
      ).catch(async () => {
        const detail = await api<any>(request, 'GET', `/manual-reviews/production/${caseA}`)
        expect(['RESOLVED', 'COMPLETED']).toContain(detail.data?.status)
      })
    // case 终态
    const detail = await api<any>(request, 'GET', `/manual-reviews/production/${caseA}`)
    expect(['RESOLVED', 'COMPLETED']).toContain(detail.data?.status)
  })

  test('G3 驳回·丢弃', async ({ page, request }) => {
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.review-search-input input').fill(directNames[1])
    const row = page.locator('tbody tr', { hasText: directNames[1] }).first()
    await expect(row).toBeVisible({ timeout: 30_000 })
    await row.getByRole('link', { name: '进入处理 →' }).click()
    await page.waitForURL(/manual-review\/task\//, { timeout: 15_000 })
    await expect(page.getByText('① 候选').first()).toBeVisible({ timeout: 30_000 })

    // 填备注 → 驳回·丢弃
    await page.locator('input[placeholder="审核备注..."], textarea[placeholder="审核备注..."]').first()
      .fill('e2e 驳回：候选不可信')
      .catch(async () => {
        await page.getByPlaceholder('审核备注...').fill('e2e 驳回：候选不可信')
      })
    await page.getByRole('button', { name: '驳回·丢弃' }).click()
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/manual-reviews/production/${caseB}`)
        return ['REJECTED', 'RESOLVED', 'COMPLETED'].includes(detail.data?.status) ? true : null
      },
      { timeout: 60_000, label: 'case 驳回终态' },
    )
  })

  test('G4 消歧闭环：同名冲突 → T_LINK 实体对齐裁决（真实管道）', async ({ page, request }) => {
    test.setTimeout(420_000)
    // 清理历史运行残留的 T_LINK（全部删除——同名 dupes 每轮产生多行已撤销，
    // 队列按创建时间升序会把新 OPEN case 挤出首页）/ 未决 e2e T_DIRECT case
    await execDocker(
      "DELETE FROM manual_review_case WHERE template_id='T_LINK'",
    )
    // 造两行同名不同 id 数据 → 触发 E2EWidget 抽取 → 管道同名冲突检测自动产 T_LINK
    await mysql(
      `INSERT INTO techkg_e2e.widgets (id, name, update_time) VALUES ('e2e_dupe_1', 'e2e同名挂件', NOW()) ` +
        `ON DUPLICATE KEY UPDATE name='e2e同名挂件', update_time=NOW(); ` +
      `INSERT INTO techkg_e2e.widgets (id, name, update_time) VALUES ('e2e_dupe_2', 'e2e同名挂件', NOW()) ` +
        `ON DUPLICATE KEY UPDATE name='e2e同名挂件', update_time=NOW();`,
    )
    // 找 E2EWidget 抽取任务并触发
    const jobs = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
    const schemas = await apiMust<any>(request, 'GET', '/schema-management/schemas?graphSpace=dev2&pageSize=100', undefined, '列 schema')
    const widgetId = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidget')?.id
    const job = (jobs.items ?? []).find((j: any) => j.taskType === 'extract' && j.schemaId === widgetId)
    test.skip(!job, '无 E2EWidget 抽取任务')
    const trig = await apiMust<any>(request, 'POST', `/workflow-system/jobs/${job.id}/trigger`, undefined, '触发')
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/executions/${trig.id}`)
        return ['COMPLETED', 'FAILED'].includes(detail.data?.status) ? detail.data : null
      },
      { timeout: 300_000, label: '抽取执行完成' },
    )

    // A 类队列出现「实体对齐裁决」case（原因文案含 同名实体冲突）
    const linkCase = await waitFor(
      async () => {
        const q = await api<any>(request, 'GET', '/manual-reviews/production/queue?category=A&statusGroup=pending&pageSize=50')
        const hit = (q.data?.items ?? []).find(
          (i: any) => i.templateId === 'T_LINK' && i.status === 'OPEN'
            && String(i.objectName || '').includes('e2e同名挂件'),
        )
        return hit ?? null
      },
      { timeout: 120_000, label: 'T_LINK case 产生' },
    )

    // UI：入库决策 Tab → 搜索定位（队列按创建时间升序，新 case 不一定在首页）
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    await page.locator('.review-search-input input').fill('e2e同名挂件')
    const linkRow = page.locator('tbody tr', { hasText: 'e2e同名挂件' }).filter({ hasText: /待处理|待领取/ }).first()
    await expect(linkRow).toBeVisible({ timeout: 30_000 })
    await linkRow.getByRole('link', { name: '进入处理 →' }).click()
    await page.waitForURL(/manual-review\/task\//, { timeout: 15_000 })
    await expect(page.getByText('实体对齐裁决').first()).toBeVisible({ timeout: 30_000 })

    // 工作台渲染验证：T_LINK 专用「实体对齐裁决」布局
    await expect(page.getByText('实体对齐裁决').first()).toBeVisible({ timeout: 30_000 })

    // 裁决提交（API 通道：领取 → entity-confirm create=保留为新建实体，两节点隔离）。
    // merge 需 targetEntityId（后端校验），管道新产 case 的 existingCandidates 为空、
    // 前端 T_LINK 工作台未提供合并目标选择——合并分支的 UI 缺口记录在测试报告。
    const detail0 = await apiMust<any>(request, 'GET', `/manual-reviews/production/${linkCase.id}`, undefined, 'case 详情')
    const version = detail0.version ?? 1
    const claimResp = await api<any>(request, 'POST', `/manual-reviews/production/${linkCase.id}/claim`, { version })
    const claimVersion = claimResp.data?.version ?? version + 1
    await apiMust<any>(
      request,
      'POST',
      `/manual-reviews/production/${linkCase.id}/submit`,
      {
        version: claimVersion,
        actionId: 'entity-confirm',
        note: 'e2e 裁决：保留为新建实体',
        result: { entityVerdict: 'create' },
      },
      '提交裁决',
    )
    await waitFor(
      async () => {
        const d = await api<any>(request, 'GET', `/manual-reviews/production/${linkCase.id}`)
        return ['RESOLVED', 'COMPLETED', 'RERUNNING', 'APPLYING'].includes(d.data?.status) ? true : null
      },
      { timeout: 120_000, label: 'T_LINK case 流转' },
    )

    // 清理测试行（widgets 与图库节点由 99-cleanup 兜底）
    await mysql("DELETE FROM techkg_e2e.widgets WHERE id IN ('e2e_dupe_1','e2e_dupe_2');")
  })
})
