import { expect, test, type Page } from '@playwright/test'

async function expectNoPageOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
  for (const selector of ['.business-service', '.graph-panel', '.result-panel', '.developer-view']) {
    const element = page.locator(selector)
    if (!await element.count()) continue
    const bounds = await element.boundingBox()
    expect(bounds!.x).toBeGreaterThanOrEqual(-1)
    expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(page.viewportSize()!.width + 1)
  }
}

for (const [width, height] of [[320, 740], [375, 812], [767, 1024], [768, 1024], [820, 1180], [1024, 768], [1280, 800], [1440, 900]]) {
  test(`${width}x${height}: menu, details and tables remain usable`, async ({ page }) => {
    await page.setViewportSize({ width, height })
    const errors: string[] = []
    page.on('pageerror', error => errors.push(error.message))
    // Only intercept backend requests, never Vite's /src/api/ modules.
    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({
      json: { code: 0, data: [], message: 'responsive test fixture' },
    }))
    await page.goto('/#/expert-direct')
    await expect(page.locator('.graph-panel')).toBeVisible()
    await expectNoPageOverflow(page)

    for (const name of ['摘要', '实体', '关系', '溯源', '算法', 'API']) {
      const tab = page.getByRole('tab', { name, exact: true })
      await tab.click()
      await expect(tab).toHaveAttribute('aria-selected', 'true')
      expect(await tab.evaluate(element => element.scrollHeight <= element.clientHeight + 1)).toBe(true)
    }
    await page.getByRole('tab', { name: '算法', exact: true }).click()
    const metrics = await page.evaluate(() => {
      const rect = (selector: string) => document.querySelector(selector)!.getBoundingClientRect()
      const main = rect('.business-service__main')
      const graph = rect('.graph-panel')
      const details = rect('.result-panel')
      const descriptions = [...document.querySelectorAll('.result-panel__rules dd')]
      return {
        stacked: main.width < 856,
        graphBottom: graph.bottom,
        detailsTop: details.top,
        descriptionWidth: Math.min(...descriptions.map(element => element.getBoundingClientRect().width)),
      }
    })
    if (metrics.stacked) expect(metrics.detailsTop).toBeGreaterThanOrEqual(metrics.graphBottom)
    expect(metrics.descriptionWidth).toBeGreaterThanOrEqual(100)

    await page.getByRole('tab', { name: '开发者接口', exact: true }).click()
    await page.locator('.developer-module-select .el-select__wrapper').click()
    const popup = page.locator('.el-popper.developer-module-options:visible')
    await expect(popup).toBeVisible()
    const bounds = (await popup.boundingBox())!
    expect(bounds.x).toBeGreaterThanOrEqual(0)
    expect(bounds.x + bounds.width).toBeLessThanOrEqual(width)
    const selectBounds = (await page.locator('.developer-module-select').boundingBox())!
    expect(bounds.width).toBeLessThanOrEqual(selectBounds.width + 2)
    await page.getByRole('option', { name: '科技产业链点TOP-N事件关系查询接口', exact: true }).click()
    await expect(page.locator('.developer-module-select')).toContainText('科技产业链点TOP-N事件关系查询接口')
    await expectNoPageOverflow(page)
    for (const table of await page.locator('.developer-view__table-scroll').all()) {
      expect(await table.evaluate(element => {
        const content = element.querySelector('table')!
        return content.scrollWidth <= element.clientWidth + 1 || getComputedStyle(element).overflowX === 'auto'
      })).toBe(true)
    }
    // Keyboard selection remains usable after replacing the native select.
    const combo = page.getByRole('combobox', { name: '子功能名称' })
    await combo.focus()
    await combo.press('ArrowDown')
    await expect(combo).toHaveAttribute('aria-expanded', 'true')
    await combo.press('Escape')
    await expect(combo).toHaveAttribute('aria-expanded', 'false')
    if (width === 768) {
      await page.locator('.developer-module-select .el-select__wrapper').click()
      await page.setViewportSize({ width: 375, height: 812 })
      await expect.poll(async () => {
        const rotated = await popup.boundingBox()
        return rotated !== null && rotated.x >= 0 && rotated.x + rotated.width <= 375
      }).toBe(true)
    }
    expect(errors).toEqual([])
  })
}
