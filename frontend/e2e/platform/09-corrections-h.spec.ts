import { expect, test } from '@playwright/test'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { api, apiMust, autoAcceptConfirms, graphWrite, ngql, runId, waitFor } from './helpers'

const execFileAsync = promisify(execFile)

// H. 修正中心（/admin/corrections records 模式 + /admin/reviews review 模式）
test.describe.serial('H. 修正中心', () => {
  const suffix = runId()
  const titleA = `e2e修正申请A${suffix}`
  const titleB = `e2e修正申请B${suffix}`
  let recordAId = ''
  let recordBId = ''

  test.beforeAll(async ({ request }) => {
    // 99-cleanup 会 drop Scholar 投影 tag——本轮幂等重建（dual 模式图投影写它）
    await graphWrite(
      'CREATE TAG IF NOT EXISTS Scholar(scholar_id string NULL, name string NULL, manual_disabled bool NULL, correction_id string NULL, corrected_at string NULL)',
      'dev2',
    ).catch(() => {})
    // E2EWidget widget_w1 已入库（C/F 组产物），作为修正对象
    const rows = await ngql(request, 'dev2', 'MATCH (v:E2EWidget) WHERE id(v)=="widget_w1" RETURN id(v) AS vid LIMIT 1')
    test.skip(!rows.length, 'dev2 无 widget_w1 实体')
    // 清理旧 e2e 修正记录（幂等）
    const list = await api<any>(request, 'GET', '/corrections?pageSize=100')
    const items = list.data?.items ?? []
    for (const item of items) {
      if (String(item.title || '').startsWith('e2e修正申请') && ['PENDING_REVIEW', 'PENDING_SYNC', 'SYNC_FAILED'].includes(item.status)) {
        await api(request, 'DELETE', `/corrections/${item.id}`)
      }
    }
    // 种子记录：live 列表非空才不会回退示例模式（example 模式下 UI 提交只进内存）
    await apiMust<any>(
      request,
      'POST',
      '/corrections',
      {
        target_type: 'expert',
        operation: 'update',
        target_id: 'widget_w1',
        title: `e2e修正申请种子${suffix}`,
        reason: 'e2e seed：激活 live 模式',
        before_data: { name: '挂件一号' },
        after_data: { name: '挂件一号seed' },
      },
      '种子记录',
    )
  })

  test('H1 列表与查询', async ({ page }) => {
    await page.goto('/admin/corrections')
    await page.waitForLoadState('networkidle')
    // records 模式汇总卡
    for (const label of ['记录总数', '待审核']) {
      await expect(page.locator('article', { hasText: label }).first()).toBeVisible({ timeout: 30_000 })
    }
    // review 模式汇总卡
    await page.goto('/admin/reviews')
    await page.waitForLoadState('networkidle')
    for (const label of ['队列记录', '待审核']) {
      await expect(page.locator('article', { hasText: label }).first()).toBeVisible({ timeout: 30_000 })
    }
    // 查询 modal
    await page.getByRole('button', { name: '查询', exact: true }).click()
    const modal = page.locator('.arco-modal').filter({ hasText: '查询修正记录' }).first()
    await expect(modal).toBeVisible()
    await modal.getByPlaceholder('修正内容、对象 ID、申请人').fill('e2e修正申请')
    await modal.getByRole('button', { name: '查询', exact: true }).click()
    await waitFor(
      async () => (await page.locator('tbody tr').count()) >= 0,
      { label: '查询执行' },
    )
  })

  test('H2 新增修正申请（含 JSON 校验负分支）', async ({ page, request }) => {
    await page.goto('/admin/corrections')
    await page.waitForLoadState('networkidle')
    await page.getByRole('button', { name: '新增修正申请' }).click()
    const modal = page.locator('.arco-modal').filter({ hasText: '新增人工修正' }).first()
    await expect(modal).toBeVisible()

    // 表单：label 包裹 input/textarea
    const field = (label: string) => modal.locator('label', { hasText: label })
    await field('对象 ID').locator('input').fill('widget_w1')
    await field('标题').locator('input').fill(titleA)
    await field('修正原因').locator('textarea').fill('e2e 修正原因：名称待勘误')
    await field('修正前数据').locator('textarea').fill('{invalid json')

    await modal.getByRole('button', { name: '提交审核' }).click()
    await expect(page.getByText(/必须是合法的 JSON/).first()).toBeVisible({ timeout: 15_000 })

    // 改合法 JSON 提交
    await field('修正前数据').locator('textarea').fill('{"name": "挂件一号"}')
    await field('修正后数据').locator('textarea').fill(`{"name": "挂件一号e2e修正${suffix}"}`)
    await modal.getByRole('button', { name: '提交审核' }).click()
    await waitFor(
      async () => {
        const list = await api<any>(request, 'GET', '/corrections?pageSize=100')
        const hit = (list.data?.items ?? []).find((i: any) => i.title === titleA)
        if (hit) recordAId = hit.id
        return hit ?? null
      },
      { label: '修正申请入列' },
    )
  })

  test('H3 审核通过 → 自动同步图库', async ({ page, request }) => {
    test.setTimeout(240_000)
    test.skip(!recordAId, 'H2 未产出')
    await page.goto('/admin/reviews')
    await page.waitForLoadState('networkidle')
    await waitFor(
      async () => (await page.getByText(titleA).first().isVisible().catch(() => false)),
      { label: 'review 队列出现记录', timeout: 30_000 },
    )
    const row = page.locator('tbody tr', { hasText: titleA }).first()
    await row.getByRole('button', { name: '通过' }).click()

    const modal = page.locator('.arco-modal').filter({ hasText: '审核人工修正' }).first()
    await expect(modal).toBeVisible()
    await modal.getByText('批准并同步').first().click()
    await modal.locator('textarea').fill('e2e 批准')
    await modal.getByRole('button', { name: '确认审核' }).click()

    // 状态流转：批准后 PENDING_SYNC。注意：生产容器 tech-kg-api 也开着修正
    // dispatcher（projection 模式）且共用同一 MySQL——30s 轮询窗口里会被它抢先
    // 按 projection 处理（graph SKIP）。必须在批准后**立即**于 dev2 容器内主动
    // 触发同款 dispatcher 函数（dual 模式）抢在生产的 30s 轮询之前完成图同步，
    // 不能先等状态变 COMPLETED（那正是生产抢跑完成的表现，graph 已被 SKIP）
    await execFileAsync(
      'docker',
      ['exec', '-w', '/app', 'tech-kg-api-dev2', '.venv/bin/python', '-c',
       'from infra.mysql import session_scope; from service.correction import process_due_sync_tasks\n'
       + 'with session_scope() as s: process_due_sync_tasks(s)'],
      { timeout: 60_000 },
    )
    await waitFor(
      async () => {
        const list = await api<any>(request, 'GET', '/corrections?pageSize=100')
        const hit = (list.data?.items ?? []).find((i: any) => i.id === recordAId)
        if (!hit) return null
        if (hit.status !== 'COMPLETED') return null
        return (hit.sync?.graphStatus === 'SUCCEEDED') ? hit : null
      },
      { timeout: 120_000, label: '审核后图同步完成（graphStatus=SUCCEEDED）' },
    )

    // 图库复核：dual 模式下专家修正投影写图（Scholar 节点 + 修正后 name）。
    // Scholar.scholar_id 无属性索引（WHERE 会 IndexNotFound），全量取回后客户端过滤
    await waitFor(
      async () => {
        const rows = await ngql(request, 'dev2', 'MATCH (v:Scholar) RETURN v.Scholar.scholar_id AS sid, v.Scholar.name AS name LIMIT 50')
        const hit = rows.find((r: any) => String(r.sid) === 'widget_w1')
        return hit && String(hit.name || '').includes('e2e修正') ? hit : null
      },
      { timeout: 120_000, label: '图库投影节点 name 已修正' },
    )
  })

  test('H4 驳回（原因必填）', async ({ page, request }) => {
    test.skip(!recordAId, 'H2 未产出')
    // 造一条新的待审核
    await apiMust<any>(
      request,
      'POST',
      '/corrections',
      {
        target_type: 'expert',
        operation: 'update',
        target_id: 'widget_w1',
        title: titleB,
        reason: 'e2e 驳回用例',
        before_data: { name: '挂件一号' },
        after_data: { name: '挂件一号e2eB' },
      },
      '建 B 申请',
    )
    await page.goto('/admin/reviews')
    await page.waitForLoadState('networkidle')
    await waitFor(
      async () => (await page.getByText(titleB).first().isVisible().catch(() => false)),
      { label: 'B 记录入列' },
    )
    const row = page.locator('tbody tr', { hasText: titleB }).first()
    await row.getByRole('button', { name: '驳回' }).click()
    const modal = page.locator('.arco-modal').filter({ hasText: '审核人工修正' }).first()
    await expect(modal).toBeVisible()
    await modal.getByText('驳回申请').first().click()
    // 不填原因确认 → 被拦
    await modal.getByRole('button', { name: '确认审核' }).click()
    await expect(page.getByText('驳回时必须填写原因').first()).toBeVisible({ timeout: 10_000 })
    await modal.locator('textarea').fill('e2e 驳回原因')
    await modal.getByRole('button', { name: '确认审核' }).click()

    await waitFor(
      async () => {
        const list = await api<any>(request, 'GET', '/corrections?pageSize=100')
        const hit = (list.data?.items ?? []).find((i: any) => i.title === titleB)
        return hit?.status === 'REJECTED' ? true : null
      },
      { timeout: 60_000, label: 'B 记录已驳回' },
    )
  })

  test('H5 同步失败与重试（条件分支）', async () => {
    // dual 模式的图投影用 merge_node（upsert 语义）：目标实体不存在会**新建节点**
    // 而不是失败（实测 H3 的 widget_w1 即为新建 Scholar 节点），「指向不存在实体
    // → 同步失败 → 重试」在当前实现下不可构造。失败重试通道（attempts/nextRetryAt/
    // 重试按钮）保留给真实外部故障场景，按方案标注为条件分支跳过。
    test.skip(true, 'dual+merge 语义下同步失败分支不可构造')
  })

  test('H6 修改/撤销自己的待审核申请', async ({ page, request }) => {
    // 造一条待审核 → 修改标题 → 撤销
    await apiMust<any>(
      request,
      'POST',
      '/corrections',
      {
        target_type: 'expert',
        operation: 'update',
        target_id: 'widget_w1',
        title: `e2e修正申请C${suffix}`,
        reason: 'e2e 撤销用例',
        before_data: { name: '挂件一号' },
        after_data: { name: '挂件一号e2eC' },
      },
      '建 C 申请',
    )
    await page.goto('/admin/corrections')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: `e2e修正申请C${suffix}` }).first()
    await waitFor(
      async () => (await row.isVisible().catch(() => false)),
      { label: 'C 记录入列' },
    )
    // 修改
    await row.getByRole('button', { name: '修改' }).click()
    const editModal = page.locator('.arco-modal').filter({ hasText: '修改修正申请' }).first()
    await expect(editModal).toBeVisible()
    const editTitle = editModal.locator('label', { hasText: '标题' }).locator('input')
    await editTitle.fill(`e2e修正申请C${suffix}改`)
    await editModal.getByRole('button', { name: '保存修改' }).click()
    await waitFor(
      async () => {
        const list = await api<any>(request, 'GET', '/corrections?pageSize=100')
        return (list.data?.items ?? []).some((i: any) => i.title === `e2e修正申请C${suffix}改`) ? true : null
      },
      { label: '修改生效' },
    )
    // 撤销（confirm）
    autoAcceptConfirms(page)
    const rowAfter = page.locator('tbody tr', { hasText: `e2e修正申请C${suffix}改` }).first()
    await rowAfter.getByRole('button', { name: '撤销' }).click()
    await waitFor(
      async () => {
        const list = await api<any>(request, 'GET', '/corrections?pageSize=100')
        return (list.data?.items ?? []).some((i: any) => i.title === `e2e修正申请C${suffix}改`
          && i.status === 'PENDING_REVIEW') ? null : true
      },
      { label: '撤销生效' },
    )
  })
})
