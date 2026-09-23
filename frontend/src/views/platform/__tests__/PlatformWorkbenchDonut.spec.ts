import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../../../api/auth'
import { getPlatformOverview, type PlatformOverviewData } from '../../../api/platformOverview'
import { useAuthStore } from '../../../stores/auth'
import PlatformWorkbenchView from '../PlatformWorkbenchView.vue'
import { donutGradient } from '../donutGradient'

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
  jobGraphSpace: (job: { graphSpace?: string }, def: string, cur: string) => job.graphSpace || def || cur,
  JOB_STATUS_TONE: { 未运行: 'warn', 运行中: 'run', 已暂停: 'warn', 已完成: 'ok', 运行失败: 'err' },
}))
vi.mock('../../../api/platformOverview', () => ({ getPlatformOverview: vi.fn() }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconInfoCircle: { template: '<i />' } }))

function adminProfile(): AuthProfile {
  return {
    user: {
      id: 1, username: 'tester', nickname: '测试用户', email: '', mobile: '',
      sex: 0, avatar: '', status: 1, userType: 0,
    },
    roles: [], permissions: [], menus: [], roleMenus: [],
    appPermissions: { roles: [], menus: [], permissions: [] },
    orgPermissions: { roles: [], menus: [], permissions: [] },
    organizations: [], expiresAt: null, authEnabled: true,
    platformRoles: [], platformPermissions: [], isAdmin: true,
  }
}

let wrapper: VueWrapper

const baseOverview: PlatformOverviewData = {
  platformStatus: '图数据库连接正常',
  pendingBatchCount: 1,
  updatedAt: '--',
  dataMode: 'partial',
  warnings: [],
  assetOverviewGroups: [],
  assetChangeRows: { entity: [], relation: [], property: [] },
  entityStructure: [],
  relationStructure: [],
  latestChanges: [],
  managementRisks: [],
  dataSources: {},
}

function mountOverview(): VueWrapper {
  return mount(PlatformWorkbenchView, {
    props: {},
    global: { plugins: [createPinia()] },
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
  setActivePinia(createPinia())
  useAuthStore().profile = adminProfile()
  vi.mocked(getPlatformOverview).mockResolvedValue({ ...baseOverview })
})

afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})

describe('donutGradient 占比分段纯函数', () => {
  const item = (ratio: number, tone: string) =>
    ({ label: 'x', schema: 'X', count: '1', ratio, tone }) as PlatformOverviewData['entityStructure'][number]

  it('多段按 tone+ratio 累计，段边界与图例一致', () => {
    expect(donutGradient([item(60, '#2e90fa'), item(25, '#7a5af8'), item(15, '#98a2b3')])).toBe(
      'conic-gradient(#2e90fa 0% 60%,#7a5af8 60% 85%,#98a2b3 85% 100%)',
    )
  })

  it('单桶 100% 也产出完整弧段', () => {
    expect(donutGradient([item(100, '#165dff')])).toBe('conic-gradient(#165dff 0% 100%)')
  })

  it('结构为空或 ratio 缺额时剩余弧段留中性灰', () => {
    expect(donutGradient([])).toBe('conic-gradient(#e5edf8 0 100%)')
    expect(donutGradient([item(70, '#2e90fa')])).toBe('conic-gradient(#2e90fa 0% 70%,#e5edf8 70% 100%)')
    // 非法 ratio 按 0 处理，不产生负段
    expect(donutGradient([item(-5, '#2e90fa'), item(100, '#7a5af8')])).toBe(
      'conic-gradient(#7a5af8 0% 100%)',
    )
  })
})

describe('平台总览占比环形图随数据驱动', () => {
  it('donut 内联 conic-gradient 与图例 tone+ratio 一致，不残留演示分段', async () => {
    vi.mocked(getPlatformOverview).mockResolvedValue({
      ...baseOverview,
      assetOverviewGroups: [
        // 卡片去重总量故意 ≠ 分段之和（900/1,500 vs 1,000/2,000），证明中心绑定的是分段和
        { key: 'entity', title: '实体数据', total: '900', totalLabel: '实体总量', added: '+5', addedLabel: '今日新增' },
        { key: 'relation', title: '关系数据', total: '1,500', totalLabel: '关系总量', added: '+2', addedLabel: '今日新增' },
      ],
      entityStructure: [
        { label: '专家', schema: 'Expert', count: '600', ratio: 60, tone: '#2e90fa' },
        { label: '论文', schema: 'Paper', count: '250', ratio: 25, tone: '#7a5af8' },
        { label: '其他', schema: 'Other', count: '150', ratio: 15, tone: '#98a2b3' },
      ],
      relationStructure: [
        { label: '发表', schema: 'PUBLISH', count: '1,200', ratio: 60, tone: '#165dff' },
        { label: '任职', schema: 'WORKS_AT', count: '800', ratio: 40, tone: '#2e90fa' },
      ],
      // 环形图中心 = 各分段之和（Σ计数），不再用资产卡去重总量
      entityStructureTotal: '1,000',
      relationStructureTotal: '2,000',
    })
    wrapper = mountOverview()
    await flushPromises()

    const entityDonut = wrapper.get('.platform-donut.is-entity')
    expect(entityDonut.attributes('style')).toContain(
      'conic-gradient(#2e90fa 0% 60%,#7a5af8 60% 85%,#98a2b3 85% 100%)',
    )
    // 图例只留中文标签与占比（真实成员名移到悬停浮窗）：600/1000=60%、250/1000=25%、150/1000=15%
    const legendRatios = wrapper.findAll('.platform-structure-chart')
      .filter((chart) => chart.text().includes('实体标签构成'))[0]
      .findAll('.platform-structure-legend article em')
      .map((em) => em.text())
    expect(legendRatios).toEqual(['60%', '25%', '15%'])

    const relationDonut = wrapper.get('.platform-donut.is-relation')
    expect(relationDonut.attributes('style')).toContain(
      'conic-gradient(#165dff 0% 60%,#2e90fa 60% 100%)',
    )

    // 中心显示各分段之和与「标签合计/类型合计」，不是资产卡的去重总量（900/1,500）
    expect(entityDonut.get('span').text()).toBe('1,000标签合计')
    expect(relationDonut.get('span').text()).toBe('2,000类型合计')
  })

  it('结构数据为空时图例为空、donut 保持中性灰回落（单段灰环见纯函数用例）', async () => {
    wrapper = mountOverview()
    await flushPromises()

    // jsdom 对单段 conic-gradient 不写入 style 属性，组件级只验证数据为空时的渲染形状
    expect(wrapper.find('.platform-donut.is-entity').exists()).toBe(true)
    expect(wrapper.findAll('.platform-structure-legend article')).toHaveLength(0)
  })

  it('今日新增与运行中执行数按接口数据渲染', async () => {
    vi.mocked(getPlatformOverview).mockResolvedValue({
      ...baseOverview,
      pendingBatchCount: 3,
      assetOverviewGroups: [
        { key: 'entity', title: '实体数据', total: '1,000', totalLabel: '实体总量', added: '+61', addedLabel: '今日新增' },
      ],
    })
    wrapper = mountOverview()
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('3 个执行运行中')
    expect(text).toContain('+61')
    expect(text).toContain('今日新增')
  })
})
