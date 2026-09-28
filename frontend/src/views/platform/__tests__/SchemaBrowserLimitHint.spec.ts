import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { Form, FormItem } from '@arco-design/web-vue'

import {
  deleteSchema,
  getSchemaOverview,
  listSchemasPaged,
  type SchemaDefinition,
} from '../../../api/schemaManagement'
import SchemaBrowserView from '../SchemaBrowserView.vue'

vi.mock('../../../api/schemaManagement', () => ({
  addSchemaProperty: vi.fn(),
  backfillSchemaHistory: vi.fn(),
  createEntitySchema: vi.fn(),
  createRelationSchema: vi.fn(),
  deleteSchema: vi.fn(),
  deleteSchemaProperty: vi.fn(),
  getSchemaDeleteImpact: vi.fn(),
  getSchemaDetail: vi.fn(),
  getSchemaTopology: vi.fn(async () => ({ nodes: [], edges: [] })),
  getScriptContent: vi.fn(),
  getSchemaOverview: vi.fn(),
  listEntityOptions: vi.fn(),
  listSchemasPaged: vi.fn(),
  replaceSchemaSources: vi.fn(),
  schemaErrorMessage: vi.fn((error: unknown) => String(error)),
  triggerSchemaExtraction: vi.fn(),
  verifyAndSaveScript: vi.fn(),
}))
vi.mock('../../../api/currentUser', () => ({ currentUserId: vi.fn(() => 'user-1') }))
vi.mock('../../../api/currentGraphSpace', () => ({ currentGraphSpace: vi.fn(() => 'dev2') }))
vi.mock('../../../api/mysqlDatasource', () => ({ listMysqlDatasources: vi.fn(async () => []) }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconSearch: { template: '<i />' } }))

// jsdom 没有 window.matchMedia：真实 arco FormItem（内部走 Grid 响应式）挂载时需要它
if (!window.matchMedia) {
  window.matchMedia = (query: string) =>
    ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }) as MediaQueryList
}

// v-model 透传 stub：只保留输入与值同步，不依赖 Arco 内部实现
const AInputStub = defineComponent({
  props: ['modelValue', 'maxLength', 'placeholder'],
  emits: ['update:modelValue'],
  template: `<input :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
})
const ATextareaStub = defineComponent({
  props: ['modelValue', 'maxLength'],
  emits: ['update:modelValue'],
  template: `<textarea :value="modelValue" @input="$emit('update:modelValue', $event.target.value)"></textarea>`,
})
const SlotStub = defineComponent({ template: '<div><slot /></div>' })
const DropdownStub = defineComponent({
  data: () => ({ open: false }),
  template: '<span><span @click="open = !open"><slot /></span><span v-if="open" class="test-dropdown-menu"><slot name="content" /></span></span>',
})
const DoptionStub = defineComponent({
  props: ['disabled'],
  template: '<button type="button" :disabled="disabled"><slot /></button>',
})
// Select 需可交互：fixed_string 长度提示的用例要切属性类型
const ASelectStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: `<select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)"><slot /></select>`,
})
const AOptionStub = defineComponent({
  props: ['value'],
  template: '<option :value="value"><slot /></option>',
})
// FormItem 需渲染 label 插槽：属性列表头部的「＋ 添加属性」按钮在 label 插槽里
const AFormItemStub = defineComponent({ template: '<div><slot name="label" /><slot /></div>' })
const ACheckboxStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: `<label><input type="checkbox" :checked="modelValue" @change="$emit('update:modelValue', $event.target.checked)" /><slot /></label>`,
})

const overviewFixture = {
  currentVersion: '', environment: '', releasedAt: '', entityTypes: 0, coreEntityTypes: 0,
  relationTypes: 0, factRelationTypes: 0, inferredRelationTypes: 0, propertyFields: 0,
  requiredFields: 0, constraintRules: 0, sourceMappings: 0,
}

function schemaFixture(overrides: Partial<SchemaDefinition> = {}): SchemaDefinition {
  return {
    id: 'sch-1', key: 'gadget', kind: 'entity', kindLabel: '实体', graphSpace: 'dev2',
    name: 'Gadget', label: '部件', description: '', identityKey: 'id', attributeIdentityKey: '',
    attributeSource: '', instanceCount: 0, version: '1', isCore: false, relationCategory: null,
    isSystem: false, createdBy: null, createdAt: null, updatedAt: null, sourceSchemaId: null,
    sourceSchemaName: null, targetSchemaId: null, targetSchemaName: null, mappings: [],
    canDelete: false, canManageProperties: true, properties: [], script: null,
    ...overrides,
  }
}

let wrapper: VueWrapper

function mountView() {
  wrapper = mount(SchemaBrowserView, {
    global: {
      components: {
        AInput: AInputStub, ATextarea: ATextareaStub, AForm: SlotStub, AFormItem: AFormItemStub,
        ASelect: ASelectStub, AOption: AOptionStub, ACheckbox: ACheckboxStub, ATooltip: SlotStub,
        ADropdown: DropdownStub, ADoption: DoptionStub,
      },
      stubs: { KgGraphCanvas: true, teleport: true },
    },
  })
  return wrapper
}

// 校验文案用例需要真的跑 arco 表单校验：AForm/AFormItem 换成真实组件
// （stub 没有 validate 方法，saveItem 会静默落到 toast 兜底，DOM 里看不到提示）。
function mountViewWithRealForm() {
  wrapper = mount(SchemaBrowserView, {
    global: {
      components: {
        AInput: AInputStub, ATextarea: ATextareaStub, AForm: Form, AFormItem: FormItem,
        ASelect: ASelectStub, AOption: AOptionStub, ACheckbox: ACheckboxStub, ATooltip: SlotStub,
        ADropdown: DropdownStub, ADoption: DoptionStub,
      },
      stubs: { KgGraphCanvas: true, teleport: true },
    },
  })
  return wrapper
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getSchemaOverview).mockResolvedValue(overviewFixture)
  vi.mocked(listSchemasPaged).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 10 })
  setActivePinia(createPinia())
})

afterEach(() => {
  wrapper?.unmount()
})

describe('Schema 管理输入框达上限提示', () => {
  it('操作列常显三项，更多菜单保留其余操作及权限状态', async () => {
    vi.mocked(listSchemasPaged).mockResolvedValue({ items: [schemaFixture()], total: 1, page: 1, pageSize: 10 })
    const view = mountView()
    await flushPromises()

    const actions = view.get('.schema-actions')
    expect(actions.findAll('.schema-action-link').map((button) => button.text())).toEqual(['更换脚本', '查看脚本', '来源表', '···'])
    expect(actions.find('.test-dropdown-menu').exists()).toBe(false)
    await actions.get('.schema-action-more').trigger('click')
    const options = actions.findAll('.test-dropdown-menu button')
    expect(options.map((button) => button.text())).toEqual(['属性管理', '删除'])
    expect(options[0].classes()).toContain('schema-action-menu-item')
    expect(options[1].classes()).toContain('schema-action-menu-item--danger')
    expect(options[0].attributes('disabled')).toBeUndefined()
    expect(options[1].attributes('disabled')).toBeDefined()

    await view.get('.schema-topology-toggle').trigger('click')
    await flushPromises()
    expect(view.get('.schema-catalog').classes()).toContain('schema-catalog--topology-expanded')
  })

  it('搜索框达 128 字上限：输入框下浮出提示，缩短后消失', async () => {
    const view = mountView()
    await flushPromises()

    const search = view.find('input.schema-search-input')
    expect(view.find('.limit-field__hint').exists()).toBe(false)

    await search.setValue('词'.repeat(128))
    expect(view.get('.limit-field__hint').text()).toContain('已达 128 字上限，无法继续输入')

    await search.setValue('部件')
    expect(view.find('.limit-field__hint').exists()).toBe(false)
  })

  it('新建弹窗实体名/中文名达 128 字上限：输入框红边高亮 + 下方提示行', async () => {
    const view = mountView()
    await flushPromises()
    await view.get('.schema-tabs .primary').trigger('click')

    const [nameInput, labelInput] = view.findAll('input.create-text-input')
    await nameInput.setValue('A'.repeat(128))
    expect(nameInput.classes()).toContain('is-at-limit')
    expect(view.get('.create-field--limit-note .limit-field-note').text()).toContain('已达 128 字上限，无法继续输入')

    await labelInput.setValue('名'.repeat(128))
    expect(labelInput.classes()).toContain('is-at-limit')

    await nameInput.setValue('Gadget')
    expect(nameInput.classes()).not.toContain('is-at-limit')
  })

  it('关系页名称上限 64：达上限红边提示 64 字，maxlength 同步收紧；实体页仍为 128', async () => {
    const view = mountView()
    await flushPromises()

    // 切到「关系」tab 再打开新增弹窗
    const relationTab = view.findAll('.schema-tabs__items button').find((button) => button.text() === '关系')
    expect(relationTab).toBeTruthy()
    await relationTab!.trigger('click')
    await view.get('.schema-tabs .primary').trigger('click')

    const nameInput = view.findAll('input.create-text-input')[0]
    expect(nameInput.attributes('maxlength')).toBe('64')
    expect(view.find('.create-field--limit-note .limit-field-note').exists()).toBe(false)

    await nameInput.setValue('U'.repeat(64))
    expect(nameInput.classes()).toContain('is-at-limit')
    expect(view.get('.create-field--limit-note .limit-field-note').text()).toContain('已达 64 字上限，无法继续输入')

    await nameInput.setValue('USES_TECHNOLOGY')
    expect(view.find('.create-field--limit-note .limit-field-note').exists()).toBe(false)

    // 实体页维持 128
    const entityTab = view.findAll('.schema-tabs__items button').find((button) => button.text() === '标准实体')
    await entityTab!.trigger('click')
    await view.get('.schema-tabs .primary').trigger('click')
    const entityNameInput = view.findAll('input.create-text-input')[0]
    expect(entityNameInput.attributes('maxlength')).toBe('128')
  })

  it('属性列表行达 128 字上限：该行输入框红边 + 列表下方汇总提示（含行号）', async () => {
    const view = mountView()
    await flushPromises()
    await view.get('.schema-tabs .primary').trigger('click')

    await view.get('.create-props__add').trigger('click')
    const propInputs = view.findAll('input.prop-name')
    // 5 个锁定公共属性 + 1 个新增行，达上限的是新增行（第 6 行）
    await propInputs[propInputs.length - 1].setValue('p'.repeat(128))
    expect(propInputs[propInputs.length - 1].classes()).toContain('is-at-limit')
    expect(view.get('.create-props .limit-field-note').text()).toContain('第 6 行属性名已达 128 字上限')

    await propInputs[propInputs.length - 1].setValue('weight')
    expect(view.find('.create-props .limit-field-note').exists()).toBe(false)
  })

  it('属性管理弹窗新增属性名达 128 字上限：红边 + 表单下方提示', async () => {
    vi.mocked(listSchemasPaged).mockResolvedValue({ items: [schemaFixture()], total: 1, page: 1, pageSize: 10 })
    const view = mountView()
    await flushPromises()

    await view.get('button.schema-action-more').trigger('click')
    await view.findAll('.test-dropdown-menu button').find((button) => button.text() === '属性管理')!.trigger('click')

    const nameInput = view.get('input.property-add-form__name')
    await nameInput.setValue('f'.repeat(128))
    // setValue 触发重渲染会替换输入框节点，重新查询拿最新 class（旧 wrapper 是游离节点）
    expect(view.get('input.property-add-form__name').classes()).toContain('is-at-limit')
    expect(view.get('.property-section .limit-field-note').text()).toContain('属性名已达 128 字上限')
  })

  it('新建弹窗属性行 fixed_string 长度实时提示随输入变化', async () => {
    const view = mountView()
    await flushPromises()
    await view.get('.schema-tabs .primary').trigger('click')
    await view.get('.create-props__add').trigger('click')

    // 新增行（唯一可编辑行）类型切到 fixed_string，出现长度输入框与实时提示（默认 64）
    await view.get('.create-prop-list select').setValue('fixed_string')
    expect(view.get('.create-prop-list .prop-length-live').text()).toContain('当前 64，可定义 1~1024')

    await view.get('input.prop-len').setValue('300')
    expect(view.get('.create-prop-list .prop-length-live').text()).toContain('当前 300，可定义 1~1024')

    // 超出 1024：提示转红（输入框红边走既有范围校验）
    await view.get('input.prop-len').setValue('5000')
    const invalidLive = view.get('.create-prop-list .prop-length-live')
    expect(invalidLive.text()).toContain('当前 5000')
    expect(invalidLive.classes()).toContain('prop-length-live--invalid')

    // 清空后显示占位符
    await view.get('input.prop-len').setValue('')
    expect(view.get('.create-prop-list .prop-length-live').text()).toContain('当前 —')
  })

  it('属性管理弹窗 fixed_string 长度实时提示随输入变化', async () => {
    vi.mocked(listSchemasPaged).mockResolvedValue({ items: [schemaFixture()], total: 1, page: 1, pageSize: 10 })
    const view = mountView()
    await flushPromises()

    await view.get('button.schema-action-more').trigger('click')
    await view.findAll('.test-dropdown-menu button').find((button) => button.text() === '属性管理')!.trigger('click')

    await view.get('.property-add-form select').setValue('fixed_string')
    expect(view.get('.property-section .prop-length-live').text()).toContain('当前 64，可定义 1~1024')

    await view.get('input.property-add-form__len').setValue('1024')
    const live = view.get('.property-section .prop-length-live')
    expect(live.text()).toContain('当前 1024，可定义 1~1024')
    expect(live.classes()).not.toContain('prop-length-live--invalid')
  })
})

describe('Schema 属性与脚本弹窗样式', () => {
  it('属性类别独立成列，公共属性删除按钮置灰并使用线性锁图标', async () => {
    vi.mocked(listSchemasPaged).mockResolvedValue({
      items: [schemaFixture({
        properties: [
          { name: 'id', dataType: 'string', required: true, rule: '', category: 'required', locked: true },
          { name: 'score', dataType: 'double', required: false, rule: '', category: 'core', locked: false },
        ],
      })],
      total: 1, page: 1, pageSize: 10,
    })
    const view = mountView()
    await flushPromises()

    const manageButton = view.findAll('button.schema-action-link').find((button) => button.text() === '属性管理')
    await manageButton!.trigger('click')

    const header = view.get('.property-table__row--head')
    expect(header.text()).toContain('属性类别')
    const rows = view.findAll('.property-table__row:not(.property-table__row--head)')
    expect(rows[0].text()).toContain('公共属性')
    expect(rows[0].get('.property-table__lock').element.tagName.toLowerCase()).toBe('svg')
    expect(rows[0].get('button').attributes('disabled')).toBeDefined()
    expect(rows[0].get('button').text()).toBe('删除')
    expect(rows[1].text()).toContain('自定义属性')
    expect(rows[1].get('button').attributes('disabled')).toBeUndefined()
  })

  it('上传脚本入口展示虚线添加文件区域和格式提示', async () => {
    vi.mocked(listSchemasPaged).mockResolvedValue({ items: [schemaFixture()], total: 1, page: 1, pageSize: 10 })
    const view = mountView()
    await flushPromises()

    const uploadButton = view.findAll('button.schema-action-link').find((button) => button.text() === '更换脚本')
    await uploadButton!.trigger('click')

    const dropzone = view.get('.upload-dropzone')
    expect(dropzone.text()).toContain('添加脚本文件')
    expect(dropzone.text()).toContain('仅支持 .py 文件')
    expect(dropzone.attributes('role')).toBe('button')
  })
})

describe('Schema 列表说明列截断显示与删除脏行兜底', () => {
  it('实体/关系说明超 10 字符截断、起点/终点超 5 字符截断（悬停看全文），短文本原样展示', async () => {
    vi.mocked(listSchemasPaged).mockResolvedValue({
      items: [schemaFixture({ kind: 'entity', description: '说'.repeat(25) })],
      total: 1, page: 1, pageSize: 10,
    })
    const view = mountView()
    await flushPromises()

    const entityDesc = view.findAll('.schema-table-wrap tbody tr')[0].findAll('td')[2]
    expect(entityDesc.text()).toBe('说'.repeat(10) + '…')

    // 关系子页面：说明（basis=description）截断 10 字符；起点 6 字符截断为 5+省略号，
    // 终点恰好 5 字符不截断
    vi.mocked(listSchemasPaged).mockResolvedValue({
      items: [schemaFixture({
        kind: 'relation', name: 'USES_TECH', description: '长'.repeat(30),
        sourceSchemaName: 'Expert', targetSchemaName: 'Paper',
      })],
      total: 1, page: 1, pageSize: 10,
    })
    const relationTab = view.findAll('.schema-tabs__items button').find((button) => button.text() === '关系')
    await relationTab!.trigger('click')
    await flushPromises()

    const relationCells = view.findAll('.schema-table-wrap tbody tr')[0].findAll('td')
    expect(relationCells[2].text()).toBe('Exper…')
    expect(relationCells[3].text()).toBe('Paper')
    expect(relationCells[4].text()).toBe('长'.repeat(10) + '…')

    // 短说明不截断（重新挂载拿新 mock 数据）
    view.unmount()
    vi.mocked(listSchemasPaged).mockResolvedValue({
      items: [schemaFixture({ kind: 'relation', name: 'USES_TECH', description: '短说明' })],
      total: 1, page: 1, pageSize: 10,
    })
    const shortView = mountView()
    await flushPromises()
    const shortTab = shortView.findAll('.schema-tabs__items button').find((button) => button.text() === '关系')
    await shortTab!.trigger('click')
    await flushPromises()
    const shortDesc = shortView.findAll('.schema-table-wrap tbody tr')[0].findAll('td')[4]
    expect(shortDesc.text()).toBe('短说明')
  })

  it('删除已不存在的行（脏行）：报「不存在」时关弹窗并刷新列表', async () => {
    vi.mocked(deleteSchema).mockRejectedValue(new Error('Schema 不存在: gone-id'))
    vi.mocked(listSchemasPaged).mockResolvedValue({
      items: [schemaFixture({ canDelete: true })],
      total: 1, page: 1, pageSize: 10,
    })
    const view = mountView()
    await flushPromises()

    await view.get('button.schema-action-more').trigger('click')
    await view.findAll('.test-dropdown-menu button').find((button) => button.text() === '删除')!.trigger('click')
    expect(view.find('.schema-delete-modal').exists()).toBe(true)

    const listCallsBefore = vi.mocked(listSchemasPaged).mock.calls.length
    await view.get('.schema-delete-modal footer .danger').trigger('click')
    await flushPromises()

    // 弹窗关闭且列表被重新拉取（脏行清除）
    expect(view.find('.schema-delete-modal').exists()).toBe(false)
    expect(vi.mocked(listSchemasPaged).mock.calls.length).toBeGreaterThan(listCallsBefore)
  })
})

describe('Schema 新增弹窗必填提示文案', () => {
  it('关系页：留空提交提示「请输入关系英文名/请选择起点实体/请选择终点实体」', async () => {
    const view = mountViewWithRealForm()
    await flushPromises()

    const relationTab = view.findAll('.schema-tabs__items button').find((button) => button.text() === '关系')
    await relationTab!.trigger('click')
    await view.get('.schema-tabs .primary').trigger('click')

    await view.get('.schema-create-modal footer .primary').trigger('click')
    await flushPromises()

    const text = view.get('.schema-create-modal').text()
    expect(text).toContain('请输入关系英文名')
    expect(text).toContain('请选择起点实体')
    expect(text).toContain('请选择终点实体')
    expect(text).not.toContain('请输入名称')
  })

  it('实体页：留空提交提示「请输入实体名」', async () => {
    const view = mountViewWithRealForm()
    await flushPromises()

    await view.get('.schema-tabs .primary').trigger('click')
    await view.get('.schema-create-modal footer .primary').trigger('click')
    await flushPromises()

    const text = view.get('.schema-create-modal').text()
    expect(text).toContain('请输入实体名')
    expect(text).not.toContain('请输入名称')
  })
})
