import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import AppLayout from './AppLayout.vue'

const mocks = vi.hoisted(() => ({ authDisabled: false }))
vi.mock('../config', () => ({ appBase: '/', get authDisabled() { return mocks.authDisabled } }))
vi.mock('../api/auth', () => ({
  getCurrentProfile: vi.fn(), getLoginUrl: vi.fn(), logoutCurrentSession: vi.fn(), refreshCurrentSession: vi.fn(),
}))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconHistory: { template: '<i />' }, IconSwap: { template: '<i />' } }))

// 普通用户侧栏按产品决策收紧：仅保留业务服务组，图谱查询并入管理端。
const sharedPaths = [
  '/expert-direct', '/node-indirect', '/two-point-achievement',
  '/expert-colleague', '/expert-alumni', '/paper-cooperation', '/enterprise-relation',
  '/industry-chain-event', '/industry-chain-panorama',
]
const managementPaths = [
  '/overview', '/schema', '/graph-build', '/manual-review', '/configurations',
  '/graph-query', '/graph-query/entities',
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

async function renderLayout(isAdmin: boolean, path = '/expert-direct', collapsed = false) {
  const pinia = createPinia()
  setActivePinia(pinia)
  const auth = useAuthStore()
  auth.profile = {
    isAdmin,
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
  it('普通用户只见业务服务，展开时所有业务子菜单保留', async () => {
    const { wrapper } = await renderLayout(false)
    const navigation = wrapper.get('.app-nav')
    expect(navigation.text()).not.toContain('工作台')
    expect(navigation.text()).not.toContain('图谱建设与治理')
    expect(navigation.text()).not.toContain('平台管理')
    expect(navigation.text()).not.toContain('查询与服务')
    expect(navigation.text()).toContain('科技专家/人才知识推理构建服务')
    for (const path of sharedPaths) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(true)
    for (const path of managementPaths) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(false)
    await wrapper.get('.app-top-actions__user').trigger('click')
    expect(wrapper.find('.portal-switch').exists()).toBe(false)
  })

  it('管理员继续看到全部原有分组及管理端入口', async () => {
    const { wrapper } = await renderLayout(true, '/graph-query')
    const navigation = wrapper.get('.app-nav')
    for (const name of ['工作台', '图谱建设与治理', '平台管理', '查询与服务', '科技专家/人才知识推理构建服务']) {
      expect(navigation.text()).toContain(name)
    }
    for (const path of [...managementPaths, ...sharedPaths]) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(true)
    await wrapper.get('.app-top-actions__user').trigger('click')
    expect(wrapper.get('.portal-switch').text()).toBe('进入管理端')
  })

  it('侧边栏收起后普通用户不能通过图标或飞出菜单进入管理页', async () => {
    const { wrapper } = await renderLayout(false, '/expert-direct', true)
    const navigation = wrapper.get('.app-nav')
    for (const path of managementPaths) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(false)
    for (const path of sharedPaths) expect(navigation.find(`a[href="${path}"]`).exists()).toBe(true)
  })

  it('有效角色刷新为普通用户后现有管理菜单立即隐藏', async () => {
    const { wrapper, auth } = await renderLayout(true, '/graph-query')
    auth.profile!.isAdmin = false
    await nextTick()
    expect(wrapper.find('.app-nav a[href="/schema"]').exists()).toBe(false)
    expect(wrapper.find('.app-nav a[href="/graph-query"]').exists()).toBe(false)
  })

  it('管理端侧栏仅对管理员保留原有成员管理等入口', async () => {
    const { wrapper, auth } = await renderLayout(true, '/admin/members')
    expect(wrapper.find('.app-nav a[href="/admin/members"]').exists()).toBe(true)
    auth.profile!.isAdmin = false
    await nextTick()
    expect(wrapper.find('.app-nav a[href="/admin/members"]').exists()).toBe(false)
  })

  it('显式免登录开发模式保留原有管理菜单', async () => {
    mocks.authDisabled = true
    const { wrapper } = await renderLayout(false)
    expect(wrapper.find('.app-nav a[href="/schema"]').exists()).toBe(true)
  })
})
