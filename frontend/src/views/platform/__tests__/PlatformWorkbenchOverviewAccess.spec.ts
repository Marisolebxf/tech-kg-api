import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../../../api/auth'
import { getPlatformOverview, type PlatformOverviewData } from '../../../api/platformOverview'
import { useAuthStore } from '../../../stores/auth'
import { useGraphSpaceStore } from '../../../stores/graphSpace'
import { getProductionReviews, listJobs } from '../../../api/workflowOperations'
import PlatformWorkbenchView from '../PlatformWorkbenchView.vue'

const { routerPush, showToast, routeQuery } = vi.hoisted(() => ({
  routerPush: vi.fn(),
  showToast: vi.fn(),
  routeQuery: {} as Record<string, string>,
}))

// 模拟线上误配：关闭前端认证不能覆盖后端返回的普通用户身份。
vi.mock('../../../config', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../../config')>(), authDisabled: true,
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery }),
  useRouter: () => ({ push: routerPush }),
  RouterLink: { template: '<a><slot /></a>' },
}))
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
  routeQuery.day = ''
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

describe('昨日新增聚合格式展示', () => {
  function withAssetChanges(overrides: Partial<PlatformOverviewData> = {}) {
    vi.mocked(getPlatformOverview).mockResolvedValue({
      platformStatus: '平台运行正常', pendingBatchCount: 0, updatedAt: '02:00',
      dataMode: 'partial', warnings: [], dataSources: {},
      entityStructure: [], relationStructure: [],
      assetOverviewGroups: [
        { key: 'entity', title: '实体数据', total: '237', totalLabel: '实体总量', added: '+23.7万', addedLabel: '昨日新增' },
        { key: 'relation', title: '关系数据', total: '64', totalLabel: '关系总量', added: '+64', addedLabel: '昨日新增' },
      ],
      assetChangeRows: {
        entity: [
          { type: '论文', count: 200000, source: 'gkx.dwd_paper', time: '10-11 02:00:00', taskId: 'TASK-paper-a', jobId: 'job-paper-a', execId: 'EXEC-paper-01' },
          { type: '期刊', count: 37000, source: 'gkx.dwd_journal', time: '10-11 01:30:00', taskId: 'TASK-journal', jobId: 'job-journal' },
          { type: '报告', count: 1200, source: 'legacy.backfill', time: '10-11 01:20:00', taskId: 'TASK-direct' },
          { type: '专利', count: 5, source: 'legacy.patent', time: '10-11 01:00:00', execStatus: 'TERMINATED' },
        ],
        relation: [
          { type: '作者', count: 64, source: 'gkx.dwd_author', time: '10-11 02:00:00', taskId: 'TASK-author', jobId: 'job-author' },
        ],
      },
      assetChangeTotals: { entity: 237005, relation: 64 },
      ...overrides,
    })
  }

  async function openChanges(index = 0) {
    wrapper = mountOverview()
    await flushPromises()
    const buttons = wrapper.findAll('button').filter(button => button.text() === '查看昨日新增')
    await buttons[index]!.trigger('click')
  }

  it('行=写入块：数量列展示精确计数，合计按对象数口径，不再逐对象展示', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges()
    await openChanges()
    const drawer = wrapper.find('.asset-change-drawer')
    // 表头为聚合格式四列，不再有「具体对象」列
    expect(drawer.find('thead').text()).toContain('数量')
    expect(drawer.find('thead').text()).not.toContain('具体对象')
    const rows = wrapper.findAll('.asset-change-table tbody tr')
    expect(rows).toHaveLength(4)
    // 数量列千分位格式，中断执行行内标注
    expect(rows[0]!.text()).toContain('200,000')
    expect(rows[3]!.text()).toContain('已中断')
    // 左下角合计 = 控制库 written 精确计数（对象数口径，与行数 3 是两回事）
    expect(drawer.find('footer').text()).toContain('共 237,005 条变化')
  })

  it('明细暂不可读时显示读取失败，不显示汇总行或暂无新增', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges({
      assetOverviewGroups: [{ key: 'entity', title: '实体数据', total: '137', totalLabel: '实体总量', added: '--', addedLabel: '昨日新增' }],
      assetChangeRows: { entity: [], relation: [] },
      assetChangeErrors: { entity: '实体新增明细暂不可读取，请稍后重试' },
      assetChangeTotals: { entity: 0, relation: 0 },
    })
    await openChanges()
    const drawer = wrapper.find('.asset-change-drawer')
    expect(drawer.text()).toContain('实体新增明细暂不可读取，请稍后重试')
    expect(drawer.text()).not.toContain('昨日暂无写图记录')
    expect(drawer.find('footer').text()).toContain('新增明细暂不可读取')
  })

  it('行点击精确跳转所属执行（job-detail 带 ?exec=）；无 jobId 的行提示来源不误导跳转', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges()
    await openChanges()
    expect(wrapper.find('.asset-change-drawer footer a').text()).toBe('查看更新任务')
    expect(wrapper.find('.asset-change-drawer footer a').attributes('to')).toBe('/graph-build')
    const rows = wrapper.findAll('.asset-change-table tbody tr')
    // 带 jobId 的行可点击（手型 + tabindex + 回车可达）；带 execId 时直达该行的执行
    // ——任务可多次运行，任务页默认展示最新执行，不带它数字会对不上
    expect(rows[0]!.classes()).toContain('is-clickable')
    expect(rows[0]!.attributes('tabindex')).toBe('0')
    await rows[0]!.trigger('click')
    expect(routerPush).toHaveBeenCalledWith({
      name: 'job-detail',
      params: { jobId: 'job-paper-a' },
      query: { tab: 'lineage', exec: 'EXEC-paper-01', src: 'gkx.dwd_paper', n: 200000 },
    })
    await rows[0]!.trigger('keydown', { key: 'Enter' })
    expect(routerPush).toHaveBeenCalledTimes(2)
    // 有 jobId 无 execId（旧执行）：仍落任务页，不带 exec 查询参数
    expect(rows[1]!.classes()).toContain('is-clickable')
    await rows[1]!.trigger('click')
    expect(routerPush).toHaveBeenLastCalledWith({
      name: 'job-detail', params: { jobId: 'job-journal' }, query: { tab: 'lineage', src: 'gkx.dwd_journal', n: 37000 },
    })
    // 有 taskId 无 jobId：非任务通道执行（回填或中断），提示而非跳转
    expect(rows[2]!.classes()).not.toContain('is-clickable')
    await rows[2]!.trigger('click')
    expect(showToast).toHaveBeenLastCalledWith('该记录来自非任务通道执行（回填或中断），未关联图谱构建任务', 'info')
    // 无 taskId 无 jobId：旧执行未记录任务，另给一条提示
    await rows[3]!.trigger('click')
    expect(showToast).toHaveBeenLastCalledWith('该记录未关联图谱构建任务', 'info')
    expect(routerPush).toHaveBeenCalledTimes(3)
  })

  it('普通用户仍可看新增明细，但行不可点击、无管理跳转入口', async () => {
    useAuthStore().profile = makeProfile(false)
    withAssetChanges()
    await openChanges()
    expect(wrapper.find('.asset-change-drawer footer a').exists()).toBe(false)
    const row = wrapper.find('.asset-change-table tbody tr')
    expect(row.classes()).not.toContain('is-clickable')
    expect(row.attributes('tabindex')).toBeUndefined()
    await row.trigger('click')
    expect(routerPush).not.toHaveBeenCalled()
    expect(showToast).not.toHaveBeenCalled()
  })

  it('?day=YYYY-MM-DD 传给总览接口回看历史统计日；非法值按缺省不传', async () => {
    useAuthStore().profile = makeProfile(true)
    withAssetChanges()
    routeQuery.day = '2026-10-13'
    wrapper = mountOverview()
    await flushPromises()
    expect(getPlatformOverview).toHaveBeenCalledWith(expect.anything(), '2026-10-13')
    wrapper.unmount()

    routeQuery.day = 'not-a-date'
    wrapper = mountOverview()
    await flushPromises()
    expect(getPlatformOverview).toHaveBeenCalledWith(expect.anything(), undefined)
    wrapper.unmount()
  })
})
