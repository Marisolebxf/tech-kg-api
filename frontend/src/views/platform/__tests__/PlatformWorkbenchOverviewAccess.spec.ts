import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../../../api/auth'
import { getPlatformOverview, type PlatformOverviewData } from '../../../api/platformOverview'
import { useAuthStore } from '../../../stores/auth'
import { useGraphSpaceStore } from '../../../stores/graphSpace'
import { getProductionReviews, listJobs } from '../../../api/workflowOperations'
import PlatformWorkbenchView from '../PlatformWorkbenchView.vue'

const { routerPush, showToast } = vi.hoisted(() => ({ routerPush: vi.fn(), showToast: vi.fn() }))

// 模拟线上误配：关闭前端认证不能覆盖后端返回的普通用户身份。
vi.mock('../../../config', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../../config')>(), authDisabled: true,
}))

vi.mock('vue-router', () => ({ useRouter: () => ({ push: routerPush }), RouterLink: { template: '<a><slot /></a>' } }))
vi.mock('../../../api/graphConsole', () => ({ runNgql: vi.fn() }))
vi.mock('../../../api/graphAlgorithm', () => ({
  fetchGraphAlgorithmMetadata: vi.fn(),
  fetchGraphAlgorithmEngine: vi.fn(),
  getAlgorithmJob: vi.fn(),
  getAlgorithmJobResult: vi.fn(),
  submitAlgorithmJob: vi.fn(),
}))
vi.mock('../../../api/workflowOperations', () => ({
  listJobs: vi.fn(),
  getProductionReviews: vi.fn(),
  deriveJobUnifiedStatus: (job: { status?: string }) => job.status ?? '未运行',
  countJobUnifiedStatuses: () => ({ 未运行: 0, 运行中: 0, 已暂停: 0, 已完成: 0, 运行异常: 0, 运行失败: 0 }),
  // 总览任务卡按当前图空间过滤（jobGraphSpace）：整体 vi.mock 工厂必须补齐视图用到的新导出
  jobGraphSpace: (job: { graphSpace?: string }, def: string, cur: string) => job.graphSpace || def || cur,
  JOB_STATUS_TONE: { 未运行: 'idle', 运行中: 'run', 已暂停: 'idle', 已完成: 'ok', 运行异常: 'warn', 运行失败: 'err' },
}))
vi.mock('../../../api/platformOverview', () => ({ getPlatformOverview: vi.fn() }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconInfoCircle: { template: '<i />' }, IconRefresh: { template: '<i />' } }))

function makeProfile(isAdmin: boolean): AuthProfile {
  return {
    user: {
      id: 1, username: 'tester', nickname: '测试用户', email: '', mobile: '',
      sex: 0, avatar: '', status: 1, userType: 0,
    },
    roles: [], permissions: [], menus: [], roleMenus: [],
    appPermissions: { roles: [], menus: [], permissions: [] },
    orgPermissions: { roles: [], menus: [], permissions: [] },
    organizations: [], expiresAt: null, authEnabled: true,
    platformRoles: [], platformPermissions: [], isAdmin,
  }
}

let wrapper: VueWrapper
let pinia: ReturnType<typeof createPinia>

function mountOverview(): VueWrapper {
  return mount(PlatformWorkbenchView, {
    props: {},
    global: {
      plugins: [pinia],
      stubs: { teleport: true, 'a-tooltip': { template: '<span><slot /></span>' }, 'a-select': true, 'a-option': true },
    },
  })
}

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  }))
  localStorage.clear()
  pinia = createPinia()
  setActivePinia(pinia)
  vi.mocked(getPlatformOverview).mockResolvedValue({
    platformStatus: '平台运行正常',
    pendingBatchCount: 0,
    updatedAt: '--',
    dataMode: 'partial',
    warnings: [],
    assetOverviewGroups: [],
    assetChangeRows: { entity: [], relation: [] },
    entityStructure: [],
    relationStructure: [],
    dataSources: {},
  })
  vi.mocked(listJobs).mockResolvedValue({ items: [], total: 0 })
  vi.mocked(getProductionReviews).mockResolvedValue({ items: [], total: 0, page: 1, pageSize: 5 })
})

afterEach(() => {
  wrapper.unmount()
  vi.unstubAllGlobals()
})

describe('平台总览管理入口按角色隐藏', () => {
  it('开发维护使用原面板，公共空间审核被拒后清除旧业务空间记录，迟到响应不能覆盖', async () => {
    useAuthStore().profile = { ...makeProfile(false), businessRbacEnabled: true, canDevelop: true, platformRole: 'developer' }
    const spaces = useGraphSpaceStore()
    spaces.spaces = ['business', 'public']
    spaces.setCurrent('business')
    let finishOld!: (value: Awaited<ReturnType<typeof getProductionReviews>>) => void
    vi.mocked(getProductionReviews).mockReturnValueOnce(new Promise(resolve => { finishOld = resolve }))
      .mockRejectedValueOnce({ response: { status: 403 } })
    wrapper = mountOverview()
    await flushPromises()
    expect(getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ graphSpace: 'business' }))
    spaces.setCurrent('public')
    await flushPromises()
    expect(getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ graphSpace: 'public' }))
    finishOld({ items: [{ id: 'old-private-case', objectName: '旧业务审核' }] as never, total: 1, page: 1, pageSize: 5 })
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧业务审核')
    expect(useAuthStore().isAdmin).toBe(false)
  })
  it('普通用户：隐藏查看任务/进入人工处理按钮与图谱构建/人工审核面板，且不发起 admin 接口请求', async () => {
    useAuthStore().profile = makeProfile(false)
    wrapper = mountOverview()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('亿级科技知识图谱平台')
    expect(text).toContain('当前图谱资产')
    expect(text).not.toContain('查看任务')
    expect(text).not.toContain('进入人工处理')
    expect(text).not.toContain('图谱构建')
    expect(text).not.toContain('人工审核')
    expect(listJobs).not.toHaveBeenCalled()
    expect(getProductionReviews).not.toHaveBeenCalled()
  })

  it('管理员：渲染 hero 按钮与图谱构建/人工审核面板，并加载任务与审核队列', async () => {
    useAuthStore().profile = makeProfile(true)
    wrapper = mountOverview()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('查看任务')
    expect(text).toContain('进入人工处理')
    expect(text).toContain('图谱构建')
    expect(text).toContain('人工审核')
    expect(listJobs).toHaveBeenCalled()
    expect(getProductionReviews).toHaveBeenCalled()
  })
})

describe('昨日新增明细跳转更新任务', () => {
  function withAssetChanges(overrides: Partial<PlatformOverviewData> = {}) {
    vi.mocked(getPlatformOverview).mockResolvedValue({
      platformStatus: '平台运行正常', pendingBatchCount: 0, updatedAt: '02:00',
      dataMode: 'partial', warnings: [], dataSources: {},
      entityStructure: [], relationStructure: [],
      assetOverviewGroups: [
        { key: 'entity', title: '实体数据', total: '2', totalLabel: '实体总量', added: '+2', addedLabel: '昨日新增' },
        { key: 'relation', title: '关系数据', total: '1', totalLabel: '关系总量', added: '+1', addedLabel: '昨日新增' },
      ],
      assetChangeRows: {
        entity: [
          { type: '论文', object: '论文甲', change: '新增', source: 'paper', time: '10-11 02:00:00', taskId: 'TASK-paper-a', jobId: 'job-paper-a' },
          { type: '论文', object: '论文乙', change: '新增', source: 'paper', time: '10-11 02:00:00', taskId: 'TASK-paper-b', jobId: 'job-paper-b' },
          { type: '论文', object: '直跑论文', change: '新增', source: 'paper', time: '10-11 01:30:00', taskId: 'TASK-direct' },
          { type: '论文', object: '历史论文', change: '新增', source: 'paper', time: '10-11 01:00:00' },
        ],
        relation: [
          { type: '作者', object: '专家 → 论文', change: '新增', source: 'paper', time: '10-11 02:00:00', taskId: 'TASK-author', jobId: 'job-author' },
        ],
      },
      ...overrides,
    })
  }

  async function openChanges(index = 0) {
    wrapper = mountOverview()
    await flushPromises()
    const buttons = wrapper.findAll('button').filter(button => button.text() === '查看昨日新增')
    await buttons[index]!.trigger('click')
  }

  it('新增32时展示32条真实记录，同名同时间记录各自保留', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges({
      assetOverviewGroups: [{ key: 'entity', title: '实体数据', total: '137', totalLabel: '实体总量', added: '+32', addedLabel: '昨日新增' }],
      assetChangeRows: {
        entity: Array.from({ length: 32 }, (_, index) => ({ type: '论文', object: '同名论文', objectId: `p-${index}`, taskId: `TASK-${index}`, jobId: `job-${index}`, change: '新增', source: 'paper', time: '10-11 02:00:00' })),
        relation: [],
      },
      assetChangeTotals: { entity: 32, relation: 0 },
    })
    await openChanges()
    expect(wrapper.find('.asset-change-drawer').text()).toContain('+32')
    const rows = wrapper.findAll('.asset-change-table tbody tr')
    expect(rows).toHaveLength(32)
    expect(wrapper.find('.asset-change-drawer footer').text()).toContain('32 条变化')
    expect(wrapper.find('.asset-change-drawer').text()).not.toContain('展示前')
    await rows[31]!.trigger('click')
    expect(routerPush).toHaveBeenLastCalledWith({ name: 'job-detail', params: { jobId: 'job-31' } })
  })

  it('明细暂不可读时显示读取失败，不显示汇总行或暂无新增', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges({
      assetOverviewGroups: [{ key: 'entity', title: '实体数据', total: '137', totalLabel: '实体总量', added: '--', addedLabel: '昨日新增' }],
      assetChangeRows: { entity: [], relation: [] },
      assetChangeErrors: { entity: '实体新增明细暂未完整读取，请稍后重试' },
      assetChangeTotals: { entity: 0, relation: 0 },
    })
    await openChanges()
    const drawer = wrapper.find('.asset-change-drawer')
    expect(drawer.text()).toContain('实体新增明细暂未完整读取，请稍后重试')
    expect(drawer.text()).not.toContain('昨日暂无写图记录')
    expect(drawer.text()).not.toContain('展示前')
    expect(drawer.find('footer').text()).toContain('新增明细暂不可读取')
  })

  it('按钮显示查看更新任务；点击不同实体行按各自任务直达图谱构建任务详情', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges()
    await openChanges()
    expect(wrapper.find('.asset-change-drawer footer a').text()).toBe('查看更新任务')
    expect(wrapper.find('.asset-change-drawer footer a').attributes('to')).toBe('/graph-build')
    const rows = wrapper.findAll('.asset-change-table tbody tr')
    await rows[0]!.find('strong').trigger('click')
    expect(routerPush).toHaveBeenLastCalledWith({ name: 'job-detail', params: { jobId: 'job-paper-a' } })
    await rows[1]!.trigger('click')
    expect(routerPush).toHaveBeenLastCalledWith({ name: 'job-detail', params: { jobId: 'job-paper-b' } })
  })

  it('关系行支持 Enter 和空格键进入对应任务', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges()
    await openChanges(1)
    const row = wrapper.find('.asset-change-table tbody tr')
    expect(row.attributes('tabindex')).toBe('0')
    await row.trigger('keydown', { key: 'Enter' })
    await row.trigger('keydown', { key: ' ' })
    expect(routerPush).toHaveBeenCalledTimes(2)
    expect(routerPush).toHaveBeenLastCalledWith({ name: 'job-detail', params: { jobId: 'job-author' } })
  })

  it('缺少图谱构建任务的记录给出提示，不猜测或跳转任务', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges()
    await openChanges()
    // 行2：直跑执行有 taskId 但无 jobId；行3：历史记录两者皆无——都不再跳转
    const rows = wrapper.findAll('.asset-change-table tbody tr')
    for (const row of [rows[2]!, rows[3]!]) {
      expect(row.classes()).not.toContain('is-clickable')
      expect(row.attributes('tabindex')).toBeUndefined()
      await row.trigger('click')
    }
    expect(routerPush).not.toHaveBeenCalled()
    expect(showToast).toHaveBeenCalledWith('该记录未关联图谱构建任务', 'info')
  })

  it('普通用户仍可看新增明细，但没有管理跳转入口', async () => {
    useAuthStore().profile = makeProfile(false)
    withAssetChanges()
    await openChanges()
    expect(wrapper.find('.asset-change-drawer footer a').exists()).toBe(false)
    const row = wrapper.find('.asset-change-table tbody tr')
    expect(row.classes()).not.toContain('is-clickable')
    expect(row.attributes('tabindex')).toBeUndefined()
    await row.trigger('click')
    await row.trigger('keydown', { key: 'Enter' })
    expect(routerPush).not.toHaveBeenCalled()
  })
})
