import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { Popover as APopover } from '@arco-design/web-vue'
import { defineComponent } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import GraphBuildView from '../GraphBuildView.vue'
import type { WorkflowJob } from '../../../api/workflowOperations'

const permission = vi.hoisted(() => ({ writable: true }))

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
  useGraphSpaceStore: () => ({ spaces: ['dev2'], current: 'dev2', currentItem: { name: 'dev2', groupKind: 'public' }, canWrite: () => permission.writable, canReview: () => permission.writable }),
}))
vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({
  IconSearch: { template: '<i />' },
  IconInfoCircle: { template: '<i />' },
  IconRefresh: { template: '<i />' },
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
      // 脚本列悬停浮层：槽位直渲染便于断言（口径同 entity-list-search.spec）
      stubs: {
        JobLaunchDialog: true,
        ListPagination: true,
        teleport: true,
        Popover: { props: ['trigger', 'position', 'contentClass'], template: '<div class="popover-stub"><slot /><div class="popover-content"><slot name="content" /></div></div>' },
      },
    },
  })
  return wrapper
}

/** 真实任务行数：空列表时表格渲染「暂无任务」占位行（td.empty），不计入。 */
const rowCount = () => wrapper.findAll('tbody tr').filter((row) => !row.text().includes('暂无任务')).length

/** 按任务名定位行。 */
const rowOf = (id: string) =>
  wrapper.findAll('tbody tr').filter((row) => row.text().includes(`任务${id}`))[0]

/** 重建列表并挂载（各用例自备 fixtures 时用）。 */
async function remountWith(items: WorkflowJob[]) {
  wrapper.unmount()
  mocks.listJobs.mockResolvedValue({ items, total: items.length })
  mountView()
  await flushPromises()
}

beforeEach(async () => {
  permission.writable = true
  mocks.listJobs.mockResolvedValue({ items: JOBS, total: JOBS.length })
  mountView()
  await flushPromises()
})

afterEach(() => {
  wrapper.unmount()
})

describe('图谱构建任务筛选与清空', () => {
  it('状态下拉仅提供真实状态，不提供空值选项', () => {
    const statusSelect = wrapper.find('#graph-build-filter-status')
    const options = statusSelect.findAll('option')
    expect(options.map(option => option.text())).toEqual(['未运行', '运行中', '已暂停', '已完成', '运行异常', '运行失败'])
    expect(options.every(option => option.attributes('value') !== '')).toBe(true)
  })

  it('类型下拉仅提供真实类型，不提供空值选项', () => {
    const typeSelect = wrapper.find('#graph-build-filter-type')
    const options = typeSelect.findAll('option')
    expect(options.map(option => option.attributes('value'))).toEqual(['extract', 'chain'])
  })

  it('状态选择后可通过清除按钮恢复全部', async () => {
    expect(rowCount()).toBe(3)
    const statusSelect = wrapper.find('#graph-build-filter-status')
    await statusSelect.setValue('已完成')
    expect(rowCount()).toBe(1)
    wrapper.findAllComponents(ASelectStub)[0].vm.$emit('update:modelValue', undefined)
    await flushPromises()
    expect(rowCount()).toBe(3)
  })

  it('类型选择后可通过清除按钮恢复全部', async () => {
    const typeSelect = wrapper.find('#graph-build-filter-type')
    await typeSelect.setValue('chain')
    expect(rowCount()).toBe(1)
    wrapper.findAllComponents(ASelectStub)[1].vm.$emit('update:modelValue', undefined)
    await flushPromises()
    expect(rowCount()).toBe(3)
  })

  it('清空状态不影响已提交的名称筛选条件', async () => {
    await wrapper.find('#graph-build-filter-name').setValue('任务j2')
    expect(rowCount()).toBe(3)
    await wrapper.find('.gb-filters').trigger('submit')
    expect(rowCount()).toBe(1)
    const statusSelect = wrapper.find('#graph-build-filter-status')
    // 名称锁定 j2（运行中）后选「已完成」→ 交集为空
    await statusSelect.setValue('已完成')
    expect(rowCount()).toBe(0)
    // 清除按钮只清空状态维度，名称条件仍在
    wrapper.findAllComponents(ASelectStub)[0].vm.$emit('update:modelValue', undefined)
    await flushPromises()
    expect(rowCount()).toBe(1)
  })

  it('查询只在提交后执行，清空输入并查询可恢复全部任务', async () => {
    const input = wrapper.find('#graph-build-filter-name')
    await input.setValue('任务j1')
    expect(rowCount()).toBe(3)
    await wrapper.find('.gb-filters').trigger('submit')
    expect(rowCount()).toBe(1)
    await input.setValue('')
    expect(rowCount()).toBe(1)
    await wrapper.find('.gb-filters').trigger('submit')
    expect(rowCount()).toBe(3)
  })

  it('ABNORMAL 独立成「运行异常」桶：有专属状态卡，不被「运行失败」筛选命中', async () => {
    // 抽取完成但含行级失败记录 = 异常，只有完全跑崩（FAILED）才是运行失败
    wrapper.unmount()
    mocks.listJobs.mockResolvedValue({
      items: [
        jobFixture('j9', { lastExecutionStatus: 'ABNORMAL' }),
        jobFixture('j10', { lastExecutionStatus: 'FAILED' }),
      ],
      total: 2,
    })
    mountView()
    await flushPromises()
    expect(wrapper.find('.gb-summary').text()).toContain('运行异常')
    const statusSelect = wrapper.find('#graph-build-filter-status')
    await statusSelect.setValue('运行失败')
    expect(rowCount()).toBe(1) // 只有真跑崩的 j10
    await statusSelect.setValue('运行异常')
    expect(rowCount()).toBe(1) // j9
  })
})

describe('重新执行入口的状态口径（问题②：运行异常也提供重跑）', () => {

  it('运行异常行平铺「重新执行」，点击调用触发接口', async () => {
    wrapper.unmount()
    mocks.listJobs.mockResolvedValue({ items: [jobFixture('j9', { lastExecutionStatus: 'ABNORMAL' })], total: 1 })
    mocks.triggerJob.mockResolvedValue({ id: 'exec-1' })
    mountView()
    await flushPromises()
    const trigger = rowOf('j9').findAll('button').find((b) => b.text() === '重新执行')
    expect(trigger).toBeTruthy()
    await trigger!.trigger('click')
    await flushPromises()
    expect(mocks.triggerJob).toHaveBeenCalledWith('j9')
  })

  it('已完成行不出现执行/重新执行（产品决策：不提供重复执行）', async () => {
    wrapper.unmount()
    mocks.listJobs.mockResolvedValue({ items: [jobFixture('j1', { lastExecutionStatus: 'COMPLETED' })], total: 1 })
    mountView()
    await flushPromises()
    const labels = rowOf('j1').findAll('button').map((b) => b.text())
    expect(labels).not.toContain('执行')
    expect(labels).not.toContain('重新执行')
  })

  it('未运行行仍显示「执行」而非「重新执行」', async () => {
    wrapper.unmount()
    mocks.listJobs.mockResolvedValue({ items: [jobFixture('j11', {})], total: 1 })
    mountView()
    await flushPromises()
    const labels = rowOf('j11').findAll('button').map((b) => b.text())
    expect(labels).toContain('执行')
    expect(labels).not.toContain('重新执行')
  })
})

describe('暂停操作的对象口径（问题：运行失败还能暂停 → 改名消歧）', () => {
  const cron = { kind: 'cron' as const, cron: '10 17 * * *' }

  it('运行失败的周期任务显示「暂停调度」而非「暂停」，悬停说明停的是调度', async () => {
    await remountWith([jobFixture('jc1', { schedule: cron, lastExecutionStatus: 'FAILED' })])
    const labels = rowOf('jc1').findAll('button').map((b) => b.text())
    expect(labels).toContain('暂停调度')
    expect(labels).not.toContain('暂停')
    const pause = rowOf('jc1').findAll('button').find((b) => b.text() === '暂停调度')!
    expect(pause.attributes('title')).toContain('停止后续自动触发')
  })

  it('运行中的周期任务仍显示「暂停」（挂起当前执行）', async () => {
    await remountWith([jobFixture('jc2', { schedule: cron, lastExecutionStatus: 'RUNNING' })])
    const labels = rowOf('jc2').findAll('button').map((b) => b.text())
    expect(labels).toContain('暂停')
    expect(labels).not.toContain('暂停调度')
  })

  it('运行失败的单次任务不出现任何暂停入口', async () => {
    await remountWith([jobFixture('j3', { lastExecutionStatus: 'FAILED' })])
    const labels = rowOf('j3').findAll('button').map((b) => b.text())
    expect(labels).not.toContain('暂停')
    expect(labels).not.toContain('暂停调度')
  })

  it('已暂停周期任务（无运行中执行）显示「恢复调度」', async () => {
    await remountWith([jobFixture('jc3', { schedule: cron, lastExecutionStatus: 'FAILED', status: '暂停' })])
    const labels = rowOf('jc3').findAll('button').map((b) => b.text())
    expect(labels).toContain('恢复调度')
    expect(labels).not.toContain('恢复')
  })

  it('点击「暂停调度」调用状态接口停调度，不触发挂起确认轮询', async () => {
    await remountWith([jobFixture('jc1', { schedule: cron, lastExecutionStatus: 'FAILED' })])
    mocks.updateJobState.mockResolvedValue(jobFixture('jc1', { schedule: cron, lastExecutionStatus: 'FAILED', status: '暂停' }))
    const pause = rowOf('jc1').findAll('button').find((b) => b.text() === '暂停调度')!
    await pause.trigger('click')
    await flushPromises()
    expect(mocks.updateJobState).toHaveBeenCalledWith('jc1', false)
    expect(mocks.getExecution).not.toHaveBeenCalled()
  })
})

it('公共只读时保留任务查看、查询与刷新，执行和删除置灰', async () => {
  wrapper.unmount()
  permission.writable = false
  localStorage.setItem('tech-kg-graph-build-space-scope', '__all__')
  mocks.listJobs.mockResolvedValue({ items: [...JOBS, jobFixture('other', { graphSpace: 'private-other' })] })
  mountView()
  await flushPromises()
  expect(wrapper.text()).not.toContain('任务other')
  expect(wrapper.find('[title*="按图空间筛选"]').exists()).toBe(false)
  const create = wrapper.findAll('button').find(button => button.text().includes('新建任务'))!
  expect(create.attributes()).toHaveProperty('disabled')
  const execute = wrapper.findAll('button').find(button => button.text() === '重新执行')!
  expect(execute.attributes()).toHaveProperty('disabled')
  const detail = wrapper.findAll('button').find(button => button.text() === '查看详情')!
  expect(detail.attributes('disabled')).toBeUndefined()
  const refresh = wrapper.findAll('button').find(button => button.text().includes('刷新'))!
  expect(refresh.attributes('disabled')).toBeUndefined()
  localStorage.removeItem('tech-kg-graph-build-space-scope')
})


it('未登记归属的历史任务不能按空间列表首项归入当前空间', async () => {
  wrapper.unmount()
  mocks.listJobs.mockResolvedValue({ items: [jobFixture('legacy', { graphSpace: undefined }), JOBS[0]] })
  mountView()
  await flushPromises()
  expect(rowCount()).toBe(1)
  expect(wrapper.text()).not.toContain('任务legacy')
  expect(wrapper.text()).toContain('任务j1')
})

it('脚本列悬停浮层列出全部脚本（按执行顺序，替代原生 title）', async () => {
  wrapper.unmount()
  mocks.listJobs.mockResolvedValue({ items: [jobFixture('script', { taskType: 'chain', definitionIds: ['first.script', 'second.script'] })] })
  mountView()
  await flushPromises()
  const popover = wrapper.findComponent(APopover)
  expect(popover.props('trigger')).toEqual(['hover', 'click'])
  expect(popover.props('position')).toBe('bl')
  expect(popover.props('contentClass')).toBe('gb-script-popover')
  const names = wrapper.findAll('.gb-script-popover__name').map((item) => item.text())
  expect(names).toEqual(['first.script', 'second.script'])
  expect(wrapper.find('.gb-script-popover__title').text()).toBe('共 2 个脚本（按执行顺序）')
})

it('公共空间只读显示管理员操作提醒，管理员不显示', async () => {
  expect(wrapper.find('.space-readonly-bar').exists()).toBe(false)
  wrapper.unmount()
  permission.writable = false
  mountView()
  await flushPromises()
  expect(wrapper.get('.space-readonly-bar').text()).toBe('当前图空间为共享生产空间：图谱构建仅可查看，操作需管理员执行。')
})
