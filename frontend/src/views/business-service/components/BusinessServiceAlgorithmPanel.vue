<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import {
  describeExpertAlumniRelation,
  queryExpertAlumniRelation,
  type AlumniQueryResult,
} from '../../../api/expertAlumniRelation'
import {
  describeExpertCooperationAchievement,
  queryExpertCooperationAchievement,
  type CooperationQueryResult,
} from '../../../api/expertCooperationAchievement'
import iconInfo from '../../../assets/icons/icon-info.svg'
import KgGraphCanvas from '../../../components/kg-graph-canvas.vue'
import { useToast } from '../../../composables/use-toast'
import { getEdgeProvenance, getNodeProvenance, getServiceGraphPreset } from '../../../data/graph-presets'
import type { GraphEdgeData, GraphNodeData } from '../../../data/graph-presets'
import type { ServiceModule, ServiceSummaryRow } from '../service-modules'

const props = defineProps<{
  moduleInfo: ServiceModule
  responseJson: string
}>()

const { showToast } = useToast()
const resultMode = ref<'summary' | 'entity' | 'relation' | 'provenance' | 'rule' | 'api'>('summary')
const running = ref(false)
const lastTestTime = ref('—')
const lastUpdateTime = ref<number | null>(null)
const autoRefresh = ref(false)
const refreshIntervalSeconds = 10
let refreshTimer: number | null = null
const panoramaLayer = ref(3)
const panoramaRelation = ref('all')
const parameterValues = ref<Record<string, string>>({})
const paramResetToken = ref(0)
const selectedGraphNodeId = ref<string | null>(null)
const selectedGraphEdgeId = ref<string | null>(null)
const liveAlumniResult = ref<AlumniQueryResult | null>(null)
const liveCoopResult = ref<CooperationQueryResult | null>(null)
const liveApiPayload = ref<unknown>(null)
const liveError = ref<string | null>(null)
const liveDescribe = ref<Record<string, unknown> | null>(null)
const isLiveAlumni = computed(() => props.moduleInfo.key === 'expert-alumni')
const isLiveCoop = computed(() => props.moduleInfo.key === 'two-point-achievement')
const isLiveModule = computed(() => isLiveAlumni.value || isLiveCoop.value)

function mapLiveGraph(nodes: Array<{
  id: string
  label: string
  nodeType?: string
  x?: number
  y?: number
  entityType: string
  confidence: number
  relations: string
  evidence: string[]
  level?: number
}> | undefined, edges: Array<{ id: string; from: string; to: string; label: string; category: string }> | undefined): {
  nodes: GraphNodeData[]
  edges: GraphEdgeData[]
} | null {
  if (!nodes?.length) return null
  const allowed = new Set(['main', 'expert', 'org', 'company', 'paper', 'topic', 'project', 'event'])
  return {
    nodes: nodes.map((node) => ({
      id: node.id,
      label: node.label,
      nodeType: (allowed.has(String(node.nodeType)) ? node.nodeType : 'expert') as GraphNodeData['nodeType'],
      x: node.x ?? 220,
      y: node.y ?? 200,
      entityType: node.entityType,
      confidence: node.confidence ?? 0.9,
      relations: node.relations ?? '',
      evidence: node.evidence ?? [],
      level: node.level,
    })),
    edges: (edges || []).map((edge) => ({
      id: edge.id,
      from: edge.from,
      to: edge.to,
      label: edge.label,
      category: edge.category,
    })),
  }
}

const graphPreset = computed(() => getServiceGraphPreset(props.moduleInfo.key))
const liveModuleGraph = computed(() => {
  if (isLiveAlumni.value) {
    const data = liveAlumniResult.value
    if (!data) return null
    return mapLiveGraph(data.graph?.nodes, data.graph?.edges) ?? buildAlumniGraph(data)
  }
  if (isLiveCoop.value) {
    const data = liveCoopResult.value
    if (!data) return null
    return mapLiveGraph(data.graph?.nodes, data.graph?.edges)
  }
  return null
})
const graphNodes = computed(() => {
  if (isLiveModule.value) return liveModuleGraph.value?.nodes ?? []
  return graphPreset.value.nodes
})
const graphEdges = computed(() => {
  const nodes = graphNodes.value
  const edges = isLiveModule.value
    ? (liveModuleGraph.value?.edges ?? [])
    : graphPreset.value.edges
  return edges.filter((edge) => (
    nodes.some((node) => node.id === edge.from) &&
    nodes.some((node) => node.id === edge.to)
  ))
})
const isPanorama = computed(() => props.moduleInfo.key === 'industry-chain-panorama')
const panoramaLayerOptions = [
  { value: 1, label: '一级 · 产业环节' },
  { value: 2, label: '二级 · 企业/专家/技术' },
  { value: 3, label: '三级 · 动态事件' },
]
const panoramaRelationOptions = [
  { value: 'all', label: '全部关系' },
  { value: 'chain', label: '产业链主干' },
  { value: 'enterprise', label: '企业布局' },
  { value: 'expert', label: '专家支撑' },
  { value: 'technology', label: '技术支撑' },
  { value: 'event', label: '事件影响' },
]
const displayedGraphNodes = computed(() => {
  if (!isPanorama.value) return graphNodes.value
  return graphNodes.value.filter((node) => (node.level ?? 1) <= panoramaLayer.value)
})
const displayedGraphEdges = computed(() => {
  const visibleNodeIds = new Set(displayedGraphNodes.value.map((node) => node.id))
  return graphEdges.value.filter((edge) => {
    if (!visibleNodeIds.has(edge.from) || !visibleNodeIds.has(edge.to)) return false
    if (!isPanorama.value || panoramaRelation.value === 'all') return true
    if (panoramaRelation.value === 'chain') {
      return ['上游环节', '中游环节', '下游环节', '资源供给', '能力输出'].includes(edge.label)
    }
    if (panoramaRelation.value === 'enterprise') return edge.label.includes('企业')
    if (panoramaRelation.value === 'expert') return edge.label.includes('专家')
    if (panoramaRelation.value === 'technology') return edge.label.includes('技术')
    return edge.label.includes('事件')
  })
})
const graphLegendItems = computed(() => Array.from(
  new Map(displayedGraphNodes.value.map((node) => [node.nodeType, {
    type: node.nodeType,
    label: node.entityType,
  }])).values(),
))
const selectedNode = computed(() => (
  selectedGraphNodeId.value
    ? graphNodes.value.find((node) => node.id === selectedGraphNodeId.value) ?? null
    : null
))
const selectedEdge = computed(() => (
  selectedGraphEdgeId.value
    ? graphEdges.value.find((edge) => edge.id === selectedGraphEdgeId.value) ?? null
    : null
))
const selectedEdgeNodes = computed(() => {
  const edge = selectedEdge.value
  return {
    from: graphNodes.value.find((node) => node.id === edge?.from),
    to: graphNodes.value.find((node) => node.id === edge?.to),
  }
})
const relationDetailRows = computed(() => {
  const edge = selectedEdge.value
  const from = selectedEdgeNodes.value.from
  const to = selectedEdgeNodes.value.to
  if (!edge || !from || !to) return []
  return [
    ['源实体', `${from.label} / ${from.entityType}`] as const,
    ['目标实体', `${to.label} / ${to.entityType}`] as const,
    ['关系类型', edge.label] as const,
    ['关系分类', edge.category] as const,
    ['置信度', `${Math.min(from.confidence, to.confidence).toFixed(2)}`] as const,
    ['命中规则', props.moduleInfo.rules[0]?.name ?? '已命中关系识别规则'] as const,
  ]
})
const selectedProvenance = computed(() => {
  if (selectedNode.value) return getNodeProvenance(selectedNode.value)
  if (selectedEdge.value) {
    return getEdgeProvenance(selectedEdge.value, selectedEdgeNodes.value.from, selectedEdgeNodes.value.to)
  }
  return null
})
const selectedProvenanceTarget = computed(() => {
  const node = selectedNode.value
  if (node) {
    return {
      kind: '实体',
      name: node.label,
      type: node.entityType,
      id: node.id,
      confidence: node.confidence.toFixed(2),
    }
  }
  const edge = selectedEdge.value
  const from = selectedEdgeNodes.value.from
  const to = selectedEdgeNodes.value.to
  if (!edge || !from || !to) return null
  return {
    kind: '关系',
    name: `${from.label} → ${to.label}`,
    type: edge.label,
    id: edge.id,
    confidence: Math.min(from.confidence, to.confidence).toFixed(2),
  }
})
function formatTimestamp(date: Date) {
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}

const updateStatus = computed(() => {
  if (running.value) return '正在拉取最新批次数据…'
  if (autoRefresh.value) return `自动更新中（每 ${refreshIntervalSeconds}s 刷新一次）`
  if (lastUpdateTime.value === null) return '尚未更新，点击"刷新数据"或开启自动更新'
  const elapsed = Math.floor((Date.now() - lastUpdateTime.value) / 1000)
  if (elapsed < 5) return `刚刚更新（${elapsed}s 前）`
  if (elapsed < 60) return `已更新（${elapsed}s 前）`
  if (elapsed < 3600) return `已更新（${Math.floor(elapsed / 60)}min 前），建议刷新`
  return `已更新（${Math.floor(elapsed / 3600)}h 前），数据可能过期`
})

const liveSummaryRows = computed((): ServiceSummaryRow[] | null => {
  if (!isLiveModule.value) return null
  if (liveError.value) {
    return [
      { label: '调用状态', value: '失败' },
      { label: '错误信息', value: liveError.value },
    ]
  }
  if (isLiveAlumni.value) {
    const data = liveAlumniResult.value
    if (!data) {
      return [
        { label: '专家', value: '' },
        { label: '模式', value: '' },
        { label: '校友数', value: '' },
        { label: '维度目录', value: '' },
        { label: '截断', value: '' },
        { label: '图空间', value: '' },
      ]
    }
    if (data.summaryRows?.length) {
      return data.summaryRows.map((row) => ({ label: row.label, value: row.value }))
    }
  }
  if (isLiveCoop.value) {
    const data = liveCoopResult.value
    if (!data) {
      return [
        { label: '专家 A', value: '' },
        { label: '专家 B', value: '' },
        { label: '合作成果类型', value: '' },
        { label: '成果总量', value: '' },
        { label: '成果分布', value: '' },
        { label: '核心贡献', value: '' },
        { label: '合作模式', value: '' },
        { label: '图空间', value: '' },
      ]
    }
    if (data.summaryRows?.length) {
      return data.summaryRows.map((row) => ({ label: row.label, value: row.value }))
    }
    const s = data.summary
    return [
      { label: '专家 A', value: `${data.source.name}（${data.source.id}）` },
      { label: '专家 B', value: `${data.target.name}（${data.target.id}）` },
      { label: '成果分布', value: `论文 ${s.papers}、专利 ${s.patents}、项目 ${s.projects}` },
      { label: '核心贡献', value: data.coreContribution },
      { label: '合作模式', value: data.cooperationMode },
    ]
  }
  return null
})

const liveRules = computed(() => {
  if (isLiveAlumni.value && liveAlumniResult.value?.rules?.length) return liveAlumniResult.value.rules
  if (isLiveCoop.value && liveCoopResult.value?.rules?.length) return liveCoopResult.value.rules
  return props.moduleInfo.rules
})

const liveEntities = computed(() => {
  if (isLiveAlumni.value) return liveAlumniResult.value?.entities
  if (isLiveCoop.value) return liveCoopResult.value?.entities
  return undefined
})

const liveRelationsList = computed(() => {
  if (isLiveAlumni.value) return liveAlumniResult.value?.relations
  if (isLiveCoop.value) return liveCoopResult.value?.relations
  return undefined
})

const liveEntityRows = computed(() => {
  if (!isLiveModule.value) return null
  const selected = selectedNode.value
  if (selected) {
    const rows: Array<readonly [string, string]> = [
      ['实体名称', selected.label],
      ['实体类型', selected.entityType],
      ['命中关系', selected.relations],
      ['置信度', selected.confidence.toFixed(2)],
    ]
    if (selected.evidence?.length) {
      rows.push(['证据', selected.evidence.join('；')])
    }
    return rows
  }
  const entities = liveEntities.value
  if (!entities?.length) return [] as Array<readonly [string, string]>
  return entities.flatMap((entity, index) => ([
    [`实体 ${index + 1}`, `${entity.label}（${entity.id}）`] as const,
    ['类型', entity.entityType] as const,
    ['关系', entity.relations] as const,
  ]))
})

const liveRelationRows = computed(() => {
  if (!isLiveModule.value) return null
  if (selectedEdge.value) return relationDetailRows.value
  const relations = liveRelationsList.value
  if (!relations?.length) return [] as Array<readonly [string, string]>
  return relations.flatMap((rel, index) => {
    const rows: Array<readonly [string, string]> = [
      [`关系 ${index + 1}`, `${rel.fromName || rel.from} → ${rel.toName || rel.to}`],
      ['类型', rel.label],
    ]
    if ('dimensions' in rel && Array.isArray(rel.dimensions)) {
      rows.push(['维度', rel.dimensions.join('、') || '—'])
    }
    if ('sharedInstitutions' in rel && Array.isArray(rel.sharedInstitutions)) {
      rows.push(['院校', rel.sharedInstitutions.join('、') || '—'])
    }
    if ('summary' in rel && typeof rel.summary === 'string') {
      rows.push(['摘要', rel.summary || '—'])
    }
    if ('interactions' in rel && rel.interactions && typeof rel.interactions === 'object') {
      const summary = (rel.interactions as { summary?: string }).summary
      rows.push(['互动', summary || '—'])
    }
    return rows
  })
})

const liveProvenance = computed(() => {
  if (isLiveAlumni.value) return liveAlumniResult.value?.provenance ?? null
  if (isLiveCoop.value) return liveCoopResult.value?.provenance ?? null
  return null
})

const detailRows = computed(() => {
  const rows = liveSummaryRows.value ?? props.moduleInfo.summaryRows
  return rows.map((row) => {
    if (row.label === '更新状态' && isPanorama.value) {
      return [row.label, updateStatus.value] as const
    }
    return [row.label, row.value] as const
  })
})
const apiResultJson = computed(() => JSON.stringify(
  liveApiPayload.value ?? {
    describe: liveDescribe.value,
    ...JSON.parse(props.responseJson),
    request_params: parameterValues.value,
  },
  null,
  2,
))

watch(
  () => props.moduleInfo.key,
  () => {
    resultMode.value = 'summary'
    panoramaLayer.value = 3
    panoramaRelation.value = 'all'
    selectedGraphNodeId.value = null
    selectedGraphEdgeId.value = null
    liveAlumniResult.value = null
    liveCoopResult.value = null
    liveApiPayload.value = null
    liveError.value = null
    liveDescribe.value = null
    resetParameters()
    autoRefresh.value = false
    if (isLiveModule.value) {
      void loadModuleDescribe()
    }
  },
  { immediate: true },
)

async function loadModuleDescribe() {
  try {
    const meta = isLiveAlumni.value
      ? await describeExpertAlumniRelation() as unknown as Record<string, unknown>
      : await describeExpertCooperationAchievement() as unknown as Record<string, unknown>
    liveDescribe.value = meta
  } catch (error) {
    const message = error instanceof Error ? error.message : '模块描述接口失败'
    liveDescribe.value = { status: 'error', msg: message }
    showToast(`模块描述接口异常：${message}`, 'warning')
  }
}

watch([panoramaLayer, panoramaRelation], () => {
  if (!isPanorama.value) return
  selectedGraphNodeId.value = null
  selectedGraphEdgeId.value = null
  resultMode.value = 'summary'
})

function formatValue(value: unknown) {
  if (Array.isArray(value)) return value.join('、')
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (value === undefined || value === null) return ''
  return String(value)
}

function resetParameters() {
  parameterValues.value = Object.fromEntries(
    props.moduleInfo.requestFields.map((field) => [
      field.name,
      formatValue(props.moduleInfo.requestExample[field.name]),
    ]),
  )
  paramResetToken.value += 1
  if (isLiveModule.value) {
    liveAlumniResult.value = null
    liveCoopResult.value = null
    liveApiPayload.value = null
    liveError.value = null
    selectedGraphNodeId.value = null
    selectedGraphEdgeId.value = null
    resultMode.value = 'summary'
    lastTestTime.value = '—'
    lastUpdateTime.value = null
    void loadModuleDescribe()
  }
  showToast('已重置为默认参数', 'info')
}

function buildAlumniGraph(data: AlumniQueryResult | null): { nodes: GraphNodeData[]; edges: GraphEdgeData[] } | null {
  if (!data) return null
  const items = data.items.slice(0, 12)
  const cx = 220
  const cy = 200
  const nodes: GraphNodeData[] = [{
    id: data.expert.id,
    label: data.expert.name || data.expert.id.slice(0, 12),
    nodeType: 'main',
    x: cx,
    y: cy,
    entityType: '科技专家',
    confidence: 1,
    relations: `校友 ${data.total}`,
    evidence: [`mode=${data.mode}`, `educations=${data.expert.educations?.length ?? 0}`],
  }]
  const edges: GraphEdgeData[] = []
  items.forEach((item, index) => {
    const angle = (Math.PI * 2 * index) / Math.max(items.length, 1) - Math.PI / 2
    const radius = 180
    nodes.push({
      id: item.alumniId,
      label: item.name || item.alumniId.slice(0, 12),
      nodeType: 'expert',
      x: cx + Math.cos(angle) * radius + 200,
      y: cy + Math.sin(angle) * radius,
      entityType: '校友专家',
      confidence: 0.9,
      relations: item.dimensions.join('、') || '同校',
      evidence: [
        `shared=${item.sharedInstitutions.join('/') || '-'}`,
        item.interactions?.summary || '无互动',
      ],
    })
    edges.push({
      id: `alumni-${data.expert.id}-${item.alumniId}`,
      from: data.expert.id,
      to: item.alumniId,
      label: item.dimensions[0] || '校友',
      category: '校友',
    })
  })
  return { nodes, edges }
}

function optionalParam(value: string | undefined): string | undefined {
  const cleaned = value?.trim()
  return cleaned ? cleaned : undefined
}

/** 解析「2020-2026」「2020~2026」「2020/2026」或单边「2020」为 API 起止时间。 */
function parseTimeRange(raw: string | undefined): { start?: string; end?: string } {
  if (!raw) return {}
  const parts = raw.split(/\s*[-~/～至到]\s*/).map((x) => x.trim()).filter(Boolean)
  if (parts.length >= 2) return { start: parts[0], end: parts[1] }
  if (parts.length === 1) return { start: parts[0] }
  return {}
}

async function handleRun() {
  if (running.value) return
  running.value = true
  liveError.value = null
  try {
    if (isLiveAlumni.value) {
      const expertId = parameterValues.value.expertId?.trim()
      if (!expertId) {
        showToast('请填写 expertId', 'warning')
        return
      }
      const body = {
        expertId,
        targetExpertId: optionalParam(parameterValues.value.targetExpertId),
        school: optionalParam(parameterValues.value.school),
        educationStage: optionalParam(parameterValues.value.educationStage),
        limit: 20,
      }
      const resp = await queryExpertAlumniRelation(body) as unknown as {
        code: number
        success: boolean
        data: AlumniQueryResult
        msg: string
      }
      liveApiPayload.value = {
        describe: liveDescribe.value,
        request: body,
        response: resp,
      }
      if (!resp.success || resp.code !== 200) {
        liveAlumniResult.value = null
        liveError.value = resp.msg || `业务码 ${resp.code}`
        showToast(liveError.value, 'warning')
        resultMode.value = 'api'
      } else {
        liveAlumniResult.value = resp.data
        showToast(
          resp.data.total > 0
            ? `命中 ${resp.data.total} 名校友（${resp.data.mode}）`
            : `调用成功，未命中校友（${resp.data.mode}）`,
          resp.data.total > 0 ? 'success' : 'info',
        )
        resultMode.value = 'summary'
        selectedGraphNodeId.value = null
        selectedGraphEdgeId.value = null
      }
    } else if (isLiveCoop.value) {
      const sourceExpertId = parameterValues.value.sourceExpertId?.trim()
      const targetExpertId = parameterValues.value.targetExpertId?.trim()
      if (!sourceExpertId || !targetExpertId) {
        showToast('请填写 sourceExpertId 与 targetExpertId', 'warning')
        return
      }
      const typesRaw = optionalParam(parameterValues.value.achievementTypes)
      const achievementTypes = typesRaw
        ? typesRaw.split(/[,，/\s]+/).map((x) => x.trim()).filter(Boolean) as Array<'paper' | 'patent' | 'project'>
        : undefined
      const { start: timeRangeStart, end: timeRangeEnd } = parseTimeRange(
        optionalParam(parameterValues.value.timeRange),
      )
      const body = {
        sourceExpertId,
        targetExpertId,
        achievementTypes,
        timeRangeStart,
        timeRangeEnd,
        limitPerType: 20,
      }
      const resp = await queryExpertCooperationAchievement(body) as unknown as {
        code: number
        success: boolean
        data: CooperationQueryResult
        msg: string
      }
      liveApiPayload.value = {
        describe: liveDescribe.value,
        request: body,
        response: resp,
      }
      if (!resp.success || resp.code !== 200) {
        liveCoopResult.value = null
        liveError.value = resp.msg || `业务码 ${resp.code}`
        showToast(liveError.value, 'warning')
        resultMode.value = 'api'
      } else {
        liveCoopResult.value = resp.data
        const total = (resp.data.summary?.papers || 0)
          + (resp.data.summary?.patents || 0)
          + (resp.data.summary?.projects || 0)
        showToast(
          total > 0
            ? `共同成果 ${total} 项（${resp.data.cooperationMode}）`
            : `调用成功，暂无共同成果（${resp.data.cooperationMode}）`,
          total > 0 ? 'success' : 'info',
        )
        resultMode.value = 'summary'
        selectedGraphNodeId.value = null
        selectedGraphEdgeId.value = null
      }
    } else {
      await new Promise((resolve) => window.setTimeout(resolve, 360))
    }
    const now = new Date()
    lastTestTime.value = formatTimestamp(now)
    lastUpdateTime.value = now.getTime()
  } catch (error) {
    const message = error instanceof Error ? error.message : '请求失败'
    liveError.value = message
    liveAlumniResult.value = null
    liveCoopResult.value = null
    liveApiPayload.value = { request_params: parameterValues.value, error: message }
    showToast(message, 'warning')
    resultMode.value = 'api'
  } finally {
    running.value = false
  }
}

function startAutoRefresh() {
  if (refreshTimer !== null) return
  refreshTimer = window.setInterval(() => {
    handleRun()
  }, refreshIntervalSeconds * 1000)
}

function stopAutoRefresh() {
  if (refreshTimer !== null) {
    window.clearInterval(refreshTimer)
    refreshTimer = null
  }
}

watch(autoRefresh, (on) => {
  if (on) {
    handleRun()
    startAutoRefresh()
  } else {
    stopAutoRefresh()
  }
})

onBeforeUnmount(() => {
  stopAutoRefresh()
})

function resetPanoramaView() {
  panoramaLayer.value = 3
  panoramaRelation.value = 'all'
  selectedGraphNodeId.value = null
  selectedGraphEdgeId.value = null
  resultMode.value = 'summary'
}

function handleParameterInput(fieldName: string, event: Event) {
  parameterValues.value = {
    ...parameterValues.value,
    [fieldName]: (event.target as HTMLInputElement).value,
  }
}

function handleSelectGraphNode(node: GraphNodeData) {
  selectedGraphNodeId.value = node.id
  selectedGraphEdgeId.value = null
  resultMode.value = 'entity'
}

function handleSelectGraphEdge(edge: GraphEdgeData) {
  selectedGraphEdgeId.value = edge.id
  selectedGraphNodeId.value = null
  resultMode.value = 'relation'
}
</script>

<template>
  <section class="kg-panel service-console">
    <div class="service-console__head">
      <div>
        <h2>{{ moduleInfo.title }}</h2>
      </div>
      <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
    </div>
    <div class="service-console__params">
      <label v-for="field in moduleInfo.requestFields" :key="field.name">
        <span><i v-if="field.required === '是'">*</i>{{ field.name }}</span>
        <input
          :key="`${field.name}-${paramResetToken}`"
          :value="parameterValues[field.name] ?? ''"
          :placeholder="field.description"
          @input="handleParameterInput(field.name, $event)"
        />
      </label>
    </div>
    <div class="service-console__actions">
      <button class="kg-button" type="button" @click="handleRun">{{ running ? '测试中...' : '执行测试' }}</button>
      <button class="kg-button kg-button--secondary" type="button" @click="resetParameters">重置参数</button>
    </div>
  </section>

  <div class="business-service__main">
    <section class="kg-panel graph-panel">
      <div class="kg-panel__header">
        <h2 class="kg-panel__title">测试结果预览</h2>
        <div class="graph-panel__time">
          <span>最近测试时间：</span>
          <strong>{{ lastTestTime }}</strong>
        </div>
      </div>
      <div v-if="isPanorama" class="graph-panel__filters" aria-label="产业链全景图显示控制">
        <label>
          <span>层级展开</span>
          <select v-model.number="panoramaLayer">
            <option v-for="item in panoramaLayerOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <label>
          <span>关系筛选</span>
          <select v-model="panoramaRelation">
            <option v-for="item in panoramaRelationOptions" :key="item.value" :value="item.value">{{ item.label }}</option>
          </select>
        </label>
        <button type="button" @click="resetPanoramaView">恢复全景</button>
        <span class="graph-panel__filters-divider" aria-hidden="true"></span>
        <button type="button" class="graph-panel__refresh" :disabled="running" @click="handleRun">
          {{ running ? '刷新中…' : '↻ 刷新数据' }}
        </button>
        <label class="graph-panel__autorefresh">
          <input type="checkbox" v-model="autoRefresh" />
          <span>自动更新（{{ refreshIntervalSeconds }}s）</span>
        </label>
      </div>
      <div class="graph-panel__legend" aria-label="图谱实体类型图例">
        <span v-for="item in graphLegendItems" :key="item.type" :class="`is-${item.type}`">
          <i />{{ item.label }}
        </span>
      </div>
      <div class="graph-panel__canvas">
        <KgGraphCanvas
          :nodes="displayedGraphNodes"
          :edges="displayedGraphEdges"
          :selected-node-id="selectedGraphNodeId"
          :selected-edge-id="selectedGraphEdgeId"
          aria-label="测试结果图谱"
          @select-node="handleSelectGraphNode"
          @select-edge="handleSelectGraphEdge"
        />
      </div>
    </section>

    <aside class="business-service__side">
      <section class="kg-panel result-panel">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">结果详情</h2>
          <div class="result-panel__tabs">
            <button :class="{ 'is-active': resultMode === 'summary' }" type="button" @click="resultMode = 'summary'">摘要</button>
            <button :class="{ 'is-active': resultMode === 'entity' }" type="button" @click="resultMode = 'entity'">实体</button>
            <button :class="{ 'is-active': resultMode === 'relation' }" type="button" @click="resultMode = 'relation'">关系</button>
            <button :class="{ 'is-active': resultMode === 'provenance' }" type="button" @click="resultMode = 'provenance'">溯源</button>
            <button :class="{ 'is-active': resultMode === 'rule' }" type="button" @click="resultMode = 'rule'">规则</button>
            <button :class="{ 'is-active': resultMode === 'api' }" type="button" @click="resultMode = 'api'">API</button>
          </div>
        </div>
        <dl v-if="resultMode === 'summary'" class="result-panel__table">
          <div v-for="([label, value], index) in detailRows" :key="`${label}-${index}`">
            <dt>{{ label }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <dl v-else-if="resultMode === 'entity' && liveEntityRows" class="result-panel__table">
          <div v-for="([label, value], index) in liveEntityRows" :key="`entity-${label}-${index}`">
            <dt>{{ label }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <dl v-else-if="resultMode === 'entity' && selectedNode" class="result-panel__table">
          <div><dt>实体名称</dt><dd>{{ selectedNode.label }}</dd></div>
          <div><dt>实体类型</dt><dd>{{ selectedNode.entityType }}</dd></div>
          <div><dt>命中关系</dt><dd>{{ selectedNode.relations }}</dd></div>
          <div><dt>置信度</dt><dd>{{ selectedNode.confidence.toFixed(2) }}</dd></div>
        </dl>
        <dl v-else-if="resultMode === 'relation' && liveRelationRows" class="result-panel__table">
          <div v-for="([label, value], index) in liveRelationRows" :key="`rel-${label}-${index}`">
            <dt>{{ label }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <dl v-else-if="resultMode === 'relation' && selectedEdge" class="result-panel__table">
          <div v-for="([label, value], index) in relationDetailRows" :key="`${label}-${index}`">
            <dt>{{ label }}</dt>
            <dd>{{ value }}</dd>
          </div>
        </dl>
        <section v-else-if="resultMode === 'provenance' && liveProvenance" class="result-provenance">
          <header><strong>数据溯源</strong><span>{{ isLiveCoop ? '合作成果查询' : isLiveAlumni ? '校友查询' : '查询结果' }}</span></header>
          <div class="result-provenance__target">
            <strong>{{ liveProvenance.sourceDatabase }}</strong>
            <span>{{ liveProvenance.summary || '—' }}</span>
          </div>
          <h3>证据列表</h3>
          <div class="result-provenance__evidence-list">
            <article v-for="(ev, index) in liveProvenance.evidences" :key="`${ev.recordId}-${index}`">
              <header><strong>{{ ev.title }}</strong></header>
              <p><b>{{ ev.summary }}</b></p>
              <span>业务表：{{ ev.businessTable }}</span>
              <span>技术表：<code>{{ ev.technicalTable }}</code></span>
              <span>记录 ID：<code>{{ ev.recordId }}</code></span>
              <span>字段：<code>{{ ev.fieldIdentifier }}</code></span>
            </article>
          </div>
        </section>
        <section v-else-if="resultMode === 'provenance' && selectedProvenance && selectedProvenanceTarget" class="result-provenance">
          <header><strong>当前追溯对象</strong><span>{{ selectedProvenanceTarget.kind }}</span></header>
          <div class="result-provenance__target">
            <strong>{{ selectedProvenanceTarget.name }}</strong>
            <span>{{ selectedProvenanceTarget.kind }}</span>
          </div>
          <template v-if="selectedNode">
            <h3>实体溯源</h3>
            <dl class="result-provenance__source">
              <div><dt>实体类型</dt><dd>{{ selectedProvenanceTarget.type }}</dd></div>
              <div><dt>源数据表</dt><dd><code>{{ selectedProvenance.evidences[0]?.technicalTable }}</code></dd></div>
              <div><dt>字段标识 ID</dt><dd><code>{{ selectedProvenance.evidences[0]?.fieldIdentifier }}</code></dd></div>
              <div><dt>构建任务 ID</dt><dd><code>{{ selectedProvenance.task.instanceId }}</code></dd></div>
            </dl>
            <div class="result-provenance__task-meta"><RouterLink :to="{ name: 'processing-instance-detail', params: { instanceId: selectedProvenance.task.instanceId }, query: { stage: '图谱构建', objectName: selectedProvenanceTarget.name, objectId: selectedProvenanceTarget.id, objectType: selectedProvenanceTarget.type, kind: selectedProvenanceTarget.kind, sourceTable: selectedProvenance.evidences[0]?.technicalTable, sourceRecordId: selectedProvenance.evidences[0]?.fieldIdentifier } }">查看构建详情 →</RouterLink></div>
          </template>
          <template v-else-if="selectedProvenance.relationEndpoints?.length">
            <h3>关系溯源</h3>
            <dl class="result-provenance__source"><div><dt>关系类型</dt><dd>{{ selectedProvenanceTarget.type }}</dd></div></dl>
            <h3>两端实体来源</h3>
            <div class="result-provenance__evidence-list">
              <article v-for="endpoint in selectedProvenance.relationEndpoints" :key="endpoint.role">
                <header><strong>{{ endpoint.role }} · {{ endpoint.name }}</strong></header>
                <p><b>实体类型：{{ endpoint.entityType }}</b></p>
                <span>源数据表：<code>{{ endpoint.technicalTable }}</code></span>
                <span>字段标识 ID：<code>{{ endpoint.fieldIdentifier }}</code></span>
              </article>
            </div>
            <dl class="result-provenance__source"><div><dt>构建任务 ID</dt><dd><code>{{ selectedProvenance.task.instanceId }}</code></dd></div></dl>
            <div class="result-provenance__task-meta"><RouterLink :to="{ name: 'processing-instance-detail', params: { instanceId: selectedProvenance.task.instanceId }, query: { stage: '图谱构建', objectName: selectedProvenanceTarget.name, objectId: selectedProvenanceTarget.id, objectType: selectedProvenanceTarget.type, kind: selectedProvenanceTarget.kind } }">查看构建详情 →</RouterLink></div>
          </template>
        </section>
        <div v-else-if="resultMode === 'rule'" class="result-panel__rules">
          <article v-for="(rule, index) in liveRules" :key="rule.name">
            <header>
              <strong>规则 {{ index + 1 }}：{{ rule.name }}</strong>
              <span>{{ rule.type }}</span>
            </header>
            <dl>
              <div><dt>适用对象</dt><dd>{{ rule.target }}</dd></div>
              <div><dt>触发条件</dt><dd>{{ rule.trigger }}</dd></div>
              <div><dt>处理逻辑</dt><dd>{{ rule.logic }}</dd></div>
              <div><dt>输出结果</dt><dd>{{ rule.output }}</dd></div>
              <div><dt>置信度阈值</dt><dd>{{ rule.threshold }}</dd></div>
              <div><dt>审核策略</dt><dd>{{ rule.audit }}</dd></div>
            </dl>
          </article>
        </div>
        <pre v-else-if="resultMode === 'api'" class="result-panel__code">{{ apiResultJson }}</pre>
        <dl v-else class="result-panel__table">
          <div><dt>提示</dt><dd>请先执行测试，或点选图谱节点/边查看详情</dd></div>
        </dl>
      </section>
    </aside>
  </div>
</template>

<style scoped>
.service-console {
  display: grid;
  grid-template-columns: minmax(240px, 0.8fr) minmax(0, 1.8fr) auto;
  align-items: end;
  gap: 14px;
  min-height: 92px;
  padding: 14px 16px;
  overflow: visible;
}

.service-console__head {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 16px;
  align-items: start;
  gap: 10px;
  min-width: 0;
}

.service-console__head h2 {
  margin: 0;
  color: #10264c;
  font-size: 18px;
  line-height: 26px;
  font-weight: 700;
}

.service-console__head p {
  margin: 4px 0 0;
  color: var(--text-tertiary);
  font-size: 14px;
  line-height: 22px;
  overflow-wrap: anywhere;
}

.service-console__params {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  min-width: 0;
}

.service-console__params label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.service-console__params span {
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 20px;
}

.service-console__params i {
  margin-right: 4px;
  color: var(--danger);
  font-style: normal;
}

.service-console__params input {
  width: 100%;
  height: 36px;
  min-width: 0;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--text-primary);
  font-size: 15px;
}

.field-info-icon {
  width: 14px;
  height: 14px;
}

.service-console__actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
  min-width: 236px;
}

.business-service__main {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: var(--space-16);
  flex: 1;
  min-height: 0;
  padding: var(--space-16);
  border-radius: var(--radius-md);
  background: var(--surface-subtle);
  overflow: hidden;
}

.business-service__side,
.graph-panel,
.result-panel {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.business-service__side,
.graph-panel,
.result-panel {
  height: 100%;
}

.graph-panel__time {
  display: flex;
  gap: var(--space-12);
  color: var(--text-tertiary);
}

.graph-panel__time strong {
  font-weight: 400;
}

.graph-panel__filters {
  display: flex;
  align-items: end;
  gap: 12px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: #f7faff;
}

.graph-panel__filters label {
  display: grid;
  gap: 4px;
  min-width: 180px;
}

.graph-panel__filters span {
  color: var(--text-tertiary);
  font-size: 12px;
}

.graph-panel__filters select,
.graph-panel__filters button {
  height: 32px;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--text-primary);
  font-size: 13px;
}

.graph-panel__filters button {
  color: var(--primary);
  cursor: pointer;
}

.graph-panel__filters button:disabled {
  color: var(--text-tertiary);
  cursor: not-allowed;
  opacity: 0.7;
}

.graph-panel__filters-divider {
  width: 1px;
  height: 24px;
  margin: 0 4px;
  border-left: 1px solid var(--border);
}

.graph-panel__refresh {
  font-weight: 600;
}

.graph-panel__autorefresh {
  display: inline-flex !important;
  align-items: center;
  gap: 6px;
  min-width: auto !important;
  cursor: pointer;
}

.graph-panel__autorefresh input {
  width: 14px;
  height: 14px;
  margin: 0;
  cursor: pointer;
  accent-color: var(--primary);
}

.graph-panel__autorefresh span {
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.graph-panel__legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 14px;
  min-height: 38px;
  padding: 7px 12px;
  border-bottom: 1px solid var(--border);
  background: #fbfdff;
}

.graph-panel__legend span {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-secondary);
  font-size: 12px;
  white-space: nowrap;
}

.graph-panel__legend i {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: #1e8ff3;
}

.graph-panel__legend .is-org i,
.graph-panel__legend .is-company i { background: #48c914; }
.graph-panel__legend .is-paper i { background: #762bd7; }
.graph-panel__legend .is-project i { background: #ffad17; }
.graph-panel__legend .is-event i { background: #eb2aa3; }
.graph-panel__legend .is-topic i { background: #2f6bff; }

.graph-panel__canvas {
  flex: 1;
  height: auto;
  min-height: 0;
  overflow: hidden;
}

:deep(.kg-graph-viewport) {
  height: 100%;
  min-height: 0;
}

.result-panel__tabs {
  display: inline-flex;
  gap: 0;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--surface-subtle);
}

.result-panel__tabs button {
  height: 28px;
  padding: 0 12px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.result-panel__tabs button.is-active {
  background: var(--surface);
  color: var(--primary);
  font-weight: 600;
}

.result-panel__table {
  flex: 1;
  min-height: 0;
  margin: 0;
  overflow: auto;
}

.result-panel__table div {
  display: grid;
  grid-template-columns: 190px minmax(0, 1fr);
  min-height: 44px;
  border-bottom: 1px solid var(--border);
}

.result-panel__table dt,
.result-panel__table dd {
  margin: 0;
  padding: 10px 14px;
  font-size: 15px;
  line-height: 24px;
}

.result-panel__table dt {
  color: var(--text-tertiary);
  text-align: right;
  border-right: 1px solid var(--border);
  font-weight: 600;
}

.result-panel__table dd {
  color: var(--text-primary);
  overflow-wrap: anywhere;
}

.result-provenance {
  display: grid;
  gap: 12px;
  margin: 12px 14px 14px;
  padding: 12px;
  border: 1px solid #cfe0ff;
  border-radius: 8px;
  background: linear-gradient(180deg, #f7faff 0%, #fff 100%);
  overflow: auto;
}

.result-provenance header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.result-provenance header strong {
  color: #10264c;
  font-size: 14px;
}

.result-provenance header span {
  padding: 2px 8px;
  border-radius: 999px;
  background: #e8f1ff;
  color: var(--primary);
  font-size: 12px;
}

.result-provenance__target {
  display: grid;
  gap: 4px;
  padding: 11px 12px;
  border-radius: 7px;
  background: #eaf2ff;
}

.result-provenance__target strong {
  color: #16355f;
  font-size: 14px;
  line-height: 20px;
}

.result-provenance__target span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.result-provenance h3 {
  margin: 2px 0 -5px;
  color: #536987;
  font-size: 12px;
  line-height: 18px;
  font-weight: 600;
}

.result-provenance .result-provenance__source {
  flex: none;
  overflow: visible;
}

.result-provenance .result-provenance__source div {
  grid-template-columns: 86px minmax(0, 1fr);
  min-height: 34px;
  border: 0;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.82);
}

.result-provenance .result-provenance__source dt,
.result-provenance .result-provenance__source dd {
  padding: 6px 8px;
  font-size: 12px;
  line-height: 20px;
}

.result-provenance code {
  color: #2458a6;
  font-family: Consolas, Monaco, monospace;
  overflow-wrap: anywhere;
}

.result-provenance__database {
  margin: 0;
  padding: 7px 9px;
  border-radius: 6px;
  background: #f3f7fd;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.result-provenance__evidence-list {
  display: grid;
  gap: 8px;
}

.result-provenance__evidence-list article {
  display: grid;
  gap: 6px;
  padding: 9px 10px;
  border: 1px solid #e1eaf8;
  border-radius: 7px;
  background: #fff;
}

.result-provenance__evidence-list article header,
.result-provenance__evidence-list article p {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin: 0;
}

.result-provenance__evidence-list article header strong,
.result-provenance__evidence-list article p b {
  color: #243b62;
  font-size: 12px;
  line-height: 18px;
}

.result-provenance__evidence-list article > span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.result-provenance__task-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 4px;
}

.result-provenance__task-meta span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.result-provenance__task-meta a {
  color: var(--primary);
  font-size: 12px;
  text-decoration: none;
}

.result-provenance__source b,
.result-provenance__output b {
  color: #00a870;
  font-weight: 600;
}

.result-panel__code {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: 14px 16px;
  overflow: auto;
  color: #2f3442;
  background: #f7f9fc;
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
}

.result-panel__rules {
  flex: 1;
  min-height: 0;
  display: grid;
  gap: 10px;
  align-content: start;
  padding: 14px;
  overflow: auto;
}

.result-panel__rules article {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid #e2ebf8;
  border-radius: 8px;
  background: #fbfdff;
}

.result-panel__rules header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  min-width: 0;
}

.result-panel__rules strong {
  color: var(--primary);
  font-size: 15px;
}

.result-panel__rules header span {
  flex: 0 0 auto;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--primary-subtle);
  color: var(--primary);
  font-size: 12px;
  line-height: 18px;
}

.result-panel__rules dl {
  display: grid;
  gap: 6px;
  margin: 0;
}

.result-panel__rules dl div {
  display: grid;
  grid-template-columns: 84px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.result-panel__rules dt,
.result-panel__rules dd {
  margin: 0;
  font-size: 14px;
  line-height: 22px;
}

.result-panel__rules dt {
  color: var(--text-tertiary);
  font-weight: 600;
  text-align: right;
}

.result-panel__rules dd {
  color: var(--text-secondary);
  overflow-wrap: anywhere;
}

@media (max-width: 1280px) {
  .service-console,
  .business-service__main,
  .service-console__params {
    grid-template-columns: minmax(0, 1fr);
  }
}
</style>
