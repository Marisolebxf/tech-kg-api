import { flushPromises } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PortalAction, portalBridge } from './iframeBridge'
import { failPageLoading, installPageLoading } from './pageLoading'

vi.mock('./iframeBridge', () => ({
  PortalAction: { LOADING_HIDE: 'loading.hide' },
  portalBridge: { send: vi.fn() },
}))

beforeEach(() => {
  vi.clearAllMocks()
  window.__KG_PAGE_LOADING__ = { start: vi.fn(), finish: vi.fn(), fail: vi.fn() }
})
afterEach(() => { delete window.__KG_PAGE_LOADING__ })

function setup() {
  const router = createRouter({
    history: createMemoryHistory('/bkg_zpt'),
    routes: [
      { path: '/expert-direct', component: {} },
      { path: '/expert-alumni', component: {} },
      { path: '/failed', component: () => Promise.reject(new Error('chunk failed')) },
    ],
  })
  installPageLoading(router)
  return router
}

describe('iframe-local route loading', () => {
  it('releases the portal mask before waiting for the route guard', async () => {
    const router = setup()
    let resolve!: () => void
    router.beforeEach(() => new Promise<void>(done => { resolve = done }))
    const navigation = router.push('/expert-direct')
    await flushPromises()
    expect(window.__KG_PAGE_LOADING__!.start).toHaveBeenCalledWith('/bkg_zpt/expert-direct')
    expect(portalBridge.send).toHaveBeenCalledWith(PortalAction.LOADING_HIDE)
    expect(window.__KG_PAGE_LOADING__!.finish).not.toHaveBeenCalled()
    resolve()
    await navigation
    await flushPromises()
    expect(window.__KG_PAGE_LOADING__!.finish).toHaveBeenCalledTimes(1)
  })

  it('shows a local failure and releases the parent mask when a lazy route cannot load', async () => {
    const router = setup()
    await router.push('/expert-direct')
    await flushPromises()
    vi.clearAllMocks()
    await expect(router.push('/failed')).rejects.toThrow('chunk failed')
    expect(window.__KG_PAGE_LOADING__!.fail).toHaveBeenCalledTimes(1)
    expect(window.__KG_PAGE_LOADING__!.finish).not.toHaveBeenCalled()
    expect(portalBridge.send).toHaveBeenCalledWith(PortalAction.LOADING_HIDE)
  })

  it('does not let a cancelled older navigation hide a newer loading shell', async () => {
    const router = setup()
    await router.push('/expert-direct')
    await flushPromises()
    vi.clearAllMocks()
    let first!: () => void
    let second!: () => void
    let oldChecks = 0
    router.beforeEach(to => new Promise<void>(done => {
      if (to.path === '/expert-alumni') { first = done; oldChecks++ }
      else second = done
    }))
    const old = router.push('/expert-alumni')
    await flushPromises()
    const current = router.push('/failed')
    await flushPromises()
    first()
    await old
    await flushPromises()
    expect(oldChecks).toBe(1)
    expect(window.__KG_PAGE_LOADING__!.finish).not.toHaveBeenCalled()
    second()
    await expect(current).rejects.toThrow('chunk failed')
    expect(window.__KG_PAGE_LOADING__!.fail).toHaveBeenCalledTimes(1)
  })

  it('does not hide an in-progress navigation when the current route is clicked again', async () => {
    const router = setup()
    await router.push('/expert-direct')
    await flushPromises()
    vi.clearAllMocks()
    let resolve!: () => void
    router.beforeEach(() => new Promise<void>(done => { resolve = done }))
    const pending = router.push('/expert-alumni')
    await flushPromises()
    await router.push('/expert-direct')
    expect(window.__KG_PAGE_LOADING__!.finish).not.toHaveBeenCalled()
    resolve()
    await pending
  })

  it('can notify the portal even when the startup shell is unavailable', () => {
    delete window.__KG_PAGE_LOADING__
    expect(failPageLoading()).toBe(false)
    expect(portalBridge.send).toHaveBeenCalledWith(PortalAction.LOADING_HIDE)
  })
})
