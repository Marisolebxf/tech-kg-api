import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import ProcessInstanceDetailView from '../ProcessInstanceDetailView.vue'

/** 复刻用户实报场景（真实数据形态）：chain 任务（kg.schema.extract.chain）被
 *  Temporal 历史淘汰后 steps/pipeline/output 全空，144 条 C 类失败案按快照
 *  锚定在早前执行的 jobId/executionId 上；按「最新执行的任务」或被丢弃的
 *  sourceTaskId 参数圈案都会数出 0 条，误报「执行级失败，无失败行记录可重跑」。 */
const state = vi.hoisted(() => ({
  route: { params: {} as Record<string, string>, query: {} as Record<string, string> },
  currentSpace: 'gkx_verify_1',
  spaceItems: [] as Array<{ name: string; groupKind: string }>,
  job: null as Record<string, unknown> | null,
  executions: [] as Array<Record<string, unknown>>,
  task: null as Record<string, unknown> | null,
  reviewTotal: 0,
  reviewCalls: [] as Array<Record<string, unknown>>,
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
  getJob: vi.fn(async () => ({ job: state.job, executions: state.executions })),
  getExecution: vi.fn(async (id: string) => state.executions.find((e) => e.id === id)),
  getTask: vi.fn(async () => state.task),
  listExecutions: vi.fn(async () => ({ items: state.executions, total: state.executions.length })),
  getProductionReviews: vi.fn(async (params: Record<string, unknown> = {}) => {
    state.reviewCalls.push(params)
    return { items: [], total: state.reviewTotal, page: 1, pageSize: 1 }
  }),
}))

const RouterLinkStub = { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' }

function baseTask(overrides: Record<string, unknown> = {}) {
  return {
    id: 'PI-20261012-96E99E', batchId: 'UPD-20261012', stage: '图谱构建', kind: '实体',
    objectId: 'chain-9e84ebcd9fb1-791a', objectName: 'gkx验证-实体链', objectType: '工作流实例',
    action: '作业执行', sourceTable: '', sourceRecordId: 'latest-cursor', rule: 'wf-chain-9e84',
    confidence: '', result: '执行已终止', status: '处理中', taskStatus: '执行出错',
    dataDomain: '综合数据域', processedAt: '2026-10-12 10:53:06', currentStep: '数据接入',
    steps: [], workflowType: 'kg.schema.extract.chain', workflowId: 'chain-9e84ebcd9fb1-791a',
    jobId: 'job-9e84ebcd9fb1', graphSpace: 'gkx_verify_1', output: null, logs: [],
    ...overrides,
  }
}

function baseJob() {
  return {
    id: 'job-9e84ebcd9fb1', name: 'gkx验证-实体链', graphSpace: 'gkx_verify_1', taskType: 'chain',
    status: '启用', lastExecutionStatus: 'TERMINATED', definitionIds: [], definitionId: 'wf-chain-9e84',
    schedule: { kind: 'once' }, owner: 'tester', createdAt: '2026-10-11 10:00:00',
  }
}

function mountView() {
  return mount(ProcessInstanceDetailView, { global: { components: { RouterLink: RouterLinkStub } } })
}

describe('任务详情「进入人工处理」入口圈案', () => {
  beforeEach(() => {
    state.route = { params: {}, query: {} }
    state.currentSpace = 'gkx_verify_1'
    state.spaceItems = []
    state.job = null
    state.executions = []
    state.task = null
    state.reviewTotal = 0
    state.reviewCalls = []
  })

  it('job 详情按 jobId 圈全部执行的失败案：chain 任务无步骤数据仍显示入口与计数', async () => {
    state.route = { params: { jobId: 'job-9e84ebcd9fb1' }, query: {} }
    state.job = baseJob()
    state.executions = [{
      id: 'EXEC-17EABD5092224497', definitionId: 'wf-chain-9e84', workflowId: 'chain-9e84ebcd9fb1-791a',
      status: 'TERMINATED', startedAt: '2026-10-12 10:53:06', triggerSource: 'MANUAL', taskId: 'PI-20261012-96E99E',
    }]
    state.task = baseTask()
    state.reviewTotal = 144
    const wrapper = mountView()
    await flushPromises()
    expect(state.reviewCalls).toHaveLength(1)
    expect(state.reviewCalls[0]).toEqual({ category: 'C', keyword: 'job-9e84ebcd9fb1', page: 1, pageSize: 1, graphSpace: 'gkx_verify_1' })
    const link = wrapper.get('.step-head-actions a')
    expect(JSON.parse(link.attributes('data-to'))).toEqual({ path: '/manual-review', query: { category: 'C', keyword: 'job-9e84ebcd9fb1' } })
    expect(link.text()).toContain('进入人工处理（本任务 144 条）')
    expect(wrapper.find('.step-head-review-note').exists()).toBe(false)
    // 任务回写「执行出错」= 跑崩：结果卡如实说未运行完成，不再落「执行成功」分支
    expect(wrapper.text()).toContain('任务未运行完成，尚未产生可验收结果')
    wrapper.unmount()
  })

  it('确无逐行审核案时计数为 0，入口改为执行级失败说明文案', async () => {
    state.route = { params: { jobId: 'job-9e84ebcd9fb1' }, query: {} }
    state.job = baseJob()
    state.executions = [{
      id: 'EXEC-17EABD5092224497', definitionId: 'wf-chain-9e84', workflowId: 'chain-9e84ebcd9fb1-791a',
      status: 'TERMINATED', startedAt: '2026-10-12 10:53:06', triggerSource: 'MANUAL', taskId: 'PI-20261012-96E99E',
    }]
    state.task = baseTask()
    state.reviewTotal = 0
    const wrapper = mountView()
    await flushPromises()
    expect(state.reviewCalls).toHaveLength(1)
    // 队列接口没有 sourceTaskId 参数，传了也会被静默丢弃（防回归到全量口径）
    expect(state.reviewCalls[0]).not.toHaveProperty('sourceTaskId')
    expect(wrapper.find('.step-head-actions a').exists()).toBe(false)
    expect(wrapper.get('.step-head-review-note').text()).toContain('执行级失败')
    wrapper.unmount()
  })

  it('任务直达视图按任务回写的 jobId 圈案，不误用定义下最新执行', async () => {
    state.route = { params: { instanceId: 'PI-20261012-96E99E' }, query: {} }
    state.task = baseTask()
    // 定义下最新执行属于另一个任务（重跑/新一轮触发场景）：按最新执行圈案会数出 0 条
    state.executions = [{
      id: 'EXEC-8A7AC45649764301', definitionId: 'wf-chain-9e84', workflowId: 'chain-9e84ebcd9fb1-791a',
      status: 'TERMINATED', startedAt: '2026-10-12 18:15:44', triggerSource: 'MANUAL', taskId: 'PI-20261012-9360D4',
    }]
    state.reviewTotal = 144
    const wrapper = mountView()
    await flushPromises()
    expect(state.reviewCalls).toHaveLength(1)
    expect(state.reviewCalls[0]).toEqual({ category: 'C', keyword: 'job-9e84ebcd9fb1', page: 1, pageSize: 1, graphSpace: 'gkx_verify_1' })
    const link = wrapper.get('.step-head-actions a')
    expect(JSON.parse(link.attributes('data-to')).query.keyword).toBe('job-9e84ebcd9fb1')
    wrapper.unmount()
  })

  it('全局空间与任务空间不一致时跳过计数请求（避免强制过滤清零/403），入口退化为不带计数', async () => {
    state.route = { params: { jobId: 'job-9e84ebcd9fb1' }, query: {} }
    state.job = baseJob()
    state.executions = [{
      id: 'EXEC-17EABD5092224497', definitionId: 'wf-chain-9e84', workflowId: 'chain-9e84ebcd9fb1-791a',
      status: 'TERMINATED', startedAt: '2026-10-12 10:53:06', triggerSource: 'MANUAL', taskId: 'PI-20261012-96E99E',
    }]
    state.task = baseTask()
    state.currentSpace = 'gaoxing_test'
    state.reviewTotal = 144
    const wrapper = mountView()
    await flushPromises()
    expect(state.reviewCalls).toHaveLength(0)
    const link = wrapper.get('.step-head-actions a')
    expect(link.text()).toContain('进入人工处理')
    expect(link.text()).not.toContain('条')
    expect(wrapper.find('.step-head-review-note').exists()).toBe(false)
    wrapper.unmount()
  })

  it('非抽取任务不显示 C 类队列入口，也不误显示执行级失败文案', async () => {
    state.route = { params: { instanceId: 'PI-20261012-PY0001' }, query: {} }
    state.task = baseTask({ id: 'PI-20261012-PY0001', workflowType: 'kg.custom.python', jobId: undefined })
    const wrapper = mountView()
    await flushPromises()
    expect(state.reviewCalls).toHaveLength(0)
    expect(wrapper.find('.step-head-actions a').exists()).toBe(false)
    expect(wrapper.find('.step-head-review-note').exists()).toBe(false)
    wrapper.unmount()
  })
})
