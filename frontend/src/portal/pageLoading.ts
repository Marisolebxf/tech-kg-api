import { nextTick } from 'vue'
import type { RouteLocationNormalized, Router } from 'vue-router'

import { PortalAction, portalBridge } from './iframeBridge'

declare global {
  interface Window {
    __KG_PAGE_LOADING__?: {
      start: (retryUrl?: string) => void
      finish: () => void
      fail: () => void
    }
  }
}

/** The shell is confined to this document/iframe; it never covers the parent portal menus. */
export function failPageLoading(): boolean {
  window.__KG_PAGE_LOADING__?.fail()
  portalBridge.send(PortalAction.LOADING_HIDE)
  return Boolean(window.__KG_PAGE_LOADING__)
}

export function installPageLoading(router: Router): void {
  let activeRoute: RouteLocationNormalized | undefined
  router.beforeEach((to) => {
    activeRoute = to
    window.__KG_PAGE_LOADING__?.start(router.resolve(to).href)
    // Release the parent mask before waiting for authentication, spaces or a lazy route module.
    portalBridge.send(PortalAction.LOADING_HIDE)
  })
  router.afterEach(async (to) => {
    // Cancelled/duplicated older navigations must not dismiss a newer route's shell.
    if (activeRoute !== to) return
    await nextTick()
    if (activeRoute !== to) return
    window.__KG_PAGE_LOADING__?.finish()
    portalBridge.send(PortalAction.LOADING_HIDE)
    activeRoute = undefined
  })
  router.onError((_error, to) => {
    if (activeRoute !== to) return
    failPageLoading()
    activeRoute = undefined
  })
}
