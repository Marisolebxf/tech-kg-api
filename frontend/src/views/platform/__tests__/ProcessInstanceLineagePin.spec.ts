import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ProcessInstanceDetailView from '../ProcessInstanceDetailView.vue'

/** 昨日新增行级跳转（job-detail?exec=&tab=lineage&src=&n=）：落对执行、落对
 *  页签，来源结果表里锚中的行（来源表+写入数双匹配，同名表可来自多个 Schema）
 *  高亮 is-pinned 并滚动到视口，用户落地即见「行上的数」——不再在概况页签里
 *  找只有合计写入的大数。 */
const state = vi.hoisted(() => ({
  route: { params: {} as Record<string, string>, query: {} as Record<string, string> },
  currentSpace: 'gkx_verify_1',
  spaceItems: [] as Array<{ name: string; groupKind: string }>,
  job: null as Record<string, unknown> | null,
  executions: [] as Array<Record<string, unknown>>,
  task: null as Record<string, unknown> | null,
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
  getProductionReviews: vi.fn(async () => ({ items: [], total: 0, page: 1, pageSize: 1 })),
}))

const RouterLinkStub = { props: ['to'], template: '<a :data-to="JSON.stringify(to)"><slot /></a>' }

/** chain 执行：两个 Schema 都读 gkx.dwd_zh_paper（同名来源表），另有 placeholder
 *  来源——锚点必须靠写入数区分到唯一一行。 */
function chainExecution() {
  return {
    id: 'EXEC-2C5669A668E04AED', definitionId: 'wf-chain-9e84', workflowId: 'chain-9e84ebcd9fb1-791a',
    status: 'COMPLETED', startedAt: '2026-10-13 23:39:27', triggerSource: 'MANUAL', taskId: 'PI-20261013-A94589',
    output: {
      chain: true,
      steps: {
        'schema:paper': { output: { sources: [{ table: 'gkx.dwd_zh_paper', written: 100900, batches: 51, rows: 100900 }] } },
        'schema:datasource': { output: { sources: [
          { table: 'gkx.placeholder', written: 39, batches: 1, rows: 1 },
          { table: 'gkx.dwd_zh_paper', written: 39, batches: 1, rows: 1 },
        ] } },
      },
    },
  }
}

function baseJob() {
  return {
    id: 'job-9e84ebcd9fb1', name: 'gkx验证-实体链', graphSpace: 'gkx_verify_1', taskType: 'chain',
    status: '启用', lastExecutionStatus: 'COMPLETED', definitionIds: [], definitionId: 'wf-chain-9e84',
    schedule: { kind: 'once' }, owner: 'tester', createdAt: '2026-10-11 10:00:00',
  }
}

function baseTask() {
  return {
    id: 'PI-20261013-A94589', batchId: 'UPD-20261013', stage: '图谱构建', kind: '实体',
    objectId: 'chain-9e84ebcd9fb1-791a', objectName: 'gkx验证-实体链', objectType: '工作流实例',
    action: '作业执行', sourceTable: '', sourceRecordId: 'latest-cursor', rule: 'wf-chain-9e84',
    confidence: '', result: '执行完成', status: '已完成', taskStatus: '已通过',
    dataDomain: '综合数据域', processedAt: '2026-10-14 00:30:00', currentStep: '数据接入',
    steps: [], workflowType: 'kg.schema.extract.chain', workflowId: 'chain-9e84ebcd9fb1-791a',
    jobId: 'job-9e84ebcd9fb1', graphSpace: 'gkx_verify_1', output: null, logs: [],
  }
}

function mountView() {
  // 挂到真实 document：组件内用 document.querySelector 定位锚行滚动，
  // 离屏挂载（默认 detach）查不到，scrollIntoView 断言会假失败
  const host = document.createElement('div')
  document.body.appendChild(host)
  return mount(ProcessInstanceDetailView, { attachTo: host, global: { components: { RouterLink: RouterLinkStub } } })
}

describe('昨日新增行级跳转锚定来源结果行', () => {
  beforeEach(() => {
    state.route = { params: {}, query: {} }
    state.currentSpace = 'gkx_verify_1'
    state.spaceItems = []
    state.job = baseJob()
    state.executions = [chainExecution()]
    state.task = baseTask()
  })

  afterEach(() => {
    document.body.innerHTML = ''
  })

  it('?exec+tab+src+n：选中该执行、直落数据溯源页签，唯一锚行高亮并滚动到视口', async () => {
    state.route = {
      params: { jobId: 'job-9e84ebcd9fb1' },
      // 路由 query 值经序列化后都是字符串（n=39 与 src/n 双匹配；同名表 gkx.dwd_zh_paper
    // 出现两次但写入数不同，只有 datasource 环的 39 行被锚中）
      query: { exec: 'EXEC-2C5669A668E04AED', tab: 'lineage', src: 'gkx.placeholder', n: '39' },
    }
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    const wrapper = mountView()
    await flushPromises()

    // 页签直落数据溯源，且选中的是 ?exec 指定的执行（非列表第一条之外的场景）
    const activeTab = wrapper.get('.detail-tabs button.active')
    expect(activeTab.text()).toBe('数据溯源')
    const pinned = wrapper.findAll('.lineage-result-table tbody tr')
      .filter((row) => row.classes().includes('is-pinned'))
    expect(pinned).toHaveLength(1)
    expect(pinned[0]!.text()).toContain('gkx.placeholder')
    expect(pinned[0]!.text()).toContain('39')
    // 行渲染后滚动到锚行（落地即见，不用自己扫表）
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' })
    wrapper.unmount()
  })

  it('无锚参数时来源结果表照常渲染、无高亮无滚动（普通动线不受影响）', async () => {
    state.route = { params: { jobId: 'job-9e84ebcd9fb1' }, query: {} }
    const scrollIntoView = vi.fn()
    Element.prototype.scrollIntoView = scrollIntoView
    const wrapper = mountView()
    await flushPromises()

    expect(wrapper.get('.detail-tabs button.active').text()).toBe('概况与结果')
    expect(wrapper.findAll('.lineage-result-table tbody tr.is-pinned')).toHaveLength(0)
    expect(scrollIntoView).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
