import type { APIRequestContext, Locator, Page } from '@playwright/test'
import { expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// yunfei3 栈（区别于 e2e/platform 的 dev2 栈 8091/8002）
export const WEB_BASE = 'http://localhost:8093'
export const API_BASE = 'http://localhost:8004/api/v1'
export const SPACE = 'yunfei_test_1'
export const ART_DIR = path.resolve(fileURLToPath(new URL('../../../artifacts/yft1-frontend-e2e-r2', import.meta.url)))
mkdirSync(ART_DIR, { recursive: true })

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

/** 截图存证到 artifacts/yft1-frontend-e2e-r2/。 */
export async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(ART_DIR, `${name}.png`), fullPage: false })
}

/** 直调 yunfei3 api（AUTH_ENABLED=false 免登录）。仅用于只读核验与兜底重试——
 *  所有「操作」按本轮 e2e 口径必须走前端 UI（CLI 兜底单独记录）。 */
export async function api<T = any>(
  request: APIRequestContext,
  method: string,
  path: string,
  body?: unknown,
): Promise<{ status: number; ok: boolean; data: T }> {
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
    data: (inner ? inner.data : payload) as T,
  }
}

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

/** 只读 nGQL 核验（走后端 graph-console，与前端控制台同一条链路）。 */
export async function ngql(request: APIRequestContext, space: string, statement: string): Promise<any[]> {
  const data = await apiMust<any>(request, 'POST', '/graph-console/query', { space, statement }, `nGQL[${statement.slice(0, 50)}]`)
  return (data?.records ?? []) as any[]
}

/** 在平台总览页用 nGQL 控制台（UI）执行语句并等结果表刷新。
 *  以查询响应为完成信号（合法空结果如空空间 SHOW TAGS 返回 0 行，不能用「行数>0」判完成）。 */
export async function runConsoleUi(page: Page, statement: string): Promise<string[][]> {
  const ta = page.locator('textarea[aria-label="nGQL 查询语句"]')
  await ta.scrollIntoViewIfNeeded()
  await ta.fill(statement)
  const respPromise = page.waitForResponse(
    (r) => r.url().includes('/api/v1/graph-console/query') && r.request().method() === 'POST',
    { timeout: 30_000 },
  )
  await page.getByRole('button', { name: '执行 nGQL' }).click()
  const resp = await respPromise
  if (resp.status() >= 400) {
    throw new Error(`控制台查询 HTTP ${resp.status()}: ${statement.slice(0, 60)}`)
  }
  await sleep(800) // 等结果表渲染
  const resultTable = page.locator('[aria-label="nGQL 查询结果"]')
  // 结果表是 arco ATable（div 结构），行/单元格选择器用 arco 类名而非原生 tbody/tr/td
  const rows = resultTable.locator('.arco-table-tr')
  const n = await rows.count().catch(() => 0)
  const out: string[][] = []
  for (let i = 0; i < n; i++) {
    const cells = await rows.nth(i).locator('.arco-table-td').allInnerTexts()
    out.push(cells)
  }
  return out
}

/** path 路由跳转并等页面骨架渲染。 */
export async function gotoRoute(page: Page, route: string): Promise<void> {
  await page.goto(route.startsWith('/') ? route : `/${route}`)
  await page.waitForLoadState('networkidle')
}

/** 切换全局图空间（.app-space-select，仅平台总览页面包屑行渲染）。 */
export async function switchGraphSpace(page: Page, space: string): Promise<void> {
  const from = new URL(page.url())
  await gotoRoute(page, '/overview')
  await page.locator('.app-breadcrumb .app-space-select').waitFor()
  await selectArcoScrolled(page, page.locator('.app-breadcrumb .app-space-select .arco-select-view-single'), space)
  await expect(page.locator('.app-breadcrumb .app-space-select .arco-select-view-value')).toHaveText(space)
  if (from.pathname !== '/overview') {
    await gotoRoute(page, from.pathname + from.search + from.hash)
  }
}

/** 打开 a-select 后在虚拟列表里滚动查找并选中选项（长列表只渲染可见切片）。 */
export async function selectArcoScrolled(page: Page, trigger: Locator, text: string): Promise<void> {
  await trigger.click()
  const container = page.locator('.arco-select-dropdown:visible .arco-scrollbar-container').first()
  for (let i = 0; i < 60; i++) {
    const opt = page.locator('li.arco-select-option:visible', { hasText: text }).first()
    if (await opt.isVisible().catch(() => false)) {
      await opt.evaluate((el) => el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true })))
      await sleep(300)
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

/** 打开 a-select（allow-search）→ 输入过滤词 → 点选可见选项。
 *  选项按 innerText 精确全等匹配（contains 会误命中：列下拉搜「id」会先中「logic_id」）。 */
export async function selectArcoSearch(page: Page, trigger: Locator, text: string): Promise<void> {
  await trigger.scrollIntoViewIfNeeded()
  await trigger.click()
  const dropdown = page.locator('.arco-select-dropdown:visible').first()
  await dropdown.waitFor({ state: 'visible', timeout: 8_000 })
  const search = trigger.locator('input').first()
  if (await search.isVisible().catch(() => false)) {
    await search.fill(text)
    await sleep(350)
  }
  const opts = dropdown.locator('li.arco-select-option')
  const n = await opts.count()
  let target: Locator | null = null
  for (let i = 0; i < n; i++) {
    const label = (await opts.nth(i).innerText().catch(() => '')).trim()
    if (label === text) {
      target = opts.nth(i)
      break
    }
  }
  if (!target) {
    // 兜底：带副文本的选项（如「数据源名（host）」）用 contains
    target = dropdown.locator('li.arco-select-option').filter({ hasText: text }).first()
  }
  await target.waitFor({ state: 'visible', timeout: 8_000 })
  await target.click()
  await sleep(250)
  if (await dropdown.isVisible().catch(() => false)) {
    await page.keyboard.press('Escape')
    await sleep(150)
  }
}

/** 打开 a-select（无搜索框，短列表）→ 直接点选项。 */
export async function selectArcoClick(page: Page, trigger: Locator, text: string): Promise<void> {
  await trigger.scrollIntoViewIfNeeded()
  await trigger.click()
  const dropdown = page.locator('.arco-select-dropdown:visible').first()
  await dropdown.waitFor({ state: 'visible', timeout: 8_000 })
  const opt = dropdown.locator('li.arco-select-option').filter({ hasText: text }).first()
  await opt.waitFor({ state: 'visible', timeout: 8_000 })
  await opt.click()
  await sleep(250)
}

/** 等 toast 出现（成功/失败通用；只等文本可见）。 */
export async function expectText(page: Page, text: string, timeout = 20_000): Promise<void> {
  await waitFor(
    async () => (await page.getByText(text, { exact: false }).first().isVisible().catch(() => false)),
    { timeout, label: `页面文案「${text}」` },
  )
}

// ---- Schema 管理页专用 ----

/** 打开 Schema 管理页并切到目标图空间（列表跟随全局空间选择器）。 */
export async function openSchemaPage(page: Page, tab: '标准实体' | '关系' = '标准实体'): Promise<void> {
  await page.goto('/overview')
  await page.waitForLoadState('networkidle')
  await switchGraphSpace(page, SPACE)
  await gotoRoute(page, '/schema')
  await page.locator('.schema-catalog').waitFor()
  const active = await page.locator('.schema-tabs button.active').innerText()
  if (active !== tab) {
    await page.locator('.schema-tabs button', { hasText: tab }).first().click()
    await sleep(600)
  }
}

// 搜索框是 a-input：aria-label 落在包裹层 span.arco-input-wrapper 上，内层 <input> 只有
// placeholder（本轮踩坑：input[aria-label^=搜索] 永不命中）。
const SEARCH_INPUT = '.schema-search-input input'

/** 提交关键字搜索并以列表接口响应为完成信号（服务端 keyword 过滤；合法空结果返回 0 行）。 */
async function submitSearch(page: Page, name: string): Promise<void> {
  const respPromise = page.waitForResponse(
    (r) => r.url().includes('/api/v1/schema-management/schemas') && r.url().includes('keyword='),
    { timeout: 15_000 },
  )
  await page.locator(SEARCH_INPUT).fill(name)
  await page.locator('.schema-toolbar__actions button[type="submit"]').click()
  const resp = await respPromise
  if (resp.status() >= 400) throw new Error(`Schema 列表搜索 HTTP ${resp.status()}`)
  await sleep(600) // 等表格渲染
}

/** 按第 2 列 code 单元格文本比对（>10 字符展示为 `前 10 字…`）。
 *  不用行级 hasText：会误匹配起点/终点列或同前缀兄弟行（Organization vs OrganizationBase）。
 *  同 10 字前缀兄弟（两行 cell 都是「Organizatio…」）用行内 ··· 按钮的 aria-label
 *  （`${中文名}更多操作`，中文名唯一）消歧——需调用方传 label。 */
async function rowsForName(page: Page, name: string, label?: string): Promise<Locator[]> {
  const want = name.length > 10 ? `${name.slice(0, 10)}…` : name
  const rows = page.locator('table tbody tr')
  const n = await rows.count().catch(() => 0)
  let out: Locator[] = []
  for (let i = 0; i < n; i++) {
    const cell = await rows.nth(i).locator('td:nth-child(2) code').innerText().catch(() => '')
    if (cell.trim() === want) out.push(rows.nth(i))
  }
  if (out.length > 1 && label) {
    const marked = await Promise.all(
      out.map(async (r) => ({
        r,
        ok:
          (await r
            .locator(`button.schema-action-more[aria-label="${label}更多操作"]`)
            .count()) > 0,
      })),
    )
    out = marked.filter((m) => m.ok).map((m) => m.r)
  }
  return out
}

/** 幂等搜索：命中返回行；列表无该行返回 null（已删/不存在，可跳过）；多行命中报错。 */
export async function findSchemaRow(page: Page, name: string, label?: string): Promise<Locator | null> {
  await submitSearch(page, name)
  const rows = await rowsForName(page, name, label)
  if (rows.length > 1) throw new Error(`搜索「${name}」命中 ${rows.length} 行，拒绝继续`)
  return rows[0] ?? null
}

/** 在 Schema 列表按英文名搜索（服务端过滤，把目标行隔离到首屏）；未命中即失败。 */
export async function searchSchema(page: Page, name: string, label?: string): Promise<Locator> {
  const row = await findSchemaRow(page, name, label)
  if (!row) throw new Error(`搜索「${name}」未命中`)
  return row
}

/** 打开行内「···」下拉里的操作项（来源表/属性管理/删除）。 */
export async function openRowMenuAction(page: Page, row: Locator, action: string): Promise<void> {
  await row.locator('button.schema-action-more').click()
  const item = page.locator('.arco-dropdown-option, .arco-dropdown .arco-dropdown-option', { hasText: action }).first()
  await item.waitFor({ state: 'visible', timeout: 8_000 })
  await item.click()
  await sleep(400)
}
