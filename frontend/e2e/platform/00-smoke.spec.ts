import { expect, test } from '@playwright/test'
import { API_BASE } from './helpers'

// J/K/L 三条冒烟（方案 §J–L）：HTTP 断言 + 公共页渲染，不写完整交互用例。
test.describe('J/K/L 冒烟', () => {
  test('J: /kg-construction/options 聚合端点 200 且各下拉数组存在', async ({ request }) => {
    const resp = await request.get(API_BASE + '/kg-construction/options')
    expect(resp.status()).toBe(200)
    const data = await resp.json()
    for (const key of [
      'scholars',
      'enterprises',
      'edges',
      'relationTypes',
      'roles',
      'dimensions',
      'techFields',
      'cpcCodes',
    ]) {
      expect(Array.isArray(data[key]), `下拉 ${key} 应为数组`).toBe(true)
    }
    // 单项失败返回 [] 不整体挂：目录类至少有 relationTypes/roles 非空
    expect(data.relationTypes.length).toBeGreaterThan(0)
    expect(data.roles.length).toBeGreaterThan(0)
  })

  test('K: 文档中心 VitePress 可访问（防回归）', async ({ request }) => {
    const resp = await request.get('http://localhost:8089/docs/')
    expect(resp.status()).toBe(200)
    const html = await resp.text()
    expect(html).toContain('Tech KG 文档中心')
  })

  test('L: /demo/t-direct 公共页渲染五段式表单（无路由守卫拦截）', async ({ page }) => {
    await page.goto('/demo/t-direct')
    await expect(page.getByRole('heading', { name: '人工审核 · 候选入库决策' })).toBeVisible()
    await expect(page.getByText('① 原始记录')).toBeVisible()
    await expect(page.getByText('② 抽取推理过程')).toBeVisible()
    await expect(page.getByText('③ 候选')).toBeVisible()
    await expect(page.getByText('④ 为什么需要你确认')).toBeVisible()
    await expect(page.getByText('⑤ 决策')).toBeVisible()
    await expect(page.getByRole('button', { name: '通过·入库' })).toBeVisible()
  })
})
