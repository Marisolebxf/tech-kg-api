import type { Page } from '@playwright/test'
import { expect, test } from '@playwright/test'
import { SPACE, gotoRoute, shot, sleep, switchGraphSpace, waitFor } from './helpers'

// 阶段 6a：前端任务中心——删除旧三链（ABNORMAL 无重触发入口，是本流程发现的问题②）
// 并经「新建任务」弹窗按手册 §5 顺序重建三条链（一次性、不立即执行——三链须串行等终态）。
const CHAINS = [
  {
    name: `还原-实体@${SPACE}`,
    schemas: ['DataSource', 'Event', 'IndustryChain', 'IndustryNode', 'Journal', 'Keyword', 'News', 'Organization', 'Paper', 'Patent', 'PatentFamily', 'Person', 'Product', 'Project', 'Report', 'OrganizationBase'],
  },
  {
    name: `还原-关系A@${SPACE}`,
    schemas: ['ACQUIRES', 'ACTUAL_CONTROLLER_OF', 'AFFILIATED_WITH', 'AUTHORED_BY', 'BELONGS_TO_NODE', 'BENEFICIAL_OWNER_OF', 'CHILD_OF', 'CITES', 'COAUTHOR_WITH', 'COVERS_CHAIN', 'DOWNSTREAM_OF', 'EXECUTIVE_OF', 'FUNDED_BY', 'HAS_KEYWORD', 'HAS_NEWS'],
  },
  {
    name: `还原-关系B@${SPACE}`,
    schemas: ['HAS_NODE', 'HAS_OUTPUT', 'HAS_PARTICIPANT', 'INVESTS_IN', 'INVOLVED_IN', 'LEADS', 'LEGAL_REP_OF', 'MEMBER_OF_FAMILY', 'PRODUCES', 'PUBLISHED_IN', 'REFERENCED_BY', 'SHAREHOLDER_OF', 'SUBSIDIARY_OF', 'STUDIED_AT'],
  },
]

/** 链队列 a-select（allow-search）：输入英文名过滤后点选，并断言队列长度+精确名。
 *  选项 label 为「中文名（实体|关系 · EnglishName）」——必须按 `· EnglishName）` 后缀精确匹配，
 *  否则搜索 Organization 会误点 OrganizationBase、Patent 误点 PatentFamily。 */
async function addChainStep(page: Page, name: string): Promise<void> {
  const field = page.locator('.job-launch-dialog div.job-field', { hasText: '串联 Schema 队列' }).first()
  await field.locator('.arco-select-view-single').click()
  // allow-search 输入框在触发器内（arco 单选搜索模式），打开下拉后可见
  const search = field.locator('.arco-select-view-single input').first()
  await search.waitFor({ state: 'visible', timeout: 8_000 })
  await search.fill(name)
  await sleep(400)
  const opt = page.locator('li.arco-select-option:visible').filter({ hasText: `· ${name}）` }).first()
  await opt.waitFor({ state: 'visible', timeout: 8_000 })
  await opt.click()
  // 队列尾行 code 以 `· EnglishName）` 结尾（防前缀误配），长度断言在调用处
  await expect(
    page.locator('ol.chain-steps li code').last(),
  ).toHaveText(new RegExp(`${name}）$`))
}

test.describe.serial('S6a 任务中心：删旧链建新链', () => {
  test('删除旧三链 + 新建三条链（不立即执行）', async ({ page }) => {
    await page.goto('/overview')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, SPACE)
    await gotoRoute(page, '/graph-build')
    await page.locator('table tbody tr').first().waitFor()

    // ① 删旧三链（行内 删除 按钮 + 应用内确认弹窗；幂等——已被上轮跑删掉则跳过）
    for (const c of CHAINS) {
      const row = page.locator('table tbody tr', { hasText: c.name }).first()
      if (await row.isVisible().catch(() => false)) {
        await row.locator('button', { hasText: '删除' }).click()
        await page.locator('.kg-delete-dialog').waitFor()
        await page.locator('.kg-delete-dialog button', { hasText: '确认删除' }).click()
        await waitFor(
          async () => !(await row.isVisible().catch(() => false)),
          { timeout: 20_000, interval: 1_000, label: `旧任务行消失 ${c.name}` },
        )
      }
    }
    await shot(page, 's6-1-old-jobs-deleted')

    // ② 依次建三条链
    for (const c of CHAINS) {
      await page.getByRole('button', { name: '＋ 新建任务' }).click()
      await page.locator('.job-launch-dialog').waitFor()
      await page.locator('input[aria-label="如：论文-专家抽取"]').fill(c.name)

      // 任务类型 → 多脚本串行
      await page.locator('div.job-field', { hasText: '任务类型' }).locator('.arco-select-view-single').click()
      await page.locator('li.arco-select-option:visible', { hasText: '多脚本串行' }).click()
      await sleep(300)

      // 按序添加 schema 队列（每步后队列长度必须 +1——防误点重复项）
      for (let i = 0; i < c.schemas.length; i++) {
        await addChainStep(page, c.schemas[i])
        await expect(page.locator('ol.chain-steps li')).toHaveCount(i + 1)
      }

      // 批大小 500（chain 分支的 input）
      await page.locator('input[aria-label="500"]').fill('500')

      // 数据源/库跟随 schema 绑定自动带出（gkx-element-yunfei1 / gkx_element_yft1）
      const dsText = await page
        .locator('div.job-field', { hasText: 'MySQL 数据源' })
        .locator('.arco-select-view-value')
        .innerText()
      expect(dsText).toContain('gkx-element-yunfei1')

      // 取消「创建后立即执行」（runNow 默认勾选——三链必须串行）
      const runNowCb = page.locator('label', { hasText: '创建后立即执行' }).locator('input[type="checkbox"]')
      if (await runNowCb.isChecked()) await page.locator('a-checkbox:has-text("创建后立即执行"), .arco-checkbox:has-text("创建后立即执行")').first().click()

      await shot(page, `s6-2-dialog-${c.name.replace(/[@]/g, '_')}`)
      await page.getByRole('button', { name: '创建任务' }).click()
      // 等 toast + 弹窗关闭 + 列表出现新行
      await waitFor(
        async () => (await page.locator('.job-launch-dialog').count()) === 0,
        { timeout: 30_000, interval: 1_000, label: `弹窗关闭 ${c.name}` },
      )
      await waitFor(
        async () => (await page.locator('table tbody tr', { hasText: c.name }).first().isVisible().catch(() => false)),
        { timeout: 30_000, interval: 1_500, label: `新任务行出现 ${c.name}` },
      )
    }
    await shot(page, 's6-3-three-chains-created')

    // ③ 三行状态都应是「未运行」
    for (const c of CHAINS) {
      const row = page.locator('table tbody tr', { hasText: c.name }).first()
      await expect(row.locator('td').nth(5)).toHaveText(/未运行/)
    }
  })
})
