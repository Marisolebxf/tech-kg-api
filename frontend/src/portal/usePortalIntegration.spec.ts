import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { PortalAction, portalBridge } from './iframeBridge'
import { usePortalIntegration } from './usePortalIntegration'

const state = vi.hoisted(() => ({
  embedded: true,
  handlers: new Map<string, (data: Record<string, unknown>) => void>(),
}))
vi.mock('../stores/auth', () => ({ useAuthStore: () => ({ logout: vi.fn() }) }))
vi.mock('./iframeBridge', async (importOriginal) => {
  const original = await importOriginal<typeof import('./iframeBridge')>()
  return {
    ...original,
    isPortalEmbeddedMode: () => state.embedded,
    portalBridge: {
      get isInIframe() { return state.embedded },
      start: vi.fn(), stop: vi.fn(), send: vi.fn(), ready: vi.fn(),
      on: vi.fn((action: string, handler: (data: Record<string, unknown>) => void) => {
        state.handlers.set(action, handler)
        return () => state.handlers.delete(action)
      }),
    },
  }
})

let wrapper: VueWrapper | undefined
async function setup(initialPath = '/overview?embedded=1') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/overview', component: {}, meta: { title: '平台总览' } },
      { path: '/graph-build', component: {}, meta: { title: '图谱构建' } },
      { path: '/graph-build/jobs/:jobId', component: {}, meta: { title: '任务详情' } },
      { path: '/manual-review', component: {}, meta: { title: '人工审核' } },
      { path: '/login', component: {} },
    ],
  })
  await router.push(initialPath)
  wrapper = mount(defineComponent({
    setup() { usePortalIntegration(); return () => null },
  }), { global: { plugins: [router] } })
  await flushPromises()
  return router
}

beforeEach(() => {
  state.embedded = true
  state.handlers.clear()
  vi.clearAllMocks()
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

describe('portal route integration', () => {
  it('waits for the initial router navigation before announcing readiness', async () => {
    let allowNavigation: () => void = () => undefined
    const pendingGuard = new Promise<void>((resolve) => { allowNavigation = resolve })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/graph-build', component: {}, meta: { title: '图谱构建' } }],
    })
    router.beforeEach(() => pendingGuard)
    const navigation = router.push('/graph-build?embedded=1')
    wrapper = mount(defineComponent({
      setup() { usePortalIntegration(); return () => null },
    }), { global: { plugins: [router] } })
    await flushPromises()
    expect(portalBridge.ready).not.toHaveBeenCalled()
    allowNavigation()
    await navigation
    await flushPromises()
    expect(portalBridge.ready).toHaveBeenCalledTimes(1)
    expect(portalBridge.send).not.toHaveBeenCalledWith(PortalAction.ROUTE_CHANGE, expect.anything())
  })

  it('announces readiness after registering the downlink listener without overwriting the initial deep link', async () => {
    await setup()
    expect(state.handlers.has(PortalAction.ROUTE_CHANGE)).toBe(true)
    expect(portalBridge.ready).toHaveBeenCalledTimes(1)
    expect(vi.mocked(portalBridge.on).mock.invocationCallOrder.at(-1))
      .toBeLessThan(vi.mocked(portalBridge.ready).mock.invocationCallOrder[0]!)
    expect(portalBridge.send).not.toHaveBeenCalledWith(PortalAction.ROUTE_CHANGE, expect.anything())
    expect(portalBridge.send).toHaveBeenCalledWith(PortalAction.LOADING_HIDE)
  })

  it('reports the configured menu code and full child route on internal navigation', async () => {
    const router = await setup()
    await router.push('/graph-build/jobs/job-123?tab=logs')
    await flushPromises()
    expect(portalBridge.send).toHaveBeenCalledWith(PortalAction.ROUTE_CHANGE, {
      code: 'graph_build', subPath: '/graph-build/jobs/job-123?tab=logs',
    })
    await router.push('/manual-review')
    await flushPromises()
    expect(portalBridge.send).toHaveBeenCalledWith(PortalAction.ROUTE_CHANGE, {
      code: 'manual_review', subPath: '/manual-review',
    })
    expect(portalBridge.ready).toHaveBeenCalledTimes(1)
  })

  it('restores a portal deep link without navigation feedback or repeated ready messages', async () => {
    const router = await setup('/graph-build?embedded=1')
    state.handlers.get(PortalAction.ROUTE_CHANGE)?.({
      code: 'graph_build', subPath: '/graph-build/jobs/job-123?tab=logs',
    })
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/graph-build/jobs/job-123?tab=logs')
    expect(portalBridge.send).not.toHaveBeenCalledWith(PortalAction.ROUTE_CHANGE, expect.anything())
    expect(portalBridge.ready).toHaveBeenCalledTimes(1)
    // 后续本地导航仍正常回报，不会被下行导航抑制永久锁住。
    await router.push('/manual-review')
    await flushPromises()
    expect(portalBridge.send).toHaveBeenCalledWith(PortalAction.ROUTE_CHANGE, {
      code: 'manual_review', subPath: '/manual-review',
    })
  })

  it.each([
    { code: 'manual_review', subPath: '/graph-build' },
    { code: 'graph_build', subPath: 'https://other.example/graph-build' },
    { code: 'graph_build', subPath: '//other.example/graph-build' },
    { code: 'graph_build', subPath: '/login' },
    { code: 'unknown', subPath: '/graph-build' },
  ])('ignores invalid or mismatched downlink routes: %j', async (data) => {
    const router = await setup()
    state.handlers.get(PortalAction.ROUTE_CHANGE)?.(data)
    await flushPromises()
    expect(router.currentRoute.value.fullPath).toBe('/overview?embedded=1')
  })

  it('does not communicate with a portal in standalone mode', async () => {
    state.embedded = false
    const router = await setup('/overview')
    await router.push('/graph-build')
    await flushPromises()
    expect(portalBridge.start).not.toHaveBeenCalled()
    expect(portalBridge.ready).not.toHaveBeenCalled()
    expect(portalBridge.send).not.toHaveBeenCalled()
  })
})
