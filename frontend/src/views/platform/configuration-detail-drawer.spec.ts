import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { Textarea } from '@arco-design/web-vue'
import { describe, expect, it, vi } from 'vitest'

import ConfigurationManagementView from './ConfigurationManagementView.vue'
import ListPagination from '../../components/list-pagination.vue'
import { useToast } from '../../composables/use-toast'
import { useAuthStore } from '../../stores/auth'
import { currentUserIsAdmin } from '../../api/currentUser'
import { useGraphSpaceStore } from '../../stores/graphSpace'

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
    canSetDefault: true,
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
vi.mock('../../api/currentUser', () => ({ currentUserIsAdmin: vi.fn(() => true) }))
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
        // 说明小字超长时外包 a-tooltip（悬浮看全文）；测试只关心行内截断文本
        'a-tooltip': { template: '<span><slot /></span>' },
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
    expect(row.get('.config-id-col').text()).toBe('LLM-E2E公共语言模型')
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
      vi.mocked(listLlmConfigs).mockResolvedValueOnce([state.current, { ...other, isDefault: true }])
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
    // 重新拉取列表：新默认置顶显示「默认」，原默认变「设为默认」
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
    const nameInput = () => wrapper.find('.detail-drawer input[aria-label="name"]')
    // 断言前现查（重渲染后旧 wrapper 可能指向已分离节点，disabled 状态读到脏值）
    const saveDisabled = () => wrapper.findAll('.detail-drawer footer button')
      .find((b) => b.text().includes('保存修改'))?.attributes('disabled')

    // 非法输入：卡片不被污染 + 保存按钮置灰
    await nameInput().setValue('非法<script>alert(1)</script>名称')
    expect(cardName()).toContain('原名称')
    expect(saveDisabled()).toBeDefined()

    // 合法输入未保存：卡片仍保持服务端值、按钮解禁
    await nameInput().setValue('合法新名称XYZ')
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

    const portInput = () => wrapper.find('.detail-drawer input[aria-label="number-input"]')
    const fieldError = () => wrapper.find('.detail-drawer .field-error').text()

    await portInput().setValue('1'.repeat(63))
    expect(fieldError()).toContain('输入超出有效范围1～65535')
    expect(fieldError()).not.toContain('需为数字')

    await portInput().setValue('1'.repeat(65))
    expect(fieldError()).toContain('数字输入长度不能超过64个字符')
    wrapper.unmount()
  })
})

// 输入即校验的显示口径：空表单刚打开不弹必填红警（保存按钮仍置灰拦截），
// 只有输入超限/非法的字段才亮红框红字，改回合法立即恢复。
describe('新建弹窗红框提示时机', () => {
  it('未输入不提示；名称超 64 字即时红字红框，改回合法恢复', async () => {
    setActivePinia(createPinia())
    const wrapper = mountView()
    await flushPromises()
    await wrapper.get('.create-entry').trigger('click')
    const dialog = wrapper.get('.config-create-dialog')
    expect(dialog.find('.field-error').exists()).toBe(false)
    expect(dialog.find('input[aria-invalid="true"]').exists()).toBe(false)
    // 未触碰的空必填（API Key）不提示，但保存/验证按钮仍禁用
    expect(dialog.text()).not.toContain('请输入配置名称')
    expect(dialog.text()).not.toContain('请输入 API Key')

    const nameInput = dialog.find('input[aria-label="例如：科技文本抽取大模型"]')
    await nameInput.setValue('长'.repeat(65))
    expect(dialog.get('.field-error').text()).toBe('输入长度不能超过64个字符')
    expect(nameInput.attributes('aria-invalid')).toBe('true')

    await nameInput.setValue('正常名称')
    expect(dialog.find('.field-error').exists()).toBe(false)
    expect(nameInput.attributes('aria-invalid')).not.toBe('true')
    wrapper.unmount()
  })
})

// 停用=退出使用：探活会真连库且结果盖掉「停用」徽标（停用配置有的库通/有的不通，
// 表现随机翻转成 正常/异常），所以停用态测试连接置灰，启用后才可测。
describe('停用配置的连接测试', () => {
  it('停用数据源抽屉里测试连接置灰且不发探活请求；启用态可点', async () => {
    setActivePinia(createPinia())
    const { listMysqlDatasources, testMysqlDatasource } = await import('../../api/mysqlDatasource')
    const base = {
      description: '', owner: 'admin', updatedAt: '', isDefault: false,
      host: '10.0.0.9', port: 3306, defaultDatabase: 'legacy', username: 'root',
      hasPassword: true, passwordMasked: '••••••',
    }
    vi.mocked(listMysqlDatasources).mockResolvedValue([
      { ...base, id: 'MY-DIS', name: '停用库', status: '停用' },
      { ...base, id: 'MY-OK', name: '在用库', status: '正常' },
    ])
    const wrapper = mountView()
    await flushPromises()
    try {
      await wrapper.findAll('.category-nav > button').find(b => b.text().includes('MySQL'))!.trigger('click')
      await flushPromises()
      const openDrawerByName = async (name: string) => {
        const row = wrapper.findAll('.config-table-wrap tbody tr')
          .find(r => r.get('.config-name strong').text() === name)!
        await row.get('.row-actions button').trigger('click')
        await flushPromises()
      }
      const testBtn = () => wrapper.findAll('.detail-drawer .health-card button')
        .find(b => b.text().includes('测试连接'))!

      await openDrawerByName('停用库')
      expect(testBtn()!.attributes('disabled')).toBeDefined()
      expect(testBtn()!.attributes('title')).toContain('请先启用')
      await testBtn()!.trigger('click')
      await flushPromises()
      expect(testMysqlDatasource).not.toHaveBeenCalled()
      await wrapper.find('.detail-drawer > header button').trigger('click')

      await openDrawerByName('在用库')
      expect(testBtn()!.attributes('disabled')).toBeUndefined()
    } finally {
      wrapper.unmount()
    }
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

// 图空间说明：新建弹窗填写，随创建提交，列表名称下方第二行展示。
describe('图空间说明', () => {
  it('新建弹窗可填说明并随创建提交；列表第二行展示说明，无说明不占行', async () => {
    setActivePinia(createPinia())
    const { listGraphSpaceItems, createGraphSpace } = await import('../../api/graphSpace')
    vi.mocked(listGraphSpaceItems)
      .mockResolvedValueOnce([]) // 首屏加载
      .mockResolvedValueOnce([]) // 切到图数据空间页签补拉
      .mockResolvedValueOnce([ // 创建成功后回读
        { name: 'demo2', bound: true, mine: true, description: '演示用途空间' },
        { name: 'bare', bound: true, mine: true, description: '' },
      ])
    // 创建成功会同步总览全局空间选择器，真实 store 会发未 mock 的请求
    const ensureLoaded = vi.spyOn(useGraphSpaceStore(), 'ensureLoaded').mockResolvedValue()
    const wrapper = mountView(true)
    await flushPromises()
    await wrapper.findAll('.category-nav button').find(b => b.text().includes('图数据空间'))!.trigger('click')
    await flushPromises()
    expect(wrapper.get('.space-table thead th').text()).toBe('图空间名称 / 说明')
    await wrapper.get('.create-entry').trigger('click')
    await wrapper.get('.space-dialog .space-name-field input').setValue('demo2')
    await wrapper.get('.space-dialog .config-description-textarea textarea').setValue('演示用途空间')
    await wrapper.get('.space-dialog footer .primary').trigger('click')
    await flushPromises()
    // mock 替换了整个函数，默认参数 userId 不参与断言
    expect(createGraphSpace).toHaveBeenCalledWith('demo2', '演示用途空间')
    // 列表按名称排序（bare 在 demo2 前），按名称定位行再断言
    const rowOf = (name: string) => wrapper.findAll('.space-table tbody tr')
      .find(r => r.get('.config-name strong').text() === name)!
    expect(rowOf('demo2').get('.config-name small').text()).toBe('演示用途空间')
    expect(rowOf('bare').find('.config-name small').exists()).toBe(false) // 无说明不留空行
    ensureLoaded.mockRestore()
    wrapper.unmount()
  })
})

describe('开发人员共享配置只读', () => {
  it.each([false, true])('公共配置只读（权限字段缺省：%s），仍能新建配置与图空间', async (legacy) => {
    setActivePinia(createPinia())
    vi.mocked(currentUserIsAdmin).mockReturnValue(false)
    const auth = useAuthStore()
    auth.profile = { isAdmin: false, businessRbacEnabled: true, canDevelop: true } as typeof auth.profile
    if (!legacy) {
      const { listLlmConfigs } = await import('../../api/llmConfig')
      vi.mocked(listLlmConfigs).mockResolvedValueOnce([{ ...state.current, visibility: 'public', businessId: null, businessName: '', canManage: false }])
    }
    const wrapper = mountView()
    try {
      await flushPromises()
      expect(wrapper.get('.create-entry').attributes('disabled')).toBeUndefined()
      const actions = wrapper.findAll('.row-actions button')
      expect(actions[0]!.text()).toBe('查看')
      expect(actions[0]!.attributes('disabled')).toBeUndefined()
      expect(actions[1]!.attributes('disabled')).toBeDefined()
      expect(actions[2]!.attributes('disabled')).toBeDefined()
      await actions[0]!.trigger('click')
      expect(wrapper.get('.detail-form input').attributes('disabled')).toBeDefined()
      expect(wrapper.get('.detail-drawer footer button').attributes('disabled')).toBeDefined()
      await wrapper.get('.detail-drawer header button').trigger('click')
      await wrapper.findAll('.category-nav > button')[2]!.trigger('click')
      await flushPromises()
      expect(wrapper.get('.create-entry').attributes('disabled')).toBeUndefined()
      await wrapper.get('.create-entry').trigger('click')
      expect(wrapper.find('.space-dialog').exists()).toBe(true)
    } finally {
      wrapper.unmount()
      vi.mocked(currentUserIsAdmin).mockReturnValue(true)
    }
  })
})

describe('业务配置权限与归属', () => {
  it.each(['llm', 'mysql'] as const)('%s：开发人员复用新建表单并管理本业务配置，模型可设置本业务默认', async (kind) => {
    setActivePinia(createPinia())
    vi.mocked(currentUserIsAdmin).mockReturnValue(false)
    const auth = useAuthStore()
    auth.profile = { isAdmin: false, businessRbacEnabled: true, canDevelop: true } as typeof auth.profile
    const { listLlmConfigs } = await import('../../api/llmConfig')
    const { listMysqlDatasources } = await import('../../api/mysqlDatasource')
    const ownership = { visibility: 'business' as const, businessId: 'business-1', businessName: '亿级知识图谱', canManage: true }
    if (kind === 'llm') vi.mocked(listLlmConfigs).mockResolvedValueOnce([{ ...state.current, ...ownership, isDefault: false }])
    else vi.mocked(listMysqlDatasources).mockResolvedValueOnce([{
      id: 'MYSQL-BIZ', name: '业务数据库', description: '', host: 'localhost', port: 3306,
      username: 'root', defaultDatabase: '', owner: 'other-developer', isDefault: false,
      status: '正常', hasPassword: true, passwordMasked: '***', createdAt: '', updatedAt: '', ...ownership,
    }])
    const wrapper = mountView()
    try {
      await flushPromises()
      if (kind === 'mysql') {
        await wrapper.findAll('.category-nav > button')[1]!.trigger('click')
        await flushPromises()
      }
      expect(wrapper.get('.config-ownership').text()).toBe(`亿级知识图谱${kind === 'llm' ? '语言模型' : '数据库'}`)
      expect(wrapper.findAll('.config-table-wrap thead th')[1]!.text()).toBe('标识 / 归属')
      const actions = wrapper.findAll('.row-actions button')
      expect(actions[0]!.text()).toBe('管理')
      expect(actions[1]!.attributes('disabled')).toBeUndefined()
      expect(actions[2]!.attributes('disabled')).toBeUndefined()
      if (kind === 'llm') expect(wrapper.get('.config-default-toggle').attributes('disabled')).toBeUndefined()
      await actions[0]!.trigger('click')
      expect(wrapper.get('.detail-form input').attributes('disabled')).toBeUndefined()
      expect(wrapper.findAll('.detail-form input').map(i => (i.element as HTMLInputElement).value)).toContain(`亿级知识图谱${kind === 'llm' ? '语言模型' : '数据库'}`)
      expect(wrapper.get('.detail-drawer footer button').attributes('disabled')).toBeUndefined()
      expect(wrapper.get('.health-card button').attributes('disabled')).toBeUndefined()
      await wrapper.get('.detail-drawer header button').trigger('click')
      await wrapper.get('.create-entry').trigger('click')
      expect(wrapper.find('.config-create-dialog').exists()).toBe(true)
      expect(wrapper.get('.default-config-checkbox').attributes('disabled')).toBeDefined()
    } finally {
      wrapper.unmount()
      vi.mocked(currentUserIsAdmin).mockReturnValue(true)
    }
  })

  it('图空间在名称与绑定状态之间显示公共或业务标识', async () => {
    setActivePinia(createPinia())
    const { listGraphSpaceItems } = await import('../../api/graphSpace')
    vi.mocked(listGraphSpaceItems).mockResolvedValueOnce([
      { name: 'public_space', mine: true, bound: true, groupKind: 'public' },
      { name: 'business_space', mine: true, bound: true, groupKind: 'business', businessName: '亿级知识图谱' },
    ])
    const wrapper = mountView()
    await flushPromises()
    await wrapper.findAll('.category-nav > button')[2]!.trigger('click')
    await flushPromises()
    expect(wrapper.findAll('.space-table th').map(cell => cell.text())).toEqual(['图空间名称 / 说明', '标识', '绑定状态', '操作'])
    expect(wrapper.findAll('.space-table tbody tr').map(row => row.findAll('td')[1]!.text())).toEqual(['亿级知识图谱图空间', '公共图空间'])
    wrapper.unmount()
  })
})


describe('业务默认模型交互', () => {
  it('开发人员可将继承的公共默认固定为业务默认，公共配置仍只读，状态以重拉结果为准', async () => {
    setActivePinia(createPinia())
    vi.mocked(currentUserIsAdmin).mockReturnValue(false)
    useAuthStore().profile = { isAdmin: false, businessRbacEnabled: true, canDevelop: true } as ReturnType<typeof useAuthStore>['profile']
    const { listLlmConfigs, setDefaultLlmConfig } = await import('../../api/llmConfig')
    const inherited = { ...state.current, visibility: 'public' as const, canManage: false, canSetDefault: true, defaultReferenced: true, defaultSource: 'public' as const, isDefault: true }
    vi.mocked(listLlmConfigs).mockResolvedValueOnce([inherited])
    vi.mocked(setDefaultLlmConfig).mockImplementationOnce(async () => {
      vi.mocked(listLlmConfigs).mockResolvedValueOnce([{ ...inherited, defaultSource: 'business' }])
      return { ...inherited, defaultSource: 'business' }
    })
    const wrapper = mountView()
    try {
      await flushPromises()
      const button = wrapper.get('.config-default-toggle')
      expect(button.text()).toBe('跟随公共默认')
      expect(button.attributes('disabled')).toBeUndefined()
      expect(wrapper.get('.config-name .default-tag').text()).toBe('跟随公共默认')
      const actions = wrapper.findAll('.row-actions button')
      expect(actions[0]!.text()).toBe('查看')
      expect(actions[1]!.attributes('disabled')).toBeDefined()
      expect(actions[2]!.attributes('disabled')).toBeDefined()
      await actions[0]!.trigger('click')
      expect(wrapper.get('.detail-drawer .default-tag').text()).toBe('跟随公共默认')
      await button.trigger('click')
      await flushPromises()
      expect(setDefaultLlmConfig).toHaveBeenLastCalledWith(inherited.id, 'user-e2e')
      expect(wrapper.get('.config-default-toggle').text()).toBe('默认')
      expect(wrapper.get('.config-default-toggle').attributes('disabled')).toBeDefined()
      expect(wrapper.get('.detail-drawer .default-tag').text()).toBe('默认')
    } finally {
      wrapper.unmount()
      vi.mocked(currentUserIsAdmin).mockReturnValue(true)
    }
  })

  it('管理员不能把业务模型设为公共默认，被业务引用的非公共默认模型不能停用删除', async () => {
    setActivePinia(createPinia())
    const { listLlmConfigs } = await import('../../api/llmConfig')
    vi.mocked(listLlmConfigs).mockResolvedValueOnce([{ ...state.current, visibility: 'business', canManage: true, canSetDefault: false, isDefault: false, defaultReferenced: true }])
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.get('.config-default-toggle').attributes('disabled')).toBeDefined()
    const actions = wrapper.findAll('.row-actions button')
    expect(actions[0]!.text()).toBe('管理')
    expect(actions[1]!.attributes('disabled')).toBeDefined()
    expect(actions[2]!.attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})

// 异常=探活事实：挂死的模型设为默认会让下游抽取全部失败——列表先置灰拦下
//（后端 set-default/update 同步加 409 守卫），恢复连接后才可设。
describe('异常语言模型不能设为默认', () => {
  const rowByName = (wrapper: ReturnType<typeof mountView>, name: string) =>
    wrapper.findAll('.config-table-wrap tbody tr').find(r => r.get('.config-name strong').text() === name)!

  it('异常模型的「设为默认」置灰并提示先恢复连接；正常模型不受影响', async () => {
    setActivePinia(createPinia())
    const { listLlmConfigs, setDefaultLlmConfig } = await import('../../api/llmConfig')
    vi.mocked(setDefaultLlmConfig).mockClear()
    vi.mocked(listLlmConfigs).mockResolvedValueOnce([
      { ...state.current, id: 'LLM-BAD', name: '异常模型', status: '异常', isDefault: false },
      { ...state.current, id: 'LLM-OK', name: '正常模型', status: '正常', isDefault: false },
    ])
    const wrapper = mountView()
    try {
      await flushPromises()
      const badToggle = rowByName(wrapper, '异常模型').get('.config-default-toggle')
      expect(badToggle.attributes('disabled')).toBeDefined()
      expect(badToggle.attributes('title')).toBe('连接异常的模型不能设为默认，请先恢复连接')
      await badToggle.trigger('click')
      await flushPromises()
      expect(setDefaultLlmConfig).not.toHaveBeenCalled()
      const okToggle = rowByName(wrapper, '正常模型').get('.config-default-toggle')
      expect(okToggle.attributes('disabled')).toBeUndefined()
      expect(okToggle.attributes('title')).toBe('设为默认配置')
    } finally {
      wrapper.unmount()
    }
  })
})

// 探活超时此前有两个坑：后端按 40s 才报错、前端 axios 20s 先中止走 catch，
// 徽标停留在「正常」且提示是英文原始报错。现在后端探活 8s 内返回 error=超时，
// 前端两条失败路径都把徽标翻成异常、提示只说「连接超时」。
describe('探活超时的状态与提示', () => {
  const rowByName = (wrapper: ReturnType<typeof mountView>, name: string) =>
    wrapper.findAll('.config-table-wrap tbody tr').find(r => r.get('.config-name strong').text() === name)!

  async function openDrawerByName(wrapper: ReturnType<typeof mountView>, name: string) {
    await rowByName(wrapper, name).get('.row-actions button').trigger('click')
    await flushPromises()
  }

  it('探活返回超时：徽标翻异常，提示只说连接超时', async () => {
    setActivePinia(createPinia())
    const { listLlmConfigs, testLlmConfig } = await import('../../api/llmConfig')
    const { toasts } = useToast()
    vi.mocked(listLlmConfigs).mockResolvedValueOnce([
      { ...state.current, id: 'LLM-TMO', name: '挂死模型', status: '正常', isDefault: false },
    ])
    vi.mocked(testLlmConfig).mockResolvedValueOnce({ ok: false, latencyMs: 8000, error: '超时' })
    const wrapper = mountView()
    try {
      await flushPromises()
      await openDrawerByName(wrapper, '挂死模型')
      await wrapper.findAll('.detail-drawer .health-card button').find(b => b.text().includes('测试连接'))!.trigger('click')
      await flushPromises()
      expect(rowByName(wrapper, '挂死模型').get('.status').classes()).toContain('is-异常')
      expect(wrapper.get('.detail-drawer .health-card i').classes()).toContain('is-异常')
      const toast = toasts.value.filter(t => t.message.includes('挂死模型')).at(-1)
      expect(toast?.message).toBe('挂死模型 连接超时')
    } finally {
      wrapper.unmount()
    }
  })

  it('请求层超时中止（axios ECONNABORTED）：徽标同样翻异常', async () => {
    setActivePinia(createPinia())
    const { listLlmConfigs, testLlmConfig } = await import('../../api/llmConfig')
    vi.mocked(listLlmConfigs).mockResolvedValueOnce([
      { ...state.current, id: 'LLM-ABT', name: '无响应模型', status: '正常', isDefault: false },
    ])
    vi.mocked(testLlmConfig).mockRejectedValueOnce(
      Object.assign(new Error('timeout of 20000ms exceeded'), { code: 'ECONNABORTED' }),
    )
    const wrapper = mountView()
    try {
      await flushPromises()
      await openDrawerByName(wrapper, '无响应模型')
      await wrapper.findAll('.detail-drawer .health-card button').find(b => b.text().includes('测试连接'))!.trigger('click')
      await flushPromises()
      expect(rowByName(wrapper, '无响应模型').get('.status').classes()).toContain('is-异常')
    } finally {
      wrapper.unmount()
    }
  })
})

// 列表「说明」小字：超长截断单行 + 悬浮 tooltip 看全文，不再整段换行撑高行。
describe('列表说明超长截断', () => {
  it('超过 40 字截断显示省略号且行内无全文；短说明原样显示', async () => {
    setActivePinia(createPinia())
    const { listLlmConfigs } = await import('../../api/llmConfig')
    const longText = '用于回归验证的超长配置说明文字。'.repeat(5) // 70 字
    vi.mocked(listLlmConfigs).mockResolvedValueOnce([
      { ...state.current, id: 'LLM-LONG', name: '长说明模型', description: longText, isDefault: false },
      { ...state.current, id: 'LLM-SHORT', name: '短说明模型', description: '短说明', isDefault: false },
    ])
    const wrapper = mountView()
    try {
      await flushPromises()
      const longRow = wrapper.findAll('.config-table-wrap tbody tr').find(r => r.get('.config-name strong').text() === '长说明模型')!
      const small = longRow.get('.config-name small')
      expect(small.text()).toBe(`${longText.slice(0, 40)}…`)
      expect(small.text().endsWith('…')).toBe(true)
      expect(longRow.text()).not.toContain(longText)
      const shortRow = wrapper.findAll('.config-table-wrap tbody tr').find(r => r.get('.config-name strong').text() === '短说明模型')!
      expect(shortRow.get('.config-name small').text()).toBe('短说明')
    } finally {
      wrapper.unmount()
    }
  })
})
