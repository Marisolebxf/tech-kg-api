import type { Locator, Page } from '@playwright/test'
import { expect } from '@playwright/test'
import { selectArcoClick, searchSchema, sleep, waitFor } from './helpers'

// 新建 Schema 弹窗的表单驱动（04 实体 / 05 关系共用）。
// 口径：fixtures/catalog.json 里每个 schema 的 props 是「去掉锁定必填行」后的全部
// 属性（含溯源名列，保 dataType 口径）；锁定行（实体 id/name/create_time/update_time/
// source_table，关系 create_time/update_time/source_table）由前端表单自动带出且锁死必填。

export interface FixtureProp {
  name: string
  dataType: string
  required: boolean
}

export interface FixtureSchema {
  name: string
  label: string
  description: string
  props: FixtureProp[]
}

export async function createSchemaViaUi(
  page: Page,
  rec: FixtureSchema,
  opts: { relation?: boolean; sourceSchemaName?: string; targetSchemaName?: string; ddlShot?: string } = {},
): Promise<void> {
  await page.locator('.schema-toolbar__actions button', { hasText: '＋ 增加' }).click()
  const modal = page.locator('.schema-create-modal')
  await modal.waitFor({ timeout: 10_000 })

  await modal.locator('input[aria-label="name"]').fill(rec.name)
  await modal.locator('input[aria-label="如：技术"]').fill(rec.label)
  const desc = modal.locator('textarea').first()
  if (rec.description) await desc.fill(rec.description)

  if (opts.relation) {
    for (const [fieldLabel, entityName] of [
      ['起点实体', opts.sourceSchemaName!],
      ['终点实体', opts.targetSchemaName!],
    ] as const) {
      const field = modal.locator('.create-field', { hasText: fieldLabel }).first()
      await selectArcoClick(page, field.locator('.schema-select'), `${entityName}（`)
    }
  }

  // 属性列表：锁定行已预置，逐个追加业务属性
  for (const prop of rec.props) {
    await modal.locator('button.create-props__add').click()
    const row = modal.locator('.create-prop-row:not(.create-prop-row--locked)').last()
    await row.waitFor({ timeout: 5_000 })
    await row.locator('input[aria-label="属性名"]').fill(prop.name)
    if (prop.dataType !== 'string') {
      await selectArcoClick(page, row.locator('.prop-type'), prop.dataType)
    }
    if (prop.required) {
      await row.locator('.prop-required input[type="checkbox"]').check()
    }
  }

  if (opts.ddlShot) {
    // DDL 预览是 NOT NULL 问题的直接 UI 证据（锁定行 NOT NULL）
    await sleep(300)
    await page.screenshot({ path: opts.ddlShot })
  }

  // 两步确认：预览并创建 → 确认创建
  await modal.getByRole('button', { name: '预览并创建' }).click()
  const confirmBtn = modal.getByRole('button', { name: '确认创建' })
  await confirmBtn.waitFor({ state: 'visible', timeout: 10_000 })
  await confirmBtn.click()
  // 创建 + DDL 执行（含重试）→ 弹窗关闭
  await waitFor(
    async () => (await modal.count()) === 0,
    { timeout: 90_000, interval: 1_000, label: `${rec.name} 创建弹窗关闭` },
  )
  await sleep(500)

  // 列表核验：搜索出目标行
  const row: Locator = await searchSchema(page, rec.name)
  await row.waitFor({ timeout: 15_000 })
  await expect(row).toBeVisible()
}
