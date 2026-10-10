import { expect, test, type Locator, type Page } from '@playwright/test'

/**
 * 平台总览图空间下拉弹层边界（GraphSpaceSelector contentClass 弹层）。
 *
 * Arco Cascader 默认从触发框左缘展开，360px 弹层贴着触发框在页面右上角，
 * 靠近视口右缘时会被 Arco 贴边放置（阴影被裁）。修复只对
 * `.app-space-select-popup` 整体 translateX(-12px)，宽度和两列 40%/60%
 * 配置不动，本规格守住三条边界：
 * - 1395px：弹层右侧至少保留 12px，不再顶死视口右缘；
 * - 375px：左移后弹层左右都不越出视口；
 * - 两列比例、360px 封顶、长名省略号与纵向滚动不因左移回归；
 * - hover 自绘滑块收掉，不再与弹层右边框并排读成"两条滚动条"（滚轮仍可滚）。
 */

const SPACES_PATH = '/graph-search/spaces'

/** 单组 12 个超长名公共空间：撑出第二列纵向滚动与省略号截断。 */
const longPublicSpaces = Array.from(
  { length: 12 },
  (_, index) => `公共演示图空间-超长中文名称用于验证省略号截断与纵向滚动-第${index + 1}号`,
)
const spaceItems = [
  ...longPublicSpaces.map((name) => ({ name, groupKind: 'public' })),
  { name: 'business-space-demo', groupKind: 'business', clientId: 'demo', businessName: '演示业务线' },
  { name: 'legacy-orphan-space' },
]
const spacesPayload = {
  code: 200,
  success: true,
  msg: '',
  data: { spaces: spaceItems.map((item) => item.name), items: spaceItems },
}

/** 只拦后端请求（/api/），vite 的 /src/ 模块请求不碰；spaces 走专用夹具。 */
async function mockBackend(page: Page) {
  await page.route(
    (url) => url.pathname.startsWith('/api/') && !url.pathname.endsWith(SPACES_PATH),
    (route) => route.fulfill({ json: { code: 200, success: true, data: [], msg: '' } }),
  )
  await page.route(
    (url) => url.pathname.endsWith(SPACES_PATH),
    (route) => route.fulfill({ json: spacesPayload }),
  )
}

/** 打开顶栏图空间下拉，点开公共分组展开第二列（expand-trigger 默认 click）。 */
async function openSpacePopup(page: Page): Promise<Locator> {
  const select = page.locator('.app-space-select').first()
  await expect(select).toBeVisible()
  const trigger = select.locator('.arco-select-view')
  await expect(trigger).toBeEnabled()
  await trigger.click()
  const popup = page.locator('.app-space-select-popup')
  await expect(popup).toBeVisible()
  await popup.locator('.arco-cascader-option', { hasText: '公共图空间' }).first().click()
  await expect(
    popup.locator('.arco-cascader-option-label', { hasText: '第12号' }),
    '点开公共分组应展开 12 个空间的第二列',
  ).toBeVisible()
  return popup
}

/** 等弹层入场动画结束后再量几何：连续两次读数稳定即认定静止。 */
async function stableBoundingBox(locator: Locator) {
  let previous = await locator.boundingBox()
  for (let attempt = 0; attempt < 10; attempt++) {
    await locator.page().waitForTimeout(120)
    const current = await locator.boundingBox()
    if (
      previous
      && current
      && Math.abs(previous.x - current.x) < 0.5
      && Math.abs(previous.y - current.y) < 0.5
      && Math.abs(previous.width - current.width) < 0.5
    ) {
      return current
    }
    previous = current
  }
  return previous!
}

test('1395px: 弹层右移腾出 ≥12px 呼吸位，宽度封顶与两列 40%/60% 保持', async ({ page }) => {
  await page.setViewportSize({ width: 1395, height: 900 })
  await mockBackend(page)
  await page.goto('/overview')
  const popup = await openSpacePopup(page)

  const box = await stableBoundingBox(popup)
  expect(box.x, '弹层左缘不越出视口').toBeGreaterThanOrEqual(-0.5)
  expect(
    1395 - (box.x + box.width),
    '弹层右侧至少保留 12px，不被 Arco 贴到视口右缘',
  ).toBeGreaterThanOrEqual(12 - 0.5)

  const panel = popup.locator('.arco-cascader-panel')
  const panelBox = await panel.boundingBox()
  expect(panelBox, '弹层面板应可见').not.toBeNull()
  expect(Math.abs(panelBox!.width - 360), '面板宽度保持 360px 封顶').toBeLessThanOrEqual(1)

  const columns = popup.locator('.arco-cascader-panel-column')
  await expect(columns, '公共分组展开后为两列').toHaveCount(2)
  const [firstColumn, secondColumn] = await columns.all()
  const firstWidth = (await firstColumn.boundingBox())!.width
  const secondWidth = (await secondColumn.boundingBox())!.width
  const firstRatio = firstWidth / (firstWidth + secondWidth)
  expect(firstRatio, '首列保持 40%').toBeGreaterThan(0.36)
  expect(firstRatio, '首列保持 40%').toBeLessThan(0.44)
})

test('1395px: 超长空间名省略号截断，列表仍可纵向滚动', async ({ page }) => {
  await page.setViewportSize({ width: 1395, height: 900 })
  await mockBackend(page)
  await page.goto('/overview')
  const popup = await openSpacePopup(page)
  await stableBoundingBox(popup)

  const longLabel = popup.locator('.arco-cascader-option-label', { hasText: '第12号' }).first()
  const truncation = await longLabel.evaluate((element) => {
    const style = getComputedStyle(element)
    return { truncated: element.scrollWidth > element.clientWidth + 1, ellipsis: style.textOverflow }
  })
  expect(truncation.truncated, '超长名实际被截断（scrollWidth 超出可视宽）').toBe(true)
  expect(truncation.ellipsis, '截断样式保持省略号').toBe('ellipsis')

  const scrolled = await popup.evaluate((root) => {
    for (const element of root.querySelectorAll<HTMLElement>('*')) {
      if (element.scrollHeight > element.clientHeight + 1) {
        element.scrollTop = 60
        return { className: String(element.className), scrolled: element.scrollTop > 0 }
      }
    }
    return null
  })
  expect(scrolled, '12 个选项超出 200px 定高面板，列表须可纵向滚动').not.toBeNull()
  expect(scrolled!.scrolled, '滚动位置实际可移动').toBe(true)

  // hover 第二列原本会淡入 Arco 自绘滑块，与弹层右边框并排像"两条滚动条"；
  // 修复=该弹层内整条轨道 display:none，滚轮滚动能力由上一断言守住。
  await popup.locator('.arco-cascader-panel-column').nth(1).hover()
  await page.waitForTimeout(300)
  const trackDisplay = await popup.evaluate(
    (root) => root.querySelector('.arco-scrollbar-track') !== null
      ? getComputedStyle(root.querySelector('.arco-scrollbar-track')!).display
      : 'absent',
  )
  expect(trackDisplay, 'hover 时自绘滑块轨道不渲染').toBe('none')
})

test('375px: 弹层左移后左右都不越出视口', async ({ page }) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await mockBackend(page)
  await page.goto('/overview')
  const popup = await openSpacePopup(page)

  const box = await stableBoundingBox(popup)
  expect(box.x, '移动端弹层左缘不越出视口').toBeGreaterThanOrEqual(-0.5)
  expect(box.x + box.width, '移动端弹层右缘不越出视口').toBeLessThanOrEqual(375.5)

  const panelBox = await popup.locator('.arco-cascader-panel').boundingBox()
  expect(panelBox, '弹层面板应可见').not.toBeNull()
  expect(
    Math.abs(panelBox!.width - (375 - 24)),
    '面板宽度保持 min(360px, 100vw - 24px)',
  ).toBeLessThanOrEqual(1)
})
