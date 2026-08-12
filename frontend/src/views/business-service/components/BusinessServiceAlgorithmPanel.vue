<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import iconInfo from '../../../assets/icons/icon-info.svg'
import KgGraphCanvas from '../../../components/kg-graph-canvas.vue'
import { convertServiceGraph, runKgService, type KgServiceResponse } from '../../../api/kgService'
import { getServiceGraphPreset } from '../../../data/graph-presets'
import type { GraphEdgeData, GraphNodeData } from '../../../data/graph-presets'
import type { ServiceModule, ServiceSummaryRow } from '../service-modules'

const props = defineProps<{
  moduleInfo: ServiceModule
  responseJson: string
}>()

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
const selectedGraphNodeId = ref<string | null>(null)
const selectedGraphEdgeId = ref<string | null>(null)
const liveResult = ref<KgServiceResponse | null>(null)
const liveError = ref<string | null>(null)
const liveCenterId = ref<string | null>(null)
const graphPreset = computed(() => getServiceGraphPreset(props.moduleInfo.key))
const liveGraph = computed(() => {
  if (!liveResult.value?.graph) return null
  return convertServiceGraph(liveResult.value.graph, liveCenterId.value ?? undefined)
})
const graphNodes = computed(() => liveGraph.value?.nodes ?? graphPreset.value.nodes)
const graphEdges = computed(() => {
  const edges = liveGraph.value?.edges ?? graphPreset.value.edges
  return edges.filter((edge) => (
    graphNodes.value.some((node) => node.id === edge.from) &&
    graphNodes.value.some((node) => node.id === edge.to)
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
function formatDetailValue(value: unknown): string {
  if (Array.isArray(value)) return value.map(formatDetailValue).join('、')
  if (value && typeof value === 'object') return JSON.stringify(value)
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value ?? '-')
}

function detailEntries(details?: Record<string, unknown>, skip: string[] = []) {
  if (!details) return [] as Array<readonly [string, string]>
  const skipped = new Set(skip)
  return Object.entries(details)
    .filter(([key, value]) => !skipped.has(key) && value !== undefined && value !== null && value !== '')
    .map(([key, value]) => [key, formatDetailValue(value)] as const)
}

const entityDetailRows = computed(() => {
  const node = selectedNode.value
  if (!node) return []
  return [
    ['实体ID', node.id] as const,
    ['实体名称', node.label] as const,
    ['实体类型', node.entityType] as const,
    ['命中关系', node.relations || '-'] as const,
    ['置信度', node.confidence.toFixed(2)] as const,
    ...detailEntries(node.details, ['details', 'provenance', 'confidence', 'evidence', 'relations']),
  ]
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
    ['置信度', typeof edge.confidence === 'number' ? edge.confidence.toFixed(2) : '-'] as const,
    ['命中规则', edge.ruleName ?? props.moduleInfo.rules[0]?.name ?? '已命中关系识别规则'] as const,
    ...detailEntries(edge.details, ['confidence', 'evidence', 'ruleName']),
    ...(edge.evidence?.length ? [['证据', edge.evidence.join('；')] as const] : []),
  ]
})
const liveEntityProvenanceRows = computed(() => {
  const node = selectedNode.value
  const provenance = node?.provenance
  if (!node || !provenance) return []
  return [
    ['实体类型', node.entityType] as const,
    ['源数据表', provenance.sourceTable || '-'] as const,
    ['来源字段', provenance.sourceField || '-'] as const,
    ['字段值', provenance.sourceValue || '-'] as const,
    ['入库批次', provenance.ingestBatch || '-'] as const,
    ['入库时间', provenance.ingestTime || '-'] as const,
  ]
})

const liveRelationEndpointProvenanceRows = computed(() => {
  const edge = selectedEdge.value
  const from = selectedEdgeNodes.value.from
  const to = selectedEdgeNodes.value.to
  if (!edge || !from || !to) return []
  return [from, to].map((node, index) => ({
    role: index === 0 ? '源实体' : '目标实体',
    name: node.label,
    entityType: node.entityType,
    rows: [
      ['源数据表', node.provenance?.sourceTable || '-'] as const,
      ['来源字段', node.provenance?.sourceField || '-'] as const,
      ['字段值', node.provenance?.sourceValue || '-'] as const,
      ['入库批次', node.provenance?.ingestBatch || '-'] as const,
      ['入库时间', node.provenance?.ingestTime || '-'] as const,
    ],
  }))
})

const liveRules = computed(() => {
  const rules = liveResult.value?.rules
  return Array.isArray(rules) && rules.length ? rules as Array<Record<string, unknown>> : null
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
    confidence: typeof edge.confidence === 'number' ? edge.confidence.toFixed(2) : '-',
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

const liveSummaryRows = computed<ServiceSummaryRow[] | null>(() => {
  const result = liveResult.value
  if (liveError.value) return [{ label: '接口状态', value: liveError.value }]
  if (!result) return null
  const summary = (result.summary ?? {}) as Record<string, unknown>
  const labelMap: Record<string, string> = {
    coreExpert: '核心专家',
    coreExpertOrganization: '核心专家机构',
    primaryColleague: '同事专家',
    commonOrganization: '共同机构',
    departmentOrTeam: '所属部门/团队',
    effectivePeriod: '关系生效时段',
    overlapDuration: '任职重叠时间',
    workContent: '共同工作内容',
    collaborationScenes: '协作场景',
    periodAchievements: '同事期间成果',
    colleagueCount: '同事关系数量',
    teamCount: '共同团队',
    maxOverlapYears: '最大重叠年限',
    achievementCount: '关联成果',
    reviewRequiredCount: '待复核',
    relationCount: '关系数量',
    expertCount: '专家数量',
    paperCount: '论文数量',
  }
  const rows: ServiceSummaryRow[] = []
  if (typeof result.total === 'number') {
    rows.push({ label: '关系数量', value: String(result.total) })
  }
  for (const [key, value] of Object.entries(summary)) {
    const label = labelMap[key]
    if (label && value !== null && value !== undefined) {
      rows.push({ label, value: String(value) })
    }
  }
  return rows.length ? rows : null
})
const detailRows = computed(() => {
  const base = liveSummaryRows.value ?? props.moduleInfo.summaryRows
  return base.map((row) => {
    if (row.label === '更新状态' && isPanorama.value) {
      return [row.label, updateStatus.value] as const
    }
    return [row.label, row.value] as const
  })
})
const apiResultJson = computed(() => {
  const envelope = liveResult.value
    ? { code: 200, success: true, data: liveResult.value, request_params: parameterValues.value }
    : { ...JSON.parse(props.responseJson), request_params: parameterValues.value }
  return JSON.stringify(envelope, null, 2)
})

watch(
  () => props.moduleInfo.key,
  () => {
    resultMode.value = 'summary'
    panoramaLayer.value = 3
    panoramaRelation.value = 'all'
    selectedGraphNodeId.value = null
    selectedGraphEdgeId.value = null
    liveResult.value = null
    liveError.value = null
    liveCenterId.value = null
    resetParameters()
    autoRefresh.value = false
  },
  { immediate: true },
)

watch([panoramaLayer, panoramaRelation], () => {
  if (!isPanorama.value) return
  selectedGraphNodeId.value = null
  selectedGraphEdgeId.value = null
  resultMode.value = 'summary'
})

function formatValue(value: unknown) {
  if (Array.isArray(value)) return value.join('、')
  if (typeof value === 'boolean') return value ? '是' : '否'
  return String(value ?? '-')
}

function resetParameters() {
  parameterValues.value = Object.fromEntries(
    props.moduleInfo.requestFields.map((field) => [
      field.name,
      formatValue(props.moduleInfo.requestExample[field.name]),
    ]),
  )
}

const LIVE_MODULE_KEY = 'expert-colleague'

function buildPayload(): Record<string, unknown> {
  const payload: Record<string, unknown> = {}
  for (const field of props.moduleInfo.requestFields) {
    const raw = parameterValues.value[field.name]
    if (raw === undefined || raw === null || String(raw).trim() === '') continue
    if (field.type === 'number') {
      const numeric = Number(raw)
      payload[field.name] = Number.isFinite(numeric) ? numeric : raw
    } else {
      payload[field.name] = String(raw)
    }
  }
  return payload
}

async function handleRun() {
  running.value = true
  if (props.moduleInfo.key !== LIVE_MODULE_KEY) {
    // 其余模块后端尚未实现，沿用示例数据预览。
    window.setTimeout(() => {
      const now = new Date()
      lastTestTime.value = formatTimestamp(now)
      lastUpdateTime.value = now.getTime()
      running.value = false
    }, 360)
    return
  }

  liveError.value = null
  try {
    const { data, error } = await runKgService(props.moduleInfo.endpoint, buildPayload())
    if (error) {
      liveResult.value = null
      liveError.value = error
    } else {
      liveResult.value = data
      liveCenterId.value = (data?.expert?.id as string | undefined) ?? null
    }
  } finally {
    const now = new Date()
    lastTestTime.value = formatTimestamp(now)
    lastUpdateTime.value = now.getTime()
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
        <dl v-else-if="resultMode === 'entity' && selectedNode" class="result-panel__table">
          <div v-for="([label, value], index) in entityDetailRows" :key="label + '-' + index">
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
        <section v-else-if="resultMode === 'provenance' && selectedProvenanceTarget" class="result-provenance">
          <header><strong>当前追溯对象</strong><span>{{ selectedProvenanceTarget.kind }}</span></header>
          <div class="result-provenance__target">
            <strong>{{ selectedProvenanceTarget.name }}</strong>
            <span>{{ selectedProvenanceTarget.kind }}</span>
          </div>
          <template v-if="selectedNode && liveEntityProvenanceRows.length">
            <h3>实体溯源</h3>
            <dl class="result-provenance__source">
              <div v-for="([label, value], index) in liveEntityProvenanceRows" :key="label + '-' + index">
                <dt>{{ label }}</dt>
                <dd><code>{{ value }}</code></dd>
              </div>
            </dl>
            <div class="result-provenance__task-meta"><span>实体溯源来自 FastAPI 返回的 graph.nodes[].data.provenance</span></div>
          </template>
          <template v-else-if="selectedEdge && liveRelationEndpointProvenanceRows.length">
            <h3>关系溯源</h3>
            <dl class="result-provenance__source">
              <div><dt>关系类型</dt><dd>{{ selectedProvenanceTarget.type }}</dd></div>
              <div><dt>关系置信度</dt><dd>{{ selectedProvenanceTarget.confidence }}</dd></div>
            </dl>
            <h3>两端实体来源</h3>
            <div class="result-provenance__evidence-list">
              <article v-for="endpoint in liveRelationEndpointProvenanceRows" :key="endpoint.role">
                <header><strong>{{ endpoint.role }} · {{ endpoint.name }}</strong></header>
                <p><b>实体类型：{{ endpoint.entityType }}</b></p>
                <span v-for="([label, value], index) in endpoint.rows" :key="endpoint.role + label + index">{{ label }}：<code>{{ value }}</code></span>
              </article>
            </div>
            <div class="result-provenance__task-meta"><span>关系边只展示关系置信度；溯源取源实体和目标实体的来源表、来源字段。</span></div>
          </template>
          <p v-else class="result-panel__empty">当前对象未返回溯源字段。</p>
        </section>
        <div v-else-if="resultMode === 'rule'" class="result-panel__rules">
          <article v-for="(rule, index) in (liveRules ?? moduleInfo.rules)" :key="String(rule.name)">
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
              <div v-if="'appliedCount' in rule"><dt>本次命中</dt><dd>{{ rule.appliedCount }}</dd></div>
            </dl>
          </article>
        </div>
        <pre v-else-if="resultMode === 'api'" class="result-panel__code">{{ apiResultJson }}</pre>
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
  overflow: hidden;
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
