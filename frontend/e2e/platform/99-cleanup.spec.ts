import { expect, test } from '@playwright/test'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { api, apiMust, autoAcceptConfirms, dropGraphEdge, dropGraphTag, mysql, waitFor } from './helpers'

const execFileAsync = promisify(execFile)

// 99. 统一清理 + C10 删除验收（引用拦截 / 假删模式 / 二次确认）
// N 组产物（test_space_01 的 schema/数据）保留作 N 组回归环境，记录在案。
test.describe.serial('99. 清理与 C10 删除验收', () => {
  test('C10 删除：引用拦截 → 删关系 → 软删实体', async ({ page, request }) => {
    autoAcceptConfirms(page)
    const schemas = await apiMust<any>(request, 'GET', '/schema-management/schemas?graphSpace=dev2&pageSize=100&includeDetails=true', undefined, '列 schema')
    const items = schemas.items ?? []
    const widget = items.find((s: any) => s.name === 'E2EWidget')
    test.skip(!widget, 'E2EWidget 不存在（C 组未跑或已清理）')

    // ① 引用拦截：E2EWidget 仍被 E2E_RELATES 引用 → 硬拦
    const blocked = await api(request, 'DELETE', `/schema-management/schemas/${widget.id}`)
    expect(blocked.status).toBe(409)
    expect(JSON.stringify(blocked.data)).toContain('仍被关系引用')

    // UI 侧同样被拦（引用信息进 canDelete 不可用态或提交后 toast 提示）
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: 'E2EWidget' }).first()
    await expect(row).toBeVisible({ timeout: 30_000 })
    const delBtn = row.getByRole('button', { name: '删除' })
    const disabled = await delBtn.isDisabled()
    if (!disabled) {
      await delBtn.click()
      const confirmModal = page.locator('.schema-delete-modal')
      await expect(confirmModal).toBeVisible()
      await confirmModal.getByRole('button', { name: '确认删除' }).click()
      await waitFor(
        async () => (await page.getByText('仍被关系引用').first().isVisible().catch(() => false)),
        { label: 'UI 引用拦截提示' },
      )
      // 关闭弹窗（若有）继续
      await page.locator('.schema-delete-modal header button').click().catch(() => {})
    }

    // ② 删关系（二次确认弹窗：文案说明后果）
    await page.locator('[aria-label="Schema 类型切换"]').getByText('关系').click()
    await waitFor(async () => (await page.locator('tbody tr').count()) > 0, { label: '关系列表' })
    const relRow = page.locator('tbody tr', { hasText: 'E2E_RELATES' }).first()
    await expect(relRow).toBeVisible({ timeout: 30_000 })
    await relRow.getByRole('button', { name: '删除' }).click()
    const relConfirm = page.locator('.schema-delete-modal')
    await expect(relConfirm).toBeVisible()
    await expect(relConfirm.getByText(/将删除目录记录与关联脚本/)).toBeVisible()
    await expect(relConfirm.getByText(/TAG\/EDGE 不会被 DROP/)).toBeVisible()
    await relConfirm.getByRole('button', { name: '确认删除' }).click()
    await waitFor(
      async () => !(await page.locator('tbody tr', { hasText: 'E2E_RELATES' }).first().isVisible().catch(() => false)),
      { label: '关系行消失' },
    )

    // ③ 删实体（软删验收）
    await page.locator('[aria-label="Schema 类型切换"]').getByText('标准实体').click()
    await waitFor(async () => (await page.locator('tbody tr').count()) > 0, { label: '实体列表' })
    const widgetRow = page.locator('tbody tr', { hasText: 'E2EWidget' }).first()
    await widgetRow.getByRole('button', { name: '删除' }).click()
    const entConfirm = page.locator('.schema-delete-modal')
    await expect(entConfirm).toBeVisible()
    await entConfirm.getByRole('button', { name: '确认删除' }).click()
    await waitFor(
      async () => !(await page.locator('tbody tr', { hasText: 'E2EWidget' }).first().isVisible().catch(() => false)),
      { label: '实体行消失' },
    )

    // 假删验收：读取路径过滤 + DB 行保留 is_deleted + 图库 TAG 不 DROP
    const after = await apiMust<any>(request, 'GET', '/schema-management/schemas?graphSpace=dev2&pageSize=100', undefined, '删除后清单')
    expect((after.items ?? []).some((s: any) => s.name === 'E2EWidget')).toBe(false)
    const { stdout } = await execFileAsync(
      'docker',
      ['exec', 'tech-kg-temporal-mysql-dev2', 'mysql', '--default-character-set=utf8mb4', '-uroot', '-ptemporal', '-N', '-e',
       "SELECT is_deleted FROM techkg_control.kg_schema_definition WHERE name LIKE 'E2EWidget%'"],
      { timeout: 30_000 },
    )
    expect(stdout.trim()).toContain('1')
    const tagStill = await api<any>(request, 'POST', '/graph-console/query', {
      space: 'dev2',
      statement: 'DESCRIBE TAG E2EWidget',
    })
    expect(tagStill.ok).toBe(true)
  })

  test('清理 M/N 组之外的 e2e 残留', async ({ request }) => {
    // M 组产物：E2eSpaceWidget / E2E_SPACE_RELATES（e2e_verify_space）+ E2eDevOnly（dev2）
    const bList = await api<any>(request, 'GET', '/schema-management/schemas?graphSpace=e2e_verify_space&pageSize=100&includeDetails=true')
    for (const item of bList.data?.items ?? []) {
      await api(request, 'DELETE', `/schema-management/schemas/${item.id}`)
    }
    await dropGraphEdge('E2E_SPACE_RELATES', 'e2e_verify_space')
    await dropGraphTag('E2eSpaceWidget', 'e2e_verify_space')
    await dropGraphTag('E2eDevOnly')
    // Scholar 是修正中心 dual 模式的图投影 tag，H 组每轮幂等重建——留着不删
    //（曾因轮间互踩导致 H3 复核 Tag not found）
    await dropGraphTag('E2EWidget', 'e2e_verify_space')

    // widgets 测试行（e2e_dupe）
    await mysql("DELETE FROM techkg_e2e.widgets WHERE id LIKE 'e2e_dupe%';")

    // e2e 任务（保留历史 e2e抽取-*，只清本轮 e2e任务-* / 审核造数）
    const jobs = await apiMust<any>(request, 'GET', '/workflow-system/jobs', undefined, '任务列表')
    for (const job of jobs.items ?? []) {
      if (/^e2e任务-|^e2e-echo|^e2e-direct/.test(String(job.name))) {
        await api(request, 'DELETE', `/workflow-system/jobs/${job.id}`)
      }
    }

    // 未决 e2e 审核 case
    await execFileAsync(
      'docker',
      ['exec', 'tech-kg-api-dev2', '.venv/bin/python', '-c',
       'from infra.mysql import get_session_factory; from sqlalchemy import text; '
       + 's = get_session_factory()(); '
       + "s.execute(text(\"UPDATE manual_review_case SET status='CANCELLED' WHERE status IN ('OPEN','CLAIMED','RERUNNING','APPLYING')\")); "
       + 's.commit(); s.close()'],
      { timeout: 30_000 },
    )
    // e2e 修正记录
    await execFileAsync(
      'docker',
      ['exec', 'tech-kg-api-dev2', '.venv/bin/python', '-c',
       'from infra.mysql import get_session_factory; from sqlalchemy import text; '
       + 's = get_session_factory()(); '
       + "s.execute(text(\"DELETE FROM kg_manual_correction WHERE title LIKE 'e2e%'\")); "
       + 's.commit(); s.close()'],
      { timeout: 30_000 },
    )
    // e2e 配置（D 组遗留兜底）
    for (const [path, name] of [
      ['/llm-config/llm-configs', 'e2e_llm'],
      ['/mysql-datasources', 'e2e_mysql'],
    ] as const) {
      const list = await api<any>(request, 'GET', path)
      const items = Array.isArray(list.data) ? list.data : (list.data?.items ?? [])
      for (const item of items) {
        if (item.name === name) await api(request, 'DELETE', `${path}/${item.id}`)
      }
    }
  })
})
