import { expect, test } from '@playwright/test'

for (const [width, height] of [[320, 568], [375, 667], [390, 400], [768, 1024], [1024, 768], [900, 420]]) {
  test(`${width}x${height}: login scrolls and the entry remains reachable`, async ({ page, browserName }) => {
    await page.setViewportSize({ width, height })
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
      if (new URL(route.request().url()).pathname.endsWith('/auth/login-url')) {
        await route.fulfill({ json: { success: true, code: 200, data: { url: '/?oauth-test=1', expiresIn: 60 } } })
      } else {
        await route.fulfill({ status: 401, json: { detail: 'Not authenticated' } })
      }
    })
    await page.goto('/#/login?error=' + encodeURIComponent('登录状态已失效，请重新登录。'.repeat(4)))
    const main = page.locator('.login-page')
    const button = page.getByRole('button', { name: /用户端/ })
    await expect(button).toBeEnabled()
    const dimensions = await main.evaluate(element => ({
      height: element.clientHeight,
      content: element.scrollHeight,
      width: element.clientWidth,
      contentWidth: element.scrollWidth,
    }))
    expect(dimensions.height).toBeLessThanOrEqual(height)
    expect(dimensions.contentWidth).toBeLessThanOrEqual(dimensions.width + 1)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true)
    expect(await page.locator('.login-intro').evaluate(element => {
      return element.querySelector('.login-intro__content')!.getBoundingClientRect().bottom <= element.getBoundingClientRect().bottom
    })).toBe(true)
    if (dimensions.content > dimensions.height) {
      // Real input must scroll; programmatic scrollTop also works on overflow:hidden.
      if (browserName === 'chromium') {
        const cdp = await page.context().newCDPSession(page)
        const x = Math.floor(width / 2)
        const y = Math.floor(height * 0.75)
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x, y }] })
        for (let step = 1; step <= 10; step++) {
          await cdp.send('Input.dispatchTouchEvent', {
            type: 'touchMove', touchPoints: [{ x, y: y - step * Math.min(25, height / 20) }],
          })
          await page.waitForTimeout(20)
        }
        await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] })
        await cdp.detach()
      } else {
        await page.mouse.move(width / 2, height / 2)
        await page.mouse.wheel(0, 400)
      }
      await expect.poll(() => main.evaluate(element => element.scrollTop)).toBeGreaterThan(0)
    }
    await button.scrollIntoViewIfNeeded()
    await expect(button).toBeInViewport()
    await button.click()
    await expect(page).toHaveURL(/\?oauth-test=1/)
  })
}
