import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import ConfigurationManagementView from '../ConfigurationManagementView.vue'
import { useAuthStore } from '../../../stores/auth'
import type { AuthProfile } from '../../../api/auth'

vi.mock('../../../api/llmConfig', () => ({
  currentUserId: () => 'u-test',
  listLlmConfigs: async () => [],
  createLlmConfig: vi.fn(),
  deleteLlmConfig: vi.fn(),
  updateLlmConfig: vi.fn(),
  setDefaultLlmConfig: vi.fn(),
  testLlmConfig: vi.fn(),
  verifyLlmConfig: vi.fn(),
}))
vi.mock('../../../api/mysqlDatasource', () => ({
  listMysqlDatasources: async () => [],
  createMysqlDatasource: vi.fn(),
  deleteMysqlDatasource: vi.fn(),
  updateMysqlDatasource: vi.fn(),
  setDefaultMysqlDatasource: vi.fn(),
  testMysqlDatasource: vi.fn(),
}))
vi.mock('../../../api/embeddingConfig', () => ({
  listEmbeddingConfigs: async () => [],
  createEmbeddingConfig: vi.fn(),
  deleteEmbeddingConfig: vi.fn(),
  updateEmbeddingConfig: vi.fn(),
  setDefaultEmbeddingConfig: vi.fn(),
  testEmbeddingConfig: vi.fn(),
  verifyEmbeddingConfig: vi.fn(),
}))
vi.mock('../../../api/graphSpace', () => ({
  // 一个已绑定 + 一个可绑定：让「绑定」按钮渲染，验证选择器落在它右边
  listGraphSpaceItems: async () => [
    { name: 'dev2', mine: true },
    { name: 'gaoxing_test', mine: false },
  ],
  bindGraphSpace: vi.fn(),
  createGraphSpace: vi.fn(),
  unbindGraphSpace: vi.fn(),
}))
vi.mock('../../../api/currentUser', () => ({ currentUserIsAdmin: () => true }))
// 业务 RBAC 分支：图数据空间页整体替换为 BusinessAccessManagement（kgetl PR #357）
vi.mock('../../../api/businessAccess', () => ({
  getBusinessAccessState: async () => ({ businesses: [], members: [], spaces: [], requests: [], currentBusinessId: '' }),
  saveBusiness: vi.fn(),
  saveBusinessMember: vi.fn(),
  saveBusinessSpace: vi.fn(),
  requestBusinessSpace: vi.fn(),
  decideBusinessSpace: vi.fn(),
  retryBusinessSpace: vi.fn(),
}))

const storeMock = vi.hoisted(() => ({
  ensureLoaded: vi.fn(),
  setCurrent: vi.fn(),
  current: 'dev2',
  spaces: ['dev2', 'gaoxing_test'],
}))
vi.mock('../../../stores/graphSpace', () => ({ useGraphSpaceStore: () => storeMock }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

describe('配置管理 · 图数据空间：图空间选择器落位', () => {
  it('图数据空间分类在「绑定」右侧渲染全局图空间选择器并懒加载空间列表', async () => {
    const wrapper = mount(ConfigurationManagementView, {
      global: {
        plugins: [createPinia()],
        stubs: {
          'a-select': { template: '<select><slot /></select>' },
          'a-option': { template: '<option><slot /></option>' },
          'a-input': { props: ['modelValue'], template: '<input :value="modelValue" />' },
        },
      },
    })
    await flushPromises()
    // 默认分类（语言模型）不渲染 bind-nav/选择器
    expect(wrapper.find('.bind-nav').exists()).toBe(false)

    await wrapper.findAll('.category-nav button').find(b => b.text().includes('图数据空间'))!.trigger('click')
    await flushPromises()

    const bindNav = wrapper.get('.bind-nav')
    const selector = bindNav.get('.app-space-select')
    expect(selector.text()).toContain('图空间')
    // 落位契约：bind-nav 的最后一个子元素（「绑定」按钮右边）
    const bindButton = bindNav.findAll('button').find(b => b.text() === '绑定')
    expect(bindButton!.exists()).toBe(true)
    expect(bindNav.element.lastElementChild?.classList.contains('app-space-select')).toBe(true)
    // 选择器挂载即懒加载全局空间列表（顶栏撤下后这里是唯一加载入口）
    expect(storeMock.ensureLoaded).toHaveBeenCalled()
    wrapper.unmount()
  })

  it('业务 RBAC 开启时页面换成业务与图空间管理，选择器挂在管理面板头部', async () => {
    setActivePinia(createPinia())
    useAuthStore().profile = { businessRbacEnabled: true, isAdmin: false } as AuthProfile
    const wrapper = mount(ConfigurationManagementView, {
      global: {
        stubs: {
          'a-select': { template: '<select><slot /></select>' },
          'a-option': { template: '<option><slot /></option>' },
          'a-input': { props: ['modelValue'], template: '<input :value="modelValue" />' },
        },
      },
    })
    await flushPromises()
    expect(wrapper.find('.bind-nav').exists()).toBe(false)

    // RBAC 下分类名变为「业务与图空间」
    await wrapper.findAll('.category-nav button').find(b => b.text().includes('业务与图空间'))!.trigger('click')
    await flushPromises()

    // 整页替换为业务管理面板，选择器落在面板头部（顶栏撤下后 RBAC 模式的切换入口）
    const panel = wrapper.get('.business-access')
    const headerSelector = panel.get('header .app-space-select')
    expect(headerSelector.text()).toContain('图空间')
    wrapper.unmount()
  })
})
