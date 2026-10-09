import { request as apiRequest, test } from '@playwright/test'
import catalog from './fixtures/catalog.json' with { type: 'json' }
import { ART_DIR, openSchemaPage, sleep } from './helpers'
import { createSchemaViaUi } from './schemaForm'
import path from 'node:path'

// 阶段 5：前端新建 33 个关系 Schema（起点/终点实体下拉选自阶段 4 建的 16 实体）。
// 已知口径漂移：UI 建关系 relationCategory 恒为 inferred（「事实关系」分支不可达），
// 旧目录全部为 fact —— 记为问题（展示层字段，不影响抽取）。
const relations = catalog.relations

test.describe.serial('S5 前端建 33 关系', () => {
  for (const [i, rec] of relations.entries()) {
    test(`S5-${String(i + 1).padStart(2, '0')} ${rec.name}`, async ({ page }) => {
      await openSchemaPage(page, '关系')
      await createSchemaViaUi(page, rec, {
        relation: true,
        sourceSchemaName: rec.sourceSchemaName,
        targetSchemaName: rec.targetSchemaName,
        ddlShot: i === 0 ? path.join(ART_DIR, 'r2-s5-1-ddl-preview-notnull.png') : undefined,
      })
      await sleep(300)
    })
  }

  test('S5-VERIFY 33 关系全部在目录', async () => {
    const req = await apiRequest.newContext()
    const resp = await req.get(
      'http://localhost:8004/api/v1/schema-management/schemas?kind=relation&page=1&pageSize=1&graphSpace=yunfei_test_1',
    )
    const body = await resp.json()
    if ((body?.data?.total ?? 0) !== relations.length) {
      throw new Error(`关系目录数 ${body?.data?.total} ≠ ${relations.length}`)
    }
  })
})
