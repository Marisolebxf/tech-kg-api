import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../api/auth'
import { useAuthStore } from '../stores/auth'
import { useAppStore } from '../stores/app'
import { useGraphSpaceStore } from '../stores/graphSpace'
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
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconHistory: { template: '<i />' }, IconHome: { template: '<i />' } }))

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
    routes: [
      // 装置用兜底路由承接所有路径；meta.title 让面包屑渲染真实总览标题
      { path: '/:pathMatch(.*)*', component: { template: '<div />' }, meta: { title: '平台总览' } },
    ],
  })
  await router.push(path)
  const wrapper = mount(AppLayout, { global: { plugins: [pinia, router] } })
  wrappers.push(wrapper)
  await flushPromises()
  return { wrapper, auth }
}

describe('既有侧边栏按有效管理员身份显隐', () => {
  it('业务开发维护保留管理菜单但不会显示管理员身份，业务页不渲染图空间选择器', async () => {
    const { wrapper, auth } = await renderLayout(false)
    auth.profile = { ...auth.profile!, businessRbacEnabled: true, platformRole: 'developer', canDevelop: true }
    await nextTick()
    for (const path of managementPaths) expect(wrapper.find(`.app-nav a[href="${path}"]`).exists()).toBe(true)
    expect(auth.isAdmin).toBe(false)
    expect(wrapper.get('.app-top-actions__user').text()).toContain('开发维护')
    expect(wrapper.get('.app-top-actions__user').text()).not.toContain('管理员')
    // 图空间选择器仅平台总览页（面包屑行）渲染，业务页与顶栏均不出现
    expect(wrapper.find('.app-space-select').exists()).toBe(false)
  })
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

  it.each([
    ['/graph-build/jobs/job-1', '/graph-build', '/manual-review'],
    ['/manual-review/task/instance-1', '/manual-review', '/graph-build'],
  ])('详情页 %s 保持父级导航 %s 的选中状态', async (path, activePath, inactivePath) => {
    const { wrapper } = await renderLayout(true, path)
    const navigation = wrapper.get('.app-nav')

    expect(navigation.get(`a[href="${activePath}"]`).classes()).toContain('app-nav__item--active')
    expect(navigation.get(`a[href="${inactivePath}"]`).classes()).not.toContain('app-nav__item--active')
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

  it('前端误关闭认证时不能把普通用户提升为管理员', async () => {
    mocks.authDisabled = true
    const { wrapper } = await renderLayout(false)
    for (const path of managementPaths) expect(wrapper.find(`.app-nav a[href="${path}"]`).exists()).toBe(false)
    expect(wrapper.get('.app-top-actions__user').text()).toContain('普通用户')
  })

  it('前端误关闭认证时开发维护仍显示开发维护', async () => {
    mocks.authDisabled = true
    const { wrapper, auth } = await renderLayout(false)
    auth.profile = { ...auth.profile!, businessRbacEnabled: true, platformRole: 'developer', canDevelop: true }
    await nextTick()
    expect(wrapper.get('.app-top-actions__user').text()).toContain('开发维护')
    expect(wrapper.get('.app-top-actions__user').text()).not.toContain('管理员')
    expect(wrapper.find('.app-nav a[href="/schema"]').exists()).toBe(true)
    auth.invalidate()
    await nextTick()
    expect(wrapper.find('.app-nav a[href="/schema"]').exists()).toBe(false)
  })

  it('非总览页不渲染图空间选择器，空间上下文由路由守卫加载', async () => {
    const { wrapper } = await renderLayout(true, '/graph-query')
    expect(wrapper.find('.app-space-select').exists()).toBe(false)
    // 空间列表/当前值不再依赖顶栏选择器挂载：路由守卫在身份就绪后 ensureLoaded
    expect(useGraphSpaceStore().initialized).toBe(false)
  })

  it('平台总览页在面包屑行右侧渲染全局图空间选择器并加载空间列表', async () => {
    const { wrapper } = await renderLayout(true, '/overview')
    const selector = wrapper.get('.app-breadcrumb .app-space-select')
    expect(selector.text()).toContain('图空间')
    // 选择器挂载即拉列表并归一当前值（构建默认 dev2）
    const store = useGraphSpaceStore()
    await flushPromises()
    expect(store.initialized).toBe(true)
    expect(store.current).toBe('dev2')
    // 面包屑标题与选择器同行：选择器是面包屑行最后一个子元素
    expect(wrapper.get('.app-breadcrumb').text()).toContain('平台总览')
    const actions = wrapper.get('.app-breadcrumb__actions')
    const docs = actions.get('a.app-docs-link')
    expect(docs.attributes('href')).toBe('/docs/')
    expect(docs.attributes('target')).toBe('_blank')
    expect(docs.element.nextElementSibling).toBe(selector.element)
    expect(wrapper.find('.app-top-actions .app-docs-link').exists()).toBe(false)
  })

  it('账号菜单只保留退出入口并正常退出，消息通知组件不再渲染', async () => {
    const { wrapper, auth } = await renderLayout(true, '/overview')
    const logout = vi.spyOn(auth, 'logout').mockResolvedValue()
    await wrapper.get('.app-top-actions__user').trigger('click')
    const buttons = wrapper.findAll('.app-user-menu nav button')
    expect(buttons.map((button) => button.text())).toEqual(['退出登录'])
    expect(wrapper.find('.app-alert-entry').exists()).toBe(false)
    expect(wrapper.find('.alert-drawer').exists()).toBe(false)
    await buttons[0]!.trigger('click')
    await flushPromises()
    expect(logout).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.app-user-menu').exists()).toBe(false)
  })

  it('文档入口只在总览显示，其他管理页面和普通用户隐藏', async () => {
    const admin = await renderLayout(true, '/manual-review')
    expect(admin.wrapper.find('.app-breadcrumb .app-docs-link').exists()).toBe(false)
    const viewer = await renderLayout(false, '/overview')
    expect(viewer.wrapper.find('.app-docs-link').exists()).toBe(false)
    expect(viewer.wrapper.find('.app-space-select').exists()).toBe(true)
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

describe('面包屑统一（Arco 规范：/ 分隔、除当前页外每级可点）', () => {
  it('管理页展开分组层级，除当前页外每级都是链接（分组默认进首个子页）', async () => {
    const { wrapper } = await renderLayout(true, '/schema')
    const breadcrumb = wrapper.get('.app-breadcrumb')
    // 行首不再渲染首页图标入口（小房子图标已按需求去掉）
    expect(breadcrumb.find('a.app-breadcrumb__home').exists()).toBe(false)
    expect(breadcrumb.findAll('.app-breadcrumb__separator').map((node) => node.text())).toEqual(['/'])
    expect(breadcrumb.findAll('.app-breadcrumb__link').map((node) => [node.text(), node.attributes('href')]))
      .toEqual([['图谱建设与治理', '/schema']])
    const current = breadcrumb.get('.app-breadcrumb__current')
    expect(current.text()).toBe('Schema 管理')
    expect(current.attributes('aria-current')).toBe('page')
  })

  it('图谱查询与业务服务页展开完整层级（分组 / 子组 / 当前页）', async () => {
    const query = await renderLayout(true, '/graph-query/entities')
    const queryNav = query.wrapper.get('.app-breadcrumb')
    expect(queryNav.findAll('.app-breadcrumb__link').map((node) => [node.text(), node.attributes('href')]))
      .toEqual([['知识图谱构建服务', '/graph-query'], ['图谱查询', '/graph-query']])
    expect(queryNav.get('.app-breadcrumb__current').text()).toBe('实体列表')

    const service = await renderLayout(true, '/expert-direct')
    const serviceNav = service.wrapper.get('.app-breadcrumb')
    expect(serviceNav.findAll('.app-breadcrumb__link').map((node) => [node.text(), node.attributes('href')]))
      .toEqual([['知识图谱构建服务', '/graph-query'], ['科技专家/人才知识推理构建服务', '/business-service']])
    expect(serviceNav.get('.app-breadcrumb__current').text()).toBe('科技专家/人才直接关系')
  })

  it('详情页挂在所属功能页之下（替代页内返回链接）', async () => {
    const job = await renderLayout(true, '/graph-build/jobs/job-1')
    const jobNav = job.wrapper.get('.app-breadcrumb')
    expect(jobNav.findAll('.app-breadcrumb__link').map((node) => [node.text(), node.attributes('href')]))
      .toEqual([['图谱建设与治理', '/schema'], ['图谱构建', '/graph-build']])
    expect(jobNav.get('.app-breadcrumb__current').text()).toBe('任务详情')

    const review = await renderLayout(true, '/manual-review/task/case-1')
    const reviewNav = review.wrapper.get('.app-breadcrumb')
    expect(reviewNav.findAll('.app-breadcrumb__link').map((node) => [node.text(), node.attributes('href')]))
      .toEqual([['图谱建设与治理', '/schema'], ['人工审核', '/manual-review']])
    expect(reviewNav.get('.app-breadcrumb__current').text()).toBe('人工审核详情')
  })

  it('行首「<」返回按钮：无应用内历史时回最近上级，首页直达时不显示', async () => {
    const job = await renderLayout(true, '/graph-build/jobs/job-1')
    const back = job.wrapper.get('button.app-breadcrumb__back')
    expect(back.attributes('title')).toBe('返回图谱构建')
    await back.trigger('click')
    await flushPromises()
    expect(job.wrapper.get('.app-breadcrumb__current').text()).toBe('图谱构建')

    // 业务服务页：组入口 /business-service 重定向回首服务（等价自页），兜底再上一级
    const service = await renderLayout(true, '/expert-direct')
    expect(service.wrapper.get('button.app-breadcrumb__back').attributes('title')).toBe('返回知识图谱构建服务')

    // 平台总览直达（无上级、无应用内历史）：不渲染返回按钮
    const home = await renderLayout(true, '/overview')
    expect(home.wrapper.find('button.app-breadcrumb__back').exists()).toBe(false)
  })
})
