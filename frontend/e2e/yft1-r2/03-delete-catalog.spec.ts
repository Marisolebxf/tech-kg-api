import type { Page } from '@playwright/test'
import { request as apiRequest, expect, test } from '@playwright/test'
import catalog from './fixtures/catalog.json' with { type: 'json' }
import { findSchemaRow, openSchemaPage, shot, sleep, waitFor } from './helpers'

// 阶段 3：前端清空 Schema 目录（本轮新增要求——上一轮目录沿用 09-30 旧绑定，
// 本轮 49 个定义全部经前端删掉重建，才能验证「建实体关系/绑脚本」的前端通道）。
// 顺序：先删 33 个关系（实体删除被「仍被关系引用」阻断），再删 16 个实体。
// 删除会连带清理图数据 + DROP TAG/EDGE（本空间刚重建为空壳 → typeExisted=false 快速路径）。
// 逐项一个用例：单条失败不吞其它项，且天然幂等（已删项搜索无行 → 跳过），可整文件重跑续删。
const relations: Array<{ name: string; label: string }> = catalog.relations
// 实体按名字长度降序删：搜索是 contains 匹配，'Organization' 会连 'OrganizationBase'
// 一起搜出（两行第 2 列截断文本同为「Organizatio…」无法区分）——先删长名兄弟即无歧义。
const entities: Array<{ name: string; label: string }> = [...catalog.entities].sort(
  (a, b) => b.name.length - a.name.length,
)

async function deleteViaUi(page: Page, name: string, label?: string): Promise<'deleted' | 'already'> {
  const row = await findSchemaRow(page, name, label)
  if (!row) return 'already'
  await row.locator('button.schema-action-more').click()
  const del = page.locator('.arco-dropdown-option', { hasText: '删除' }).first()
  await del.waitFor({ state: 'visible', timeout: 8_000 })
  await del.click()
  const modal = page.locator('.schema-delete-modal')
  await modal.waitFor({ timeout: 8_000 })
  // 实体删除等「关系引用检查」完成，确认按钮从 disabled 变 enabled
  await waitFor(
    async () => await modal.locator('footer button.danger').isEnabled(),
    { timeout: 20_000, interval: 800, label: `${name} 删除确认可点` },
  )
  await modal.locator('footer button.danger').click()
  await waitFor(
    async () => (await modal.count()) === 0,
    { timeout: 100_000, interval: 1_000, label: `${name} 删除弹窗关闭` },
  )
  await sleep(300)
  // 删后复核：重新搜索，该行应已消失
  if (await findSchemaRow(page, name, label)) throw new Error(`${name} 删除后仍可在列表命中`)
  return 'deleted'
}

/** 删除带重试：Nebula 内存水位（问题⑫）会间歇性把后端「查图数据」请求打成 500 →
 *  DELETE 502 → 弹窗滞留错误态（toast 已逝）。关掉弹窗退避后整删重试；水位是波动的，
 *  前 15 个关系都能过。幂等：迟到成功的删除在重试的搜索步自然跳过。 */
async function deleteViaUiRetry(page: Page, name: string, label?: string, attempts = 4): Promise<'deleted' | 'already'> {
  let lastErr: unknown = null
  for (let i = 0; i < attempts; i++) {
    try {
      return await deleteViaUi(page, name, label)
    } catch (e) {
      lastErr = e
      const modal = page.locator('.schema-delete-modal')
      if (await modal.count()) {
        await modal.getByRole('button', { name: '取消' }).click().catch(() => undefined)
        await sleep(1_500)
      }
      await sleep(12_000)
    }
  }
  throw lastErr
}

test.describe.serial('S3 前端清空 Schema 目录', () => {
  test.beforeEach(async () => {
    // 单条删除含最多 4 次重试（每次最长 ~110s：SHOW EDGES 30s 超时 + 图数据查询 30s + 退避）
    test.setTimeout(600_000)
  })

  for (const r of relations) {
    test(`S3a 删除关系 ${r.name}（${r.label}）`, async ({ page }) => {
      await openSchemaPage(page, '关系')
      const state = await deleteViaUiRetry(page, r.name, r.label)
      if (state === 'already') test.skip(true, `${r.name} 已不存在（幂等跳过）`)
    })
  }

  for (const e of entities) {
    test(`S3b 删除实体 ${e.name}（${e.label}）`, async ({ page }) => {
      await openSchemaPage(page, '标准实体')
      const state = await deleteViaUiRetry(page, e.name, e.label)
      if (state === 'already') test.skip(true, `${e.name} 已不存在（幂等跳过）`)
    })
  }

  test('S3c 目录清零核验（UI 总数 + API）', async ({ page }) => {
    await openSchemaPage(page, '标准实体')
    // 清空关键字重新查询（空 keyword 时接口 URL 不带 keyword= 参数，不能复用 submitSearch）
    const respPromise = page.waitForResponse(
      (r) => r.url().includes('/api/v1/schema-management/schemas'),
      { timeout: 15_000 },
    )
    await page.locator('.schema-search-input input').fill('')
    await page.locator('.schema-toolbar__actions button[type="submit"]').click()
    await respPromise
    await sleep(600)
    await expect(page.locator('.list-pagination__summary')).toHaveText(/共 0 条/)
    await page.locator('.schema-tabs button', { hasText: '关系' }).first().click()
    await sleep(800)
    await expect(page.locator('.list-pagination__summary')).toHaveText(/共 0 条/)
    await shot(page, 'r2-s3-3-catalog-empty')

    const req = await apiRequest.newContext()
    for (const kind of ['entity', 'relation']) {
      const resp = await req.get(`http://localhost:8004/api/v1/schema-management/schemas?kind=${kind}&page=1&pageSize=1&graphSpace=yunfei_test_1`)
      const body = await resp.json()
      expect(body?.data?.total ?? -1).toBe(0)
    }
  })
})
