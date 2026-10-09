import { request as apiRequest, test } from '@playwright/test'
import catalog from './fixtures/catalog.json' with { type: 'json' }
import { ART_DIR, openSchemaPage, sleep } from './helpers'
import { createSchemaViaUi } from './schemaForm'
import path from 'node:path'

// 阶段 4：前端新建 16 个实体 Schema（目录 + 图 DDL 一步完成）。
// 属性全量按上一轮目录导出录入（670 行中实体部分）；锁定必填行自动带出。
// 注意：锁定行必填 → 图 DDL 带 NOT NULL（与离线域整行 INSERT 冲突，问题记录⑬；
// DDL 预览截图即证据，链前由 CLI 归一化为全可空——同手册 §4 预建口径）。
const entities = catalog.entities

test.describe.serial('S4 前端建 16 实体', () => {
  for (const [i, rec] of entities.entries()) {
    test(`S4-${String(i + 1).padStart(2, '0')} ${rec.name}`, async ({ page }) => {
      await openSchemaPage(page, '标准实体')
      await createSchemaViaUi(page, rec, {
        ddlShot: i === 0 ? path.join(ART_DIR, 'r2-s4-1-ddl-preview-notnull.png') : undefined,
      })
      await sleep(300)
    })
  }

  test('S4-VERIFY 16 实体全部在目录', async ({ request }) => {
    const req = await apiRequest.newContext()
    const resp = await req.get(
      'http://localhost:8004/api/v1/schema-management/schemas?kind=entity&page=1&pageSize=1&graphSpace=yunfei_test_1',
    )
    const body = await resp.json()
    if ((body?.data?.total ?? 0) !== entities.length) {
      throw new Error(`实体目录数 ${body?.data?.total} ≠ ${entities.length}`)
    }
  })
})
