import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import {
  getFilteredSubgraph,
  getGraphNode,
  getGraphStats,
  getSubgraph,
  type GraphData,
  type GetSubgraphParams,
} from '../../../api/graphSearch'
import { browseEntities, searchEntities, type EntitySearchItem } from '../../../api/entitySearch'
import {
  getSchemaTopology,
  type SchemaDefinition,
} from '../../../api/schemaManagement'
import { useGraphSpaceStore } from '../../../stores/graphSpace'
import GraphVisualizationView from '../GraphVisualizationView.vue'

const { showToast } = vi.hoisted(() => ({ showToast: vi.fn() }))

// 只替换网络函数，保留 unwrapApiResponse 等纯函数的真实实现
vi.mock('../../../api/graphSearch', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/graphSearch')>()
  return {
    ...actual,
    getGraphStats: vi.fn(),
    getSubgraph: vi.fn(),
    getFilteredSubgraph: vi.fn(),
    getGraphNode: vi.fn(),
  }
})
vi.mock('../../../api/schemaManagement', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/schemaManagement')>()
  return { ...actual, getSchemaTopology: vi.fn() }
})
vi.mock('../../../api/entitySearch', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../api/entitySearch')>()
  return { ...actual, searchEntities: vi.fn(), browseEntities: vi.fn() }
})
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconSearch: { template: '<i />' } }))

// 保留 v-model/change 语义的 DOM 桩，不依赖 arco 弹层
const SelectStub = defineComponent({
  props: { modelValue: { type: [String, Number, Array], default: undefined }, multiple: { type: Boolean, default: false } },
  emits: ['update:modelValue', 'change'],
  template: `<select :multiple="multiple" :value="modelValue"
    @change="$emit('change', multiple ? Array.from($event.target.selectedOptions, o => o.value) : $event.target.value); $emit('update:modelValue', multiple ? Array.from($event.target.selectedOptions, o => o.value) : $event.target.value)">
    <slot /></select>`,
})
const OptionStub = defineComponent({
  props: ['value'],
  template: '<option :value="value"><slot /></option>',
})
const InputStub = defineComponent({
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: `<div class="input-stub"><input :value="modelValue"
    @input="$emit('update:modelValue', $event.target.value)" /><slot name="prefix" /></div>`,
})
// a-input-number 桩：输入即回传数值并触发 change
const InputNumberStub = defineComponent({
  props: { modelValue: { type: Number, default: 100 } },
  emits: ['update:modelValue', 'change'],
  template: `<div class="input-number-stub"><input type="number" :value="modelValue"
    @input="$emit('update:modelValue', Number($event.target.value)); $emit('change', Number($event.target.value))" /></div>`,
})
// 画布桩：渲染节点按钮触发 selectNode，计数用于断言过滤效果
const CanvasStub = defineComponent({
  name: 'KgGraphCanvas',
  props: ['nodes', 'edges'],
  emits: ['selectNode', 'selectEdge'],
  template: `<div class="canvas-stub">
    <span class="canvas-count">{{ nodes.length }}/{{ edges.length }}</span>
    <button v-for="node in nodes" :key="node.id" type="button" class="canvas-node" @click="$emit('selectNode', node)">{{ node.label }}</button>
  </div>`,
})

function apiOk<T>(data: T) {
  // 运行时 http 拦截器已剥掉 AxiosResponse 外壳，类型上仍标注 AxiosResponse——mock 按 never 传入
  return { code: 200, success: true, data, msg: '' } as never
}

const apiNode = (id: string, labels: string[], properties: Record<string, unknown> = {}) => ({
  id,
  labels,
  properties,
})
const apiEdge = (
  id: string,
  type: string,
  source: string,
  target: string,
  properties: Record<string, unknown> = {},
) => ({ id, type, source, target, properties })

function entityItem(vid: string, name: string, entityType: string): EntitySearchItem {
  return { vid, entityId: null, name, entityType, properties: {}, score: 0.9 }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => {
    resolve = done
  })
  return { promise, resolve }
}

let wrapper: VueWrapper
let store: ReturnType<typeof useGraphSpaceStore>

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  }))
  localStorage.clear()
  const pinia = createPinia()
  setActivePinia(pinia)
  store = useGraphSpaceStore()
  store.setCurrent('space-a')
  vi.mocked(getGraphStats).mockResolvedValue(
    apiOk({ nodes: { 专家: 12, 论文: 8 }, edges: { 撰写: 20, 任职: 6 } }),
  )
  // 默认空目录：类型名回退原名显示（不依赖 Schema 目录的用例不受影响）
  vi.mocked(getSchemaTopology).mockResolvedValue({ nodes: [], edges: [] })
  // 默认浏览无实体：自动预览直接跳过，不影响「未查询」空态用例
  vi.mocked(browseEntities).mockResolvedValue({
    items: [], offset: 0, limit: 1, entityType: null, mode: 'browse',
  })
  mountView()
})

/** 自动预览在挂载瞬间就发 browse 请求：需要先改 mock 再挂载的用例走这里重挂 */
function mountView() {
  const pinia = createPinia()
  setActivePinia(pinia)
  store = useGraphSpaceStore()
  store.setCurrent('space-a')
  wrapper = mount(GraphVisualizationView, {
    global: {
      plugins: [pinia],
      stubs: {
        'a-select': SelectStub,
        'a-option': OptionStub,
        'a-input': InputStub,
        'a-input-number': InputNumberStub,
        KgGraphCanvas: CanvasStub,
      },
    },
  })
}

afterEach(() => {
  wrapper.unmount()
  vi.unstubAllGlobals()
})

async function clickButton(label: string) {
  const button = wrapper.findAll('button').find((item) => item.text() === label)
  expect(button, `Missing button: ${label}`).toBeDefined()
  await button!.trigger('click')
}

async function searchStart(items: EntitySearchItem[]) {
  vi.mocked(searchEntities).mockResolvedValue({
    items,
    offset: 0,
    limit: 20,
    entityType: null,
    mode: 'hybrid',
  })
  await wrapper.get('#graphviz-keyword input').setValue('张三')
  await clickButton('搜索起点')
  await flushPromises()
}

async function runQuery(data: GraphData) {
  vi.mocked(getSubgraph).mockResolvedValue(apiOk(data))
  await clickButton('查询图谱')
  await flushPromises()
}

function canvasCount(): string {
  return wrapper.get('.canvas-count').text()
}

/** 读组件内 perHopLimit 的当前值（经 stub 的受控 value 绑定回显） */
function perHopLimitInputValue(): number {
  return Number((wrapper.get('#graphviz-limit input').element as HTMLInputElement).value)
}

describe('GraphVisualizationView', () => {
  it('挂载按全局图空间加载统计，未查询时给空态提示', async () => {
    await flushPromises()
    expect(getGraphStats).toHaveBeenCalledWith('space-a')
    expect(wrapper.text()).toContain('图空间跟随右上角全局选择器：space-a')
    expect(wrapper.get('.graphviz-canvas__empty').text()).toContain('暂无图谱数据')
    // 类型下拉来自 stats 的标签/边类型计数
    expect(wrapper.text()).toContain('专家（12）')
    expect(wrapper.text()).toContain('撰写（20）')
  })

  it('类型名显示 Schema 目录中文名（目录缺失的类型回退英文原名）', async () => {
    wrapper.unmount()
    vi.mocked(getGraphStats).mockResolvedValue(
      apiOk({ nodes: { Expert: 3, Legacy: 1 }, edges: { AUTHORED_BY: 5 } }),
    )
    vi.mocked(getSchemaTopology).mockResolvedValue({
      nodes: [{ name: 'Expert', label: '专家' } as SchemaDefinition],
      edges: [{ name: 'AUTHORED_BY', label: '撰写' } as SchemaDefinition],
    })
    vi.mocked(browseEntities).mockResolvedValue({
      items: [entityItem('exp-1', '张三', 'Expert')],
      offset: 0, limit: 1, entityType: null, mode: 'browse',
    })
    vi.mocked(getSubgraph).mockResolvedValue(
      apiOk({ nodes: [apiNode('exp-1', ['Expert'], { name: '张三' })], edges: [] }),
    )
    mountView()
    await flushPromises()
    expect(getSchemaTopology).toHaveBeenCalledWith('space-a')
    // 实体/边类型下拉用目录中文名；目录没有的 Legacy 回退英文原名
    const entitySelectText = wrapper.get('#graphviz-entity-type').text()
    expect(entitySelectText).toContain('专家（3）')
    expect(entitySelectText).toContain('Legacy（1）')
    expect(wrapper.get('#graphviz-edge-types').text()).toContain('撰写（5）')
    // 图例（实体类型显隐开关）同样显示中文名
    expect(wrapper.get('.graphviz-legend').text()).toContain('专家')
  })

  it('打开页面自动取图里第一个实体预览出图，免手动搜索起点', async () => {
    // 自动预览随挂载触发：先备好 mock 再重挂
    wrapper.unmount()
    vi.mocked(browseEntities).mockResolvedValue({
      items: [entityItem('scholar-7', '赵六', '专家')],
      offset: 0, limit: 1, entityType: null, mode: 'browse',
    })
    vi.mocked(getSubgraph).mockResolvedValue(
      apiOk({ nodes: [apiNode('scholar-7', ['专家'], { name_cn: '赵六' })], edges: [] }),
    )
    mountView()
    await flushPromises()
    expect(browseEntities).toHaveBeenCalledWith({ space: 'space-a', limit: 10 })
    expect(getSubgraph).toHaveBeenCalledWith(
      'scholar-7',
      expect.objectContaining({ space: 'space-a' }),
    )
    expect(canvasCount()).toBe('1/0')
    // 摘要里的查询起点即自动预览命中的实体
    expect(wrapper.text()).toContain('赵六')
  })

  it('自动预览跳过无边孤点，选有边的实体当起点', async () => {
    wrapper.unmount()
    vi.mocked(browseEntities).mockResolvedValue({
      items: [entityItem('lone-1', '孤点实体', '专家'), entityItem('hub-1', '枢纽实体', '专家')],
      offset: 0, limit: 10, entityType: null, mode: 'browse',
    })
    // 孤点候选子图无边；枢纽候选带 1 条边
    vi.mocked(getSubgraph).mockImplementation(async (nodeId: string) =>
      apiOk(
        nodeId === 'lone-1'
          ? { nodes: [apiNode('lone-1', ['专家'])], edges: [] }
          : {
              nodes: [apiNode('hub-1', ['专家']), apiNode('paper-1', ['论文'])],
              edges: [apiEdge('e1', '撰写', 'hub-1', 'paper-1')],
            },
      ),
    )
    mountView()
    await flushPromises()
    // 探测（lone-1 无边跳过）+ 正式（hub-1 出图）
    expect(getSubgraph).toHaveBeenCalledWith('lone-1', expect.objectContaining({ space: 'space-a' }))
    expect(getSubgraph).toHaveBeenCalledWith('hub-1', expect.objectContaining({ space: 'space-a' }))
    expect(canvasCount()).toBe('2/1')
    expect(wrapper.text()).toContain('枢纽实体')
  })

  it('实体类型下拉选了具体类型后可选回「全部类型」', async () => {
    await flushPromises()
    vi.mocked(searchEntities).mockResolvedValue({
      items: [], offset: 0, limit: 20, entityType: null, mode: 'hybrid',
    })
    const select = wrapper.get('#graphviz-entity-type')
    await select.setValue('专家')
    await wrapper.get('#graphviz-keyword input').setValue('张三')
    await clickButton('搜索起点')
    await flushPromises()
    expect(searchEntities).toHaveBeenCalledWith(expect.objectContaining({ entityType: '专家' }))

    // 通过固定首项「全部类型」选回：检索不再限定类型
    await select.setValue('')
    await clickButton('搜索起点')
    await flushPromises()
    expect(searchEntities).toHaveBeenLastCalledWith(expect.objectContaining({ entityType: null }))
  })

  it('起点检索结果栏可收起与展开，新检索命中自动展开', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家'), entityItem('scholar-2', '李四', '专家')])
    expect(wrapper.findAll('.graphviz-start__item')).toHaveLength(2)

    await clickButton('×')
    expect(wrapper.find('.graphviz-start__item').exists()).toBe(false)
    expect(wrapper.text()).toContain('命中 2 个实体')
    // 已收起时消息行出现展开入口
    await clickButton('展开检索结果（2 条）')
    expect(wrapper.findAll('.graphviz-start__item')).toHaveLength(2)

    // 收起后再次检索命中会自动展开
    await clickButton('×')
    await searchStart([entityItem('scholar-3', '王五', '专家')])
    expect(wrapper.findAll('.graphviz-start__item')).toHaveLength(1)
  })

  it('每跳边数上限可自由输入并夹紧到 1-256', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')

    // 自定义值 7：随查询参数下发
    vi.mocked(getSubgraph).mockResolvedValue(apiOk({ nodes: [], edges: [] }))
    await wrapper.get('#graphviz-limit input').setValue('7')
    await clickButton('查询图谱')
    await flushPromises()
    expect(getSubgraph).toHaveBeenLastCalledWith(
      'scholar-1',
      expect.objectContaining({ limit: 7 }),
    )

    // 手输越界值被夹回边界内：0 → 1、999 → 256
    await wrapper.get('#graphviz-limit input').setValue('0')
    expect(perHopLimitInputValue()).toBe(1)
    await wrapper.get('#graphviz-limit input').setValue('999')
    expect(perHopLimitInputValue()).toBe(256)
  })

  it('起点检索点选后按参数查询子图并出图画布', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    expect(wrapper.text()).toContain('命中 1 个实体')
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')

    await runQuery({
      nodes: [
        apiNode('scholar-1', ['专家'], { name_cn: '张三' }),
        apiNode('paper-1', ['论文'], { title: '论文 A' }),
      ],
      edges: [apiEdge('e1', '撰写', 'scholar-1', 'paper-1')],
    })
    expect(getSubgraph).toHaveBeenCalledWith(
      'scholar-1',
      expect.objectContaining({ depth: 3, limit: 16, direction: 'both', space: 'space-a' }),
    )
    expect(canvasCount()).toBe('2/1')
    expect(showToast).toHaveBeenCalledWith('已加载 2 个实体、1 条关系', 'success')
  })

  it('名称未命中且关键词无空格时按 VID 直查兜底，带空格则不兜底', async () => {
    vi.mocked(searchEntities).mockResolvedValue({ items: [], offset: 0, limit: 20, entityType: null, mode: 'hybrid' })
    vi.mocked(getGraphNode).mockResolvedValue(
      apiOk(apiNode('scholar-9', ['专家'], { name_cn: '李四' })),
    )
    await wrapper.get('#graphviz-keyword input').setValue('scholar-9')
    await clickButton('搜索起点')
    await flushPromises()
    expect(getGraphNode).toHaveBeenCalledWith('scholar-9', 'space-a')
    expect(wrapper.text()).toContain('已按节点 ID 直查命中 1 个实体')

    // 带空格的关键词不走 VID 兜底
    vi.mocked(getGraphNode).mockClear()
    await wrapper.get('#graphviz-keyword input').setValue('两个 词')
    await clickButton('搜索起点')
    await flushPromises()
    expect(getGraphNode).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('未找到匹配「两个 词」的实体')
  })

  it('选择多个边类型时走 filtered-subgraph 并拼接 edge_types', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await wrapper.get('#graphviz-edge-types').setValue(['撰写', '任职'])

    vi.mocked(getFilteredSubgraph).mockResolvedValue(
      apiOk({ nodes: [apiNode('scholar-1', ['专家'])], edges: [] }),
    )
    await clickButton('查询图谱')
    await flushPromises()
    expect(getFilteredSubgraph).toHaveBeenCalledWith(
      'scholar-1',
      expect.objectContaining({ edge_types: '撰写,任职', space: 'space-a' }),
    )
    expect(getSubgraph).not.toHaveBeenCalled()
  })

  it('VID 含斜杠且选了边类型时回退逐边类型查询并合并去重', async () => {
    await searchStart([entityItem('专家/001', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await wrapper.get('#graphviz-edge-types').setValue(['撰写', '任职'])

    vi.mocked(getSubgraph).mockImplementation(
      async (_nodeId: string, params: GetSubgraphParams = {}) =>
        apiOk(
          params.edge_type === '撰写'
            ? {
                nodes: [apiNode('专家/001', ['专家']), apiNode('paper-1', ['论文'])],
                edges: [apiEdge('e1', '撰写', '专家/001', 'paper-1')],
              }
            : {
                nodes: [apiNode('专家/001', ['专家']), apiNode('org-1', ['机构'])],
                edges: [apiEdge('e2', '任职', '专家/001', 'org-1')],
              },
        ),
    )
    await clickButton('查询图谱')
    await flushPromises()
    expect(getFilteredSubgraph).not.toHaveBeenCalled()
    expect(getSubgraph).toHaveBeenCalledWith('专家/001', expect.objectContaining({ edge_type: '撰写' }))
    expect(getSubgraph).toHaveBeenCalledWith('专家/001', expect.objectContaining({ edge_type: '任职' }))
    // 两份子图合并去重后共 3 个节点（中心重复）
    expect(canvasCount()).toBe('3/2')
  })

  it('查询结果为空时给出明确空态', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await runQuery({ nodes: [], edges: [] })
    expect(wrapper.get('.graphviz-canvas__empty').text()).toContain('未查询到「张三」的关联子图')
    expect(showToast).toHaveBeenCalledWith('未查询到该起点的关联子图', 'warning')
  })

  it('图例点击隐藏实体类型并裁掉关联边，再点恢复', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await runQuery({
      nodes: [
        apiNode('scholar-1', ['专家']),
        apiNode('paper-1', ['论文']),
        apiNode('paper-2', ['论文']),
      ],
      edges: [
        apiEdge('e1', '撰写', 'scholar-1', 'paper-1'),
        apiEdge('e2', '撰写', 'scholar-1', 'paper-2'),
        apiEdge('e3', '引用', 'paper-1', 'paper-2'),
      ],
    })
    expect(canvasCount()).toBe('3/3')

    const expertLegend = wrapper
      .findAll('.graphviz-legend__item')
      .find((item) => item.text().includes('专家'))!
    await expertLegend.trigger('click')
    // 隐藏专家：中心及两条边被裁，两个论文节点靠「引用」边保持连通
    expect(canvasCount()).toBe('2/1')

    await expertLegend.trigger('click')
    expect(canvasCount()).toBe('3/3')
  })

  it('全部类型隐藏时提示专门的空态文案', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await runQuery({
      nodes: [apiNode('scholar-1', ['专家']), apiNode('paper-1', ['论文'])],
      edges: [apiEdge('e1', '撰写', 'scholar-1', 'paper-1')],
    })
    for (const label of ['专家', '论文']) {
      const legend = wrapper
        .findAll('.graphviz-legend__item')
        .find((item) => item.text().includes(label))!
      await legend.trigger('click')
    }
    expect(wrapper.get('.graphviz-canvas__empty').text()).toContain('所有实体类型已被隐藏')
  })

  it('结果超过节点上限时按连接度裁剪并出横幅，可显示全部', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    // 星型 305 节点：中心 + 304 个邻居，全部度数为 1（中心除外）
    const nodes = [
      apiNode('scholar-1', ['专家']),
      ...Array.from({ length: 304 }, (_, i) => apiNode(`paper-${i}`, ['论文'])),
    ]
    const edges = Array.from({ length: 304 }, (_, i) =>
      apiEdge(`e-${i}`, '撰写', 'scholar-1', `paper-${i}`),
    )
    await runQuery({ nodes, edges })

    expect(canvasCount()).toBe('300/299')
    expect(wrapper.get('.graphviz-cap-banner').text()).toContain('隐藏 5 个低连接度节点')

    await clickButton('显示全部')
    expect(canvasCount()).toBe('305/304')
  })

  it('点选节点看实体详情并可从该节点重新查询', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await runQuery({
      nodes: [
        apiNode('scholar-1', ['专家'], { name_cn: '张三' }),
        apiNode('paper-1', ['论文'], { title: '论文 A' }),
      ],
      edges: [apiEdge('e1', '撰写', 'scholar-1', 'paper-1')],
    })
    const paperNode = wrapper.findAll('.canvas-node').find((item) => item.text() === '论文 A')!
    await paperNode.trigger('click')
    expect(wrapper.text()).toContain('实体结构化结果')

    await clickButton('以此节点为中心重新查询')
    await flushPromises()
    expect(getSubgraph).toHaveBeenLastCalledWith(
      'paper-1',
      expect.objectContaining({ space: 'space-a' }),
    )
  })

  it('重定中心/手动查询后可点「自动预览」回到自动选点', async () => {
    // 默认 browse 空：先手动检索起点并查询
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await runQuery({ nodes: [apiNode('scholar-1', ['专家'])], edges: [] })
    expect(canvasCount()).toBe('1/0')

    // 自动预览命中另一个有边起点并出图
    vi.mocked(browseEntities).mockResolvedValue({
      items: [entityItem('hub-9', '枢纽实体', '专家')],
      offset: 0, limit: 10, entityType: null, mode: 'browse',
    })
    vi.mocked(getSubgraph).mockResolvedValue(
      apiOk({
        nodes: [apiNode('hub-9', ['专家']), apiNode('paper-1', ['论文'])],
        edges: [apiEdge('e1', '撰写', 'hub-9', 'paper-1')],
      }),
    )
    await clickButton('自动预览')
    await flushPromises()
    expect(canvasCount()).toBe('2/1')
    expect(wrapper.text()).toContain('枢纽实体')
    // 自动选中的实体同步为「已选起点」：可继续用「查询图谱」重复查询
    expect(wrapper.text()).toContain('已选起点')
    expect(wrapper.text()).toContain('枢纽实体（专家）')
  })

  it('切换全局图空间后整体重置并按新空间加载统计', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')
    await runQuery({
      nodes: [apiNode('scholar-1', ['专家'])],
      edges: [],
    })
    expect(canvasCount()).toBe('1/0')

    store.setCurrent('space-b')
    await nextTick()
    await flushPromises()
    expect(getGraphStats).toHaveBeenLastCalledWith('space-b')
    expect(wrapper.get('.graphviz-canvas__empty').text()).toContain('暂无图谱数据')
    expect(wrapper.find('.graphviz-start__item').exists()).toBe(false)
  })

  it('空间切换后在途的旧查询响应不再写入结果', async () => {
    await searchStart([entityItem('scholar-1', '张三', '专家')])
    await wrapper.findAll('.graphviz-start__item')[0].trigger('click')

    const stale = deferred<never>()
    vi.mocked(getSubgraph).mockReturnValueOnce(stale.promise)
    await clickButton('查询图谱')
    store.setCurrent('space-b')
    await nextTick()

    stale.resolve(apiOk({ nodes: [apiNode('scholar-1', ['专家'])], edges: [] }))
    await flushPromises()
    expect(wrapper.get('.graphviz-canvas__empty').text()).toContain('暂无图谱数据')
    // loading 已被空间切换重置：按钮文案恢复「查询图谱」（起点被清空故禁用属预期）
    const queryButton = wrapper.findAll('button').find((item) => item.text() === '查询图谱')
    expect(queryButton).toBeDefined()
    expect(queryButton!.attributes('disabled')).toBeDefined()
  })
})
