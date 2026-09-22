import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../../../api/auth'
import { getPlatformOverview } from '../../../api/platformOverview'
import { useAuthStore } from '../../../stores/auth'
import { getProductionReviews, listJobs } from '../../../api/workflowOperations'
import PlatformWorkbenchView from '../PlatformWorkbenchView.vue'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }), RouterLink: { template: '<a><slot /></a>' } }))
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
  countJobUnifiedStatuses: () => ({ 未运行: 0, 运行中: 0, 已暂停: 0, 已完成: 0, 运行失败: 0 }),
  JOB_STATUS_TONE: { 未运行: 'warn', 运行中: 'run', 已暂停: 'warn', 已完成: 'ok', 运行失败: 'err' },
}))
vi.mock('../../../api/platformOverview', () => ({ getPlatformOverview: vi.fn() }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconInfoCircle: { template: '<i />' } }))

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
    global: { plugins: [pinia] },
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
    dataMode: 'live',
    warnings: [],
    assetOverviewGroups: [],
    assetChangeRows: { entity: [], relation: [], property: [] },
    entityStructure: [],
    relationStructure: [],
    latestChanges: [],
    managementRisks: [],
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
