import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const transport = vi.hoisted(() => ({
  me: vi.fn(), spaces: vi.fn(),
  handlers: new Map<string, (data: Record<string, unknown>) => void>(),
}))
vi.mock('../config', async (importOriginal) => ({
  ...await importOriginal<typeof import('../config')>(),
  appBase: '/', apiBase: '/', graphSpace: 'dev', graphVisualizationEnabled: false,
}))
vi.mock('../api/auth', () => ({
  getCurrentProfile: transport.me, getLoginUrl: vi.fn(), logoutCurrentSession: vi.fn(), refreshCurrentSession: vi.fn(),
}))
vi.mock('../api/graphSearch', () => ({ listGraphSpaces: transport.spaces }))
vi.mock('../api/http', () => ({ setSessionExpiredHandler: vi.fn() }))
vi.mock('../portal/iframeBridge', async (importOriginal) => ({
  ...await importOriginal<typeof import('../portal/iframeBridge')>(),
  isPortalEmbeddedMode: () => true,
  portalBridge: {
    isInIframe: true, start: vi.fn(), stop: vi.fn(), send: vi.fn(), ready: vi.fn(),
    on: (action: string, callback: (data: Record<string, unknown>) => void) => {
      transport.handlers.set(action, callback)
      return () => transport.handlers.delete(action)
    },
  },
}))
vi.mock('../views/business-service/BusinessServiceView.vue', () => ({ default: {} }))
vi.mock('../views/auth/LoginView.vue', () => ({ default: {} }))
vi.mock('../views/auth/UserCenterView.vue', () => ({ default: {} }))
vi.mock('../views/auth/AccountSecurityView.vue', () => ({ default: {} }))
vi.mock('../views/auth/OperationLogsView.vue', () => ({ default: {} }))
vi.mock('../views/auth/AccessDeniedView.vue', () => ({ default: {} }))
vi.mock('../views/platform/PlatformWorkbenchView.vue', () => ({ default: {} }))
vi.mock('../views/platform/OperationsCenterView.vue', () => ({ default: {} }))
vi.mock('../views/platform/ManualReviewWorkspaceView.vue', () => ({ default: {} }))
vi.mock('../views/platform/TDirectDemoView.vue', () => ({ default: {} }))
vi.mock('../views/platform/ProcessInstanceDetailView.vue', () => ({ default: {} }))
vi.mock('../views/platform/SchemaBrowserView.vue', () => ({ default: {} }))
vi.mock('../views/platform/GraphBuildView.vue', () => ({ default: {} }))
vi.mock('../views/platform/EntityListView.vue', () => ({ default: {} }))
vi.mock('../views/platform/GraphVisualizationView.vue', () => ({ default: {} }))
vi.mock('../views/platform/ConfigurationManagementView.vue', () => ({ default: {} }))
let wrapper: VueWrapper | undefined
const member = { user: { id: '101' }, isAdmin: false, permissions: [] }
beforeEach(() => {
  vi.resetModules()
  vi.clearAllMocks()
  transport.handlers.clear()
  transport.me.mockResolvedValue(member)
  transport.spaces.mockResolvedValue({ data: { spaces: ['dev'] } })
  vi.spyOn(performance, 'getEntriesByType').mockReturnValue([{ type: 'navigate' } as PerformanceNavigationTiming])
  localStorage.clear()
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })

async function startAt(path = '/expert-colleague?embedded=1') {
  const pinia = createPinia()
  setActivePinia(pinia)
  const { router } = await import('./index')
  const { usePortalIntegration } = await import('../portal/usePortalIntegration')
  await router.push(path)
  wrapper = mount(defineComponent({ setup() { usePortalIntegration(); return () => null } }), {
    global: { plugins: [pinia, router] },
  })
  await flushPromises()
  return router
}

describe('router initialization request counts', () => {
  it('initializes once, ignores an echo without embedded, and reuses initialization on business switches', async () => {
    const router = await startAt()
    expect(transport.me).toHaveBeenCalledTimes(1)
    expect(transport.spaces).toHaveBeenCalledTimes(1)
    const { PortalAction } = await import('../portal/iframeBridge')
    const { portalMenuCode } = await import('../portal/portalRoutes')
    expect(transport.handlers.has(PortalAction.ROUTE_CHANGE)).toBe(true)
    transport.handlers.get(PortalAction.ROUTE_CHANGE)?.({
      code: portalMenuCode('/expert-colleague'), subPath: '/expert-colleague',
    })
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/expert-colleague?embedded=1')
    for (const path of ['/expert-alumni', '/paper-cooperation', '/industry-chain-event']) {
      await router.push(path + '?embedded=1')
    }
    expect(transport.me).toHaveBeenCalledTimes(1)
    expect(transport.spaces).toHaveBeenCalledTimes(1)
  })

  it('revalidates both identity and spaces after the 15 second navigation window', async () => {
    let now = 100_000
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    const router = await startAt()
    now += 15_000
    await router.push('/expert-alumni?embedded=1')
    expect(transport.me).toHaveBeenCalledTimes(2)
    expect(transport.spaces).toHaveBeenCalledTimes(2)
  })

  it('revalidates each management entry and rejects a revoked developer role immediately', async () => {
    transport.me.mockResolvedValue({ ...member, isAdmin: true })
    const router = await startAt()
    await router.push('/schema')
    expect(router.currentRoute.value.path).toBe('/schema')
    expect(transport.me).toHaveBeenCalledTimes(2)
    transport.me.mockResolvedValue(member)
    await router.push('/configurations')
    expect(router.currentRoute.value.path).toBe('/forbidden')
    expect(transport.me).toHaveBeenCalledTimes(3)
  })

  it('shares a changed-scope request between the selector watcher and a management guard', async () => {
    const router = await startAt()
    const { default: GraphSpaceSelector } = await import('../components/GraphSpaceSelector.vue')
    const selector = mount(GraphSpaceSelector, {
      global: { stubs: { ATooltip: { template: '<slot />' }, ACascader: true } },
    })
    try {
      await flushPromises()
      expect(transport.spaces).toHaveBeenCalledTimes(1)
      transport.me.mockResolvedValue({
        ...member, businessRbacEnabled: true, canDevelop: true, developerBusinessIds: ['a'],
      })
      await router.push('/schema')
      await flushPromises()
      expect(router.currentRoute.value.path).toBe('/schema')
      expect(transport.spaces).toHaveBeenCalledTimes(2)
    } finally {
      selector.unmount()
    }
  })

  it('reinitializes graph spaces for a new identity and discards the previous selection', async () => {
    const router = await startAt()
    transport.me.mockResolvedValue({ ...member, user: { id: '202' }, isAdmin: true })
    transport.spaces.mockResolvedValue({ data: { spaces: ['new-user-space'] } })
    await router.push('/schema')
    const { useGraphSpaceStore } = await import('../stores/graphSpace')
    expect(useGraphSpaceStore().userId).toBe('202')
    expect(useGraphSpaceStore().current).toBe('new-user-space')
  })
})
