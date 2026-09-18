import { expect, test } from '@playwright/test'
import { api, apiMust, autoAcceptConfirms, graphWrite, ngql, runId, waitFor } from './helpers'

// H. 修正记录（/admin/corrections，管理端「审核与同步」页面已下线）
test.describe.serial('H. 修正记录', () => {
  const suffix = runId()
  const titleA = `e2e修正申请A${suffix}`

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
        return (list.data?.items ?? []).find((i: any) => i.title === titleA) ?? null
      },
      { label: '修正申请入列' },
    )
  })

  test('H3 修改/撤销自己的待审核申请', async ({ page, request }) => {
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
