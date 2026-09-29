import { expect, test } from '@playwright/test'
import { readFile, writeFile } from 'node:fs/promises'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { api, apiMust, mysql, purgeExtractFailCases, waitFor } from './helpers'

const execFileAsync = promisify(execFile)
const ENV_PATH = '/home/zhangzhong_e43d4db3/src/tech-kg-api-dev2/backend/.env'
const MARKER = 'ENTITY_SEARCH_EMBEDDING_BASE_URL=http://127.0.0.1:1/v1'

async function upStack(): Promise<void> {
  await execFileAsync(
    'docker',
    ['compose', '-f', 'docker-compose.dev2.yml', 'up', '-d', 'api-dev2', 'temporal-worker-dev2'],
    { cwd: '/home/zhangzhong_e43d4db3/src/tech-kg-api-dev2', timeout: 180_000 },
  )
  const deadline = Date.now() + 90_000
  while (Date.now() < deadline) {
    try {
      const resp = await fetch('http://localhost:8002/api/v1/kg-construction/options', { signal: AbortSignal.timeout(3000) })
      if (resp.ok) return
    } catch {
      // 还在启动
    }
    await new Promise((r) => setTimeout(r, 2000))
  }
  throw new Error('api 容器重启后未就绪')
}

// F6. embedding 服务故障必须显式提醒用户（2026-09-29 口径：索引构建失败整链
// FAILED，失败原因经 cause 链展开进执行 message，详情页失败说明条显眼展示，
// 不再是「执行成功 + 结果 JSON 里埋 degraded 标记」的静默降级）
test.describe.serial('F6 embedding 故障显式提醒', () => {
  let widgetSchemaId = ''
  let envOriginal = ''

  test.beforeAll(async ({ request }) => {
    envOriginal = await readFile(ENV_PATH, 'utf-8')
    const schemas = await apiMust<any>(request, 'GET', '/schema-management/schemas?graphSpace=dev2&pageSize=100', undefined, '列 schema')
    const widget = (schemas.items ?? []).find((s: any) => s.name === 'E2EWidget')
    test.skip(!widget, '无 E2EWidget schema')
    widgetSchemaId = widget.id
    await purgeExtractFailCases()
  })

  test.afterAll(async () => {
    // 恢复 env 并重建（即使中途失败也要恢复）
    await writeFile(ENV_PATH, envOriginal, 'utf-8')
    await upStack()
  })

  test('注入坏 embedding 地址 → 索引构建失败，执行标 FAILED 并显眼提示', async ({ page, request }) => {
    test.setTimeout(900_000)
    // 1. 注入故障：ENTITY_SEARCH_EMBEDDING_BASE_URL 指向不可用地址 + 重建容器
    await writeFile(ENV_PATH, `${envOriginal.trimEnd()}\n${MARKER}\n`, 'utf-8')
    await upStack()

    // 2. 跑一次实体抽取（默认 buildIndex=true → 索引构建失败整链 FAILED）
    await mysql(
      "UPDATE techkg_e2e.widgets SET name='挂件一号', update_time=NOW() WHERE id='w1'; " +
        "UPDATE techkg_e2e.widgets SET name='挂件二号', update_time=NOW() WHERE id='w2';",
    )
    const trig = await apiMust<any>(
      request,
      'POST',
      `/schema-management/schemas/${widgetSchemaId}/extract`,
      { graphSpace: 'dev2', batchSize: 2 },
      '坏 embedding 下抽取',
    )
    const exec = await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/executions/${trig.executionId}`)
        return ['COMPLETED', 'FAILED'].includes(detail.data?.status) ? detail.data : null
      },
      { timeout: 600_000, interval: 5_000, label: '抽取终态' },
    )
    // 索引构建失败即任务 FAILED（图数据在索引前已写图，但任务不再算成功）
    expect(exec.status).toBe('FAILED')

    // 3. 执行详情页 UI：失败说明条显眼展示真实原因（cause 链展开进 message，
    //    不翻 JSON 即可见），不再是静默降级
    const execDetail = await apiMust<any>(request, 'GET', `/workflow-system/executions/${trig.executionId}`, undefined, '执行详情')
    expect(String(execDetail.message || '')).toMatch(/失败|error|连接|embedding/i)
    await page.goto(`/processing-instance/${trig.executionId}`)
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.exec-failure-alert')).toBeVisible({ timeout: 30_000 })
    await expect(page.getByText('本次执行标记为失败').first()).toBeVisible()
  })

  test('恢复正确配置 → 重跑成功、无失败提示', async ({ page, request }) => {
    test.setTimeout(900_000)
    // 1. 恢复 env（afterAll 也会兜底）+ 重建
    await writeFile(ENV_PATH, envOriginal, 'utf-8')
    await upStack()

    await mysql(
      "UPDATE techkg_e2e.widgets SET name='挂件一号', update_time=NOW() WHERE id='w1'; " +
        "UPDATE techkg_e2e.widgets SET name='挂件二号', update_time=NOW() WHERE id='w2';",
    )
    const trig = await apiMust<any>(
      request,
      'POST',
      `/schema-management/schemas/${widgetSchemaId}/extract`,
      { graphSpace: 'dev2', batchSize: 2 },
      '正确 embedding 下抽取',
    )
    const exec = await waitFor(
      async () => {
        const detail = await api<any>(request, 'GET', `/workflow-system/executions/${trig.executionId}`)
        return ['COMPLETED', 'FAILED'].includes(detail.data?.status) ? detail.data : null
      },
      { timeout: 600_000, interval: 5_000, label: '抽取终态' },
    )
    expect(exec.status).toBe('COMPLETED')
    const execDetail = await apiMust<any>(request, 'GET', `/workflow-system/executions/${trig.executionId}`, undefined, '执行详情')

    // 索引正常重建（无失败提示）
    await page.goto(`/processing-instance/${trig.executionId}`)
    await page.waitForLoadState('networkidle')
    await expect(page.locator('.exec-failure-alert')).toHaveCount(0)
    const index = execDetail.output?.index
    expect(index?.entityCount).toBeGreaterThanOrEqual(2)
  })
})
