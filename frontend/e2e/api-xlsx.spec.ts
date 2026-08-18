import { test, expect } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

type ApiCase = {
  sheet: string; row: number; id: string; module: string; name: string
  method: string; path: string; body: unknown; expected: string
  expectedStatus: number | number[] | null; recordedResult: string
}

const cases: ApiCase[] = JSON.parse(fs.readFileSync(path.resolve('../artifacts/playwright-api/cases.json'), 'utf8'))
const baseURL = process.env.API_BASE_URL || 'http://127.0.0.1:8003'
const outputDir = path.resolve('../artifacts/playwright-api')

test.describe.configure({ mode: 'serial' })
test('execute xlsx API cases and create visual evidence', async ({ playwright, browser }) => {
  test.setTimeout(10 * 60_000)
  fs.mkdirSync(outputDir, { recursive: true })
  const api = await playwright.request.newContext({ baseURL, timeout: 30_000 })
  const results = []
  for (const [index, item] of cases.entries()) {
    const started = Date.now()
    try {
      const response = await api.fetch(item.path, {
        method: item.method,
        data: item.body === null ? undefined : item.body,
        headers: item.body === null ? undefined : { 'Content-Type': 'application/json' },
      })
      const text = await response.text()
      let parsed: unknown = text
      try { parsed = JSON.parse(text) } catch { /* retain text */ }
      const accepted = item.expectedStatus === null ? null :
        (Array.isArray(item.expectedStatus) ? item.expectedStatus : [item.expectedStatus]).includes(response.status())
      results.push({ ...item, actualStatus: response.status(), statusMatches: accepted, durationMs: Date.now() - started, response: parsed })
    } catch (error) {
      results.push({ ...item, actualStatus: 0, statusMatches: false, durationMs: Date.now() - started, response: String(error) })
    }
    console.log(`[${index + 1}/${cases.length}] ${item.sheet} ${item.name}`)
  }
  await api.dispose()
  fs.writeFileSync(path.join(outputDir, 'results.json'), JSON.stringify(results, null, 2))

  const page = await browser.newPage({ viewport: { width: 1500, height: 950 }, deviceScaleFactor: 1 })
  await page.setContent(`<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><style>
    body{font-family:Arial,"Microsoft YaHei",sans-serif;background:#f3f6fb;color:#172033;margin:0;padding:28px}h1{margin:0 0 8px}.sub{color:#657089;margin-bottom:20px}.cards{display:flex;gap:14px;margin-bottom:20px}.card{background:white;border-radius:10px;padding:14px 22px;box-shadow:0 2px 10px #1d2b4a16}.num{font-size:26px;font-weight:700}.ok{color:#16865a}.bad{color:#c23b31}table{width:100%;border-collapse:collapse;background:white;font-size:12px}th,td{padding:8px;border-bottom:1px solid #e6eaf0;text-align:left;vertical-align:top}th{background:#eaf0fa;position:sticky;top:0}.pill{padding:2px 7px;border-radius:9px;background:#edf1f7}.fail{background:#ffe7e5;color:#a62d25}.pass{background:#ddf5e9;color:#126b49}</style></head><body>
    <h1>亿级科技知识图谱引擎 · Playwright 接口测试</h1><div class="sub">环境：${baseURL}　生成时间：${new Date().toLocaleString('zh-CN')}</div>
    <div class="cards"><div class="card"><div class="num">${results.length}</div>执行用例</div><div class="card"><div class="num ok">${results.filter(r=>r.statusMatches===true).length}</div>HTTP 状态符合</div><div class="card"><div class="num bad">${results.filter(r=>r.statusMatches===false).length}</div>HTTP 状态不符</div><div class="card"><div class="num">${results.filter(r=>r.statusMatches===null).length}</div>需业务断言</div></div>
    <table><thead><tr><th>#</th><th>分类</th><th>功能项</th><th>用例</th><th>方法 / 路径</th><th>期望 HTTP</th><th>实际</th><th>耗时</th></tr></thead><tbody>${results.map((r,i)=>`<tr><td>${i+1}</td><td>${r.sheet}</td><td>${r.module}</td><td>${r.name}</td><td>${r.method} ${r.path}</td><td>${r.expectedStatus===null?'业务断言':JSON.stringify(r.expectedStatus)}</td><td><span class="pill ${r.statusMatches===false?'fail':r.statusMatches===true?'pass':''}">${r.actualStatus}</span></td><td>${r.durationMs}ms</td></tr>`).join('')}</tbody></table>
  </body></html>`)
  await page.screenshot({ path: path.join(outputDir, 'summary-full.png'), fullPage: true })
  await page.screenshot({ path: path.join(outputDir, 'summary-overview.png') })
  await page.close()
  expect(results.length).toBe(cases.length)
})
