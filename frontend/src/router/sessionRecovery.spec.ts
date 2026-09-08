import { AxiosError, type AxiosAdapter, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { createMemoryHistory, createRouter } from 'vue-router'
import { flushPromises } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../api/auth'
import { http } from '../api/http'
import { PortalAction, portalBridge } from '../portal/iframeBridge'
import { useAuthStore } from '../stores/auth'
import { safeLoginTarget } from './loginTarget'
import { installSessionRecovery, notifySessionExpired } from './sessionRecovery'

const bridgeState = vi.hoisted(() => ({ embedded: false }))

vi.mock('../portal/iframeBridge', () => ({
  PortalAction: { SESSION_EXPIRED: 'session-expired', NO_PERMISSION: 'no-permission' },
  portalBridge: { get isInIframe() { return bridgeState.embedded }, send: vi.fn() },
  isPortalEmbeddedMode: () => bridgeState.embedded,
}))

const profile = { user: { id: 1 }, isAdmin: false, permissions: [] } as AuthProfile
const originalAdapter = http.defaults.adapter

function failure(config: InternalAxiosRequestConfig, status: number) {
  return new AxiosError('Request failed', undefined, config, undefined, {
    status, statusText: 'Rejected', headers: {}, config, data: { detail: '尚未登录' },
  })
}

async function setup(status = 401) {
  setActivePinia(createPinia())
  const store = useAuthStore()
  store.profile = profile
  store.initialized = true
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/overview', component: {} },
      { path: '/login', name: 'login', component: {} },
    ],
  })
  await router.push('/overview?search=paper#results')
  installSessionRecovery(router)
  http.defaults.adapter = (async (config) => { throw failure(config, status) }) as AxiosAdapter
  const replace = vi.spyOn(router, 'replace')
  return { store, router, replace }
}

beforeEach(() => {
  bridgeState.embedded = false
  vi.mocked(portalBridge.send).mockClear()
})

afterEach(() => {
  http.defaults.adapter = originalAdapter
  vi.restoreAllMocks()
})

describe('business request authentication recovery', () => {
  it('clears the profile and preserves the safe page for one recovery after parallel 401s', async () => {
    const { store, router, replace } = await setup()
    await Promise.allSettled([http.get('/v1/graph-query'), http.get('/v1/options')])
    await flushPromises()
    notifySessionExpired('登录状态已失效或已超时，请重新登录')
    expect(store.profile).toBeNull()
    expect(replace).toHaveBeenCalledTimes(1)
    expect(router.currentRoute.value.name).toBe('login')
    expect(router.currentRoute.value.query.redirect).toBe('/overview?search=paper#results')
    expect(portalBridge.send).not.toHaveBeenCalled()
  })

  it('notifies the portal once and enters its embedded recovery state', async () => {
    bridgeState.embedded = true
    const { router } = await setup()
    await Promise.allSettled([http.get('/v1/graph-query'), http.get('/v1/options')])
    await flushPromises()
    expect(portalBridge.send).toHaveBeenCalledExactlyOnceWith(PortalAction.SESSION_EXPIRED, { message: '尚未登录' })
    expect(router.currentRoute.value.query).toEqual({ embedded: '1', portalState: 'session-expired' })
  })

  it.each(['me', 'login-url', 'callback', 'logout'])('does not recursively recover from auth/%s 401', async (endpoint) => {
    const { store, replace } = await setup()
    await http.get(`/v1/auth/${endpoint}?_t=1`).catch(() => {})
    expect(store.profile).toEqual(profile)
    expect(replace).not.toHaveBeenCalled()
    expect(portalBridge.send).not.toHaveBeenCalled()
  })

  it('notifies once when a protected-route profile check discovers expiry', async () => {
    bridgeState.embedded = true
    const { store } = await setup()
    store.invalidate()
    notifySessionExpired('登录状态已失效或已超时，请重新登录')
    notifySessionExpired('登录状态已失效或已超时，请重新登录')
    expect(portalBridge.send).toHaveBeenCalledTimes(1)
  })

  it('keeps the identity on 403 and retains the portal permission notification', async () => {
    bridgeState.embedded = true
    const { store, replace } = await setup(403)
    await http.get('/v1/admin/members').catch(() => {})
    expect(store.profile).toEqual(profile)
    expect(replace).not.toHaveBeenCalled()
    expect(portalBridge.send).toHaveBeenCalledExactlyOnceWith(PortalAction.NO_PERMISSION, { message: '尚未登录' })
  })

  it('does not let a late old 401 invalidate a newer identity', async () => {
    const { store, replace } = await setup()
    let reject!: (error: AxiosError) => void
    let request!: InternalAxiosRequestConfig
    http.defaults.adapter = (config) => new Promise((_resolve, fail) => { request = config; reject = fail })
    const pending = http.get('/v1/graph-query').catch(() => {})
    await flushPromises()
    store.invalidate()
    store.profile = profile
    reject(failure(request, 401))
    await pending
    expect(store.profile).toEqual(profile)
    expect(replace).not.toHaveBeenCalled()
  })

  it('does not start recovery again while logout is in progress', async () => {
    const { store, replace } = await setup()
    await store.logout()
    await http.get('/v1/graph-query').catch(() => {})
    expect(replace).not.toHaveBeenCalled()
    expect(store.profile).toBeNull()
  })

  it.each(['https://external.test', '//external.test', '/\\external.test', '/login?redirect=/login', '/overview\n'])('rejects unsafe or recursive login return path %s', (path) => {
    expect(safeLoginTarget(path)).toBe('')
  })
})
