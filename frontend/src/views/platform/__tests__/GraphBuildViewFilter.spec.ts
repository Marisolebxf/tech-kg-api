import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import GraphBuildView from '../GraphBuildView.vue'
import type { WorkflowJob } from '../../../api/workflowOperations'

const mocks = vi.hoisted(() => ({
  listJobs: vi.fn(),
  createJob: vi.fn(),
  deleteJob: vi.fn(),
  triggerJob: vi.fn(),
  updateJobState: vi.fn(),
  getExecution: vi.fn(),
  getTask: vi.fn(),
}))

// 纯函数（deriveJobUnifiedStatus 等）保留真实实现，只拦网络请求
vi.mock('../../../api/workflowOperations', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../api/workflowOperations')>()),
  ...mocks,
}))
vi.mock('../../../api/schemaManagement', () => ({ schemaErrorMessage: vi.fn((e: unknown) => String(e)) }))
vi.mock('../../../api/jobEvents', () => ({ subscribeJobEvents: vi.fn(() => () => {}) }))
vi.mock('../../../stores/graphSpace', () => ({
  useGraphSpaceStore: () => ({ spaces: ['dev2'], current: 'dev2' }),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({
  IconSearch: { template: '<i />' },
  IconInfoCircle: { template: '<i />' },
}))

// v-model 透传 stub：native select/option 同步值，不依赖 Arco 内部实现（口径同 SchemaBrowserLimitHint）
const ASelectStub = defineComponent({
  props: ['modelValue', 'placeholder'],
  emits: ['update:modelValue'],
  template: `<select :value="modelValue" @change="$emit('update:modelValue', $event.target.value)"><slot /></select>`,
})
const AOptionStub = defineComponent({ props: ['value'], template: '<option :value="value"><slot /></option>' })
const AInputStub = defineComponent({
  props: ['modelValue', 'maxLength', 'placeholder'],
  emits: ['update:modelValue'],
  template: `<input :value="modelValue" @input="$emit('update:modelValue', $event.target.value)" />`,
})
const SlotStub = defineComponent({ template: '<div><slot /></div>' })

/** 三条任务：状态 分别 已完成/运行中/运行失败，类型 分别 extract/chain/upload。 */
function jobFixture(id: string, overrides: Partial<WorkflowJob>): WorkflowJob {
  return {
    id,
    name: `任务${id}`,
    taskType: 'extract',
    definitionIds: [`def-${id}`],
    definitionId: `def-${id}`,
    schedule: { kind: 'once' },
    owner: 'tester',
    status: '启用',
    createdAt: '2026-09-19 09:00:00',
    graphSpace: 'dev2',
    ...overrides,
  } as WorkflowJob
}

const JOBS = [
  jobFixture('j1', { lastExecutionStatus: 'COMPLETED' }),
  jobFixture('j2', { taskType: 'chain', lastExecutionStatus: 'RUNNING' }),
  jobFixture('j3', { taskType: 'upload', lastExecutionStatus: 'FAILED' }),
]

let wrapper: VueWrapper

function mountView() {
  wrapper = mount(GraphBuildView, {
    global: {
      components: { ASelect: ASelectStub, AOption: AOptionStub, AInput: AInputStub, ATooltip: SlotStub },
      stubs: { JobLaunchDialog: true, ListPagination: true, teleport: true },
    },
  })
  return wrapper
}

/** 真实任务行数：空列表时表格渲染「暂无任务」占位行（td.empty），不计入。 */
const rowCount = () => wrapper.findAll('tbody tr').filter((row) => !row.text().includes('暂无任务')).length

beforeEach(async () => {
  mocks.listJobs.mockResolvedValue({ items: JOBS, total: JOBS.length })
  mountView()
  await flushPromises()
})

afterEach(() => {
  wrapper.unmount()
})

describe('图谱构建任务筛选「未选择」伪选项（00843/00847）', () => {
  it('状态下拉提供「未选择」选项，value 为空串', () => {
    const statusSelect = wrapper.find('#graph-build-filter-status')
    const options = statusSelect.findAll('option')
    expect(options[0].attributes('value')).toBe('')
    expect(options[0].text()).toBe('未选择')
  })

  it('类型下拉提供「未选择」选项，value 为空串', () => {
    const typeSelect = wrapper.find('#graph-build-filter-type')
    const options = typeSelect.findAll('option')
    expect(options[0].attributes('value')).toBe('')
    expect(options[0].text()).toBe('未选择')
  })

  it('状态选真实值过滤、选「未选择」清空恢复全部', async () => {
    expect(rowCount()).toBe(3)
    const statusSelect = wrapper.find('#graph-build-filter-status')
    await statusSelect.setValue('已完成')
    expect(rowCount()).toBe(1)
    await statusSelect.setValue('')
    expect(rowCount()).toBe(3)
  })

  it('类型选真实值过滤、选「未选择」清空恢复全部', async () => {
    const typeSelect = wrapper.find('#graph-build-filter-type')
    await typeSelect.setValue('chain')
    expect(rowCount()).toBe(1)
    await typeSelect.setValue('')
    expect(rowCount()).toBe(3)
  })

  it('「未选择」与名称筛选可叠加：清空状态不影响名称条件', async () => {
    await wrapper.find('#graph-build-filter-name').setValue('任务j2')
    expect(rowCount()).toBe(1)
    const statusSelect = wrapper.find('#graph-build-filter-status')
    // 名称锁定 j2（运行中）后选「已完成」→ 交集为空
    await statusSelect.setValue('已完成')
    expect(rowCount()).toBe(0)
    // 选「未选择」只清空状态维度，名称条件仍在
    await statusSelect.setValue('')
    expect(rowCount()).toBe(1)
  })
})
