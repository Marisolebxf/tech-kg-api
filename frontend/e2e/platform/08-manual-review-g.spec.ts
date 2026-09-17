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

// G. 人工审核（A 类：入库决策 Tab 只筛 T_LINK；T_DIRECT 直达工作台 URL 处理）
// 造数：容器内直调 create_direct_case（管道同款入口）注入 T_DIRECT 合成 case。
test.describe.serial('G. 人工审核（A 类）', () => {
  const suffix = runId()
  const directNames = [`e2e直入库甲${suffix}`, `e2e直入库乙${suffix}`]
  let caseA = ''
  let caseB = ''


  /** 造数：容器内直调 create_direct_case（_enqueue_pending_review 同款入口）注入
   *  T_DIRECT 合成 case。原 kg.custom.steps 造数通道已随 D2 下线（HTTP create_case
   *  的 validate_step_template 不认 T_DIRECT）；execute_transform 的 pendingReview
   *  真实入队链路由 G4（T_LINK 同名冲突）覆盖，这里只负责可控的 case 内容。 */
  async function seedDirectCasesViaWorkflow(request: any): Promise<void> {
    for (const [index, name] of directNames.entries()) {
      const payload = {
        task_id: `e2e-direct-seed-${suffix}`,
        execution_id: null,
        step_id: 'extract',
        kind: 'entity',
        node_label: 'E2EWidget',
        template_id: 'T_DIRECT',
        object_id: `e2e_obj_${suffix}_${name}`,
        object_name: name,
        reason: 'LLM 输出 confidence = 0.42 低于阈值 0.85，未达自动入库线',
        confidence: 0.42,
        source_table: 'techkg_e2e.widgets',
        source_record_id: `e2e_src_${index}_${suffix}`,
        workflow_id: `e2e-seed-${suffix}`,
        candidate: {
          _kind: 'entity',
          _nodeLabel: 'E2EWidget',
          id: `e2e_direct_${suffix}_${name}`,
          name,
          confidence: 0.42,
        },
      }
      const py =
        'import json; from service.manual_review_production import manual_review_service; '
        + 'manual_review_service.create_direct_case(**json.loads('
        + JSON.stringify(JSON.stringify(payload)) + '))'
      await execFileAsync(
        'docker',
        ['exec', 'tech-kg-api-dev2', '.venv/bin/python', '-c', py],
        { timeout: 30_000 },
      )
    }
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
  test('G1 队列与筛选（入库决策 Tab 只筛 T_LINK）', async ({ page, request }) => {
    await page.goto('/manual-review')
    await page.waitForLoadState('networkidle')
    // 入库决策 Tab（默认 A 类）只筛 T_LINK：搜 T_DIRECT 造数名应无命中（防抖后落到条件空态）
    await page.locator('.review-search-input input').fill(directNames[0])
    await expect(page.getByText('暂无符合条件的记录').first()).toBeVisible({ timeout: 30_000 })

    // 表格与 queue API 一致：后端 category=A 语义不变（仍含 T_DIRECT/T_LINK），
    // 入库决策 Tab 的实际请求是 A + templateId=T_LINK → 只回 T_LINK
    const q = await apiMust<any>(request, 'GET', '/manual-reviews/production/queue?category=A&statusGroup=pending&pageSize=50', undefined, 'A 队列')
    expect((q.items ?? []).length).toBeGreaterThanOrEqual(2)
    const qLink = await apiMust<any>(request, 'GET', '/manual-reviews/production/queue?category=A&templateId=T_LINK&statusGroup=pending&pageSize=50', undefined, 'A·T_LINK 队列')
    expect((qLink.items ?? []).every((i: any) => i.templateId === 'T_LINK')).toBe(true)
    expect((qLink.items ?? []).some((i: any) => i.objectName === directNames[0])).toBe(false)
  })

  test('G2 T_DIRECT 裁决框处理：修正后入库', async ({ page, request }) => {
    // 入库决策 Tab 只筛 T_LINK 后，T_DIRECT case 不再出现在队列——
    // 用 beforeAll 记下的 case id 直达工作台 URL
    await page.goto(`/manual-review/task/${caseA}`)
    await page.waitForLoadState('networkidle')

    // A 类统一裁决框布局：待入库记录卡 + 候选字段 + 裁决单选
    await expect(page.getByText('待入库记录（已扣留，未写图）').first()).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText(/抽取置信度 0\.42/).first()).toBeVisible()
    await expect(page.getByText('待入库候选字段').first()).toBeVisible()
    await expect(page.getByText('通过·入库').first()).toBeVisible()
    await expect(page.getByText('驳回·丢弃').first()).toBeVisible()

    // 编辑字段（name + 后缀）→ 底部「确认」自动按修正后候选走 accept-fix
    await page.getByRole('button', { name: '编辑字段' }).click()
    const nameInput = page.locator(`.direct-fields input[placeholder="${directNames[0]}"]`)
    await expect(nameInput).toBeVisible()
    await nameInput.fill(`${directNames[0]}修正`)
    await expect(page.getByText('修改 1 个字段').first()).toBeVisible()
    await page.getByRole('button', { name: '确认', exact: true }).click()
    await expect(page.getByText(/已按修正后候选写入图/).first()).toBeVisible({ timeout: 30_000 })
    // case 终态
    await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/manual-reviews/production/${caseA}`)
        return ['RESOLVED', 'COMPLETED'].includes(detail.data?.status) ? true : null
      },
      { timeout: 60_000, label: '修正后入库终态' },
    )
  })

  test('G3 驳回·丢弃', async ({ page, request }) => {
    await page.goto(`/manual-review/task/${caseB}`)
    await page.waitForLoadState('networkidle')
    await expect(page.getByText('待入库记录（已扣留，未写图）').first()).toBeVisible({ timeout: 30_000 })

    // 填备注 → 选「驳回·丢弃」→ 底部「确认」
    await page.locator('input[placeholder="审核备注…"]').fill('e2e 驳回：候选不可信')
    await page.getByText('驳回·丢弃（候选不写图）').first().click()
    await page.getByRole('button', { name: '确认', exact: true }).click()
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
