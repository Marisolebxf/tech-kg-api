import type { APIRequestContext, Page } from '@playwright/test'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'

const execFileAsync = promisify(execFile)

export const WEB_BASE = 'http://localhost:8091'
export const API_BASE = 'http://localhost:8002/api/v1'

/** 造数统一前缀 + 短随机后缀，保证幂等重跑不撞名。 */
export function runId(): string {
  return Date.now().toString(36).slice(-5) + Math.random().toString(36).slice(2, 5)
}

export interface ApiResult<T = unknown> {
  status: number
  ok: boolean
  data: T
}

/** 直调 dev2 api（AUTH_ENABLED=false 免登录）。信封 {code,success,data} 自动解包。 */
export async function api<T = any>(
  request: APIRequestContext,
  method: string,
  path: string,
  body?: unknown,
): Promise<ApiResult<T>> {
  const resp = await request.fetch(API_BASE + path, {
    method,
    data: body === undefined ? undefined : JSON.stringify(body),
    headers: { 'Content-Type': 'application/json' },
    maxRedirects: 0,
  })
  let payload: any = null
  try {
    payload = await resp.json()
  } catch {
    payload = null
  }
  const status = resp.status()
  const inner = payload && typeof payload === 'object' && 'code' in payload ? payload : null
  return {
    status,
    ok: status < 400 && (!inner || inner.code === 200),
    data: (inner ? inner.data : payload?.detail !== undefined ? payload : payload) as T,
  }
}

/** 期望业务成功的 API 调用，失败抛错并带上下文。 */
export async function apiMust<T = any>(
  request: APIRequestContext,
  method: string,
  path: string,
  body?: unknown,
  label = '',
): Promise<T> {
  const r = await api<T>(request, method, path, body)
  if (!r.ok) {
    throw new Error(`API ${method} ${path} ${label} 失败: HTTP ${r.status} ${JSON.stringify(r.data).slice(0, 400)}`)
  }
  return r.data
}

const TERMINAL = new Set(['COMPLETED', 'FAILED', 'TERMINATED', 'CANCELED', 'TIMED_OUT'])

export interface Execution {
  id: string
  status: string
  output?: any
  message?: string
  triggerSource?: string
}

/** 轮询执行直到终态（抽取含索引重建可达分钟级）。 */
export async function waitExecution(
  request: APIRequestContext,
  executionId: string,
  { timeout = 300_000, interval = 4_000 }: { timeout?: number; interval?: number } = {},
): Promise<Execution> {
  const deadline = Date.now() + timeout
  let last: Execution | null = null
  while (Date.now() < deadline) {
    const data = await apiMust<any>(request, 'GET', `/workflow-system/executions/${executionId}`, undefined, '查询执行')
    last = data
    if (TERMINAL.has(data?.status)) return data
    await sleep(interval)
  }
  throw new Error(`执行 ${executionId} 超时未终态: ${JSON.stringify(last)?.slice(0, 300)}`)
}

/** 通过 graph-console 只读 nGQL（DESCRIBE/MATCH 等），返回原始 records。 */
export async function ngql(request: APIRequestContext, space: string, statement: string): Promise<any[]> {
  const data = await apiMust<any>(
    request,
    'POST',
    '/graph-console/query',
    { space, statement },
    `nGQL[${statement.slice(0, 60)}]`,
  )
  return (data?.records ?? []) as any[]
}

/** MATCH count 断言用：`MATCH (v:Tag) RETURN count(v) AS c`。 */
export async function graphCount(request: APIRequestContext, space: string, pattern: string): Promise<number> {
  const records = await ngql(request, space, `MATCH ${pattern} RETURN count(v) AS c`)
  return Number(records?.[0]?.c ?? -1)
}

/** 直连 trs-graph 执行语句（绕过 graph-console 的 DDL 禁令，仅测试环境造数/清理用）。 */
export async function graphWrite(statement: string, space = 'dev2'): Promise<any> {
  const resp = await fetch(`http://localhost:8091/api/v1/query/write`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-API-Key': 'ysukeg', 'X-Graph-Space': space },
    body: JSON.stringify({ query: statement }),
  })
  return resp.json()
}

/** 清理图库残留 TAG/EDGE（删点 → DROP），供测试前重置。 */
export async function dropGraphTag(tag: string, space = 'dev2'): Promise<void> {
  const res: any = await graphWrite(`MATCH (v:${tag}) RETURN id(v) AS vid`, space)
  for (const r of res.records ?? []) {
    await graphWrite(`DELETE VERTEX "${r.vid}" WITH EDGE`, space)
  }
  await graphWrite(`DROP TAG IF EXISTS ${tag}`, space)
}

export async function dropGraphEdge(edge: string, space = 'dev2'): Promise<void> {
  const res: any = await graphWrite(`MATCH ()-[e:${edge}]->() RETURN id(e) AS eid`, space)
  for (const r of res.records ?? []) {
    await graphWrite(`DELETE EDGE ${edge} ${String(r.eid).replace(/"/g, '')}`, space)
  }
  await graphWrite(`DROP EDGE IF EXISTS ${edge}`, space)
}

/** DESCRIBE TAG/EDGE 字段列表（图库复核）。 */
export async function describeColumns(
  request: APIRequestContext,
  space: string,
  kind: 'TAG' | 'EDGE',
  name: string,
): Promise<string[]> {
  const records = await ngql(request, space, `DESCRIBE ${kind} ${name}`)
  return records.map((r: any) => String(r.Field))
}

/** 在 temporal-mysql-dev2 容器内执行 SQL（造数/复核）。 */
export async function mysql(sql: string): Promise<string> {
  const { stdout } = await execFileAsync(
    'docker',
    [
      'exec',
      'tech-kg-temporal-mysql-dev2',
      'mysql',
      '--default-character-set=utf8mb4',
      '-uroot',
      '-ptemporal',
      '-N',
      '-e',
      sql,
    ],
    { timeout: 30_000, maxBuffer: 32 * 1024 * 1024 },
  )
  return stdout
}

export function sleep(ms: number): Promise<void> {
  return new Promise((r) => setTimeout(r, ms))
}

/** 通用轮询等待（条件函数返回真值即停）。 */
export async function waitFor<T>(
  fn: () => Promise<T> | T,
  { timeout = 30_000, interval = 1_500, label = '条件' }: { timeout?: number; interval?: number; label?: string } = {},
): Promise<T> {
  const deadline = Date.now() + timeout
  let lastErr: unknown = null
  while (Date.now() < deadline) {
    try {
      const v = await fn()
      if (v) return v
    } catch (e) {
      lastErr = e
    }
    await sleep(interval)
  }
  throw new Error(`等待${label}超时${lastErr ? `，最后错误: ${String(lastErr).slice(0, 300)}` : ''}`)
}

/** 打开 a-select 后在虚拟列表里滚动查找并选中选项（长列表只渲染可见切片）。 */
export async function selectArcoScrolled(page: Page, trigger: import('@playwright/test').Locator, text: string): Promise<void> {
  await trigger.click()
  const container = page
    .locator('.arco-select-dropdown:visible .arco-scrollbar-container')
    .first()
  for (let i = 0; i < 40; i++) {
    const opt = page.locator('li.arco-select-option:visible', { hasText: text }).first()
    if (await opt.isVisible().catch(() => false)) {
      // 弹层可能被业务 modal 内元素遮挡指针（z-index 低于 modal）：坐标点击
      // 会落在遮挡层上，直接在选项节点上派发 click 事件
      await opt.evaluate((el) =>
        el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })),
      )
      await sleep(300)
      // 派发事件可能不触发弹层收起：残留 dropdown 会挡住 modal 底部按钮
      if (await page.locator('.arco-select-dropdown:visible').first().isVisible().catch(() => false)) {
        await page.keyboard.press('Escape')
        await sleep(200)
      }
      return
    }
    await container
      .evaluate((el) => {
        el.scrollTop += 240
      })
      .catch(() => {})
    await sleep(150)
  }
  throw new Error(`下拉选项「${text}」滚动查找未命中`)
}

/** path 路由跳转并等页面骨架渲染（createWebHistory，非 hash 模式）。 */
export async function gotoRoute(page: Page, route: string): Promise<void> {
  await page.goto(route.startsWith('/') ? route : `/${route}`)
  await page.waitForLoadState('networkidle')
}

/** 自动接受原生 confirm（配置删除/任务删除/解绑等）。 */
export function autoAcceptConfirms(page: Page): void {
  page.on('dialog', (d) => void d.accept())
}

/** 等待页面出现包含指定文案的可见元素（toast/提示通用断言）。 */
export async function expectText(page: Page, text: string, timeout = 20_000): Promise<void> {
  await waitFor(
    async () => (await page.getByText(text, { exact: false }).first().isVisible().catch(() => false)),
    { timeout, label: `页面文案「${text}」` },
  )
}

/** 现网找一个可抽取 schema（有脚本 + 有来源绑定），供 E/F 组复用。 */
export async function findExtractableSchema(request: APIRequestContext, space = 'dev2') {
  const data = await apiMust<any>(
    request,
    'GET',
    `/schema-management/schemas?page=1&pageSize=100&includeDetails=true&graphSpace=${space}`,
    undefined,
    '列 schema',
  )
  const items: any[] = data.items ?? []
  return items.find((s) => s.script && (s.sources?.length ?? 0) > 0) ?? null
}

export const WIDGET_SCRIPT = `"""E2E 毒行转换脚本：POISON 行报 failures，其余出实体。"""
from typing import Any, Mapping


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    rows = payload.get("rows") or []
    entities, failures = [], []
    for row in rows:
        name = str(row.get("name") or "")
        if "POISON" in name:
            failures.append({"recordId": str(row["id"]), "error": "ValueError: POISON 行拒绝解析"})
        else:
            entities.append({"id": "widget_" + str(row["id"]), "props": {"id": str(row["id"]), "name": name}})
    return {"entities": entities, "failures": failures}
`

/** 清空积压的抽取失败 OPEN case（测试环境清理：旧 case 绑定已删 schema，重跑必 409）。 */
export async function purgeExtractFailCases(): Promise<void> {
  await execFileAsync(
    'docker',
    [
      'exec', 'tech-kg-api-dev2', '.venv/bin/python', '-c',
      'from infra.mysql import get_session_factory; from sqlalchemy import text; '
      + 's = get_session_factory()(); '
      + "s.execute(text(\"UPDATE manual_review_case SET status='CANCELLED' WHERE template_id='T_EXTRACT_FAIL' AND status='OPEN'\")); "
      + 's.commit(); s.close()',
    ],
    { timeout: 30_000 },
  )
}

/** 重置 widgets 测试数据（w1/w2 正常，w3/w4 毒行；推水位保证下次抽取读到；幂等）。 */
export async function resetWidgetRows(): Promise<void> {
  await mysql(
    `UPDATE techkg_e2e.widgets SET name='挂件一号', update_time=NOW() WHERE id='w1'; ` +
      `UPDATE techkg_e2e.widgets SET name='挂件二号', update_time=NOW() WHERE id='w2'; ` +
      `UPDATE techkg_e2e.widgets SET name='POISON坏行', update_time=NOW() WHERE id='w3'; ` +
      `UPDATE techkg_e2e.widgets SET name='POISON又坏', update_time=NOW() WHERE id='w4';`,
  )
}
