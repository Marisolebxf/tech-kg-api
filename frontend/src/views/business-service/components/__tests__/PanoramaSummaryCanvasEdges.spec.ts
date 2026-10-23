import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import BusinessServiceAlgorithmPanel from '../BusinessServiceAlgorithmPanel.vue'
import { getServiceModule } from '../../service-modules'
import { queryIndustryChainPanorama } from '../../../../api/industryChainPanorama'
import type { IndustryChainPanoramaQueryResponse } from '../../../../api/industryChainPanorama'

vi.mock('element-plus/es/components/select/style/css', () => ({}))
vi.mock('../../../../api/industryChainPanorama', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../../api/industryChainPanorama')>()),
  queryIndustryChainPanorama: vi.fn(),
}))
vi.mock('../../../../composables/use-space-permissions', () => ({
  useSpacePermissions: () => ({ canWrite: { value: true }, spaces: { contextKey: 'test', current: 'dev' } }),
}))
vi.mock('../../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

/**
 * 画布口径关联关系计数测试夹具：graph.edges 共 10 条（summary.totalEdges=10），
 * 但画布只渲染 7 条连线 —— 4 条真实图库边（两端节点都在画布上）+ 3 条分层
 * 展示连线（虚拟中心 → 三个分层实体），其余 6 条边因任一端点不在画布节点集
 * 或重复被丢弃。摘要「关联关系」必须显示画布口径 7，而不是全量 10。
 */
function buildCanvasEdgesFixture(): IndustryChainPanoramaQueryResponse {
  const nodes = [
    { id: 'kw_1', type: 'Keyword', label: '人工智能' },
    { id: 'p_1', type: 'Person', label: '专家一' },
    { id: 'p_2', type: 'Person', label: '专家二' },
    ...Array.from({ length: 30 }, (_, i) => ({
      id: `n_${i + 1}`,
      type: 'Paper',
      label: `论文${i + 1}`,
    })),
  ]
  const edges = [
    { source: 'kw_1', target: 'p_1', label: 'HAS_KEYWORD' },
    { source: 'p_1', target: 'p_2', label: 'COAUTHOR_WITH' },
    { source: 'kw_1', target: 'n_1', label: 'HAS_KEYWORD' },
    { source: 'p_1', target: 'n_1', label: 'AUTHORED_BY' },
    // 与第 3 条同源同目标同类型：画布按 from::to::label 去重
    { source: 'kw_1', target: 'n_1', label: 'HAS_KEYWORD' },
    // 以下 6 条至少一端不在画布节点集（展开层只取前 24 个候选，n_25 起不上画布）
    { source: 'n_2', target: 'n_26', label: 'CITES' },
    { source: 'n_25', target: 'n_26', label: 'CITES' },
    { source: 'n_26', target: 'n_27', label: 'CITES' },
    { source: 'n_27', target: 'n_28', label: 'CITES' },
    { source: 'n_28', target: 'n_29', label: 'CITES' },
    { source: 'n_29', target: 'n_30', label: 'CITES' },
  ]
  return {
    taskName: '科技产业链全景图',
    input: { industry: '人工智能', anchorId: '', depth: 2, topK: 5, relationTypes: [] },
    summary: { industry: '人工智能', industryChains: [], totalNodes: 3, totalEdges: 10 },
    layers: [
      { key: 'core_technology', title: '核心技术', total: 1, items: [
        { id: 'kw_1', label: '人工智能', type: 'technology' },
      ] },
      { key: 'leading_enterprise', title: '领军企业', total: 0, items: [] },
      { key: 'leading_expert', title: '领军专家', total: 2, items: [
        { id: 'p_1', label: '专家一', type: 'expert' },
        { id: 'p_2', label: '专家二', type: 'expert' },
      ] },
      { key: 'flagship_achievement', title: '产业动态事件', total: 0, items: [] },
    ],
    graph: { nodes, edges },
    provenance: null,
    apiResultExample: {
      url: '/api/v1/kg-construction/industry-chain-panorama/query',
      method: 'POST',
      query: {},
    },
  }
}

let view: VueWrapper | undefined

afterEach(() => { view?.unmount(); view = undefined })

function summaryRowValue(wrapper: VueWrapper, label: string): string {
  const row = wrapper
    .findAll('.result-panel__table > div')
    .find((div) => div.find('dt').text() === label)
  if (!row) throw new Error(`summary row not found: ${label}`)
  return row.find('dd').text()
}

describe('panorama summary canvas edge count', () => {
  it('关联关系显示画布实际渲染连线数（真实边+分层展示连线），不显示子图全量 totalEdges', async () => {
    vi.mocked(queryIndustryChainPanorama).mockResolvedValue(buildCanvasEdgesFixture())
    view = mount(BusinessServiceAlgorithmPanel, {
      props: { moduleInfo: getServiceModule('industry-chain-panorama'), responseJson: '{}' },
      attachTo: document.body,
      global: {
        stubs: { KgGraphCanvas: true, ListPagination: true },
        config: { errorHandler: vi.fn() },
      },
    })
    await flushPromises()

    await view.get('input[aria-label="industry"]').setValue('人工智能')
    const runButton = view
      .findAll('button.kg-button')
      .find((button) => button.text() === '执行测试')
    if (!runButton) throw new Error('run button not found')
    await runButton.trigger('click')
    await flushPromises()

    // 画布连线 = 4 条真实图库边 + 3 条分层展示连线 = 7 条；全量 totalEdges=10
    expect(summaryRowValue(view, '关联关系')).toBe('7 条')
    // 核心节点等其余行仍走后端汇总口径，不受本次改动影响
    expect(summaryRowValue(view, '核心节点')).toBe('3 个')
  })
})
