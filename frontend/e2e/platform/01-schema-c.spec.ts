import { expect, test } from '@playwright/test'
import {
  api,
  apiMust,
  describeColumns,
  dropGraphEdge,
  dropGraphTag,
  graphCount,
  resetWidgetRows,
  selectArcoScrolled,
  waitFor,
  WIDGET_SCRIPT,
} from './helpers'

// C. Schema 管理与属性管理（/schema）——欠账验收组（ae31551）。
// 顺序链：C1 列表 → C2 建实体 E2EWidget → C3 传脚本 → C4 绑源抽取 →
// C5 加属性(角标) → C6 回填 → C7 属性硬删 → C8 非法脚本 → C9 关系。
// 删除（C10 假删）与统一清理在 99-cleanup 执行（E/F 组依赖本组产物）。
// 偏差记录：属性类型表无 int32（string/int64/double/bool/date/datetime/geo/fixed_string），
// price 用 int64；目录会自动注入公共列与溯源列，DDL/属性行多于用户填写的 3 列。
test.describe.serial('C. Schema 管理与属性管理', () => {
  const NAME = 'E2EWidget'
  let schemaId = ''

  test.beforeAll(async ({ request }) => {
    // 清掉旧 E2EWidget（目录软删）+ 图库残留 TAG/EDGE（旧 TAG 会让
    // CREATE TAG IF NOT EXISTS 跳过，目录属性与图库列漂移）+ 重置测试数据
    const data = await apiMust<any>(
      request,
      'GET',
      '/schema-management/schemas?graphSpace=dev2&pageSize=100&includeDetails=true',
      undefined,
      '列 schema',
    )
    for (const item of data.items ?? []) {
      if (item.name === NAME) await api(request, 'DELETE', `/schema-management/schemas/${item.id}`)
    }
    await dropGraphEdge('E2E_RELATES')
    await dropGraphTag(NAME)
    await resetWidgetRows()
    const ds = await apiMust<any>(request, 'GET', '/mysql-datasources', undefined, '列数据源')
    const list = Array.isArray(ds) ? ds : (ds.items ?? [])
    const existing = list.find((d: any) => d.name === 'e2e-mysql-src' && d.host === 'temporal-mysql-dev2')
    if (existing) {
      await api(request, 'DELETE', `/mysql-datasources/${existing.id}`)
    }
    await apiMust<any>(
      request,
      'POST',
      '/mysql-datasources',
      {
        name: 'e2e-mysql-src',
        host: 'temporal-mysql-dev2',
        port: 3306,
        username: 'root',
        password: 'temporal',
        defaultDatabase: 'techkg_e2e',
        description: 'e2e 抽取数据源',
      },
      '建数据源',
    )
  })

  test('C1 列表与拓扑加载 + 属性一等公民展示', async ({ page, request }) => {
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')

    // 拓扑画布 + 图空间选择器
    await expect(page.getByText('Schema 拓扑总览')).toBeVisible()
    await expect(page.locator('[aria-label="Schema 实体关系拓扑"]')).toBeVisible()
    await expect(page.locator('.space-picker')).toBeVisible()

    // 两个 Tab 可切换，行数与 API 一致
    const data = await apiMust<any>(
      request,
      'GET',
      '/schema-management/schemas?graphSpace=dev2&pageSize=100&includeDetails=true',
      undefined,
      '列 schema',
    )
    const entities = (data.items ?? []).filter((s: any) => s.kind === 'entity')
    const relations = (data.items ?? []).filter((s: any) => s.kind === 'relation')
    await expect(page.locator('tbody tr').first()).toBeVisible()
    const entityCount = await page.locator('[aria-label="Schema 类型切换"]').getByText('标准实体').innerText()
    await page.locator('[aria-label="Schema 类型切换"]').getByText('关系').click()
    await waitFor(
      async () => (await page.locator('tbody tr').count()) > 0,
      { label: '关系列表加载' },
    )
    // 行数量级与 API 一致（页面无分页时全量展示）
    const relRows = await page.locator('tbody tr').count()
    expect(relRows).toBeGreaterThanOrEqual(Math.min(relations.length, 1))
    await page.locator('[aria-label="Schema 类型切换"]').getByText('标准实体').click()

    // 搜索框可过滤（客户端过滤：行数收敛且含 Person 行）
    const rowsBefore = await page.locator('tbody tr').count()
    await page.locator('.schema-search-input input').fill('Person')
    await waitFor(
      async () => {
        const rows = page.locator('tbody tr')
        const n = await rows.count()
        if (n === 0 || n >= rowsBefore) return false
        return (await rows.filter({ hasText: 'Person' }).count()) >= 1
      },
      { label: '搜索过滤 Person' },
    )
    await page.locator('.schema-search-input input').fill('')

    // 属性展示断言：实体行展示属性 chip（抽查 Person 行）
    const personRow = page.locator('tbody tr', { hasText: 'Person' }).first()
    await expect(personRow).toBeVisible()
    const chips = await apiMust<any>(
      request,
      'GET',
      `/schema-management/schemas?graphSpace=dev2&pageSize=100&keyword=Person&includeDetails=true`,
      undefined,
      '搜 Person',
    )
    const detail = (chips.items ?? []).find((s: any) => s.name === 'Person')
    if (detail) {
      const full = await apiMust<any>(request, 'GET', `/schema-management/schemas/${detail.id}`, undefined, 'Person 详情')
      const firstProp = full.properties?.[0]
      if (firstProp) {
        await expect(personRow.getByText(`${firstProp.name}:`, { exact: false }).first()).toBeVisible()
      }
    }
    expect(entities.length).toBeGreaterThan(0)
  })

  test('C2 新增标准实体（含 nGQL 预览）', async ({ page, request }) => {
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    await page.locator('.space-picker .arco-select-view-single').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'dev2' }).first().click()
    await waitFor(async () => (await page.locator('tbody tr').count()) > 0, { label: '切空间后列表' })

    await page.getByRole('button', { name: '＋ 增加' }).click()
    const modal = page.locator('.schema-create-modal')
    await expect(modal).toBeVisible()

    // 图空间默认跟随 activeSpace=dev2（无需重选；重选会因值未变合层导致点击悬空）
    const spaceValue = await modal
      .locator('.create-field', { hasText: '图空间' })
      .locator('.arco-select-view-value')
      .first()
      .innerText()
    expect(spaceValue).toContain('dev2')
    await modal.locator('input[placeholder="Gadget"]').fill(NAME)
    await modal.locator('input[placeholder="如：技术"]').fill('E2E测试挂件')
    await modal.locator('textarea').first().fill('e2e 属性管理验收')

    // 属性：id/name 为公共锁定行；追加 price(int64)
    await modal.locator('button.create-props__add').click()
    const propRow = modal.locator('.create-prop-row:not(.create-prop-row--locked)').last()
    await propRow.locator('input.prop-name').fill('price')
    await propRow.locator('.prop-type').click()
    await modal.locator('li.arco-select-option:visible', { hasText: 'int64' }).first().click()

    // 两段式：预览并创建 → nGQL 预览 → 确认创建
    await modal.getByRole('button', { name: '预览并创建' }).click()
    await expect(modal.getByText('nGQL 预览（创建时将执行）')).toBeVisible()
    const ddl = await modal.locator('pre').first().innerText()
    expect(ddl).toContain('CREATE TAG')
    expect(ddl).toContain('id')
    expect(ddl).toContain('name')
    expect(ddl).toContain('price')
    await modal.getByRole('button', { name: '确认创建' }).click()

    // 表格出现新行 + 属性 chip
    const newRow = page.locator('tbody tr', { hasText: NAME }).first()
    await expect(newRow).toBeVisible({ timeout: 30_000 })
    await expect(newRow.getByText('price:int64', { exact: false })).toBeVisible()

    // 图库 + API 复核
    const cols = await describeColumns(request, 'dev2', 'TAG', NAME)
    for (const c of ['id', 'name', 'price']) expect(cols).toContain(c)
    const data = await apiMust<any>(
      request,
      'GET',
      `/schema-management/schemas?graphSpace=dev2&keyword=${NAME}&includeDetails=true`,
      undefined,
      '查 E2EWidget',
    )
    schemaId = (data.items ?? []).find((s: any) => s.name === NAME)?.id ?? ''
    expect(schemaId).toBeTruthy()
  })

  test('C3 上传/更换抽取脚本（合法脚本）', async ({ page, request }) => {
    test.setTimeout(240_000)
    test.skip(!schemaId, 'C2 未产出 schemaId')
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: NAME }).first()
    await expect(row).toBeVisible()
    await row.getByRole('button', { name: /上传脚本|更换脚本/ }).click()

    // LLM 安全校验偶发慢：单次 60s 未完成则关闭重传（最多 3 次）
    for (let attempt = 1; attempt <= 3; attempt++) {
      const modal = page.locator('.script-upload-modal')
      await expect(modal).toBeVisible()
      await modal.getByRole('button', { name: '选择 .py 文件' }).click()
      // 文件 input 挂在页面级（modal 外）
      await page.locator('input[type="file"][accept=".py"]').setInputFiles({
        name: 'e2e_widget_extract.py',
        mimeType: 'text/x-python',
        buffer: Buffer.from(WIDGET_SCRIPT, 'utf-8'),
      })
      const success = modal.getByText('脚本已通过安全校验并保存')
      const failed = modal.getByText('校验未通过')
      let ok = false
      let failInfo = ''
      const deadline = Date.now() + 90_000
      while (Date.now() < deadline) {
        if (await success.isVisible().catch(() => false)) { ok = true; break }
        if (await failed.isVisible().catch(() => false)) {
          failInfo = await modal.innerText()
          break
        }
        await page.waitForTimeout(1000)
      }
      if (ok) break
      if (failInfo) throw new Error(`合法脚本被安全校验误拦（attempt ${attempt}）：${failInfo.replace(/\n+/g, ' | ').slice(0, 300)}`)
      expect(attempt, '脚本上传校验三次均未完成').toBeLessThan(3)
      await modal.locator('header button').click()
    }
    await page.locator('.script-upload-modal').getByRole('button', { name: '关闭' }).click()

    // 行上出现 查看脚本 →，可打开看到源码
    await expect(row.getByRole('button', { name: '查看脚本 →' })).toBeVisible()
    await row.getByRole('button', { name: '查看脚本 →' }).click()
    const viewModal = page.locator('.script-view-modal')
    await expect(viewModal).toBeVisible()
    await expect(viewModal.getByText('def transform')).toBeVisible()
    await viewModal.getByRole('button', { name: '关闭' }).click()

    // API：脚本绑定信息 + 无「落后 N 版」角标
    const detail = await apiMust<any>(request, 'GET', `/schema-management/schemas/${schemaId}`, undefined, '详情')
    expect(detail.script?.capturedRevision ?? detail.script).toBeTruthy()
    await expect(row.getByText(/落后 \d+ 版/)).toHaveCount(0)
  })

  test('C4 绑定来源表并触发抽取', async ({ page, request }) => {
    test.skip(!schemaId, 'C2 未产出 schemaId')
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: NAME }).first()
    await row.getByRole('button', { name: '来源表' }).click()

    const modal = page.locator('.sources-modal')
    await expect(modal).toBeVisible()

    // ＋ 绑定来源表 → 数据源/库/表
    await modal.getByRole('button', { name: '＋ 绑定来源表' }).click()
    const bindRow = modal.locator('.source-binding-row').last()
    await bindRow.locator('.source-binding-row__ds').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'e2e-mysql-src' }).first().click()
    await bindRow.locator('.source-binding-row__db').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'techkg_e2e' }).first().click()
    await bindRow.locator('.source-binding-row__table').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'widgets' }).first().click()

    // 保存并触发抽取
    await modal.getByRole('button', { name: '保存并触发抽取' }).click()
    await waitFor(
      async () => (await page.getByText(/抽取已触发（执行/, { exact: false }).first().isVisible().catch(() => false)),
      { label: '抽取触发提示', timeout: 30_000 },
    )

    // 执行完成（来源触发的抽取产生执行记录；平台抽取执行不建 job，经执行列表核对）
    let executionId = ''
    const doneExec = await waitFor(
      async () => {
        const list = await apiMust<any>(request, 'GET', '/workflow-system/executions?limit=30', undefined, '执行列表')
        const mine = (list.items ?? []).filter((e: any) => e.payload?.schemaId === schemaId)
        if (!mine.length) return null
        // 列表状态可能滞后于 Temporal：RUNNING 的执行回查详情确认终态
        for (const e of mine) {
          let status = e.status
          if (status === 'RUNNING') {
            const detail = await api<any>(request, 'GET', `/workflow-system/executions/${e.id}`)
            status = detail.data?.status ?? status
          }
          if (['COMPLETED', 'FAILED'].includes(status)) {
            executionId = e.id
            return status === 'COMPLETED' ? e : null
          }
        }
        return null
      },
      { timeout: 240_000, label: '抽取执行完成' },
    )
    expect(doneExec).toBeTruthy()
    const count = await graphCount(request, 'dev2', `(v:${NAME})`)
    expect(count).toBeGreaterThanOrEqual(1)
    // schema 无「落后 N 版」角标
    const rowAgain = page.locator('tbody tr', { hasText: NAME }).first()
    await expect(rowAgain.getByText(/落后 \d+ 版/)).toHaveCount(0)
  })

  test('C5 新增属性 → 「落后 N 版」角标', async ({ page, request }) => {
    test.skip(!schemaId, 'C2 未产出 schemaId')
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: NAME }).first()
    await row.getByRole('button', { name: '属性管理' }).click()

    const modal = page.locator('.property-modal')
    await expect(modal).toBeVisible()
    await modal.locator('input[placeholder="属性名（字母/数字/下划线）"]').fill('e2e_prop')
    await modal.getByRole('button', { name: '＋ 新增属性' }).click()
    await expect(modal.getByText('e2e_prop').first()).toBeVisible({ timeout: 30_000 })

    // 触发重新抽取弹窗 → 稍后再说
    const extractConfirm = page.locator('.property-extract-modal')
    await expect(extractConfirm).toBeVisible({ timeout: 30_000 })
    await extractConfirm.getByRole('button', { name: '稍后再说' }).click()
    await modal.getByRole('button', { name: '关闭' }).click()

    // 行上出现 落后 1 版 角标；图库含新列
    await expect(row.getByText(/落后 1 版/)).toBeVisible({ timeout: 30_000 })
    const cols = await describeColumns(request, 'dev2', 'TAG', NAME)
    expect(cols).toContain('e2e_prop')
  })

  test('C6 回填历史数据（含强确认弹窗）', async ({ page, request }) => {
    test.skip(!schemaId, 'C2 未产出 schemaId')
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: NAME }).first()
    await row.getByRole('button', { name: '来源表' }).click()
    const modal = page.locator('.sources-modal')
    await expect(modal).toBeVisible()

    await modal.getByRole('button', { name: '回填历史数据' }).click()
    // 强确认弹窗：文案含「未覆盖最新属性（落后 N 版），回填可能无效」
    const confirmModal = page.locator('.backfill-confirm-modal')
    await expect(confirmModal).toBeVisible()
    await expect(confirmModal.getByText(/落后 \d+ 版[）)]?，回填可能无效/)).toBeVisible()
    // 触发前记录已有执行 ID 集合：回填产生的是"新 ID"，避免误匹配旧执行
    const beforeIds = new Set((await countSchemaExecs(request, schemaId)).map((e: any) => e.id))
    await confirmModal.getByRole('button', { name: '仍要回填' }).click()
    await waitFor(
      async () => (await page.getByText(/回填已触发（执行/, { exact: false }).first().isVisible().catch(() => false)),
      { label: '回填触发提示', timeout: 30_000 },
    )

    // 回填执行（新 ID）终态且完成
    await waitFor(
      async () => {
        const mine = await countSchemaExecs(request, schemaId)
        const fresh = mine.filter((e: any) => !beforeIds.has(e.id))
        if (!fresh.length) return null
        // 列表状态可能滞后：回查详情
        for (const e of fresh) {
          let status = e.status
          if (status === 'RUNNING') {
            const detail = await api<any>(request, 'GET', `/workflow-system/executions/${e.id}`)
            status = detail.data?.status ?? status
          }
          if (status === 'COMPLETED') return e
        }
        return null
      },
      { timeout: 240_000, label: '回填执行完成' },
    )
  })

  test('C7 属性硬删除 + 硬拦', async ({ page, request }) => {
    test.skip(!schemaId, 'C2 未产出 schemaId')
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: NAME }).first()
    await row.getByRole('button', { name: '属性管理' }).click()
    const modal = page.locator('.property-modal')
    await expect(modal).toBeVisible()

    // ① 删除 e2e_prop → 确认弹窗（不可逆）→ 确认删除 → 触发重新抽取弹窗 → 稍后再说
    const propRow = modal.locator('.property-table__row', { hasText: 'e2e_prop' }).first()
    await propRow.getByRole('button', { name: '删除' }).click()
    const confirmModal = page.locator('.property-delete-modal')
    await expect(confirmModal).toBeVisible()
    await expect(confirmModal.getByText(/此操作不可逆/)).toBeVisible()
    await expect(confirmModal.getByText(/ALTER/)).toBeVisible()
    await confirmModal.getByRole('button', { name: '确认删除（不可逆）' }).click()
    await waitFor(
      async () => !(await modal.locator('.property-table__row', { hasText: 'e2e_prop' }).first().isVisible().catch(() => false)),
      { label: 'e2e_prop 属性行消失' },
    )
    const extractConfirm = page.locator('.property-extract-modal')
    if (await extractConfirm.isVisible().catch(() => false)) {
      await extractConfirm.getByRole('button', { name: '稍后再说' }).click()
    }

    // ② 必填属性（id/name）无删除入口：🔒 公共属性行只显示"公共属性"说明
    const lockedRows = modal.locator('.property-table__row--locked')
    expect(await lockedRows.count()).toBeGreaterThanOrEqual(2)
    await expect(lockedRows.first().getByRole('button', { name: '删除' })).toHaveCount(0)
    await expect(lockedRows.first().getByText('公共属性')).toBeVisible()

    await modal.getByRole('button', { name: '关闭' }).click()

    // 图库复核：e2e_prop 列已 ALTER DROP；id/name 仍在
    const cols = await describeColumns(request, 'dev2', 'TAG', NAME)
    expect(cols).not.toContain('e2e_prop')
    expect(cols).toContain('id')
    expect(cols).toContain('name')
  })

  test('C8 非法脚本上传被安全校验拦截', async ({ page, request }) => {
    test.setTimeout(240_000)
    test.skip(!schemaId, 'C2 未产出 schemaId')
    const before = await apiMust<any>(request, 'GET', `/schema-management/schemas/${schemaId}/script/content`, undefined, '原脚本')
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    const row = page.locator('tbody tr', { hasText: NAME }).first()
    await row.getByRole('button', { name: /上传脚本|更换脚本/ }).click()
    const modal = page.locator('.script-upload-modal')
    await expect(modal).toBeVisible()
    await modal.getByRole('button', { name: /选择 \.py 文件|重新选择/ }).click()
    await page.locator('input[type="file"][accept=".py"]').setInputFiles({
      name: 'bad_script.py',
      mimeType: 'text/x-python',
      buffer: Buffer.from('import os\n\n\ndef transform(payload):\n    with open("/etc/passwd") as f:\n        return {"entities": [], "failures": []}\n', 'utf-8'),
    })
    await expect(modal.getByText('校验未通过')).toBeVisible({ timeout: 180_000 })
    await expect(modal.locator('ul li').first()).toBeVisible()
    await modal.getByRole('button', { name: '重新选择' }).click()
    await modal.getByRole('button', { name: '取消' }).click().catch(() => {})

    // 原脚本绑定不被破坏
    const after = await apiMust<any>(request, 'GET', `/schema-management/schemas/${schemaId}/script/content`, undefined, '脚本复核')
    expect(JSON.stringify(after)).toBe(JSON.stringify(before))
  })

  test('C12 权限：标准实体/关系只读（条件分支）', async () => {
    // 方案 C12：需 AUTH_ENABLED=true + 普通/管理员双账号。dev2 测试栈
    // AUTH_ENABLED=false（admin 校验直通，UI 无法区分角色）→ 本用例仅具备
    // 双账号环境时执行；角色判定由后端集成测试覆盖（tests/integration/test_schema_*）。
    test.skip(true, '需 AUTH_ENABLED=true 双账号环境（dev2 免登录栈不满足）')
  })

  test('C9 新增关系（含起点/终点）', async ({ page, request }) => {
    await page.goto('/schema')
    await page.waitForLoadState('networkidle')
    await page.locator('[aria-label="Schema 类型切换"]').getByText('关系').click()
    await waitFor(
      async () => (await page.locator('tbody tr').count()) > 0,
      { label: '关系列表' },
    )
    await page.getByRole('button', { name: '＋ 增加' }).click()
    const modal = page.locator('.schema-create-modal')
    await expect(modal).toBeVisible()
    const relSpace = await modal
      .locator('.create-field', { hasText: '图空间' })
      .locator('.arco-select-view-value')
      .first()
      .innerText()
    expect(relSpace).toContain('dev2')
    await modal.locator('input[placeholder="USES_TECHNOLOGY"]').fill('E2E_RELATES')
    await modal.locator('input[placeholder="如：技术"]').fill('E2E挂件关系')
    // 起点/终点选 E2EWidget（下拉只列当前空间实体；长列表虚拟滚动需滚动查找）
    await selectArcoScrolled(page, modal.locator('.create-field', { hasText: '起点实体' }).locator('.arco-select-view-single'), NAME)
    await selectArcoScrolled(page, modal.locator('.create-field', { hasText: '终点实体' }).locator('.arco-select-view-single'), NAME)

    await modal.getByRole('button', { name: '预览并创建' }).click()
    const ddl = await modal.locator('pre').first().innerText()
    expect(ddl).toContain('CREATE EDGE')
    await modal.getByRole('button', { name: '确认创建' }).click()
    await expect(page.locator('tbody tr', { hasText: 'E2E_RELATES' }).first()).toBeVisible({ timeout: 30_000 })

    const cols = await describeColumns(request, 'dev2', 'EDGE', 'E2E_RELATES')
    expect(cols.length).toBeGreaterThan(0)
  })
})

async function countSchemaExecs(request: any, sid: string): Promise<any[]> {
  const list = await apiMust<any>(request, 'GET', '/workflow-system/executions?limit=30', undefined, '执行列表')
  return (list.items ?? []).filter((e: any) => e.payload?.schemaId === sid)
}
