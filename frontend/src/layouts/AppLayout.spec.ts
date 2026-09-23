import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import AppLayout from './AppLayout.vue'

const mocks = vi.hoisted(() => ({ authDisabled: false, graphVisualization: false }))
vi.mock('../config', () => ({
  appBase: '/',
  graphSpace: 'dev2',
  get authDisabled() { return mocks.authDisabled },
  get graphVisualizationEnabled() { return mocks.graphVisualization },
}))
vi.mock('../api/auth', () => ({
  getCurrentProfile: vi.fn(), getLoginUrl: vi.fn(), logoutCurrentSession: vi.fn(), refreshCurrentSession: vi.fn(),
}))
vi.mock('../api/graphSearch', () => ({
  listGraphSpaces: vi.fn(async () => ({ data: { spaces: ['dev2'] } })),
}))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconHistory: { template: '<i />' } }))

// 普通用户可见工作台（平台总览）、图谱查询与业务服务组；图谱建设与治理/平台管理仅管理员。
const sharedPaths = [
  '/expert-direct', '/node-indirect', '/two-point-achievement',
  '/expert-colleague', '/expert-alumni', '/paper-cooperation', '/enterprise-relation',
  '/industry-chain-event', '/industry-chain-panorama',
]
const queryPaths = ['/graph-query', '/graph-query/entities']
const managementPaths = [
  '/schema', '/graph-build', '/manual-review', '/configurations',
]
const wrappers: ReturnType<typeof mount>[] = []

beforeEach(() => {
  mocks.authDisabled = false
  vi.stubGlobal('matchMedia', () => ({ matches: false }))
  vi.spyOn(window, 'requestAnimationFrame').mockReturnValue(0)
  Object.defineProperty(document, 'fonts', { configurable: true, value: { ready: Promise.resolve() } })
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
})

async function renderLayout(isAdmin: boolean, path = '/expert-direct', collapsed = false, businessOnly = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.profile = {
    isAdmin,
    businessOnly,
    user: { id: 'viewer', username: 'viewer', nickname: '测试用户', avatar: '' },
  } as AuthProfile
  useAppStore().collapsed = collapsed
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/:pathMatch(.*)*', component: { template: '<div />' } }],
  })
  await router.push(path)
  const wrapper = mount(AppLayout, { global: { plugins: [pinia, router] } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, auth }
}

describe('既有侧边栏按有效管理员身份显隐', () => {
  it.each([false, true])('业务限定账号只保留九大模块，收起=%s', async (collapsed) => {
    const { wrapper } = await renderLayout(true, '/expert-direct', collapsed, true)
    const navigation = wrapper.get('.app-nav')
    for (const path of ['/overview', ...queryPaths, ...managementPaths]) {
      expect(navigation.find(`a[href="${path}"]`).exists()).toBe(false)
    }
    for (const path of sharedPaths) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(true)
    expect(navigation.text()).not.toContain('工作台')
  })

  it('普通用户可见工作台/平台总览与业务服务，管理菜单隐藏', async () => {
    const { wrapper } = await renderLayout(false)
    const navigation = wrapper.get('.app-nav')
    expect(navigation.text()).toContain('工作台')
    expect(navigation.text()).not.toContain('图谱建设与治理')
    expect(navigation.text()).not.toContain('平台管理')
    expect(navigation.text()).toContain('知识图谱构建服务')
    expect(navigation.text()).toContain('科技专家/人才知识推理构建服务')
    expect(navigation.find('a[href="/overview"]').exists()).toBe(true)
    for (const path of [...queryPaths, ...sharedPaths]) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(true)
    for (const path of managementPaths) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(false)
  })

  it('管理员继续看到全部原有分组', async () => {
    const { wrapper } = await renderLayout(true, '/graph-query')
    const navigation = wrapper.get('.app-nav')
    for (const name of ['工作台', '图谱建设与治理', '平台管理', '知识图谱构建服务', '科技专家/人才知识推理构建服务']) {
      expect(navigation.text()).toContain(name)
    }
    for (const path of ['/overview', ...queryPaths, ...managementPaths, ...sharedPaths]) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(true)
  })

  it('侧边栏收起后普通用户不能通过图标或飞出菜单进入管理页', async () => {
    const { wrapper } = await renderLayout(false, '/expert-direct', true)
    const navigation = wrapper.get('.app-nav')
    for (const path of managementPaths) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(false)
    for (const path of ['/overview', ...queryPaths, ...sharedPaths]) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(true)
  })

  it('有效角色刷新为普通用户后现有管理菜单立即隐藏', async () => {
    const { wrapper, auth } = await renderLayout(true, '/graph-query')
    auth.profile!.isAdmin = false
    await nextTick()
    expect(wrapper.find('.app-nav a[href="/schema"]').exists()).toBe(false)
    expect(wrapper.find('.app-nav a[href="/graph-build"]').exists()).toBe(false)
  })

  it('显式免登录开发模式保留原有管理菜单', async () => {
    mocks.authDisabled = true
    const { wrapper } = await renderLayout(false)
    expect(wrapper.find('.app-nav a[href="/schema"]').exists()).toBe(true)
  })

  it('图谱可视化入口默认隐藏，开关开启后出现在图谱查询组', async () => {
    mocks.graphVisualization = false
    const hidden = await renderLayout(true, '/graph-query')
    expect(hidden.wrapper.find('.app-nav a[href="/graph-query/visualization"]').exists()).toBe(false)

    mocks.graphVisualization = true
    const shown = await renderLayout(true, '/graph-query')
    const link = shown.wrapper.find('.app-nav a[href="/graph-query/visualization"]')
    expect(link.exists()).toBe(true)
    expect(link.text()).toContain('图谱可视化')
  })
})
