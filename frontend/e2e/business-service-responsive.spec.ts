import { expect, test, type Page } from '@playwright/test'
import { serviceModules } from '../src/views/business-service/service-modules'

for (const width of [293, 375, 768, 1024]) {
  test(`${width}px: all module inputs and expanded menus stay within bounds`, async ({ page }) => {
    test.setTimeout(120_000)
    await page.setViewportSize({ width, height: 1024 })
    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({
      json: { code: 200, success: true, data: [] },
    }))
    for (const module of serviceModules) {
      await page.goto(`/#/${module.key}`)
      await expect(page.locator('.service-console')).toBeVisible()
      for (const field of module.requestFields) {
        const label = page.locator(`.service-console__params > label[data-field="${field.name}"]`)
        const select = label.locator('.el-select')
        const month = label.locator('.service-console__month-picker')
        const input = label.locator('.service-console__input-wrap > input')
        if (await select.count()) {
          await select.locator('.el-select__wrapper').click()
          const popup = page.locator('.el-popper.business-parameter-options:visible')
          await expect(popup).toBeVisible()
          const bounds = (await popup.boundingBox())!
          const control = (await select.boundingBox())!
          expect(bounds.x, `${module.key}/${field.name}`).toBeGreaterThanOrEqual(0)
          expect(bounds.x + bounds.width, `${module.key}/${field.name}`).toBeLessThanOrEqual(width)
          expect(bounds.width).toBeLessThanOrEqual(control.width + 2)
          await popup.locator('.el-select-dropdown__item:not(.is-disabled)').filter({ hasNotText: /^请选择$/ }).first().click()
          if (await popup.isVisible()) await select.getByRole('combobox').press('Escape')
          await expect(popup).toBeHidden()
        } else if (await month.count()) {
          await month.click()
          const popup = page.locator('.business-month-options:visible')
          await expect(popup).toBeVisible()
          const bounds = (await popup.boundingBox())!
          expect(bounds.x).toBeGreaterThanOrEqual(0)
          expect(bounds.x + bounds.width).toBeLessThanOrEqual(width)
          expect(await popup.evaluate(element => element.scrollWidth <= element.clientWidth + 1), `${module.key}/${field.name}: calendar content`).toBe(true)
          await popup.locator('.arco-picker-header-label').click()
          const year = popup.locator('.arco-panel-year')
          await expect(year).toBeVisible()
          expect((await year.boundingBox())!.width).toBeLessThanOrEqual(bounds.width)
          await year.locator('.arco-picker-cell-in-view:not(.arco-picker-cell-disabled)').first().click()
          const months = popup.locator('.arco-panel-month')
          expect((await months.boundingBox())!.width).toBeLessThanOrEqual(bounds.width)
          await months.locator('.arco-picker-cell:not(.arco-picker-cell-disabled)').first().click()
          await expect(popup).toBeHidden()
          await expect(month.locator('input')).not.toHaveValue('')
        } else if (await input.count()) {
          await input.fill(field.type === 'number' ? '10' : 'test_expert_identifier_abcdefghijklmnopqrstuvwxyz_0123456789')
          await expect(input).not.toHaveValue('')
          const clear = label.locator('.service-console__input-clear')
          if (await clear.count()) {
            await clear.click()
            await expect(input).toHaveValue('')
          }
        }
      }
      const failures = await page.locator('.service-console').evaluate(element => {
        const result: string[] = []
        const viewport = document.documentElement.clientWidth
        const heading = element.querySelector('h2')!
        if (heading.getBoundingClientRect().height > parseFloat(getComputedStyle(heading).lineHeight) * 3 + 1) result.push('module title squeezed into a vertical column')
        for (const label of element.querySelectorAll('.service-console__params > label')) {
          const parent = label.getBoundingClientRect()
          for (const child of label.children) {
            const box = child.getBoundingClientRect()
            if (box.width && (box.left < parent.left - 1 || box.right > parent.right + 1 || box.right > viewport + 1)) result.push(`${label.getAttribute('data-field')}: control overflow`)
            if (child.matches('span, small')) {
              const range = document.createRange()
              range.selectNodeContents(child)
              for (const text of range.getClientRects()) {
                if (text.left < box.left - 1 || text.right > box.right + 1 || text.bottom > box.bottom + 1) result.push(`${label.getAttribute('data-field')}: text overflow`)
              }
            }
          }
        }
        return result
      })
      expect(failures, `${width}px ${module.key}`).toEqual([])
      await expectNoPageOverflow(page)
      await page.getByRole('button', { name: '重置参数', exact: true }).click()
    }
  })
}

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

for (const width of [293, 320, 375, 767, 768, 820, 1024, 1280, 1440]) {
  test(`${width}px: every interface keeps text inside its own table cell`, async ({ page }) => {
    await page.setViewportSize({ width, height: 1024 })
    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({
      json: { code: 200, success: true, data: [] },
    }))
    await page.goto('/#/expert-direct')
    await page.getByRole('tab', { name: '开发者接口', exact: true }).click()
    for (const module of serviceModules) {
      await page.locator('.developer-module-select .el-select__wrapper').click()
      await page.getByRole('option', { name: `${module.title}查询接口`, exact: true }).click()
      await expect(page.locator('.developer-module-select')).toContainText(module.title)
      const overflow = await page.locator('.prototype-table').evaluateAll(tables => {
        const failures: string[] = []
        for (const table of tables) {
          for (const cell of table.querySelectorAll('th, td')) {
            const box = cell.getBoundingClientRect()
            const style = getComputedStyle(cell)
            const left = box.left + parseFloat(style.paddingLeft)
            const right = box.right - parseFloat(style.paddingRight)
            const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT)
            while (walker.nextNode()) {
              if (!walker.currentNode.textContent?.trim()) continue
              const range = document.createRange()
              range.selectNodeContents(walker.currentNode)
              for (const text of range.getClientRects()) {
                if (text.left < left - 1 || text.right > right + 1 || text.top < box.top - 1 || text.bottom > box.bottom + 1) {
                  failures.push(`${table.className}: ${cell.textContent?.trim()}`)
                  break
                }
              }
            }
          }
        }
        return failures
      })
      expect(overflow, `${width}px ${module.key}: text must not cross cell boundaries`).toEqual([])
      await expectNoPageOverflow(page)
    }
  })
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
