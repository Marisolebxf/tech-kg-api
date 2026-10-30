import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent, h, ref } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import App from './App.vue'

vi.mock('./stores/graphSpace', () => ({ useGraphSpaceStore: () => ({ contextKey: '101|dev' }) }))
vi.mock('./portal/usePortalIntegration', () => ({
  usePortalIntegration: () => ({ isEmbedded: ref(true), portalStatusText: ref('') }),
}))
vi.mock('./portal/iframeBridge', () => ({
  PortalAction: { LOADING_HIDE: 'loading.hide' }, portalBridge: { send: vi.fn() },
}))
vi.mock('./components/kg-toast.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/GraphSpaceSelector.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./components/AppBreadcrumb.vue', () => ({ default: { template: '<div />' } }))
vi.mock('./layouts/AppLayout.vue', () => ({ default: { template: '<div />' } }))

let wrapper: VueWrapper | undefined
beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
  window.__KG_PAGE_LOADING__ = { start: vi.fn(), finish: vi.fn(), fail: vi.fn() }
})
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks(); delete window.__KG_PAGE_LOADING__ })

describe('embedded view recovery', () => {
  it('lets the user retry a failed render without reloading the iframe or changing business', async () => {
    let attempts = 0
    const component = defineComponent({
      setup() {
        if (++attempts === 1) throw new Error('render failed')
        return () => h('div', 'recovered colleague')
      },
    })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/expert-colleague', component }],
    })
    await router.push('/expert-colleague')
    wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('页面渲染异常')
    expect(window.__KG_PAGE_LOADING__!.finish).toHaveBeenCalled()
    await wrapper.get('button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('recovered colleague')
    expect(router.currentRoute.value.path).toBe('/expert-colleague')
    expect(attempts).toBe(2)
  })

  it('clears a previous render error when another business is selected', async () => {
    const router = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/expert-colleague', component: defineComponent({ setup() { throw new Error('render failed') } }) },
        { path: '/expert-alumni', component: { template: '<div>alumni page</div>' } },
      ],
    })
    await router.push('/expert-colleague')
    wrapper = mount(App, { global: { plugins: [router] } })
    await flushPromises()
    expect(wrapper.text()).toContain('页面渲染异常')
    await router.push('/expert-alumni')
    await flushPromises()
    expect(wrapper.text()).toContain('alumni page')
    expect(wrapper.text()).not.toContain('页面渲染异常')
  })
})
