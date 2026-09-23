import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AuthProfile } from '../../../api/auth'
import { getPlatformOverview, type PlatformOverviewData } from '../../../api/platformOverview'
import { useAuthStore } from '../../../stores/auth'
import PlatformWorkbenchView from '../PlatformWorkbenchView.vue'
import { pieSlices } from '../pieSlices'

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

describe('pieSlices 占比分段纯函数', () => {
  const item = (ratio: number, tone: string) =>
    ({ label: `x${ratio}`, schema: 'X', count: '1', ratio, tone }) as PlatformOverviewData['entityStructure'][number]

  it('多段按 ratio 生成扇形 path：12 点起顺时针，过半分段 largeArc=1', () => {
    const slices = pieSlices([item(60, '#2e90fa'), item(25, '#7a5af8'), item(15, '#98a2b3')])
    expect(slices).toHaveLength(3)
    // 60% 段：-90°起点 (80,16)，终点 126° (42.38,131.78)，弧超过半圆
    expect(slices[0]!.path).toBe('M 80 80 L 80 16 A 64 64 0 1 1 42.38 131.78 Z')
    // 25% 段：126°(42.38,131.78) → 216°(28.34,-6.65 换算到圆上 28.34,25.35)……只断言起点与 largeArc=0
    expect(slices[1]!.path).toContain('A 64 64 0 0 1')
    expect(slices[1]!.path.startsWith('M 80 80 L 42.38 131.78')).toBe(true)
    // 悬浮外移向量沿中角（60% 段中角 18°）
    expect(slices[0]!.dx).toBeCloseTo(4.76, 2)
    expect(slices[0]!.dy).toBeCloseTo(1.55, 2)
    // 百分比标签锚点在质心方向 0.62r 处
    expect(slices[0]!.labelX).toBeCloseTo(117.74, 1)
    expect(slices[0]!.labelY).toBeCloseTo(92.26, 1)
  })

  it('占比 <5% 的窄段不标百分比（showLabel=false），≥5% 才标', () => {
    const slices = pieSlices([item(70, '#165dff'), item(26, '#2e90fa'), item(4, '#98a2b3')])
    expect(slices.map((slice) => slice.showLabel)).toEqual([true, true, false])
  })

  it('单段 100% 用整圆双弧特判，不再产生零面积弧', () => {
    const [slice] = pieSlices([item(100, '#165dff')])
    expect(slice!.path).toBe('M 80 16 A 64 64 0 1 1 80 144 A 64 64 0 1 1 80 16 Z')
    expect(slice!.showLabel).toBe(true)
  })

  it('零/负 ratio 段不产生扇形，结构为空返回空数组', () => {
    expect(pieSlices([])).toEqual([])
    expect(pieSlices([item(0, '#2e90fa'), item(-5, '#7a5af8')])).toEqual([])
  })
})

describe('平台总览构成饼图随数据驱动', () => {
  it('饼图扇区 fill 与图例 tone 一致、图上只标百分比、图例不展示数量', async () => {
    vi.mocked(getPlatformOverview).mockResolvedValue({
      ...baseOverview,
      assetOverviewGroups: [
        { key: 'entity', title: '实体数据', total: '900', totalLabel: '实体总量', added: '+5', addedLabel: '今日新增' },
        { key: 'relation', title: '关系数据', total: '1,500', totalLabel: '关系总量', added: '+2', addedLabel: '今日新增' },
      ],
      entityStructure: [
        { label: '专家', schema: 'Expert', count: '600', ratio: 60, tone: '#2e90fa' },
        { label: '论文', schema: 'Paper', count: '250', ratio: 25, tone: '#7a5af8' },
        { label: '其他实体', schema: 'Other', count: '150', ratio: 15, tone: '#98a2b3' },
      ],
      relationStructure: [
        { label: '发表', schema: 'PUBLISH', count: '1,200', ratio: 96, tone: '#165dff' },
        { label: '其他关系', schema: 'OTHER', count: '800', ratio: 4, tone: '#2e90fa' },
      ],
    })
    wrapper = mountOverview()
    await flushPromises()

    const entityChart = wrapper.findAll('.platform-structure-chart')
      .filter((chart) => chart.text().includes('实体标签构成'))[0]!
    const entityPie = entityChart.get('svg.platform-pie.is-entity')
    const slices = entityPie.findAll('g.platform-pie-slice')
    expect(slices).toHaveLength(3)
    // 扇区颜色与图例 tone 一致（数据驱动，不残留演示分段）
    expect(slices.map((g) => g.get('path').attributes('fill'))).toEqual(['#2e90fa', '#7a5af8', '#98a2b3'])
    // 图上只标百分比：60%/25%/15%，且不出现数量（600/250/150）
    const sliceLabels = slices.map((g) => g.find('text').exists() ? g.get('text').text() : '')
    expect(sliceLabels).toEqual(['60%', '25%', '15%'])
    // 图例只留中文标签 + 百分比
    const legendRatios = entityChart.findAll('.platform-structure-legend article .platform-legend-ratio')
      .map((strong) => strong.text())
    expect(legendRatios).toEqual(['60%', '25%', '15%'])
    expect(entityChart.get('.platform-structure-legend').text()).not.toContain('600')

    // 关系图 4% 窄段不标百分比
    const relationChart = wrapper.findAll('.platform-structure-chart')
      .filter((chart) => chart.text().includes('关系类型构成'))[0]!
    const relationSlices = relationChart.findAll('g.platform-pie-slice')
    expect(relationSlices).toHaveLength(2)
    expect(relationSlices[0]!.get('text').text()).toBe('96%')
    expect(relationSlices[1]!.find('text').exists()).toBe(false)

    // 旧环形图残留清零：无中心合计、无标签合计文案
    expect(wrapper.find('.platform-donut').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('标签合计')
    expect(wrapper.text()).not.toContain('类型合计')
  })

  it('悬浮扇区外移放大并出白底浮窗（分类名+数量+占比），移开复位', async () => {
    vi.mocked(getPlatformOverview).mockResolvedValue({
      ...baseOverview,
      entityStructure: [
        { label: '专家', schema: 'Expert', count: '600', ratio: 60, tone: '#2e90fa' },
        { label: '其他实体', schema: 'Other', count: '400', ratio: 40, tone: '#98a2b3' },
      ],
      relationStructure: [],
    })
    wrapper = mountOverview()
    await flushPromises()

    const entityChart = wrapper.findAll('.platform-structure-chart')
      .filter((chart) => chart.text().includes('实体标签构成'))[0]!
    const first = entityChart.findAll('g.platform-pie-slice')[0]!
    // 未悬浮：无位移、无浮窗
    expect(first.attributes('style') ?? '').not.toContain('translate')
    expect(entityChart.find('.platform-pie-tip').exists()).toBe(false)

    await first.trigger('mouseenter')
    // 悬浮：分段沿中角外移（放大互动）
    expect(first.attributes('style')).toContain('translate(')
    const tip = entityChart.get('.platform-pie-tip')
    expect(tip.text()).toContain('专家')
    expect(tip.text()).toContain('600')
    expect(tip.text()).toContain('60%')

    await first.trigger('mouseleave')
    expect(first.attributes('style') ?? '').not.toContain('translate')
    expect(entityChart.find('.platform-pie-tip').exists()).toBe(false)
  })

  it('结构数据为空时饼图落空态占位、图例为空', async () => {
    wrapper = mountOverview()
    await flushPromises()

    const entityPie = wrapper.get('svg.platform-pie.is-entity')
    expect(entityPie.findAll('g.platform-pie-slice')).toHaveLength(0)
    expect(entityPie.find('circle').exists()).toBe(true)
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
