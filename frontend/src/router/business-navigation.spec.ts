import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  authDisabled: false,
  graphVisualization: false,
  embedded: false,
  sessionExpired: false,
  skipSilentLogin: false,
  send: vi.fn(),
  loadCurrentUser: vi.fn(),
}))

vi.mock('../config', () => ({
  appBase: '/',
  apiBase: '/',
  get authDisabled() { return mocks.authDisabled },
  get graphVisualizationEnabled() { return mocks.graphVisualization },
}))
vi.mock('../stores/auth', () => ({ useAuthStore: () => ({ loadCurrentUser: mocks.loadCurrentUser, get sessionExpired() { return mocks.sessionExpired }, get skipSilentLogin() { return mocks.skipSilentLogin } }) }))
vi.mock('../portal/iframeBridge', () => ({
  isPortalEmbeddedMode: () => mocks.embedded,
  PortalAction: { SESSION_EXPIRED: 'session-expired' },
  portalBridge: { get isInIframe() { return mocks.embedded }, send: mocks.send },
}))
vi.mock('../views/business-service/components/BusinessServiceAlgorithmPanel.vue', () => ({ default: { template: '<div>business</div>' } }))
vi.mock('../views/business-service/components/BusinessServiceContractPanel.vue', () => ({ default: { template: '<div />' } }))
vi.mock('../stores/graphSpace', () => ({ useGraphSpaceStore: () => ({ bindUser: vi.fn(), ensureLoaded: vi.fn() }) }))
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


import { afterEach } from 'vitest'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { RouterView } from 'vue-router'

const businessPaths = [
  '/expert-direct', '/node-indirect', '/two-point-achievement', '/expert-colleague',
  '/expert-alumni', '/paper-cooperation', '/enterprise-relation',
  '/industry-chain-event', '/industry-chain-panorama',
]
let wrapper: VueWrapper | undefined

async function startAt(path: string, type: string = 'reload') {
  vi.resetModules()
  vi.spyOn(performance, 'getEntriesByType').mockReturnValue([{ type } as PerformanceNavigationTiming])
  mocks.loadCurrentUser.mockResolvedValue({ isAdmin: true, permissions: ['*'] })
  const { router } = await import('./index')
  await router.push(path)
  wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
  return router
}

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  vi.restoreAllMocks()
})

describe('业务页刷新与站内导航', () => {
  it.each(['/overview', '/schema'])('刷新 %s 后进入每个业务均保留点击目标', async (platform) => {
    const router = await startAt(platform)
    for (const target of businessPaths) {
      await router.push(platform)
      await flushPromises()
      await router.push(target)
      await flushPromises()
      expect(router.currentRoute.value.path).toBe(target)
    }
  })

  it.each(businessPaths)('刷新业务 %s 仅在首次导航回到第一个业务', async (path) => {
    const router = await startAt(path + '?embedded=1#entry')
    expect(router.currentRoute.value.path).toBe('/expert-direct')
    expect(router.currentRoute.value.query.embedded).toBe('1')
    expect(router.currentRoute.value.hash).toBe('#entry')
    for (const target of businessPaths) {
      await router.push(target)
      await flushPromises()
      expect(router.currentRoute.value.path).toBe(target)
    }
  })

  it('普通深链进入业务保持原目标', async () => {
    const router = await startAt('/expert-alumni', 'navigate')
    expect(router.currentRoute.value.path).toBe('/expert-alumni')
  })

  it('浏览器历史恢复业务保持原目标', async () => {
    const router = await startAt('/paper-cooperation', 'back_forward')
    expect(router.currentRoute.value.path).toBe('/paper-cooperation')
  })
})
