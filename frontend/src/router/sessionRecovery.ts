import type { Router } from 'vue-router'

import { setSessionExpiredHandler } from '../api/http'
import { currentSessionVersion } from '../auth/sessionVersion'
import { isPortalEmbeddedMode, PortalAction, portalBridge } from '../portal/iframeBridge'
import { useAuthStore } from '../stores/auth'
import { safeLoginTarget } from './loginTarget'

let notifiedVersion = -1

export function notifySessionExpired(message: string): void {
  const version = currentSessionVersion()
  if (!portalBridge.isInIframe || notifiedVersion === version) return
  notifiedVersion = version
  portalBridge.send(PortalAction.SESSION_EXPIRED, { message })
}

export function loginRedirect(fullPath: string, error?: string) {
  if (isPortalEmbeddedMode()) {
    return { path: '/login', query: { embedded: '1', portalState: 'session-expired' } }
  }
  return {
    path: '/login',
    query: {
      redirect: safeLoginTarget(fullPath) || '/overview',
      ...(error ? { error } : {}),
    },
  }
}

export function installSessionRecovery(router: Router): void {
  setSessionExpiredHandler((message) => {
    const authStore = useAuthStore()
    // 并发请求失效只恢复一次登录，且不打断用户主动退出。
    if (authStore.initialized && !authStore.isAuthenticated) return
    authStore.invalidate()
    notifySessionExpired(message)
    if (router.currentRoute.value.name === 'login') return
    return router.replace(loginRedirect(router.currentRoute.value.fullPath, message))
  })
}
