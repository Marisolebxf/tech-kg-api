import { request as apiRequest, expect, test } from '@playwright/test'
import catalog from './fixtures/catalog.json' with { type: 'json' }
import { openSchemaPage, searchSchema, selectArcoSearch, shot, sleep, waitFor } from './helpers'

// 阶段 7：前端绑定来源表（行级「···→来源表」弹窗，数据源/库/表/主键列/时间列五级联动）。
// 已知缺口（问题记录⑭，比预想更重）：表单无 querySql 字段，且 47 条 querySql 绑定里大量
// pk/time 是 SQL 合成列（row_pk / wm_col / source_row_id）——不在物理表的列下拉里，
// 连「绑基础五项、CLI 只补 querySql」都做不到。因此：
//   - 纯普通表绑定（16 schema）+ 混合 schema 的普通表部分（12 个）→ 走 UI；
//   - 21 个 schema 的来源（全 querySql / DataSource placeholder）→ CLI PUT 兜底恢复。
type Src = { tableName: string; pkColumn: string; timeColumn: string; querySql?: string | null }
const all: Array<{ name: string; label: string; sources?: Src[] }> = [...catalog.entities, ...catalog.relations]
const DS_LABEL = 'gkx-element-yunfei1'
const DB_NAME = 'gkx_element_yft1'
const plainSources = (rec: { sources?: Src[] }) => (rec.sources || []).filter((s) => !s.querySql)

test.describe.serial('S7 前端绑来源表', () => {
  test('S7a DataSource：placeholder 虚拟表无法经 UI 绑定（取证）', async ({ page }) => {
    await openSchemaPage(page, '标准实体')
    const row = await searchSchema(page, 'DataSource', '数据来源')
    await row.locator('button.schema-action-more').click()
    const item = page.locator('.arco-dropdown-option', { hasText: '来源表' }).first()
    await item.waitFor({ state: 'visible', timeout: 8_000 })
    await item.click()
    const modal = page.locator('.sources-modal')
    await modal.waitFor()
    await modal.locator('button.source-bindings__add').click()
    const rowEl = modal.locator('.source-binding-row').first()
    await selectArcoSearch(page, rowEl.locator('.source-binding-row__ds'), DS_LABEL)
    await selectArcoSearch(page, rowEl.locator('.source-binding-row__db'), DB_NAME)
    // 表下拉搜 placeholder：不存在该物理表 → 选项里没有名为 placeholder 的项（下拉可能
    // 仍列出全部 73 张 dwd 表，断言只看目标项不存在）
    await rowEl.locator('.source-binding-row__table').click()
    const search = rowEl.locator('.source-binding-row__table input').first()
    await search.fill('placeholder')
    await sleep(800)
    await shot(page, 'r2-s7-1-placeholder-table-not-listable')
    const opts = await page
      .locator('.arco-select-dropdown:visible li.arco-select-option')
      .allInnerTexts()
    expect(opts.filter((t) => t.trim() === 'placeholder'), `选项里出现 placeholder: ${opts.slice(0, 5)}`).toEqual([])
    await page.keyboard.press('Escape') // 关掉悬空的空下拉弹层（否则拦截「取消」的点击）
    await sleep(400)
    await modal.getByRole('button', { name: '取消' }).click()
    await waitFor(async () => (await modal.count()) === 0, { timeout: 8_000, label: '来源弹窗关闭' })
  })

  test('S7b UI 重绑普通表来源（精确匹配下拉验证，默认 CITES/Paper/HAS_KEYWORD）', async ({ page }) => {
    // 重绑语义（本轮实测教训）：「来源表」弹窗打开时会预填当前已保存的绑定（openSourcesModal
    // 回填五项），必须先经 UI 逐行删除（.source-binding-row__remove）再加，直接「加一遍」
    // 会造出重复行，保存 PUT 撞后端 uk_kg_schema_source_table 唯一键 → error toast 一闪即逝。
    // 另外预填/保存链路都不含 querySql（toSourcePayload 无该字段），UI 保存会把混合 schema
    // 的 querySql 绑定整体抹掉（问题记录⑭）——重绑目标只取纯普通表 schema。
    // 默认选 pk='id' 且列下拉存在前缀兄弟列（logic_id）的三个（CITES 即 contains 误选的
    // 实锤案例），验证 selectArcoSearch 精确全等不再错绑；REBIND_TARGETS=all 可全量重绑
    // 16 个纯普通表 schema（混合 12 个重绑后需再跑 cli/restore_querysql.py 补回 querySql）。
    test.setTimeout(20 * 60_000)
    const envTargets = (process.env.REBIND_TARGETS || 'CITES,Paper,HAS_KEYWORD')
      .split(',').map((s) => s.trim()).filter(Boolean)
    const targets =
      envTargets[0] === 'all'
        ? all.filter((r) => plainSources(r).length && !(r.sources || []).some((s) => s.querySql))
        : all.filter((r) => envTargets.includes(r.name))
    expect(targets.length, `重绑目标不存在: ${envTargets.join(',')}`).toBeGreaterThan(0)
    await openSchemaPage(page, '标准实体')
    const failed: string[] = []
    for (const rec of targets) {
      const plain = plainSources(rec)
      if (!plain.length) continue
      const isRelation = 'sourceSchemaName' in rec && (rec as any).sourceSchemaName !== undefined
      const tab = await page.locator('.schema-tabs button.active').innerText()
      const wantTab = isRelation ? '关系' : '标准实体'
      if (tab !== wantTab) {
        await page.locator('.schema-tabs button', { hasText: wantTab }).first().click()
        await sleep(600)
      }
      try {
        const row = await searchSchema(page, rec.name, rec.label)
        await row.locator('button.schema-action-more').click()
        const item = page.locator('.arco-dropdown-option', { hasText: '来源表' }).first()
        await item.waitFor({ state: 'visible', timeout: 8_000 })
        await item.click()
        const modal = page.locator('.sources-modal')
        await modal.waitFor()

        // 清空预填行（已保存的绑定会回显成行；不清就加会重复 → PUT 撞唯一键）
        for (let guard = 0; guard < 30; guard++) {
          const del = modal.locator('.source-binding-row__remove').last()
          if (!(await del.count())) break
          await del.click()
          await sleep(120)
        }
        if (await modal.locator('.source-binding-row').count()) {
          throw new Error('预填行未清空')
        }

        for (const src of plain) {
          await modal.locator('button.source-bindings__add').click()
          const rowEl = modal.locator('.source-binding-row').last()
          await rowEl.waitFor({ timeout: 5_000 })
          await selectArcoSearch(page, rowEl.locator('.source-binding-row__ds'), DS_LABEL)
          await selectArcoSearch(page, rowEl.locator('.source-binding-row__db'), DB_NAME)
          await selectArcoSearch(page, rowEl.locator('.source-binding-row__table'), src.tableName)
          await selectArcoSearch(page, rowEl.locator('.source-binding-row__col').nth(0), src.pkColumn)
          await selectArcoSearch(page, rowEl.locator('.source-binding-row__col').nth(1), src.timeColumn)
        }

        await modal.getByRole('button', { name: '保存绑定' }).click()
        await waitFor(
          async () => (await page.getByText('来源表绑定已保存').first().isVisible().catch(() => false)),
          { timeout: 20_000, interval: 800, label: `${rec.name} 保存绑定 toast` },
        )
        await modal.getByRole('button', { name: '取消' }).click()
        await waitFor(async () => (await modal.count()) === 0, { timeout: 8_000, label: '来源弹窗关闭' })
        await sleep(300)
      } catch (e) {
        await shot(page, `r2-s7-fail-${rec.name}`).catch(() => undefined)
        failed.push(`${rec.name}: ${String(e).slice(0, 140)}`)
        // 尽量关掉残留弹窗再继续
        await page.keyboard.press('Escape').catch(() => undefined)
        await sleep(500)
        const modal = page.locator('.sources-modal')
        if (await modal.count()) await modal.getByRole('button', { name: '取消' }).click().catch(() => undefined)
      }
    }
    expect(failed, `来源重绑失败的 schema: ${failed.join(' || ')}`).toEqual([])
  })

  test('S7c API 核验：全量 49 schema 来源六元组与清场前逐字段全等', async () => {
    // 不只核条数——CITES 的教训是 pk 列被 contains 误选成 logic_id 时条数全对；
    // 逐条核 表/主键列/时间列/querySql（集合比较，顺序无关）。
    const req = await apiRequest.newContext()
    const byName = new Map<string, any>()
    for (const kind of ['entity', 'relation']) {
      const resp = await req.get(
        `http://localhost:8004/api/v1/schema-management/schemas?kind=${kind}&page=1&pageSize=100&includeDetails=true&graphSpace=yunfei_test_1`,
      )
      // 先建全量名单再统一对账（否则 entity 轮会把关系 rec 全算成 0 来源）
      for (const it of (await resp.json())?.data?.items ?? []) byName.set(it.name, it)
    }
    const problems: string[] = []
    let qsCount = 0
    for (const rec of all) {
      const want = (rec.sources || []).map((s: any) =>
        `${s.tableName}|${s.pkColumn}|${s.timeColumn}|${s.querySql || ''}`).sort()
      const got = ((byName.get(rec.name)?.sources || []) as any[]).map((s) =>
        `${s.tableName}|${s.pkColumn}|${s.timeColumn}|${s.querySql || ''}`).sort()
      qsCount += (byName.get(rec.name)?.sources || []).filter((s: any) => s.querySql).length
      if (JSON.stringify(want) !== JSON.stringify(got)) {
        problems.push(`${rec.name}: 期望 ${JSON.stringify(want)} 实得 ${JSON.stringify(got)}`)
      }
    }
    expect(problems, `来源不符: ${problems.join(' ;; ')}`).toEqual([])
    expect(qsCount, 'querySql 绑定总数（UI 重绑不得触碰）').toBe(47)
  })
})
