import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { listAllSchemas, type SchemaDefinition } from '../../api/schemaManagement'

const selectedSpace = ref('gaoxing_test')
const writable = ref(true)

vi.mock('../../composables/use-space-permissions', () => ({ useSpacePermissions: () => ({ canWrite: writable }) }))

import JobLaunchDialog from '../JobLaunchDialog.vue'

// 批大小字符串绑定回归（复测捉虫：填了批大小提交报 c.value.trim is not a function）：
// Vue 的 vModelText 对 type="number" 无条件 parseFloat（castToNumber 不看 .number 修饰符），
// v-model 会把纯数字输入变成 number 存进 ref，提交链路按字符串处理即炸；
// 65 位数字也会被折叠成 1e+64，位数校验（FUNC-00872）失效。
// 抽屉内输入一律显式字符串赋值，ref 保持 string。
const { schema } = vi.hoisted(() => ({
  schema: {
    id: 'SCH-E2E',
    key: 'SCH-E2E',
    kind: 'entity',
    kindLabel: '实体',
    name: 'ent',
    label: '实体E2E',
    description: '',
    identityKey: 'id',
    attributeIdentityKey: 'name',
    attributeSource: '',
    version: 'v1',
    isCore: false,
    relationCategory: null,
    isSystem: false,
    createdBy: null,
    createdAt: null,
    updatedAt: null,
    script: { available: true },
    sources: [{ datasourceId: 'MYSQL-1', databaseName: 'gkx_element' }],
  },
}))

vi.mock('../../api/workflowOperations', () => ({ createJob: vi.fn(async () => ({ id: 'JOB-1', name: 'x' })) }))
vi.mock('../../api/schemaManagement', () => ({ listAllSchemas: vi.fn(async () => [schema]) }))
vi.mock('../../api/currentUser', () => ({ currentUserId: () => 'user-e2e' }))
vi.mock('../../api/currentGraphSpace', () => ({ currentGraphSpace: () => selectedSpace.value }))
vi.mock('../../api/mysqlDatasource', () => ({
  listMysqlDatasources: vi.fn(async () => []),
  listMysqlDatabases: vi.fn(async () => ['gkx_element']),
}))

const ASelectStub = {
  props: ['modelValue', 'options', 'loading', 'placeholder', 'allowSearch', 'allowClear'],
  emits: ['update:modelValue', 'change'],
  template: '<select :value="modelValue ?? \'\'" @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\', $event.target.value)"><slot /></select>',
}
const AOptionStub = { props: ['value'], template: '<option :value="value"><slot /></option>' }
const ARadioGroupStub = {
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<select data-test="execute-mode" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
}
const ARadioStub = { props: ['value'], template: '<option :value="value"><slot /></option>' }

function mountDialog() {
  return mount(JobLaunchDialog, {
    props: { open: true },
    global: {
      stubs: {
        teleport: true,
        'a-select': ASelectStub,
        'a-option': AOptionStub,
        'a-radio-group': ARadioGroupStub,
        'a-radio': ARadioStub,
        'a-checkbox': true,
      },
    },
  })
}

/** 选中目标 Schema（第 2 个 a-select：taskType 之后就是 extractSchemaId） */
async function pickSchema(wrapper: ReturnType<typeof mountDialog>) {
  const selects = wrapper.findAllComponents(ASelectStub)
  selects[1].vm.$emit('update:modelValue', 'SCH-E2E')
  await flushPromises()
}

async function fillBasics(wrapper: ReturnType<typeof mountDialog>) {
  await wrapper.find('input[aria-label="如：论文-专家抽取"]').setValue('周期任务E2E')
  await pickSchema(wrapper)
  const batch = wrapper.find('input[aria-label="500"]')
  await batch.setValue('500')
  return batch
}

beforeEach(() => {
  vi.clearAllMocks()
  selectedSpace.value = 'gaoxing_test'
  writable.value = true
  vi.mocked(listAllSchemas).mockResolvedValue([schema as SchemaDefinition])
})

describe('新建任务弹窗 · 批大小字符串绑定', () => {
  it('填了批大小可正常创建周期任务（数字不再炸 .trim，提交为 number）', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    await fillBasics(wrapper)

    // 执行模式切周期性：schedule 走 cron 分支（每天 02:00 → `0 2 * * *`）
    wrapper.findComponent(ARadioGroupStub).vm.$emit('update:modelValue', 'recurring')
    await flushPromises()

    const { createJob } = await import('../../api/workflowOperations')
    await wrapper.find('footer .primary').trigger('click')
    await flushPromises()

    expect(createJob).toHaveBeenCalledWith(expect.objectContaining({
      batchSize: 500,
      schedule: { kind: 'cron', cron: '0 2 * * *', timezone: 'Asia/Shanghai' },
      runNow: false,
    }))
    wrapper.unmount()
  })

  it('批大小留空提交 undefined；65 位数字触发位数校验且拦截提交', async () => {
    const { createJob } = await import('../../api/workflowOperations')
    const wrapper = mountDialog()
    await flushPromises()

    await wrapper.find('input[aria-label="如：论文-专家抽取"]').setValue('留空批大小')
    await pickSchema(wrapper)
    await wrapper.find('footer .primary').trigger('click')
    await flushPromises()
    expect(createJob).toHaveBeenCalledWith(expect.objectContaining({ batchSize: undefined }))

    // 65 位：位数校验文案 + 按钮置灰（FUNC-00872）
    const batch = wrapper.find('input[aria-label="500"]')
    await batch.setValue('1'.repeat(65))
    expect(wrapper.find('.field-error').text()).toContain('数字输入长度不能超过64个字符')
    expect(wrapper.find('footer .primary').attributes('disabled')).toBeDefined()
    wrapper.unmount()
  })
})


describe('新建任务弹窗 · 统一空间与新鲜 Schema', () => {
  it('每次打开重新加载并展示全局空间标签，不提供独立图空间选择', async () => {
    const wrapper = mountDialog()
    await flushPromises()
    expect(listAllSchemas).toHaveBeenCalledWith('user-e2e', 'gaoxing_test')
    expect(wrapper.find('.space-scope-chip').text()).toBe('图空间：gaoxing_test')
    expect(wrapper.find('select[aria-label="图空间"]').exists()).toBe(false)
    await wrapper.setProps({ open: false })
    vi.mocked(listAllSchemas).mockResolvedValueOnce([{ ...schema, id: 'NEW', label: '新脚本' } as SchemaDefinition])
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(listAllSchemas).toHaveBeenCalledTimes(2)
    expect(wrapper.text()).toContain('新脚本')
    wrapper.unmount()
  })

  it('切换空间时立即重查，旧空间迟到响应不能覆盖新列表', async () => {
    let resolveOld!: (schemas: SchemaDefinition[]) => void
    vi.mocked(listAllSchemas)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce([{ ...schema, id: 'NEW', label: '新空间脚本' } as SchemaDefinition])
    const wrapper = mountDialog()
    await flushPromises()
    selectedSpace.value = 'dev2'
    await flushPromises()
    expect(listAllSchemas).toHaveBeenLastCalledWith('user-e2e', 'dev2')
    expect(wrapper.find('.space-scope-chip').text()).toBe('图空间：dev2')
    expect(wrapper.text()).toContain('新空间脚本')
    resolveOld([schema as SchemaDefinition])
    await flushPromises()
    expect(wrapper.text()).toContain('新空间脚本')
    expect(wrapper.text()).not.toContain('实体E2E')
    wrapper.unmount()
  })

  it('上次打开的请求未完成时关闭重开也必须重新查询', async () => {
    let resolveOld!: (schemas: SchemaDefinition[]) => void
    vi.mocked(listAllSchemas)
      .mockImplementationOnce(() => new Promise((resolve) => { resolveOld = resolve }))
      .mockResolvedValueOnce([])
    const wrapper = mountDialog()
    await wrapper.setProps({ open: false })
    await wrapper.setProps({ open: true })
    await flushPromises()
    expect(listAllSchemas).toHaveBeenCalledTimes(2)
    resolveOld([schema as SchemaDefinition])
    await flushPromises()
    expect(wrapper.text()).toContain('暂无可抽取 Schema')
    expect(wrapper.text()).not.toContain('实体E2E')
    wrapper.unmount()
  })

  it('公共只读空间可以查看 Schema，但不能创建任务', async () => {
    writable.value = false
    const wrapper = mountDialog()
    await flushPromises()
    await fillBasics(wrapper)
    expect(wrapper.find('footer .primary').attributes('disabled')).toBeDefined()
    await wrapper.find('footer .primary').trigger('click')
    const { createJob } = await import('../../api/workflowOperations')
    expect(createJob).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
