import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import ConfigurationManagementView from './ConfigurationManagementView.vue'
import { useAuthStore } from '../../stores/auth'
import type { AuthProfile } from '../../api/auth'

// platform_developer（开发维护账号）：与管理员同权，但图空间由管理员写
// kg_user_graph_space 分配——配置页不出现 新建/绑定/解绑 自助入口，
// 已绑定空间行以「由管理员分配」提示替代操作。
vi.mock('../../api/llmConfig', () => ({
  listLlmConfigs: vi.fn(async () => []),
  createLlmConfig: vi.fn(),
  updateLlmConfig: vi.fn(),
  deleteLlmConfig: vi.fn(),
  setDefaultLlmConfig: vi.fn(),
  testLlmConfig: vi.fn(),
  verifyLlmConfig: vi.fn(),
  currentUserId: () => 'dev-1',
}))
vi.mock('../../api/embeddingConfig', () => ({
  listEmbeddingConfigs: vi.fn(async () => []),
  createEmbeddingConfig: vi.fn(),
  updateEmbeddingConfig: vi.fn(),
  deleteEmbeddingConfig: vi.fn(),
  setDefaultEmbeddingConfig: vi.fn(),
  testEmbeddingConfig: vi.fn(),
  verifyEmbeddingConfig: vi.fn(),
}))
vi.mock('../../api/mysqlDatasource', () => ({
  listMysqlDatasources: vi.fn(async () => []),
  createMysqlDatasource: vi.fn(),
  updateMysqlDatasource: vi.fn(),
  deleteMysqlDatasource: vi.fn(),
  setDefaultMysqlDatasource: vi.fn(),
  testMysqlDatasource: vi.fn(),
}))
vi.mock('../../api/graphSpace', () => ({
  // 开发者的空间列表已由后端收敛为 默认+本人绑定
  listGraphSpaceItems: vi.fn(async () => [
    { name: 'dev', bound: false, mine: false },
    { name: 'gaoxing_test', bound: true, mine: true },
  ]),
  createGraphSpace: vi.fn(),
  bindGraphSpace: vi.fn(),
  unbindGraphSpace: vi.fn(),
}))
vi.mock('../../api/currentUser', () => ({ currentUserIsAdmin: () => true }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconSearch: { template: '<i />' } }))

function developerProfile(overrides: Record<string, unknown> = {}): AuthProfile {
  return {
    isAdmin: true,
    isDeveloper: true,
    ...overrides,
  } as unknown as AuthProfile
}

function mountView() {
  return mount(ConfigurationManagementView, {
    global: {
      stubs: {
        teleport: true,
        GraphSpaceSelector: true,
        'a-select': true, 'a-option': true, 'a-input': true,
        'a-form': { template: '<form><slot /></form>' },
        'a-form-item': { template: '<label><slot /></label>' },
        'a-textarea': true, 'a-checkbox': true,
      },
    },
  })
}

async function openSpaceCategory(wrapper: ReturnType<typeof mountView>) {
  const spaceNav = wrapper.findAll('.category-nav > button').find((b) => b.text().includes('图数据空间'))
  await spaceNav?.trigger('click')
  await flushPromises()
}

describe('配置管理 · 开发维护账号图空间由管理员分配', () => {
  it('隐藏 新建/绑定/解绑 自助入口，绑定行提示「由管理员分配」', async () => {
    setActivePinia(createPinia())
    useAuthStore().profile = developerProfile()
    const wrapper = mountView()
    await flushPromises()
    await openSpaceCategory(wrapper)

    // 自助入口全部不渲染
    expect(wrapper.findAll('button').some((b) => b.text().includes('新建图数据空间'))).toBe(false)
    expect(wrapper.findAll('button').some((b) => b.text() === '绑定')).toBe(false)
    expect(wrapper.findAll('button').some((b) => b.text().includes('解除绑定'))).toBe(false)

    // 已绑定空间行：操作列改为提示文案 + 页脚说明
    const rows = wrapper.findAll('.space-table tbody tr')
    expect(rows.some((r) => r.text().includes('gaoxing_test'))).toBe(true)
    expect(wrapper.text()).toContain('由管理员分配')
    expect(wrapper.text()).toContain('开发维护账号的图空间由管理员分配，如需新增请联系管理员')
    wrapper.unmount()
  })

  it('纯管理员仍保留全部自助入口（回归对照）', async () => {
    setActivePinia(createPinia())
    useAuthStore().profile = developerProfile({ isDeveloper: false })
    const wrapper = mountView()
    await flushPromises()
    await openSpaceCategory(wrapper)

    expect(wrapper.findAll('button').some((b) => b.text().includes('新建图数据空间'))).toBe(true)
    expect(wrapper.findAll('button').some((b) => b.text().includes('解除绑定'))).toBe(true)
    expect(wrapper.text()).not.toContain('开发维护账号的图空间由管理员分配')
    wrapper.unmount()
  })
})
