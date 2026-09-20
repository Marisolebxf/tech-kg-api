import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

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
    instanceCount: 0,
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
vi.mock('../../api/currentGraphSpace', () => ({ currentGraphSpace: () => 'gaoxing_test' }))
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
