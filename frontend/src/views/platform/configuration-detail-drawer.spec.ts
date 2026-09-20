import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { describe, expect, it, vi } from 'vitest'

import ConfigurationManagementView from './ConfigurationManagementView.vue'

// 管理抽屉编辑隔离（第一轮复测捉虫）：抽屉直接绑定列表项共享引用时，
// 未保存输入（含非法值）实时串进页面卡片、关抽屉后残留脏值到刷新。
// 打开抽屉应改为编辑副本；保存按钮在非法输入时置灰。
const { state } = vi.hoisted(() => {
  const llmItem = {
    id: 'LLM-E2E',
    name: '原名称',
    description: '原说明',
    baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
    model: 'glm-4.7-flash',
    owner: 'admin',
    isDefault: true,
    status: '正常',
    hasApiKey: true,
    apiKeyMasked: 'ab****cd',
    createdAt: '2026-09-20 10:00:00',
    updatedAt: '2026-09-20 10:00:00',
  }
  return { llmItem, state: { current: { ...llmItem } } }
})

// 保存成功后列表回填读 listLlmConfigs：用可变当前值模拟「服务端已更新」
vi.mock('../../api/llmConfig', () => ({
  listLlmConfigs: vi.fn(async () => [state.current]),
  createLlmConfig: vi.fn(),
  updateLlmConfig: vi.fn(async (_id: string, input: Record<string, unknown>) => {
    state.current = { ...state.current, ...input, name: String(input.name ?? state.current.name) }
    return state.current
  }),
  deleteLlmConfig: vi.fn(),
  setDefaultLlmConfig: vi.fn(),
  testLlmConfig: vi.fn(),
  verifyLlmConfig: vi.fn(),
  currentUserId: () => 'user-e2e',
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
  listGraphSpaceItems: vi.fn(async () => []),
  createGraphSpace: vi.fn(),
  bindGraphSpace: vi.fn(),
  unbindGraphSpace: vi.fn(),
}))
vi.mock('../../api/currentUser', () => ({ currentUserIsAdmin: () => true }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconSearch: { template: '<i />' } }))

function mountView() {
  return mount(ConfigurationManagementView, {
    global: {
      stubs: {
        teleport: true,
        'a-select': true, 'a-option': true, 'a-input': true,
        'a-form': { template: '<form><slot /></form>' },
        'a-form-item': { template: '<label><slot /></label>' },
        'a-textarea': true, 'a-checkbox': true,
      },
    },
  })
}

async function openDrawer(wrapper: ReturnType<typeof mountView>) {
  await wrapper.find('tbody tr [class~="row-actions"] button').trigger('click')
  await flushPromises()
}

describe('配置管理 · 管理抽屉编辑隔离', () => {
  it('抽屉输入（含非法值）不实时串进列表卡片，关闭后卡片保持服务端值', async () => {
    setActivePinia(createPinia())
    const wrapper = mountView()
    await flushPromises()

    const cardName = () => wrapper.find('tbody tr .config-name strong').text()
    expect(cardName()).toContain('原名称')

    await openDrawer(wrapper)
    const nameInput = wrapper.find('.detail-drawer input[aria-label="name"]')
    // 断言前现查（重渲染后旧 wrapper 可能指向已分离节点，disabled 状态读到脏值）
    const saveDisabled = () => wrapper.findAll('.detail-drawer footer button')
      .find((b) => b.text().includes('保存修改'))?.attributes('disabled')

    // 非法输入：卡片不被污染 + 保存按钮置灰
    await nameInput.setValue('非法<script>alert(1)</script>名称')
    expect(cardName()).toContain('原名称')
    expect(saveDisabled()).toBeDefined()

    // 合法输入未保存：卡片仍保持服务端值、按钮解禁
    await nameInput.setValue('合法新名称XYZ')
    expect(cardName()).toContain('原名称')
    expect(saveDisabled()).toBeUndefined()

    // 关闭抽屉不保存：卡片不残留脏值
    await wrapper.find('.detail-drawer > header button').trigger('click')
    expect(wrapper.find('.detail-drawer').exists()).toBe(false)
    expect(cardName()).toContain('原名称')

    wrapper.unmount()
  })

  it('保存成功后列表由服务端数据回填', async () => {
    setActivePinia(createPinia())
    const { updateLlmConfig } = await import('../../api/llmConfig')
    // 服务端归一化改名，证明卡片刷新来自回填（loadByCategory），而非草稿串扰
    vi.mocked(updateLlmConfig).mockImplementation(async (_id: string, input: Record<string, unknown>) => {
      state.current = { ...state.current, ...input, name: '服务端新名称' }
      return state.current
    })
    const wrapper = mountView()
    await flushPromises()

    await openDrawer(wrapper)
    const cardName = () => wrapper.find('tbody tr .config-name strong').text()
    await wrapper.find('.detail-drawer input[aria-label="name"]').setValue('草稿新名称')
    expect(cardName()).toContain('原名称')
    const saveBtn = wrapper.findAll('.detail-drawer footer button').find((b) => b.text().includes('保存修改'))
    await saveBtn?.trigger('click')
    await flushPromises()

    expect(updateLlmConfig).toHaveBeenCalledWith('LLM-E2E', expect.objectContaining({ name: '草稿新名称' }), 'user-e2e')
    expect(cardName()).toContain('服务端新名称')
    wrapper.unmount()
  })
})
