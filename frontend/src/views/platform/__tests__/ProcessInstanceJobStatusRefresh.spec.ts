import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProcessInstanceDetailView from '../ProcessInstanceDetailView.vue'

/** 复现（2026-10-21 job-1e89e0b6fbc4）：链执行含 7 条逐行失败被标 ABNORMAL，
 *  详情页顶部「执行状态」格取 job.lastExecutionStatus（开页时 RUNNING）——
 *  执行轮询把执行行翻成终态后无人补拉 job，顶部停在「运行中」，与执行历史
 *  的「异常」同屏矛盾。修复：轮询观察到执行离开运行态时补拉一次 job。 */
const state = vi.hoisted(() => ({
  route: { params: {} as Record<string, string>, query: {} as Record<string, string> },
  currentSpace: 'gkx_verify_1',
  spaceItems: [] as Array<{ name: string; groupKind: string }>,
  job: null as Record<string, unknown> | null,
  executions: [] as Array<Record<string, unknown>>,
  task: null as Record<string, unknown> | null,
  jobCalls: 0,
}))
vi.mock('../../../stores/graphSpace', () => ({ useGraphSpaceStore: () => ({
  get current() { return state.currentSpace },
  get items() { return state.spaceItems },
  canWrite: () => true,
  canReview: () => true,
}) }))
vi.mock('vue-router', () => ({ useRoute: () => state.route, useRouter: () => ({ replace: vi.fn() }) }))
vi.mock('../../../api/workflowOperations', async (original) => ({
  ...await original<typeof import('../../../api/workflowOperations')>(),
  // axios 每次返回新 JSON 对象；mock 返回同一实例会被 Vue ref 的 raw 值比较
  // 去重（同 raw 再赋值不触发响应），必须克隆——否则「执行翻终态」永远传不到视图
  getJob: vi.fn(async () => {
    state.jobCalls += 1
    return { job: { ...state.job }, executions: state.executions.map((e) => ({ ...e })) }
  }),
  getExecution: vi.fn(async (id: string) =>
    ({ ...state.executions.find((e) => e.id === id) })),
  getTask: vi.fn(async () => state.task),
  listExecutions: vi.fn(async () => ({ items: state.executions.map((e) => ({ ...e })), total: state.executions.length })),
  getProductionReviews: vi.fn(async () => ({ items: [], total: 0, page: 1, pageSize: 1 })),
}))

const RouterLinkStub = { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' }

function mountView() {
  return mount(ProcessInstanceDetailView, { global: { components: { RouterLink: RouterLinkStub } } })
}

describe('任务详情顶部执行状态随执行终态补拉 job', () => {
  beforeEach(() => {
    state.route = { params: { jobId: 'job-x' }, query: {} }
    state.job = {
      id: 'job-x', name: '链任务', graphSpace: 'gkx_verify_1', taskType: 'chain', status: '启用',
      lastExecutionStatus: 'RUNNING', definitionIds: [], definitionId: 'wf-chain-x',
      schedule: { kind: 'once' }, owner: 'tester', createdAt: '2026-10-21 09:39:00',
    }
    state.executions = [{
      id: 'EXEC-1', definitionId: 'wf-chain-x', workflowId: 'chain-x-1', status: 'RUNNING',
      startedAt: '2026-10-21 09:39:38', triggerSource: 'MANUAL', taskId: 'PI-1',
    }]
    state.task = {
      id: 'PI-1', batchId: 'UPD-20261021', stage: '图谱构建', kind: '实体',
      objectId: 'chain-x-1', objectName: '链任务', objectType: '工作流实例', action: '作业执行',
      sourceTable: '', sourceRecordId: 'latest-cursor', rule: 'wf-chain-x', confidence: '',
      result: '工作流已下发', status: '处理中', taskStatus: '执行中', dataDomain: '综合数据域',
      processedAt: '2026-10-21 09:39:38', currentStep: '数据接入', steps: [],
      workflowType: 'kg.schema.extract.chain', workflowId: 'chain-x-1', runId: 'run-1',
      jobId: 'job-x', graphSpace: 'gkx_verify_1', output: null, logs: [],
    }
    state.jobCalls = 0
  })
  afterEach(() => { vi.useRealTimers() })

  it('执行轮询翻成 ABNORMAL 后补拉 job，顶部离开「运行中」显示「运行异常」', async () => {
    vi.useFakeTimers()
    const wrapper = mountView()
    await flushPromises()
    // 开页：getJob 一次，顶部按开页口径显示「运行中」
    expect(state.jobCalls).toBe(1)
    expect(wrapper.get('.job-config-panel .exec-status-cell').text()).toBe('运行中')

    // 执行在 Temporal 侧已终态（含逐行失败 → ABNORMAL），服务端对账后的聚合随之翻转
    ;(state.executions[0] as Record<string, unknown>).status = 'ABNORMAL'
    ;(state.job as Record<string, unknown>).lastExecutionStatus = 'ABNORMAL'

    await vi.advanceTimersByTimeAsync(5000)
    await flushPromises()

    expect(state.jobCalls).toBe(2)
    expect(wrapper.get('.job-config-panel .exec-status-cell').text()).toBe('运行异常')
    wrapper.unmount()
  })

  it('执行一直运行中时只按轮询拉执行，不重复拉 job', async () => {
    vi.useFakeTimers()
    const wrapper = mountView()
    await flushPromises()
    expect(state.jobCalls).toBe(1)

    await vi.advanceTimersByTimeAsync(15000)
    await flushPromises()

    expect(state.jobCalls).toBe(1)
    expect(wrapper.get('.job-config-panel .exec-status-cell').text()).toBe('运行中')
    wrapper.unmount()
  })
})
