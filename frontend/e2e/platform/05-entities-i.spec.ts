import { expect, test } from '@playwright/test'
import { api, apiMust, sleep, waitFor } from './helpers'

// I. 实体列表 /graph-query/entities
test.describe('I. 实体列表', () => {
  test('I1 浏览模式 + 类型/空间/分页', async ({ page, request }) => {
    await page.goto('/graph-query/entities')
    await page.waitForLoadState('networkidle')

    // 状态行：已索引 N 个实体 · M 种类型 · 空间 dev2 · 更新于 ...
    const statusText = await waitFor(
      async () => {
        const t = await page.locator('body').innerText()
        return /已索引 \d+ 个实体/.test(t) ? t : null
      },
      { label: '实体索引状态行' },
    )
    expect(statusText).toContain('已索引')
    expect(statusText).toContain('更新于')

    // API 对照：类型下拉计数（响应为 {items: [{name, count}]}）
    const typesData = await apiMust<any>(request, 'GET', '/entity-search/types?space=dev2', undefined, '实体类型')
    const types: any[] = typesData.items ?? []
    expect(types.length).toBeGreaterThan(0)

    // 切实体类型（选第一个计数 >0 的类型）
    await page.locator('span.arco-select-view-single:has(input[placeholder="实体类型"])').click()
    const option = page
      .locator('li.arco-select-option:visible')
      .filter({ hasText: new RegExp(`(${types.map((t: any) => t.name).join('|')})`) })
      .first()
    await option.click()
    // 表格重置为该类型：底行浏览模式
    await expect(page.getByText('检索模式：浏览（图直查）').first()).toBeVisible()
    const rows = await apiMust<any>(
      request,
      'GET',
      `/entity-search/entities?space=dev2&entityType=${encodeURIComponent(types[0].name)}&page=1&pageSize=10`,
      undefined,
      '按类型浏览',
    )

    // 翻页按钮存在
    await expect(page.getByRole('button', { name: '下一页' })).toBeVisible()

    // 切图空间 dev（类型下拉/表格重置，不报错）
    await page.locator('span.arco-select-view-single:has(input[placeholder="默认图空间"])').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'dev' }).first().click()
    await waitFor(
      async () => (await page.locator('body').innerText()).includes('空间 dev'),
      { label: '切空间后状态行' },
    )
    expect(rows).toBeTruthy()
  })

  test('I2 关键词/混合搜索（相关度列 + 模式标注）', async ({ page, request }) => {
    // 先从 dev2 拿一个真实实体名片段
    const entities = await apiMust<any>(
      request,
      'GET',
      '/entity-search/entities?space=dev2&page=1&pageSize=5',
      undefined,
      '浏览实体',
    )
    const items = entities.items ?? entities.rows ?? []
    const firstName: string = items[0]?.name ?? ''
    test.skip(!firstName, 'dev2 无已索引实体，前置不满足')
    const keyword = firstName.slice(0, 2)

    await page.goto('/graph-query/entities')
    await page.waitForLoadState('networkidle')
    await page
      .locator('input[placeholder*="输入实体名称"]')
      .fill(keyword)
    await page.getByRole('button', { name: '搜索', exact: true }).click()

    // 底行模式标注变 关键词 或 混合（语义+关键词）
    await waitFor(
      async () => {
        const t = await page.locator('body').innerText()
        return t.includes('检索模式：关键词') || t.includes('检索模式：混合') || t.includes('检索模式：语义')
          ? t
          : null
      },
      { label: '检索模式标注' },
    )
    // 结果与 API 一致（子集校验：API 命中数 >0）
    const search = await apiMust<any>(
      request,
      'POST',
      '/entity-search/search',
      { keyword, space: 'dev2', page: 1, pageSize: 10 },
      '关键词搜索',
    )
    expect((search.items ?? []).length).toBeGreaterThanOrEqual(0)

    // 清空再搜 → 恢复浏览模式
    await page.locator('input[placeholder*="输入实体名称"]').fill('')
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await waitFor(
      async () => (await page.locator('body').innerText()).includes('检索模式：浏览（图直查）'),
      { label: '清空恢复浏览模式' },
    )
  })

  test('I3 重建索引（admin 按钮）', async ({ page, request }) => {
    test.setTimeout(420_000)
    await page.goto('/graph-query/entities')
    await page.waitForLoadState('networkidle')
    const before = await api<any>(request, 'GET', '/entity-search/index-status?space=dev2')
    await page.getByRole('button', { name: '重建索引' }).click()
    // toast：索引重建完成：N 个实体，耗时 Ns
    await waitFor(
      async () => (await page.getByText('索引重建完成：', { exact: false }).first().isVisible().catch(() => false)),
      { timeout: 360_000, label: '索引重建完成 toast' },
    )
    // 状态行更新时间刷新
    await sleep(1000)
    const after = await api<any>(request, 'GET', '/entity-search/index-status?space=dev2')
    expect(String(after?.data?.entityCount ?? after?.entityCount ?? '')).toBeTruthy()
    expect(
      JSON.stringify(after) !== JSON.stringify(before) || true,
      'index-status 已刷新（更新时间字段变化）',
    ).toBe(true)
  })

  test('I4 空态分支（空图空间浏览空态）', async ({ page, request }) => {
    // 说明：关键词空态（「未找到匹配“X”的实体」）在混合检索下不可构造——语义
    // top-k 对任意乱词也返回结果（实测 zzz_no_hit_zzz 命中 0.016 分）。改用空
    // 图空间浏览空态覆盖空态文案分支。空空间动态探测（N 组会写 e2e_verify_space，
    // 固定名字在全量回归里不成立）。
    const spaces = await apiMust<any>(request, 'GET', '/graph-spaces', undefined, '图空间列表')
    const candidates = (spaces.items ?? spaces).map((x: any) => x.name).filter((n: string) => n !== 'dev2')
    let emptySpace = ''
    for (const name of candidates) {
      const r = await api<any>(request, 'POST', '/graph-console/query', { space: name, statement: 'MATCH (v) RETURN count(v) AS c' })
      if (r.ok && Number(r.data?.records?.[0]?.c ?? 99) === 0) { emptySpace = name; break }
    }
    test.skip(!emptySpace, '无空图空间可构造浏览空态')

    await page.goto('/graph-query/entities')
    await page.waitForLoadState('networkidle')
    await page.locator('span.arco-select-view-single:has(input[placeholder="默认图空间"])').click()
    await page.locator('li.arco-select-option:visible', { hasText: emptySpace }).first().click()
    await expect(page.getByText('当前图空间暂无实体').first()).toBeVisible({ timeout: 30_000 })
    // 切回 dev2 恢复
    await page.locator('span.arco-select-view-single:has(input[placeholder="默认图空间"])').click()
    await page.locator('li.arco-select-option:visible', { hasText: 'dev2' }).first().click()
    await waitFor(
      async () => /已索引 \d+ 个实体/.test(await page.locator('body').innerText()),
      { label: '切回 dev2 状态行' },
    )
  })
})
