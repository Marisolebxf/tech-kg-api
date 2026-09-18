import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getSchemaOverview, listSchemasPaged, type SchemaDefinition } from '../../../api/schemaManagement'
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
        ASelect: SlotStub, AOption: SlotStub, ACheckbox: ACheckboxStub, ATooltip: SlotStub,
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

    const manageButton = view.findAll('button.schema-action-link').find((button) => button.text() === '属性管理')
    expect(manageButton).toBeTruthy()
    await manageButton!.trigger('click')

    const nameInput = view.get('input.property-add-form__name')
    await nameInput.setValue('f'.repeat(128))
    // setValue 触发重渲染会替换输入框节点，重新查询拿最新 class（旧 wrapper 是游离节点）
    expect(view.get('input.property-add-form__name').classes()).toContain('is-at-limit')
    expect(view.get('.property-section .limit-field-note').text()).toContain('属性名已达 128 字上限')
  })
})
