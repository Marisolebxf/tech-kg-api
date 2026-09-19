<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { IconSearch } from '@arco-design/web-vue/es/icon'

import KgGraphCanvas from '../../components/kg-graph-canvas.vue'
import {
  getFilteredSubgraph,
  getGraphNode,
  getGraphStats,
  getSubgraph,
  unwrapApiResponse,
  type ApiResponse,
  type GraphData,
  type GraphDepth,
  type GraphDirection,
  type GraphStatsData,
} from '../../api/graphSearch'
import {
  entitySearchErrorMessage,
  searchEntities,
  type EntitySearchItem,
} from '../../api/entitySearch'
import { currentGraphSpace } from '../../api/currentGraphSpace'
import { useGraphSpaceStore } from '../../stores/graphSpace'
import { useToast } from '../../composables/use-toast'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import {
  applyNodeCap,
  assignLabelTones,
  convertApiGraphEdges,
  convertApiGraphNodes,
  getApiNodeDisplayName,
  mergeGraphData,
  normalizeReturnedSubgraph,
} from '../../utils/graphQueryConversion'
import {
  getEdgeProvenance,
  getNodeProvenance,
  type GraphEdgeData,
  type GraphNodeData,
  type GraphNodeType,
} from '../../data/graph-presets'

const { showToast } = useToast()

/** 展示侧节点数上限：超过后按连接度保留前 N 个（可一键显示全部）。 */
const NODE_CAP = 300
/** 实体/关系明细列表最多展开条数（画布点选可看单个详情）。 */
const LIST_CAP = 30
const SEARCH_RESULT_LIMIT = 20
const DEPTH_OPTIONS: GraphDepth[] = [1, 2, 3]
const LIMIT_OPTIONS = [50, 100, 200]
const DIRECTION_LABELS: Record<GraphDirection, string> = {
  both: '双向',
  out: '仅出边',
  in: '仅入边',
}

type DetailMode = 'summary' | 'entity' | 'relation' | 'provenance'

interface AppliedQuery {
  space: string
  vid: string
  centerLabel: string
  depth: GraphDepth
  limit: number
  direction: GraphDirection
  edgeTypes: string[]
  time: string
}

/** 全局图空间切换/组件卸载时递增，作废在途请求的回写。 */
let graphContextVersion = 0

const graphSpaceStore = useGraphSpaceStore()
const space = computed(() => currentGraphSpace())

// ---------- 查询表单 ----------
const stats = ref<GraphStatsData | null>(null)
const entityTypeFilter = ref('')
const searchKeyword = ref('')
const searching = ref(false)
const searchMessage = ref('')
const searchResults = ref<EntitySearchItem[]>([])
const startNode = ref<EntitySearchItem | null>(null)
const depth = ref<GraphDepth>(2)
const perHopLimit = ref(100)
const direction = ref<GraphDirection>('both')
const selectedEdgeTypes = ref<string[]>([])

// ---------- 查询结果与展示过滤 ----------
const rawGraph = ref<GraphData | null>(null)
const centerNodeId = ref('')
const querying = ref(false)
const hasQueried = ref(false)
const appliedQuery = ref<AppliedQuery | null>(null)
const hiddenLabels = ref<Set<string>>(new Set())
const showAllNodes = ref(false)

// ---------- 详情面板 ----------
const detailMode = ref<DetailMode>('summary')
const selectedNodeId = ref<string | null>(null)
const selectedEdgeId = ref<string | null>(null)

function statsToOptions(record: Record<string, number> | undefined) {
  if (!record) return []
  return Object.entries(record)
    .filter(([, count]) => count > 0)
    .map(([name, count]) => ({ name, count }))
    .sort((a, b) => b.count - a.count || (a.name < b.name ? -1 : 1))
}

/**
 * 兼容 http 拦截器剥壳前后的两种返回形状：
 * 运行时拦截器返回 response.data（ApiResponse 本体），
 * 但 axios 类型上仍标注 AxiosResponse（.data 里才是 ApiResponse）。
 */
function unwrapGraphResponse<T>(
  response: ApiResponse<T> | { data: ApiResponse<T> },
): T {
  return unwrapApiResponse('success' in response ? response : response.data)
}

const entityTypeOptions = computed(() => statsToOptions(stats.value?.nodes))
const edgeTypeOptions = computed(() => statsToOptions(stats.value?.edges))

// ---------- 计算链：转换 → 图例 → 类型过滤 → 节点上限 ----------
const labelTones = computed(() =>
  assignLabelTones(
    (rawGraph.value?.nodes ?? [])
      .map((node) => node.labels[0] ?? '')
      .filter(Boolean),
  ),
)

const allNodes = computed(() => {
  if (!rawGraph.value) return []
  return convertApiGraphNodes(rawGraph.value, centerNodeId.value, (label) =>
    labelTones.value.get(label) ?? 'topic',
  )
})
const allEdges = computed(() => convertApiGraphEdges(rawGraph.value?.edges ?? []))

/** 图例即显隐开关：按结果里实际出现的实体类型给出色调/计数/隐藏态。 */
const legendItems = computed(() => {
  const counts = new Map<string, number>()
  for (const node of allNodes.value) {
    counts.set(node.entityType, (counts.get(node.entityType) ?? 0) + 1)
  }
  return Array.from(counts.entries()).map(([label, count]) => ({
    label,
    count,
    tone: (labelTones.value.get(label) ?? 'topic') as GraphNodeType,
    hidden: hiddenLabels.value.has(label),
  }))
})

/** 类型过滤：去掉隐藏类型的节点及其关联边，再清理因此孤立的非中心节点。 */
const labelFiltered = computed(() => {
  const nodes = allNodes.value.filter((node) => !hiddenLabels.value.has(node.entityType))
  const keptIds = new Set(nodes.map((node) => node.id))
  const edges = allEdges.value.filter(
    (edge) => keptIds.has(edge.from) && keptIds.has(edge.to),
  )
  const degrees = new Map<string, number>()
  for (const edge of edges) {
    degrees.set(edge.from, (degrees.get(edge.from) ?? 0) + 1)
    degrees.set(edge.to, (degrees.get(edge.to) ?? 0) + 1)
  }
  const connected = nodes.filter(
    (node) => node.id === centerNodeId.value || (degrees.get(node.id) ?? 0) > 0,
  )
  const connectedIds = new Set(connected.map((node) => node.id))
  return {
    nodes: connected,
    edges: edges.filter((edge) => connectedIds.has(edge.from) && connectedIds.has(edge.to)),
  }
})

const capApplied = computed(() =>
  showAllNodes.value
    ? { ...labelFiltered.value, hiddenCount: 0 }
    : applyNodeCap(labelFiltered.value.nodes, labelFiltered.value.edges, NODE_CAP, centerNodeId.value),
)

const visibleNodes = computed(() => capApplied.value.nodes)
const visibleEdges = computed(() => capApplied.value.edges)
const capHiddenCount = computed(() => capApplied.value.hiddenCount)

// ---------- 详情数据 ----------
const selectedNode = computed(
  () => allNodes.value.find((node) => node.id === selectedNodeId.value) ?? null,
)
const selectedEdge = computed(
  () => allEdges.value.find((edge) => edge.id === selectedEdgeId.value) ?? null,
)
const selectedEdgeNodes = computed(() => {
  const byId = new Map(allNodes.value.map((node) => [node.id, node]))
  const edge = selectedEdge.value
  return {
    from: edge ? byId.get(edge.from) ?? null : null,
    to: edge ? byId.get(edge.to) ?? null : null,
  }
})

function formatConfidence(value: number | undefined): string {
  return value === undefined ? '—' : value.toFixed(2)
}

const DETAIL_TABS: Array<{ mode: DetailMode; label: string }> = [
  { mode: 'summary', label: '摘要' },
  { mode: 'entity', label: '实体' },
  { mode: 'relation', label: '关系' },
  { mode: 'provenance', label: '溯源' },
]

const detailTitle = computed(() => {
  if (detailMode.value === 'entity') return '实体结构化结果'
  if (detailMode.value === 'relation') return '关系结构化结果'
  if (detailMode.value === 'provenance') return '数据溯源'
  return '查询结果摘要'
})

const summaryRows = computed<Array<[string, string]>>(() => {
  if (!appliedQuery.value) {
    return [
      ['图空间', space.value || '默认'],
      ['查询起点', '尚未查询'],
    ]
  }
  const q = appliedQuery.value
  return [
    ['图空间', q.space || '默认'],
    ['查询起点', `${q.centerLabel}（${q.vid}）`],
    ['查询条件', `深度 ${q.depth} 跳 · 每跳上限 ${q.limit} · ${DIRECTION_LABELS[q.direction]}`],
    ['边类型筛选', q.edgeTypes.length ? q.edgeTypes.join('、') : '全部边类型'],
    ['图谱规模', `返回 ${allNodes.value.length} 实体 / ${allEdges.value.length} 关系`],
    [
      '当前展示',
      `展示 ${visibleNodes.value.length} 实体 / ${visibleEdges.value.length} 关系`
        + (capHiddenCount.value ? `（已按连接度隐藏 ${capHiddenCount.value} 个节点）` : ''),
    ],
    ['查询时间', q.time],
  ]
})

const entityRows = computed<Array<[string, string]>>(() => {
  const selected = selectedNode.value
  if (selected) {
    return [
      ['实体名称', selected.label],
      ['实体类型', selected.entityType],
      ['节点 VID', selected.id],
      ['关联关系', selected.relations || '—'],
      ['置信度', formatConfidence(selected.confidence)],
    ]
  }
  return visibleNodes.value.slice(0, LIST_CAP).flatMap((node, index) => [
    [`实体 ${index + 1}`, `${node.label}（${node.id}）`],
    ['类型', node.entityType],
    ['关联关系', node.relations || '—'],
    ['置信度', formatConfidence(node.confidence)],
  ])
})

const relationRows = computed<Array<[string, string]>>(() => {
  const selected = selectedEdge.value
  const byId = new Map(allNodes.value.map((node) => [node.id, node]))
  if (selected) {
    const from = byId.get(selected.from)
    const to = byId.get(selected.to)
    return [
      ['源实体', `${from?.label || selected.from} / ${from?.entityType || '—'}`],
      ['目标实体', `${to?.label || selected.to} / ${to?.entityType || '—'}`],
      ['关系类型', selected.label],
      ['关系分类', selected.category],
      ['置信度', formatConfidence(selected.confidence)],
      ['匹配证据', selected.matchEvidence || '—'],
      ['匹配方式', selected.matchMethod || '—'],
    ]
  }
  return visibleEdges.value.slice(0, LIST_CAP).flatMap((edge, index) => [
    [
      `关系 ${index + 1}`,
      `${byId.get(edge.from)?.label || edge.from} → ${byId.get(edge.to)?.label || edge.to}`,
    ],
    ['类型', edge.label],
    ['置信度', formatConfidence(edge.confidence)],
  ])
})

const entityListTruncated = computed(
  () => !selectedNode.value && visibleNodes.value.length > LIST_CAP,
)
const relationListTruncated = computed(
  () => !selectedEdge.value && visibleEdges.value.length > LIST_CAP,
)

// 溯源：选中优先，否则回退第一个节点（中心排前，与老页一致）
const provenanceNode = computed(() => {
  if (selectedNodeId.value) return selectedNode.value
  if (selectedEdge.value) return null
  return allNodes.value[0] ?? null
})

const provenance = computed(() => {
  if (provenanceNode.value) return getNodeProvenance(provenanceNode.value)
  const edge = selectedEdge.value
  if (edge) {
    return getEdgeProvenance(
      edge,
      selectedEdgeNodes.value.from ?? undefined,
      selectedEdgeNodes.value.to ?? undefined,
    )
  }
  return null
})

const provenanceTarget = computed(() => {
  const node = provenanceNode.value
  if (node) {
    return { kind: '实体', name: node.label, type: node.entityType, id: node.id }
  }
  const edge = selectedEdge.value
  const { from, to } = selectedEdgeNodes.value
  if (!edge || !from || !to) return null
  return { kind: '关系', name: `${from.label} → ${to.label}`, type: edge.label, id: edge.id }
})

// ---------- 请求 ----------
async function loadStats(): Promise<void> {
  const context = graphContextVersion
  try {
    stats.value = unwrapGraphResponse(await getGraphStats(space.value || undefined))
  } catch {
    if (context !== graphContextVersion) return
    stats.value = null
    showToast('图空间统计加载失败，类型下拉暂不可用（仍可检索起点直接查询）', 'warning')
  }
}

async function doSearch(): Promise<void> {
  if (searching.value) return
  const keyword = searchKeyword.value.trim()
  if (!keyword) {
    searchMessage.value = '请输入实体名称或关键词后再检索'
    return
  }
  const context = graphContextVersion
  searching.value = true
  searchMessage.value = ''
  const missMessage = `未找到匹配「${keyword}」的实体${entityTypeFilter.value ? `（类型 ${entityTypeFilter.value}）` : ''}`
  try {
    const result = await searchEntities({
      keyword,
      space: space.value || null,
      entityType: entityTypeFilter.value || null,
      limit: SEARCH_RESULT_LIMIT,
    })
    if (context !== graphContextVersion) return
    if (result.items.length > 0) {
      searchResults.value = result.items
      searchMessage.value = `命中 ${result.items.length} 个实体，点击选择查询起点`
      return
    }
    if (!/\s/.test(keyword)) {
      // 名称未命中且关键词无空格：尝试整体当作节点 VID 直查（兜底）
      try {
        const node = unwrapGraphResponse(await getGraphNode(keyword, space.value || undefined))
        if (context !== graphContextVersion) return
        searchResults.value = [
          {
            vid: node.id,
            entityId: null,
            name: getApiNodeDisplayName(node),
            entityType: node.labels[0] ?? null,
            properties: {},
            score: null,
          },
        ]
        searchMessage.value = '按名称未命中，已按节点 ID 直查命中 1 个实体'
        return
      } catch {
        if (context !== graphContextVersion) return
      }
    }
    searchResults.value = []
    searchMessage.value = missMessage
  } catch (error) {
    if (context !== graphContextVersion) return
    searchResults.value = []
    searchMessage.value = entitySearchErrorMessage(error)
  } finally {
    if (context === graphContextVersion) searching.value = false
  }
}

function pickStartNode(item: EntitySearchItem): void {
  startNode.value = item
}

async function runQuery(vidOverride?: string, labelOverride?: string): Promise<void> {
  const vid = vidOverride ?? startNode.value?.vid
  if (!vid) {
    showToast('请先检索并选择起点实体', 'info')
    return
  }
  if (querying.value) return
  const context = graphContextVersion
  const edgeTypes = [...selectedEdgeTypes.value]
  const baseParams = {
    depth: depth.value,
    limit: perHopLimit.value,
    direction: direction.value,
  }
  querying.value = true
  selectedNodeId.value = null
  selectedEdgeId.value = null
  detailMode.value = 'summary'
  try {
    let data: GraphData
    if (edgeTypes.length === 0) {
      data = unwrapGraphResponse(await getSubgraph(vid, { ...baseParams, space: space.value || undefined }))
    } else if (!vid.includes('/')) {
      data = unwrapGraphResponse(
        await getFilteredSubgraph(vid, {
          ...baseParams,
          edge_types: edgeTypes.join(','),
          space: space.value || undefined,
        }),
      )
    } else {
      // filtered-subgraph 的 node_id 路径参数无 :path 转换，VID 含「/」会 404：
      // 回退为按边类型逐个 getSubgraph 查询后客户端合并去重。
      const parts = await Promise.all(
        edgeTypes.map((edgeType) =>
          getSubgraph(vid, { ...baseParams, edge_type: edgeType, space: space.value || undefined })
            .then((response) => unwrapGraphResponse(response)),
        ),
      )
      data = mergeGraphData(parts)
    }
    if (context !== graphContextVersion) return

    const normalized = normalizeReturnedSubgraph(data, vid)
    rawGraph.value = normalized
    centerNodeId.value = vid
    hiddenLabels.value = new Set()
    showAllNodes.value = false
    hasQueried.value = true
    appliedQuery.value = {
      space: space.value,
      vid,
      centerLabel: labelOverride ?? startNode.value?.name ?? vid,
      depth: depth.value,
      limit: perHopLimit.value,
      direction: direction.value,
      edgeTypes,
      time: formatQueryTimestamp(new Date()),
    }
    if (normalized.nodes.length === 0) {
      showToast('未查询到该起点的关联子图', 'warning')
    } else {
      showToast(`已加载 ${normalized.nodes.length} 个实体、${normalized.edges.length} 条关系`, 'success')
    }
  } catch (error) {
    if (context !== graphContextVersion) return
    showToast(error instanceof Error ? error.message : '图谱查询失败', 'warning')
  } finally {
    if (context === graphContextVersion) querying.value = false
  }
}

function recenterFromNode(node: GraphNodeData): void {
  startNode.value = {
    vid: node.id,
    entityId: null,
    name: node.label,
    entityType: node.entityType,
    properties: {},
    score: null,
  }
  void runQuery(node.id, node.label)
}

function openNodeDetail(node: GraphNodeData): void {
  selectedNodeId.value = node.id
  selectedEdgeId.value = null
  detailMode.value = 'entity'
}

function openEdgeDetail(edge: GraphEdgeData): void {
  selectedEdgeId.value = edge.id
  selectedNodeId.value = null
  detailMode.value = 'relation'
}

function toggleLabel(label: string): void {
  const next = new Set(hiddenLabels.value)
  if (next.has(label)) {
    next.delete(label)
  } else {
    next.add(label)
  }
  hiddenLabels.value = next
}

// a-select 的 change 回调参数是宽联合类型，这里收敛回严格类型
function onEntityTypeSelect(value: unknown): void {
  entityTypeFilter.value = value == null ? '' : String(value)
  // 类型变化后旧结果不再匹配，清掉待选列表（已选起点保留）
  searchResults.value = []
  searchMessage.value = ''
}

function onDepthSelect(value: unknown): void {
  const n = Number(value)
  if (n === 1 || n === 2 || n === 3) depth.value = n
}

function onLimitSelect(value: unknown): void {
  const n = Number(value)
  if (LIMIT_OPTIONS.includes(n)) perHopLimit.value = n
}

function onDirectionSelect(value: unknown): void {
  const s = String(value)
  if (s === 'both' || s === 'out' || s === 'in') direction.value = s
}

function onEdgeTypesSelect(value: unknown): void {
  selectedEdgeTypes.value = Array.isArray(value) ? value.map((item) => String(item)) : []
}

function formatQueryTimestamp(date: Date): string {
  const pad = (value: number) => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

onMounted(() => {
  void loadStats()
})

// 切换图空间：作废在途请求并整体重置（表单/结果/过滤/详情），按新空间重载统计
watch(
  () => graphSpaceStore.current,
  () => {
    graphContextVersion += 1
    stats.value = null
    searchKeyword.value = ''
    searchResults.value = []
    searchMessage.value = ''
    startNode.value = null
    entityTypeFilter.value = ''
    selectedEdgeTypes.value = []
    rawGraph.value = null
    centerNodeId.value = ''
    hasQueried.value = false
    appliedQuery.value = null
    hiddenLabels.value = new Set()
    showAllNodes.value = false
    selectedNodeId.value = null
    selectedEdgeId.value = null
    detailMode.value = 'summary'
    querying.value = false
    searching.value = false
    void loadStats()
  },
  { flush: 'sync' },
)

onUnmounted(() => {
  graphContextVersion += 1
})
</script>

<template>
  <main class="graphviz-page">
    <!-- 查询参数 -->
    <section class="graphviz-panel graphviz-form" aria-label="图谱查询参数">
      <div class="graphviz-panel__header">
        <h2 class="graphviz-panel__title">图谱可视化查询</h2>
        <span class="graphviz-space-hint">图空间跟随右上角全局选择器：{{ space || '默认' }}</span>
      </div>
      <div class="graphviz-form__body">
        <div class="graphviz-form__grid">
          <div class="graphviz-field">
            <label for="graphviz-entity-type">实体类型（限定起点检索）</label>
            <a-select
              id="graphviz-entity-type"
              class="graphviz-select"
              :model-value="entityTypeFilter"
              placeholder="全部类型"
              allow-clear
              :scrollbar="false"
              @change="onEntityTypeSelect"
            >
              <a-option v-for="t in entityTypeOptions" :key="t.name" :value="t.name">
                {{ t.name }}（{{ t.count }}）
              </a-option>
              <template #empty>当前图空间暂无实体</template>
            </a-select>
          </div>
          <div class="graphviz-field graphviz-field--grow">
            <label for="graphviz-keyword">起点检索（实体名称 / 关键词，无空格词可作 VID 直查）</label>
            <div class="graphviz-search">
              <a-input
                id="graphviz-keyword"
                v-model="searchKeyword"
                class="graphviz-input"
                :max-length="SEARCH_KEYWORD_MAX_LENGTH"
                placeholder="输入实体名称或关键词检索查询起点"
                @keyup.enter="doSearch"
              >
                <template #prefix><IconSearch /></template>
              </a-input>
              <button class="kg-button" type="button" :disabled="searching" @click="doSearch">
                {{ searching ? '检索中…' : '搜索起点' }}
              </button>
            </div>
          </div>
        </div>

        <div v-if="searchResults.length" class="graphviz-start" aria-label="起点检索结果">
          <button
            v-for="item in searchResults"
            :key="item.vid"
            type="button"
            :class="['graphviz-start__item', { 'is-selected': startNode?.vid === item.vid }]"
            :title="item.vid"
            @click="pickStartNode(item)"
          >
            <b>{{ item.name || '（未命名）' }}</b>
            <span>{{ item.entityType || '未知类型' }}</span>
            <code>{{ item.vid }}</code>
          </button>
        </div>

        <p v-if="searchMessage" class="graphviz-form__message">
          {{ searchMessage }}
          <template v-if="startNode">｜已选起点：<b>{{ startNode.name || startNode.vid }}</b>（{{ startNode.entityType || '未知类型' }}）</template>
        </p>

        <div class="graphviz-form__grid graphviz-form__grid--params">
          <div class="graphviz-field">
            <label for="graphviz-depth">查询深度</label>
            <a-select
              id="graphviz-depth"
              class="graphviz-select"
              :model-value="depth"
              :scrollbar="false"
              @change="onDepthSelect"
            >
              <a-option v-for="option in DEPTH_OPTIONS" :key="option" :value="option">{{ option }} 跳</a-option>
            </a-select>
          </div>
          <div class="graphviz-field">
            <label for="graphviz-limit">每跳上限</label>
            <a-select
              id="graphviz-limit"
              class="graphviz-select"
              :model-value="perHopLimit"
              :scrollbar="false"
              @change="onLimitSelect"
            >
              <a-option v-for="option in LIMIT_OPTIONS" :key="option" :value="option">{{ option }}</a-option>
            </a-select>
          </div>
          <div class="graphviz-field">
            <label for="graphviz-direction">查询方向</label>
            <a-select
              id="graphviz-direction"
              class="graphviz-select"
              :model-value="direction"
              :scrollbar="false"
              @change="onDirectionSelect"
            >
              <a-option value="both">双向</a-option>
              <a-option value="out">仅出边</a-option>
              <a-option value="in">仅入边</a-option>
            </a-select>
          </div>
          <div class="graphviz-field graphviz-field--wide">
            <label for="graphviz-edge-types">边类型多选（不选 = 全部边类型）</label>
            <a-select
              id="graphviz-edge-types"
              class="graphviz-select"
              :model-value="selectedEdgeTypes"
              placeholder="全部边类型"
              multiple
              allow-clear
              :scrollbar="false"
              @change="onEdgeTypesSelect"
            >
              <a-option v-for="t in edgeTypeOptions" :key="t.name" :value="t.name">
                {{ t.name }}（{{ t.count }}）
              </a-option>
              <template #empty>当前图空间暂无关系</template>
            </a-select>
          </div>
          <div class="graphviz-field graphviz-field--actions">
            <label aria-hidden="true">查询</label>
            <button class="kg-button" type="button" :disabled="querying || !startNode" @click="runQuery()">
              {{ querying ? '查询中…' : '查询图谱' }}
            </button>
          </div>
        </div>

        <p v-if="!stats" class="graphviz-form__message graphviz-form__message--muted">
          图空间统计未加载或为空：类型下拉不可用，仍可直接检索起点查询图谱。
        </p>
      </div>
    </section>

    <div class="graphviz-lower">
      <!-- 画布 -->
      <section class="graphviz-panel graphviz-canvas-panel" aria-label="图谱展示">
        <div class="graphviz-panel__header">
          <h2 class="graphviz-panel__title">图谱展示</h2>
          <span v-if="hasQueried" class="graphviz-panel__meta">
            {{ allNodes.length }} 实体 · {{ allEdges.length }} 关系
          </span>
        </div>
        <div v-if="legendItems.length" class="graphviz-legend" aria-label="实体类型图例（点击显隐）">
          <button
            v-for="item in legendItems"
            :key="item.label"
            type="button"
            :class="['graphviz-legend__item', `is-${item.tone}`, { 'is-hidden': item.hidden }]"
            :title="item.hidden ? '点击显示该类型' : '点击隐藏该类型'"
            @click="toggleLabel(item.label)"
          >
            <i /><span>{{ item.label }}</span><em>{{ item.count }}</em>
          </button>
        </div>
        <div v-if="capHiddenCount > 0" class="graphviz-cap-banner" role="status">
          <span>结果超过 {{ NODE_CAP }} 个节点，已按连接度保留 {{ visibleNodes.length }} 个（隐藏 {{ capHiddenCount }} 个低连接度节点）。</span>
          <button type="button" @click="showAllNodes = true">显示全部</button>
        </div>
        <div class="graphviz-canvas">
          <KgGraphCanvas
            v-if="visibleNodes.length"
            :nodes="visibleNodes"
            :edges="visibleEdges"
            :selected-node-id="selectedNodeId"
            :selected-edge-id="selectedEdgeId"
            node-shape="circle"
            show-edge-labels
            uniform-node-size
            aria-label="图谱可视化结果"
            @select-node="openNodeDetail"
            @select-edge="openEdgeDetail"
          />
          <div v-else class="graphviz-canvas__empty" role="status">
            <span v-if="querying">图谱查询中…</span>
            <span v-else-if="!hasQueried">暂无图谱数据，请检索并选择起点实体后点击「查询图谱」</span>
            <span v-else-if="allNodes.length === 0">未查询到「{{ appliedQuery?.centerLabel }}」的关联子图（可尝试调整深度/边类型或更换起点）</span>
            <span v-else>所有实体类型已被隐藏，点击上方图例恢复显示</span>
          </div>
        </div>
      </section>

      <!-- 详情 -->
      <aside class="graphviz-panel graphviz-detail" aria-label="图谱详情">
        <div class="graphviz-panel__header">
          <h2 class="graphviz-panel__title">{{ detailTitle }}</h2>
          <div class="graphviz-detail__tabs" aria-label="图谱详情类型">
            <button
              v-for="tab in DETAIL_TABS"
              :key="tab.mode"
              type="button"
              :class="{ 'is-active': detailMode === tab.mode }"
              @click="detailMode = tab.mode"
            >
              {{ tab.label }}
            </button>
          </div>
        </div>

        <div v-if="detailMode === 'summary'" class="graphviz-detail__body">
          <dl>
            <div v-for="[label, value] in summaryRows" :key="label">
              <dt>{{ label }}</dt>
              <dd>{{ value }}</dd>
            </div>
          </dl>
        </div>

        <div v-else-if="detailMode === 'entity'" class="graphviz-detail__body">
          <p v-if="!hasQueried" class="graphviz-detail__empty">请先查询图谱。</p>
          <template v-else>
            <dl>
              <div v-for="[label, value] in entityRows" :key="label">
                <dt>{{ label }}</dt>
                <dd>{{ value }}</dd>
              </div>
            </dl>
            <p v-if="entityListTruncated" class="graphviz-detail__note">
              仅列出前 {{ LIST_CAP }} 条，点击画布节点查看单个实体详情。
            </p>
            <button
              v-if="selectedNode"
              class="kg-button graphviz-detail__recenter"
              type="button"
              :disabled="querying"
              @click="recenterFromNode(selectedNode)"
            >
              以此节点为中心重新查询
            </button>
          </template>
        </div>

        <div v-else-if="detailMode === 'relation'" class="graphviz-detail__body">
          <p v-if="!hasQueried" class="graphviz-detail__empty">请先查询图谱。</p>
          <template v-else>
            <dl>
              <div v-for="[label, value] in relationRows" :key="label">
                <dt>{{ label }}</dt>
                <dd>{{ value }}</dd>
              </div>
            </dl>
            <p v-if="relationListTruncated" class="graphviz-detail__note">
              仅列出前 {{ LIST_CAP }} 条，点击画布关系查看单条关系详情。
            </p>
          </template>
        </div>

        <div v-else class="graphviz-detail__body">
          <section v-if="provenance && provenanceTarget" class="graphviz-provenance" aria-label="图谱数据溯源">
            <div class="graphviz-provenance__target">
              <strong>{{ provenanceTarget.name }}</strong>
              <span>{{ provenanceTarget.kind }} · {{ provenanceTarget.type }}</span>
            </div>
            <template v-if="provenanceNode">
              <h3>实体溯源</h3>
              <dl class="graphviz-provenance__rows">
                <div><dt>实体类型</dt><dd>{{ provenanceTarget.type }}</dd></div>
                <div><dt>源数据库</dt><dd>{{ provenance.sourceDatabase }}</dd></div>
                <div><dt>源数据表</dt><dd><code>{{ provenance.evidences[0]?.technicalTable || '—' }}</code></dd></div>
                <div><dt>英文字段名</dt><dd><code>{{ provenance.evidences[0]?.sourceField || '—' }}</code></dd></div>
                <div><dt>图空间 VID</dt><dd><code>{{ provenance.evidences[0]?.graphVid || provenanceTarget.id }}</code></dd></div>
                <div><dt>入库批次</dt><dd><code>{{ provenance.task.instanceId }}</code></dd></div>
                <div><dt>入库时间</dt><dd>{{ provenance.task.executedAt }}</dd></div>
              </dl>
            </template>
            <template v-else-if="selectedEdge">
              <h3>关系溯源</h3>
              <dl class="graphviz-provenance__rows">
                <div><dt>关系类型</dt><dd>{{ selectedEdge.label }}</dd></div>
                <div><dt>源数据表</dt><dd><code>{{ provenance.evidences[0]?.technicalTable || '—' }}</code></dd></div>
                <div><dt>匹配证据</dt><dd>{{ selectedEdge.matchEvidence || '—' }}</dd></div>
                <div><dt>匹配方式</dt><dd>{{ selectedEdge.matchMethod || '—' }}</dd></div>
              </dl>
              <template v-if="provenance.relationEndpoints?.length">
                <h3>两端实体来源</h3>
                <div class="graphviz-provenance__endpoints">
                  <article v-for="endpoint in provenance.relationEndpoints" :key="endpoint.role">
                    <header>{{ endpoint.role }} · {{ endpoint.name }}</header>
                    <span>实体类型：{{ endpoint.entityType }}</span>
                    <span>源数据表：<code>{{ endpoint.technicalTable }}</code></span>
                    <span>图空间 VID：<code>{{ endpoint.graphVid }}</code></span>
                  </article>
                </div>
              </template>
            </template>
          </section>
          <p v-else class="graphviz-detail__empty">暂无溯源数据，请先查询图谱，或在图谱中选中一个实体/关系。</p>
        </div>
      </aside>
    </div>
  </main>
</template>

<style scoped>
.graphviz-page{display:flex;height:100%;min-height:0;flex-direction:column;gap:16px;color:#1d2129;overflow:hidden}
.graphviz-panel{display:flex;flex-direction:column;min-height:0;border:1px solid #e5e6eb;border-radius:6px;background:#fff}
.graphviz-panel__header{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:12px;padding:12px 16px;border-bottom:1px solid #f2f3f5}
.graphviz-panel__title{margin:0;font-size:15px;line-height:22px;font-weight:600}
.graphviz-panel__meta{color:#86909c;font-size:12px;line-height:20px;white-space:nowrap}
.graphviz-space-hint{color:#86909c;font-size:12px;line-height:20px;white-space:nowrap}

/* ---------- 查询参数面板 ---------- */
.graphviz-form__body{display:flex;flex-direction:column;gap:12px;padding:12px 16px}
.graphviz-form__grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px 16px}
.graphviz-form__grid--params{grid-template-columns:repeat(5,minmax(0,1fr))}
.graphviz-field{display:flex;min-width:0;flex-direction:column;gap:4px}
.graphviz-field>label{color:#4e5969;font-size:12px;line-height:18px}
.graphviz-field--grow{grid-column:span 3}
.graphviz-field--wide{grid-column:span 2}
.graphviz-field--actions{justify-content:flex-end}
.graphviz-search{display:flex;gap:8px}
.graphviz-form__message{margin:0;color:#4e5969;font-size:12px;line-height:20px}
.graphviz-form__message--muted{color:#86909c}
.graphviz-start{display:flex;flex-direction:column;gap:4px;max-height:168px;overflow:auto;border:1px solid #f2f3f5;border-radius:4px;padding:8px;background:#fafbfc}
.graphviz-start__item{display:flex;align-items:center;gap:8px;min-width:0;padding:6px 8px;border:1px solid transparent;border-radius:4px;background:#fff;cursor:pointer;text-align:left;font-size:12px;line-height:20px}
.graphviz-start__item:hover{border-color:#4080ff}
.graphviz-start__item.is-selected{border-color:#165dff;background:#f2f7ff}
.graphviz-start__item b{flex:0 1 auto;max-width:240px;overflow:hidden;font-size:13px;text-overflow:ellipsis;white-space:nowrap}
.graphviz-start__item span{flex:0 0 auto;color:#165dff}
.graphviz-start__item code{flex:1;min-width:0;overflow:hidden;color:#86909c;text-overflow:ellipsis;white-space:nowrap}

/* a-select/a-input 根节点不带 data-v，选择器须经 :deep 从包裹层命中 */
.graphviz-field :deep(.graphviz-select.arco-select-view){display:inline-flex;box-sizing:border-box;align-items:center;width:100%;min-width:0;min-height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important}
.graphviz-field :deep(.graphviz-select.arco-select-view:hover){border-color:#4080ff!important;background:#fff!important}
.graphviz-field :deep(.graphviz-select.arco-select-view:focus-within),.graphviz-field :deep(.graphviz-select.arco-select-view-focus){border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.graphviz-field :deep(.graphviz-select .arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important}
.graphviz-field :deep(.graphviz-select .arco-select-view-value){min-width:0;overflow:hidden;background:transparent!important;font-size:13px;line-height:22px;font-weight:400;text-overflow:ellipsis;white-space:nowrap}
.graphviz-field :deep(.graphviz-select[multiple] .arco-select-view-value){display:flex;flex-wrap:wrap;gap:4px;overflow:visible;white-space:normal}
.graphviz-field :deep(.graphviz-input.arco-input-wrapper){display:inline-flex;box-sizing:border-box;width:100%;min-width:0;min-height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important}
.graphviz-field :deep(.graphviz-input.arco-input-wrapper:hover){border-color:#4080ff!important}
.graphviz-field :deep(.graphviz-input.arco-input-wrapper:focus-within){border-color:#165dff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.graphviz-field :deep(.graphviz-input input.arco-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:13px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}

/* ---------- 画布与图例 ---------- */
.graphviz-lower{display:grid;grid-template-columns:minmax(0,1fr) 360px;gap:16px;flex:1;min-height:0}
.graphviz-legend{display:flex;flex:0 0 auto;flex-wrap:wrap;gap:6px 12px;padding:8px 16px;border-bottom:1px solid #f2f3f5}
.graphviz-legend__item{display:inline-flex;align-items:center;gap:6px;padding:2px 8px;border:0;border-radius:999px;background:transparent;color:#4e5969;cursor:pointer;font-size:12px;line-height:20px}
.graphviz-legend__item i{width:9px;height:9px;border-radius:50%}
.graphviz-legend__item em{color:#86909c;font-style:normal}
.graphviz-legend__item.is-hidden{opacity:.4;text-decoration:line-through}
.graphviz-legend__item.is-expert i{background:#168cff}
.graphviz-legend__item.is-org i{background:#0ea5a4}
.graphviz-legend__item.is-company i{background:#36c414}
.graphviz-legend__item.is-paper i{background:#f5b700}
.graphviz-legend__item.is-project i{background:#ff9f0a}
.graphviz-legend__item.is-event i{background:#d97706}
.graphviz-legend__item.is-topic i{background:#722ed1}
.graphviz-legend__item.is-chain i{background:#4f46e5}
.graphviz-legend__item.is-field i{background:#a855f7}
.graphviz-legend__item.is-source i{background:#eb2f96}
.graphviz-cap-banner{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:12px;padding:6px 16px;border-bottom:1px solid #ffe4ba;background:#fff7e8;color:#b54708;font-size:12px;line-height:20px}
.graphviz-cap-banner button{flex:0 0 auto;border:0;background:transparent;color:#165dff;cursor:pointer;font-size:12px;line-height:20px;white-space:nowrap}
.graphviz-cap-banner button:hover{text-decoration:underline}
.graphviz-canvas{position:relative;flex:1;min-height:0;overflow:hidden;border-radius:4px}
.graphviz-canvas__empty{position:absolute;inset:0;z-index:2;display:grid;place-items:center;padding:24px;background:transparent;color:#86909c;font-size:13px;line-height:22px;text-align:center;pointer-events:none}

/* ---------- 详情面板 ---------- */
.graphviz-detail__tabs{display:flex;flex:0 0 auto;gap:4px;padding:4px;border-radius:4px;background:#f2f3f5}
.graphviz-detail__tabs button{padding:4px 12px;border:0;border-radius:4px;background:transparent;color:#4e5969;cursor:pointer;font-size:12px;line-height:20px;white-space:nowrap}
.graphviz-detail__tabs button.is-active{background:#fff;color:#004ecc;font-weight:500}
.graphviz-detail__body{flex:1;min-height:0;overflow:auto;padding:12px 16px}
.graphviz-detail__body dl{margin:0}
.graphviz-detail__body dl>div{display:flex;flex-direction:column;gap:2px;padding:6px 0;border-bottom:1px dashed #f2f3f5}
.graphviz-detail__body dt{color:#86909c;font-size:12px;line-height:18px}
.graphviz-detail__body dd{margin:0;color:#1d2129;font-size:13px;line-height:20px;overflow-wrap:anywhere}
.graphviz-detail__empty{margin:0;padding:24px 0;color:#86909c;font-size:13px;line-height:22px;text-align:center}
.graphviz-detail__note{margin:8px 0 0;color:#86909c;font-size:12px;line-height:20px}
.graphviz-detail__recenter{margin-top:12px}

.graphviz-provenance__target{display:flex;flex-direction:column;gap:2px;padding:8px 12px;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa}
.graphviz-provenance__target strong{font-size:13px;line-height:20px}
.graphviz-provenance__target span{color:#86909c;font-size:12px;line-height:18px}
.graphviz-provenance h3{margin:14px 0 4px;color:#1d2129;font-size:12px;line-height:18px;font-weight:600}
.graphviz-provenance__rows{margin:0}
.graphviz-provenance__rows>div{display:flex;flex-direction:column;gap:2px;padding:5px 0;border-bottom:1px dashed #f2f3f5}
.graphviz-provenance__rows dt{color:#86909c;font-size:12px;line-height:18px}
.graphviz-provenance__rows dd{margin:0;color:#1d2129;font-size:12px;line-height:20px;overflow-wrap:anywhere}
.graphviz-provenance__rows code{padding:1px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:11px;word-break:break-all}
.graphviz-provenance__endpoints{display:flex;flex-direction:column;gap:8px}
.graphviz-provenance__endpoints article{display:flex;flex-direction:column;gap:4px;padding:8px 12px;border:1px solid #e5e6eb;border-radius:4px;background:#fafbfc;font-size:12px;line-height:18px}
.graphviz-provenance__endpoints article header{color:#1d2129;font-weight:600}
.graphviz-provenance__endpoints article span{color:#4e5969}
.graphviz-provenance__endpoints article code{padding:1px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:11px;word-break:break-all}
</style>
