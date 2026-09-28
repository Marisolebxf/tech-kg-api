import { expect, test } from '@playwright/test'
import { api, apiMust, switchGraphSpace, waitFor } from './helpers'

// I. 实体列表 /graph-query/entities（图空间跟随平台总览页的全局选择器，本页无空间控件）
test.describe('I. 实体列表', () => {
  test.beforeAll(async ({ request }) => {
    // 选择器列表已收敛为「默认+本人绑定」：I1 要切的 dev 先绑定（bind 幂等）
    await api(request, 'POST', '/graph-spaces/dev/bind', {})
  })

  test('I1 浏览模式 + 类型/空间/分页', async ({ page, request }) => {
    // 全局空间默认 dev2（免登录模式无用户维度不落盘、选择器仅平台总览页渲染，
    // 以页面实际请求的 space 参数核对）
    const dev2Types = page.waitForRequest(
      (r) => r.url().includes('/entity-search/types') && /[?&]space=dev2(&|$)/.test(r.url()),
    )
    await page.goto('/graph-query/entities')
    await page.waitForLoadState('networkidle')
    await dev2Types

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

    // 切图空间 dev（类型/索引状态按新空间重查，不报错）
    const devTypes = page.waitForRequest(
      (r) => r.url().includes('/entity-search/types') && /[?&]space=dev(&|$)/.test(r.url()),
    )
    await switchGraphSpace(page, 'dev')
    await devTypes
    expect(rows).toBeTruthy()
  })

  test('I2 关键词/混合搜索（相关度列 + 模式标注）', async ({ page, request }) => {
    // 从实时图库浏览结果中选择一个普通标量属性，验证该属性确实进入 Milvus 索引。
    const entities = await apiMust<any>(
      request,
      'GET',
      '/entity-search/entities?space=dev2&limit=100&offset=0',
      undefined,
      '浏览实体',
    )
    const items = entities.items ?? entities.rows ?? []
    const identityKeys = new Set([
      'id',
      'entity_id',
      'name',
      'name_zh',
      'name_cn',
      'name_en',
      'title',
      'title_zh',
      'title_en',
      'project_name',
      'paper_title',
      'patent_name',
      'patent_title',
      'product_name',
      'keyword',
      'label',
      'cn_name',
      'display_name',
      'org_name',
    ])
    const candidate = items
      .flatMap((item: any) =>
        Object.entries(item.properties ?? {}).map(([key, value]) => ({
          item,
          key,
          value,
        })),
      )
      .find(({ key, value }: any) => {
        const text = typeof value === 'string' ? value.trim() : ''
        return !identityKeys.has(key) && text.length >= 2 && text.length <= 128
      })
    test.skip(!candidate, 'dev2 浏览窗口中没有可验证的普通标量属性')
    const keyword = String(candidate!.value).trim()

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
    // API 必须返回真正含该属性值的实体；不能再用“结果数 >= 0”的无效断言。
    const search = await apiMust<any>(
      request,
      'POST',
      '/entity-search/search',
      { keyword, space: 'dev2', limit: 100, offset: 0 },
      '属性关键词搜索',
    )
    const searchItems: any[] = search.items ?? []
    expect(searchItems.length).toBeGreaterThan(0)
    expect(
      searchItems.some((item: any) =>
        Object.values(item.properties ?? {}).some((value) => String(value).includes(keyword)),
      ),
    ).toBe(true)

    // 清空再搜 → 恢复浏览模式
    await page.locator('input[placeholder*="输入实体名称"]').fill('')
    await page.getByRole('button', { name: '搜索', exact: true }).click()
    await waitFor(
      async () => (await page.locator('body').innerText()).includes('检索模式：浏览（图直查）'),
      { label: '清空恢复浏览模式' },
    )
  })

  test('I4 空态分支（空图空间浏览空态）', async ({ page, request }) => {
    // 说明：关键词空态（「未找到匹配“X”的实体」）在混合检索下不可构造——语义
    // top-k 对任意乱词也返回结果（实测 zzz_no_hit_zzz 命中 0.016 分）。改用空
    // 图空间浏览空态覆盖空态文案分支。空空间动态探测（N 组会写 e2e_verify_space，
    // 固定名字在全量回归里不成立）。选择器只列「默认+本人绑定」，候选同样
    // 限定 bound=true（否则选中的空间在全局选择器里根本切不过去）。
    const spaces = await apiMust<any>(request, 'GET', '/graph-spaces', undefined, '图空间列表')
    const candidates = (spaces.items ?? spaces)
      .filter((x: any) => x.bound && x.name !== 'dev2')
      .map((x: any) => x.name)
    let emptySpace = ''
    for (const name of candidates) {
      const r = await api<any>(request, 'POST', '/graph-console/query', { space: name, statement: 'MATCH (v) RETURN count(v) AS c' })
      if (r.ok && Number(r.data?.records?.[0]?.c ?? 99) === 0) { emptySpace = name; break }
    }
    test.skip(!emptySpace, '无空图空间可构造浏览空态')

    await page.goto('/graph-query/entities')
    await page.waitForLoadState('networkidle')
    await switchGraphSpace(page, emptySpace)
    await expect(page.getByText('当前图空间暂无实体').first()).toBeVisible({ timeout: 30_000 })
    // 切回 dev2 恢复（类型/索引状态按 dev2 重查）
    const dev2Reload = page.waitForRequest(
      (r) => r.url().includes('/entity-search/') && /[?&]space=dev2(&|$)/.test(r.url()),
    )
    await switchGraphSpace(page, 'dev2')
    await dev2Reload
  })
})
