import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { Textarea } from '@arco-design/web-vue'
import { describe, expect, it, vi } from 'vitest'

import ConfigurationManagementView from './ConfigurationManagementView.vue'
import ListPagination from '../../components/list-pagination.vue'

const AInputStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />',
})

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

function mountView(realTextarea = false) {
  return mount(ConfigurationManagementView, {
    global: {
      stubs: {
        teleport: true,
        'a-select': true, 'a-option': true, 'a-input': AInputStub,
        'a-form': { template: '<form><slot /></form>' },
        'a-form-item': { template: '<label><slot /></label>' },
        'a-textarea': realTextarea ? Textarea : true, 'a-checkbox': true,
      },
    },
  })
}

async function openDrawer(wrapper: ReturnType<typeof mountView>) {
  await wrapper.find('tbody tr [class~="row-actions"] button').trigger('click')
  await flushPromises()
}

describe('配置管理 · 管理抽屉编辑隔离', () => {
  it('仅管理按钮打开详情；标识独立成列，抽屉底部不再提供启停与删除', async () => {
    setActivePinia(createPinia())
    const wrapper = mountView()
    await flushPromises()
    const row = wrapper.get('.config-table-wrap tbody tr')
    expect(row.get('.config-id-col').text()).toBe('LLM-E2E')
    expect(row.get('.config-name').text()).not.toContain('LLM-E2E')
    await row.get('.config-name').trigger('click')
    expect(wrapper.find('.detail-drawer').exists()).toBe(false)
    await openDrawer(wrapper)
    const footer = wrapper.get('.detail-drawer footer')
    expect(footer.text()).toContain('保存修改')
    expect(footer.text()).not.toContain('停用配置')
    expect(footer.text()).not.toContain('启用配置')
    expect(footer.text()).not.toContain('删除')
    wrapper.unmount()
  })

  it('输入关键字后点击查询才筛选，分页只显示总条数且页大小在末尾', async () => {
    setActivePinia(createPinia())
    const wrapper = mountView()
    await flushPromises()
    const search = wrapper.get('.config-search-input')
    await search.setValue('没有匹配的配置')
    expect(wrapper.find('.config-table-wrap tbody tr .config-id-col').exists()).toBe(true)
    await wrapper.get('.config-search-form').trigger('submit')
    expect(wrapper.find('.config-table-wrap tbody tr .config-id-col').exists()).toBe(false)
    await search.setValue('')
    await wrapper.get('.config-search-form').trigger('submit')
    expect(wrapper.find('.config-table-wrap tbody tr .config-id-col').exists()).toBe(true)
    expect(wrapper.get('.config-page-summary').text()).toBe('共 1 条')
    expect(wrapper.findComponent(ListPagination).props()).toMatchObject({ showJumper: false, sizeAtEnd: true })
    wrapper.unmount()
  })

  it('操作列阴影只在右侧尚有内容时出现', async () => {
    setActivePinia(createPinia())
    const wrapper = mountView()
    await flushPromises()
    const scroll = wrapper.get('.config-table-wrap')
    const element = scroll.element as HTMLElement
    Object.defineProperties(element, {
      scrollWidth: { configurable: true, value: 1400 },
      clientWidth: { configurable: true, value: 800 },
      scrollLeft: { configurable: true, writable: true, value: 0 },
    })
    await scroll.trigger('scroll')
    expect(scroll.classes()).toContain('has-scroll-right')
    element.scrollLeft = 600
    await scroll.trigger('scroll')
    expect(scroll.classes()).not.toContain('has-scroll-right')
    // Sticky action column can cover no data even if the scroll container
    // still reports a few pixels of remaining horizontal scroll.
    element.scrollLeft = 590
    const lastData = wrapper.get('.config-table-wrap thead .config-time-col').element as HTMLElement
    const action = wrapper.get('.config-table-wrap thead .config-action-col').element as HTMLElement
    const dataRect = vi.spyOn(lastData, 'getBoundingClientRect').mockReturnValue({ width: 100, right: 650 } as DOMRect)
    const actionRect = vi.spyOn(action, 'getBoundingClientRect').mockReturnValue({ width: 100, left: 650 } as DOMRect)
    await scroll.trigger('scroll')
    expect(scroll.classes()).not.toContain('has-scroll-right')
    dataRect.mockReturnValue({ width: 100, right: 720 } as DOMRect)
    await scroll.trigger('scroll')
    expect(scroll.classes()).toContain('has-scroll-right')
    dataRect.mockRestore()
    actionRect.mockRestore()
    wrapper.unmount()
  })

  it('引用情况使用清晰的默认状态按钮；默认必须恒有一条，当前默认不可取消', async () => {
    setActivePinia(createPinia())
    const { updateLlmConfig } = await import('../../api/llmConfig')
    const previous = { ...state.current }
    const wrapper = mountView()
    await flushPromises()
    const control = wrapper.get('.config-usage-col .config-default-toggle')
    expect(control.text()).toBe('默认')
    expect(control.attributes('aria-pressed')).toBe('true')
    // 全都不是默认就没有可用大模型：当前默认的开关禁用，点击无副作用
    expect(control.attributes('disabled')).toBeDefined()
    await control.trigger('click')
    await flushPromises()
    expect(updateLlmConfig).not.toHaveBeenCalled()
    expect(wrapper.get('.config-usage-col .config-default-toggle').text()).toBe('默认')
    wrapper.unmount()
    state.current = previous
  })

  it('非默认项「设为默认」走 set-default 转移接口，原默认自动取消', async () => {
    setActivePinia(createPinia())
    const { listLlmConfigs, setDefaultLlmConfig, updateLlmConfig } = await import('../../api/llmConfig')
    const previous = { ...state.current }
    const other = { ...previous, id: 'LLM-2', name: '备用模型', isDefault: false }
    vi.mocked(listLlmConfigs).mockResolvedValueOnce([previous, other])
    // set-default 返回服务端视角：新默认开启，原默认已被 clear_other_defaults 关闭
    vi.mocked(setDefaultLlmConfig).mockImplementationOnce(async (id: string) => {
      state.current = { ...state.current, isDefault: false }
      return { ...other, isDefault: id === 'LLM-2' }
    })
    const wrapper = mountView()
    await flushPromises()
    const candidate = wrapper.findAll('.config-usage-col .config-default-toggle')
      .find((t) => t.text() === '设为默认')
    expect(candidate?.attributes('disabled')).toBeUndefined()
    await candidate?.trigger('click')
    await flushPromises()
    expect(setDefaultLlmConfig).toHaveBeenCalledWith('LLM-2', 'user-e2e')
    expect(updateLlmConfig).not.toHaveBeenCalled()
    // 列表就地更新：新默认置顶显示「默认」，原默认变「设为默认」
    const toggles = wrapper.findAll('.config-usage-col .config-default-toggle').map((t) => t.text())
    expect(toggles[0]).toBe('默认')
    expect(toggles).toContain('设为默认')
    wrapper.unmount()
    state.current = previous
  })

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

  it('端口位数校验：63 位数字按范围校验（不折叠成 1e+63），65 位触发位数上限', async () => {
    setActivePinia(createPinia())
    const { listMysqlDatasources } = await import('../../api/mysqlDatasource')
    // type="number" 的 v-model 会被 Vue 自动 parseFloat（不看 .number 修饰符），
    // 63 位数字进 ref 就成 1e+63——位数/范围校验全错口径（FUNC-00462/00463）
    vi.mocked(listMysqlDatasources).mockResolvedValue([{
      id: 'MY-E2E',
      name: '端口位数回归',
      description: '',
      owner: 'admin',
      updatedAt: '2026-09-20 10:00:00',
      status: '正常',
      isDefault: false,
      host: '127.0.0.1',
      port: 3306,
      defaultDatabase: 'gkx_element',
      username: 'root',
      hasPassword: true,
      passwordMasked: '••••••',
    }])
    const wrapper = mountView()
    await flushPromises()

    // 切到 MySQL 数据源分类并打开管理抽屉
    const mysqlNav = wrapper.findAll('.category-nav > button').find((b) => b.text().includes('MySQL'))
    await mysqlNav?.trigger('click')
    await flushPromises()
    await openDrawer(wrapper)

    const portInput = wrapper.find('.detail-drawer input[aria-label="number-input"]')
    const fieldError = () => wrapper.find('.detail-drawer .field-error').text()

    await portInput.setValue('1'.repeat(63))
    expect(fieldError()).toContain('输入超出有效范围1～65535')
    expect(fieldError()).not.toContain('需为数字')

    await portInput.setValue('1'.repeat(65))
    expect(fieldError()).toContain('数字输入长度不能超过64个字符')
    wrapper.unmount()
  })
})

// 使用真实 Arco Textarea，验证计数随编辑更新且超长粘贴不能超过实际提交上限。
describe('配置说明计数与输入上限', () => {
  it('语言模型：新建与管理显示 /64，回填说明和长文本粘贴均正确计数', async () => {
    setActivePinia(createPinia())
    state.current.description = '原说明'
    const wrapper = mountView(true)
    await flushPromises()
    try {
      await wrapper.get('.create-entry').trigger('click')
      const create = wrapper.get('.config-create-dialog .config-description-textarea')
      expect(create.get('.arco-textarea-word-limit').text()).toBe('0/64')
      await create.get('textarea').setValue('测'.repeat(65))
      expect(create.get('.arco-textarea-word-limit').text()).toBe('64/64')
      expect((create.get('textarea').element as HTMLTextAreaElement).value).toHaveLength(64)
      await wrapper.get('.config-create-dialog header button').trigger('click')
      await openDrawer(wrapper)
      const detail = wrapper.get('.detail-drawer .config-description-textarea')
      expect(detail.get('.arco-textarea-word-limit').text()).toBe('3/64')
      await detail.get('textarea').setValue('新说明')
      expect(detail.get('.arco-textarea-word-limit').text()).toBe('3/64')
      expect(wrapper.get('.config-table-wrap .config-name').text()).toContain('原说明')
      await detail.get('textarea').setValue('文'.repeat(65))
      expect(detail.get('.arco-textarea-word-limit').text()).toBe('64/64')
      expect((detail.get('textarea').element as HTMLTextAreaElement).value).toHaveLength(64)
    } finally {
      wrapper.unmount()
    }
  })

  it('MySQL：新建显示 /200，管理显示 /500，并保留既有说明', async () => {
    setActivePinia(createPinia())
    const { listMysqlDatasources } = await import('../../api/mysqlDatasource')
    vi.mocked(listMysqlDatasources).mockResolvedValue([{
      id: 'MY-COUNTER', name: '说明测试', description: '数据库说明', owner: 'admin',
      updatedAt: '', status: '正常', isDefault: false, host: '127.0.0.1', port: 3306,
      defaultDatabase: 'test', username: 'root', hasPassword: true, passwordMasked: '••••••',
    }])
    const wrapper = mountView(true)
    await flushPromises()
    try {
      await wrapper.findAll('.category-nav > button').find(b => b.text().includes('MySQL'))!.trigger('click')
      await flushPromises()
      await wrapper.get('.create-entry').trigger('click')
      const create = wrapper.get('.config-create-dialog .config-description-textarea')
      expect(create.get('.arco-textarea-word-limit').text()).toBe('0/200')
      await create.get('textarea').setValue('测'.repeat(201))
      expect(create.get('.arco-textarea-word-limit').text()).toBe('200/200')
      await wrapper.get('.config-create-dialog header button').trigger('click')
      await openDrawer(wrapper)
      const detail = wrapper.get('.detail-drawer .config-description-textarea')
      expect(detail.get('.arco-textarea-word-limit').text()).toBe('5/500')
      await detail.get('textarea').setValue('文'.repeat(501))
      expect(detail.get('.arco-textarea-word-limit').text()).toBe('500/500')
      expect((detail.get('textarea').element as HTMLTextAreaElement).value).toHaveLength(500)
    } finally {
      wrapper.unmount()
    }
  })
})
