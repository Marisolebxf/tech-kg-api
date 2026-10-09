import type { APIRequestContext, Page } from '@playwright/test'
import { expect } from '@playwright/test'
import { mkdirSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// yunfei3 栈（区别于 e2e/platform 的 dev2 栈 8091/8002）
export const WEB_BASE = 'http://localhost:8093'
export const API_BASE = 'http://localhost:8004/api/v1'
export const SPACE = 'yunfei_test_1'
export const ART_DIR = path.resolve(fileURLToPath(new URL('../../../artifacts/yft1-frontend-e2e', import.meta.url)))
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

/** 截图存证到仓库 artifacts/yft1-frontend-e2e/。 */
export async function shot(page: Page, name: string): Promise<void> {
  await page.screenshot({ path: path.join(ART_DIR, `${name}.png`), fullPage: false })
}

/** 直调 yunfei3 api（AUTH_ENABLED=false 免登录）。仅用于只读核验——
 *  所有「操作」按本次 e2e 口径必须走前端 UI。 */
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

/** 在平台总览页用 nGQL 控制台（UI）执行语句并等结果表刷新。 */
export async function runConsoleUi(page: Page, statement: string): Promise<string[][]> {
  const ta = page.locator('textarea[aria-label="nGQL 查询语句"]')
  await ta.scrollIntoViewIfNeeded()
  await ta.fill(statement)
  const resultTable = page.locator('[aria-label="nGQL 查询结果"]')
  // 结果表是 arco ATable（div 结构），行/单元格选择器用 arco 类名而非原生 tbody/tr/td
  const rowSel = '.arco-table-tr'
  const beforeRows = await resultTable.locator(rowSel).count().catch(() => 0)
  await page.getByRole('button', { name: '执行 nGQL' }).click()
  await waitFor(
    async () => {
      await page.waitForTimeout(200)
      const rows = await resultTable.locator(rowSel).count().catch(() => 0)
      return rows > 0 || beforeRows > 0
    },
    { timeout: 30_000, interval: 1_000, label: `控制台结果[${statement.slice(0, 40)}]` },
  )
  const rows = resultTable.locator(rowSel)
  const n = await rows.count()
  const out: string[][] = []
  for (let i = 0; i < n; i++) {
    const cells = await rows.nth(i).locator('.arco-table-td').allInnerTexts()
    out.push(cells)
  }
  return out
}

/** 打开 a-select 后在虚拟列表里滚动查找并选中选项（长列表只渲染可见切片）。 */
export async function selectArcoScrolled(page: Page, trigger: import('@playwright/test').Locator, text: string): Promise<void> {
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

/** 自动接受原生 confirm（任务删除等）。 */
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
