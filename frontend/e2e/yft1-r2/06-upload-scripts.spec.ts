import { request as apiRequest, expect, test } from '@playwright/test'
import catalog from './fixtures/catalog.json' with { type: 'json' }
import { openSchemaPage, searchSchema, shot, sleep, waitFor } from './helpers'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

// 阶段 6：前端上传 45 个抽取脚本（行级「更换脚本」→ 文件选择 → SSE 安全校验含 LLM）。
// 脚本文件来自上一轮目录导出（fixtures/scripts/*.py，内容与旧目录逐字节一致）。
const SCRIPTS_DIR = path.resolve(fileURLToPath(new URL('./fixtures/scripts', import.meta.url)))
const all = [...catalog.entities, ...catalog.relations].filter((s) => s.hasScript)

test.describe.serial('S6 前端上传 45 脚本', () => {
  test('S6a 逐个上传（实体 16 + 关系 29）', async ({ page, request }) => {
    // 45 个脚本 × SSE 校验（含 LLM 安全校验，单个最长 120s；限流退避重试）远超 config 默认 300s
    test.setTimeout(90 * 60_000)
    // 幂等续传：LLM 限流会让本轮中断，重跑前先查已传名单（available 且 sha256 与
    // fixtures 一致才跳过），只补缺——重复上传会再耗一次 LLM 校验的限流窗口。
    const fixtures = await import('node:fs')
    const uploaded = new Set<string>()
    for (const kind of ['entity', 'relation']) {
      const resp = await request.get(
        `http://localhost:8004/api/v1/schema-management/schemas?kind=${kind}&page=1&pageSize=100&includeDetails=true&graphSpace=yunfei_test_1`,
      )
      for (const it of (await resp.json())?.data?.items ?? []) {
        const sha = (it.script || {}).sha256
        if (!sha) continue
        const content = fixtures.readFileSync(
          path.join(SCRIPTS_DIR, `${it.name}.py`),
        )
        const crypto = await import('node:crypto')
        const local = crypto.createHash('sha256').update(content).digest('hex')
        if (sha === local) uploaded.add(it.name)
      }
    }
    const pending = all.filter((rec) => !uploaded.has(rec.name))
    console.log(`已传 ${uploaded.size} 个，本轮补传 ${pending.length} 个`)

    await openSchemaPage(page, '标准实体')
    const failed: string[] = []
    for (const rec of pending) {
      // 关系脚本切到关系页签再搜（两页签表结构不同，行定位一致）
      const isRelation = 'sourceSchemaName' in rec && rec.sourceSchemaName !== undefined
      const tab = await page.locator('.schema-tabs button.active').innerText()
      const wantTab = isRelation ? '关系' : '标准实体'
      if (tab !== wantTab) {
        await page.locator('.schema-tabs button', { hasText: wantTab }).first().click()
        await sleep(600)
      }
      const row = await searchSchema(page, rec.name, rec.label)
      await row.locator('button', { hasText: '更换脚本' }).click()
      const modal = page.locator('.script-upload-modal')
      await modal.waitFor({ timeout: 8_000 })
      await page.setInputFiles('input[aria-label="file-input"]', path.join(SCRIPTS_DIR, rec.scriptFile!))
      // LLM 限流（429 访问量过大/速率限制 → 「LLM 调用失败」/「network error」）时上传被拒且
      // 不落盘——问题记录素材：LLM 服务不可用 = 上传通道不可用，无降级放行。
      // 原地重试：error 态点「重新选择」回 idle 再选同一文件；限流是窗口性的，退避能过。
      let msg = ''
      // LLM 安全校验判定不可复现（问题记录⑯）：与上轮逐字节一致的脚本上轮 45/45 全过，
      // 本轮大面积被拒且理由漂移（同脚本两轮理由都不同），另有「LLM 返回格式异常」
      // （输出解析失败）也判拒。重试=对非确定性判定重新抽样；限流类退避更长。
      for (let attempt = 0; ; attempt++) {
        const result = await waitFor(
          async () => {
            if (await modal.locator('.upload-result__icon.ok').isVisible().catch(() => false)) return 'ok'
            if (await modal.locator('.upload-result__icon.err').isVisible().catch(() => false)) return 'err'
            return false
          },
          { timeout: 120_000, interval: 1_500, label: `${rec.name} 脚本校验结果` },
        )
        if (result === 'ok') break
        msg = await modal.locator('.upload-result__msg').innerText().catch(() => '')
        const throttled = /LLM 调用失败|network error|访问量过大|速率限制/i.test(msg)
        if (attempt < (throttled ? 3 : 5)) {
          await modal.getByRole('button', { name: '重新选择' }).click()
          await sleep(throttled ? 30_000 : 8_000)
          await page.setInputFiles('input[aria-label="file-input"]', path.join(SCRIPTS_DIR, rec.scriptFile!))
          continue
        }
        await shot(page, `r2-s6-fail-${rec.name}`)
        failed.push(`${rec.name}: ${msg.slice(0, 120)}`)
        break
      }
      // footer 按钮随状态改名：success=关闭 / error=取消
      await modal.getByRole('button', { name: /关闭|取消/ }).click()
      await waitFor(async () => (await modal.count()) === 0, { timeout: 8_000, label: '上传弹窗关闭' })
      await sleep(6_000) // 脚本间隔降速：连发 45 个 LLM 校验会触发账户级速率限制（1302）
    }
    expect(failed, `LLM 安全校验未通过的脚本: ${failed.join(' || ')}`).toEqual([])
  })

  test('S6b API 核验 45 个脚本 available', async () => {
    const req = await apiRequest.newContext()
    const missing: string[] = []
    for (const kind of ['entity', 'relation']) {
      const resp = await req.get(
        `http://localhost:8004/api/v1/schema-management/schemas?kind=${kind}&page=1&pageSize=100&includeDetails=true&graphSpace=yunfei_test_1`,
      )
      const items = (await resp.json())?.data?.items ?? []
      for (const it of items) {
        if (!it.script?.available || !it.script?.sha256) missing.push(it.name)
      }
    }
    expect(missing, `脚本缺失的 schema: ${missing.join(',')}`).toEqual([])
  })
})
