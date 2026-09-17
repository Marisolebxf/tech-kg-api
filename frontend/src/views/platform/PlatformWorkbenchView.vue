<script setup lang="ts">
import {
  computed,
  onUnmounted,
  ref,
  watch,
} from 'vue'
import { useRouter } from 'vue-router'
import { runNgql, type GraphConsoleResult } from '../../api/graphConsole'
import { currentGraphSpace } from '../../api/currentGraphSpace'
import { useGraphSpaceStore } from '../../stores/graphSpace'
import ListPagination from '../../components/list-pagination.vue'
import { useClientPagination } from '../../composables/use-client-pagination'
import { getErrorMessage } from '../../api/http'
import {
  getPlatformOverview,
  type AssetChangeRow,
  type AssetOverviewGroup,
  type AssetOverviewKey,
  type PlatformOverviewData,
  type StructureItem,
} from '../../api/platformOverview'
import {
  countJobUnifiedStatuses,
  deriveJobUnifiedStatus,
  getProductionReviews,
  JOB_STATUS_TONE,
  listJobs,
  type ProductionReviewCase,
  type WorkflowJob,
} from '../../api/workflowOperations'
import { useToast } from '../../composables/use-toast'
import { IconInfoCircle } from '@arco-design/web-vue/es/icon'
import {
  fetchGraphAlgorithmEngine,
  fetchGraphAlgorithmMetadata,
  getAlgorithmJob,
  getAlgorithmJobResult,
  submitAlgorithmJob,
  type AlgorithmJobSnapshot,
  type AlgorithmResultPayload,
  type GraphAlgorithmMetadata,
} from '../../api/graphAlgorithm'
import {
  GRAPH_ALGORITHMS,
  type AlgorithmParamDef,
  type GraphAlgorithmDefinition,
} from './graph-algorithm-catalog'

type PlatformTab = 'overview' | 'processing' | 'construction' | 'query' | 'service'
type ServiceField = {
  name: string
  type: string
  required?: boolean
  description: string
}
type ServiceModule = {
  key: string
  title: string
  endpoint: string
  method: 'POST'
  requestFields: ServiceField[]
  responseFields: ServiceField[]
  requestExample: Record<string, string | number | boolean | string[]>
  responseExample: { data: Record<string, unknown> }
  resultRows: Array<{ label: string; value: string }>
  evidence: string[]
}

const commonResponseFields: ServiceField[] = [
  { name: 'code', type: 'number', description: '服务状态码' },
  { name: 'message', type: 'string', description: '服务返回信息' },
  { name: 'data', type: 'object', description: '结构化业务结果、图谱节点关系和证据链' },
  { name: 'confidence', type: 'number', description: '综合置信度' },
  { name: 'evidence', type: 'array', description: '支撑本次结果的数据来源和证据' },
]

const modules: ServiceModule[] = [
  {
    key: 'expert-direct',
    title: '科技专家/人才直接关系',
    endpoint: '/api/v1/kg-service/expert-direct-relation',
    method: 'POST',
    requestFields: [
      { name: 'source_expert_id', type: 'string', required: true, description: '第一个专家唯一标识' },
      { name: 'target_expert_id', type: 'string', required: false, description: '第二个专家唯一标识' },
      { name: 'relation_scene', type: 'string', required: false, description: '交互场景筛选条件' },
      { name: 'start_time', type: 'string', required: false, description: '关系起始时间' },
    ],
    responseFields: commonResponseFields,
    requestExample: { source_expert_id: 'E10001', target_expert_id: 'E10002', relation_scene: '科研合作', start_time: '2020-01' },
    responseExample: { data: { relation_type: '论文合作', relation_count: 12, scenario: '科研合作', confidence: 0.94 } },
    resultRows: [{ label: '直接关系', value: '12' }, { label: '关系类型', value: '4' }, { label: '关联成果', value: '18' }, { label: '最高置信度', value: '0.94' }],
    evidence: ['共同发表论文 4 篇，作者列表和单位信息一致。', '共同参与项目 3 项，项目角色存在协作链路。', '关系发生时间、场景和成果均已结构化记录。'],
  },
  {
    key: 'node-indirect',
    title: '科技单节点间接关系',
    endpoint: '/api/v1/kg-service/node-indirect-relation',
    method: 'POST',
    requestFields: [
      { name: 'core_node_id', type: 'string', required: true, description: '核心专家或人才节点 ID' },
      { name: 'relation_types', type: 'array', required: false, description: '间接关系类型' },
      { name: 'path_depth', type: 'number', required: false, description: '路径分析深度（2-3 跳）' },
      { name: 'min_strength', type: 'number', required: false, description: '最小关联强度阈值（0-1）' },
    ],
    responseFields: commonResponseFields,
    requestExample: { core_node_id: '4G7t0B0t', relation_types: ['学术关联'], path_depth: 2, min_strength: 0.65 },
    responseExample: { data: { indirect_nodes: 36, paths: 58, average_strength: 0.76 } },
    resultRows: [{ label: '间接节点', value: '36' }, { label: '路径数量', value: '58' }, { label: '关系类型', value: '4' }, { label: '平均强度', value: '0.76' }],
    evidence: ['路径：张明远 -> 李佳宁 -> 专家C。', '路径深度为 2，命中学术关联和机构关联。', '每条间接关系均返回传递路径和强度。'],
  },
  {
    key: 'two-point-achievement',
    title: '科技两点合作成果',
    endpoint: '/api/v1/kg-construction/expert-cooperation-achievements/query',
    method: 'POST',
    requestFields: [
      { name: 'sourceExpertId', type: 'string', required: true, description: '专家 A 图节点 ID' },
      { name: 'targetExpertId', type: 'string', required: true, description: '专家 B 图节点 ID' },
      { name: 'achievementTypes', type: 'string', required: false, description: 'paper,patent,project' },
      { name: 'timeRangeStart', type: 'string', required: false, description: '时间起点' },
    ],
    responseFields: commonResponseFields,
    requestExample: {
      sourceExpertId: 'person_00095d2b6e69e0d4a6365c7fac495d8b',
      targetExpertId: 'person_5f9b3a46091dbcc38eeb58696187385c',
      achievementTypes: '',
      timeRangeStart: '',
    },
    responseExample: {
      data: {
        summary: { papers: 1, patents: 0, projects: 0, awards: 0 },
        coreContribution: '共同论文产出',
        cooperationMode: '单类型合作（论文）',
      },
    },
    resultRows: [{ label: '合作论文', value: '' }, { label: '合作专利', value: '' }, { label: '共同项目', value: '' }, { label: '价值评分', value: '' }],
    evidence: ['按论文、专利、项目分类统计合作成果。', '标注完成时间、所属领域和奖项评价。', '输出核心贡献和合作模式。'],
  },
  {
    key: 'expert-colleague',
    title: '科技专家同事关系',
    endpoint: '/api/v1/kg-service/expert-colleague-relation',
    method: 'POST',
    requestFields: [
      { name: 'expert_id', type: 'string', required: true, description: '专家唯一标识' },
      { name: 'organization', type: 'string', required: false, description: '任职机构筛选' },
      { name: 'department', type: 'string', required: false, description: '部门或团队筛选' },
      { name: 'overlap_period', type: 'string', required: false, description: '任职重叠时间' },
    ],
    responseFields: commonResponseFields,
    requestExample: { expert_id: 'E10001', organization: '中国科学院自动化研究所', department: '智能系统实验室', overlap_period: '2018-2022' },
    responseExample: { data: { colleagues: 18, teams: 4, overlap_years: 4, achievements: 6 } },
    resultRows: [{ label: '同事关系', value: '18' }, { label: '共同团队', value: '4' }, { label: '重叠年限', value: '4' }, { label: '期间成果', value: '6' }],
    evidence: ['任职时间存在重叠，机构层级匹配到同一实验室。', '标注共同工作内容和协作场景。', '关联同事期间产生的合作成果。'],
  },
  {
    key: 'expert-alumni',
    title: '科技专家校友关系',
    endpoint: '/api/v1/kg-construction/expert-alumni-relations/query',
    method: 'POST',
    requestFields: [
      { name: 'expertId', type: 'string', required: true, description: '源专家图节点 ID' },
      { name: 'targetExpertId', type: 'string', required: false, description: '目标专家 ID；有则 pair，空则 list' },
      { name: 'school', type: 'string', required: false, description: '院校关键词过滤' },
      { name: 'educationStage', type: 'string', required: false, description: '学历/教育阶段过滤' },
    ],
    responseFields: commonResponseFields,
    requestExample: {
      expertId: 'person_alumni_test_liu28',
      targetExpertId: 'person_alumni_test_wang64',
      school: '',
      educationStage: '',
    },
    responseExample: {
      data: {
        total: 1,
        mode: 'pair',
        dimensions: ['同校', '同学历', '同期'],
        sharedInstitutions: ['上海交通大学'],
      },
    },
    resultRows: [{ label: '校友数量', value: '' }, { label: '关系维度', value: '' }, { label: '学术互动', value: '' }, { label: '模式', value: '' }],
    evidence: ['基于教育经历匹配校友关系。', '细分同校、同学历、同期等关联维度。', '关联后续学术交流与合作互动。'],
  },
  {
    key: 'paper-cooperation',
    title: '科技专家论文合作关系',
    endpoint: '/api/v1/kg-construction/expert-paper-cooperation-relations/structured-result',
    method: 'POST',
    requestFields: [
      { name: 'expertAId', type: 'string', required: true, description: '专家 A 唯一标识' },
      { name: 'expertBId', type: 'string', required: true, description: '专家 B 唯一标识' },
      { name: 'startTime', type: 'month', required: false, description: '开始月份 YYYY-MM' },
      { name: 'endTime', type: 'month', required: false, description: '结束月份 YYYY-MM' },
    ],
    responseFields: commonResponseFields,
    requestExample: { expertAId: 'person_121d48631f434f4d323ba521d33032ad', expertBId: 'person_42914016fe8d6e0e1d01dad5845c47e6', startTime: '2021-01', endTime: '2026-08' },
    responseExample: { data: { structuredResult: { cooperationPaperCount: 14, citation: { total: 1260, max: 90 }, stableTeamMembers: [], paperTopics: ['人工智能', '先进计算'] } } },
    resultRows: [{ label: '合作论文', value: '14' }, { label: '总被引', value: '1260' }, { label: '研究方向', value: '5' }, { label: '核心人员', value: '7' }],
    evidence: ['提取作者列表、作者单位、发表时间和论文主题。', '统计期刊会议级别和被引情况。', '识别长期稳定合作团队和核心合作人员。'],
  },
  {
    key: 'enterprise-relation',
    title: '重点关注科技企业关系',
    endpoint: '/api/v1/kg-service/key-enterprise-relation',
    method: 'POST',
    requestFields: [
      { name: 'expert_id', type: 'string', required: true, description: '专家唯一标识' },
      { name: 'enterprise_name', type: 'string', required: false, description: '企业名称筛选' },
      { name: 'role_type', type: 'string', required: false, description: '专家企业角色' },
      { name: 'industry', type: 'string', required: false, description: '企业行业方向' },
    ],
    responseFields: commonResponseFields,
    requestExample: { expert_id: 'E10001', enterprise_name: '华南智能芯片', role_type: '顾问/股东/合作方', industry: '集成电路' },
    responseExample: { data: { enterprises: 9, roles: 4, cooperation_fields: ['芯片设计', '智能制造'] } },
    resultRows: [{ label: '关联企业', value: '9' }, { label: '角色类型', value: '4' }, { label: '合作领域', value: '6' }, { label: '经营风险', value: '2' }],
    evidence: ['标注专家在企业中的角色、合作领域、合作时间和模式。', '关联企业行业地位、技术方向与经营状况。', '支持产业界资源对接分析。'],
  },
  {
    key: 'industry-chain-event',
    title: '科技产业链点TOP-N事件关系',
    endpoint: '/api/v1/kg-service/industry-node-top-events',
    method: 'POST',
    requestFields: [
      { name: 'chain_node_id', type: 'string', required: true, description: '产业链节点标识' },
      { name: 'top_n', type: 'number', required: false, description: '返回事件数量' },
      { name: 'event_type', type: 'string', required: false, description: '事件类型筛选' },
      { name: 'time_range', type: 'string', required: false, description: '事件时间范围' },
    ],
    responseFields: commonResponseFields,
    requestExample: { chain_node_id: 'IC-CHIP-DESIGN', top_n: 10, event_type: '投融资/政策/风险', time_range: '2025-2026' },
    responseExample: { data: { events: 10, experts: 18, enterprises: 24, risk_level: '中' } },
    resultRows: [{ label: 'TOP事件', value: '10' }, { label: '关联专家', value: '18' }, { label: '关联企业', value: '24' }, { label: '风险等级', value: '中' }],
    evidence: ['按影响力评估筛选产业链节点 TOP-N 事件。', '构建事件与专家、企业、人才的关联关系。', '分析产业链影响和后续发展趋势。'],
  },
  {
    key: 'industry-chain-panorama',
    title: '科技产业链全景图',
    endpoint: '/api/v1/kg-service/industry-chain-panorama',
    method: 'POST',
    requestFields: [
      { name: 'chain_id', type: 'string', required: true, description: '产业链标识' },
      { name: 'layer_depth', type: 'number', required: false, description: '层级展开深度' },
      { name: 'relation_filter', type: 'array', required: false, description: '关系筛选条件' },
      { name: 'include_events', type: 'boolean', required: false, description: '是否包含事件' },
    ],
    responseFields: commonResponseFields,
    requestExample: { chain_id: 'AI-COMPUTING', layer_depth: 3, relation_filter: ['技术', '企业', '专家'], include_events: true },
    responseExample: { data: { nodes: 186, relations: 420, key_technologies: 22, key_enterprises: 48 } },
    resultRows: [{ label: '产业节点', value: '186' }, { label: '链路关系', value: '420' }, { label: '关键技术', value: '22' }, { label: '重点企业', value: '48' }],
    evidence: ['整合产业链实体、关系、事件数据。', '展示核心节点、关联关系和数据流向。', '支持层级展开、关系筛选和动态更新。'],
  },
]

const props = defineProps<{
  initialTab?: PlatformTab
  initialServiceKey?: string
}>()

const router = useRouter()

const activeTab = ref<PlatformTab>(props.initialTab ?? 'overview')
const activeServiceKey = ref(props.initialServiceKey ?? modules[0]?.key ?? '')
const activeServiceMode = ref<'test' | 'api'>('test')
const processingDomainFilter = ref('全部业务域')
const processingStatusFilter = ref('全部状态')
const processingTaskDomain = ref('论文域')
const processingScope = ref('自上次成功点增量')
const processingPriority = ref('普通')
const processingReason = ref('')
const processingStartDate = ref('2026-07-12')
const processingEndDate = ref('2026-07-13')
const isActionLoading = ref(false)

/**
 * 实际请求使用的 TRSGraph 图空间：跟随右上角全局图空间选择器。
 *
 * 页面内不再单独提供图空间下拉，nGQL 与图算法两种模式共用全局选择。
 */
const graphSpaceStore = useGraphSpaceStore()

/** 查询模式：nGQL 直查 | 图算法。 */
const queryMode = ref<'ngql' | 'algo'>('ngql')
const ngqlStatement = ref('')
const ngqlLoading = ref(false)
const ngqlResult = ref<GraphConsoleResult | null>(null)
// nGQL 结果客户端分页：后端不限制返回行数，大结果集翻页展示（表头徽标仍显示总行数）
const ngqlRecords = computed(() => ngqlResult.value?.records ?? [])
const {
  page: ngqlPage,
  pageSize: ngqlPageSize,
  total: ngqlTotal,
  pagedItems: pagedNgqlRecords,
  resetPage: resetNgqlPage,
  changePage: changeNgqlPage,
  changePageSize: changeNgqlPageSize,
} = useClientPagination(ngqlRecords, 20)

// ---------- 图算法模式 ----------
/** 图算法空间跟随顶栏全局选择器（切换即重载边类型与引擎状态）。 */
const algoSpace = computed(() => currentGraphSpace())
const selectedAlgorithm = ref(GRAPH_ALGORITHMS[0].id)
const algoLabels = ref<string[]>([])
/** 按算法 id 分桶的参数值；切换算法时按目录默认值初始化该桶。 */
const algoParamValues = ref<Record<string, Record<string, number | string | boolean>>>({})
const algoHasWeight = ref(false)
/** 按已选边类型键控的权重属性名（加权开启后逐项必填）。 */
const algoWeightCols = ref<Record<string, string>>({})
const algoEncodeId = ref(true)
const algoPartitionNum = ref(1)
const algoMetadataLoading = ref(false)
const algoMetadata = ref<GraphAlgorithmMetadata | null>(null)
const algoSubmitLoading = ref(false)
/** 当前作业快照；algoJobSpace 为提交时冻结的图空间，轮询/取结果固定使用。 */
const algoJob = ref<AlgorithmJobSnapshot | null>(null)
const algoJobSpace = ref('')
const algoResult = ref<AlgorithmResultPayload | null>(null)
let algoPollTimer: number | undefined
let algoPollFailures = 0

const selectedAlgorithmDef = computed<GraphAlgorithmDefinition>(
  () => GRAPH_ALGORITHMS.find((item) => item.id === selectedAlgorithm.value) ?? GRAPH_ALGORITHMS[0],
)
const algoParamDefs = computed<AlgorithmParamDef[]>(() => selectedAlgorithmDef.value.params)
const algoRows = computed(() => algoResult.value?.rows ?? [])
const algoResultColumns = computed<string[]>(() =>
  algoRows.value.length ? Object.keys(algoRows.value[0]) : [],
)
const {
  page: algoPage,
  pageSize: algoPageSize,
  total: algoTotal,
  pagedItems: pagedAlgoRows,
  resetPage: resetAlgoPage,
  changePage: changeAlgoPage,
  changePageSize: changeAlgoPageSize,
} = useClientPagination(algoRows, 20)

/** 引擎状态徽标（正常 / 不可用 / 检测中）。 */
const algoEngineStatus = computed(() => {
  if (algoMetadataLoading.value) return { label: '检测中', tone: 'is-运行中' }
  const engine = algoMetadata.value?.engine
  if (!engine) return { label: '未知', tone: 'is-运行中' }
  return engine.status === 'UP'
    ? { label: '正常', tone: 'is-正常' }
    : { label: '不可用', tone: 'is-阻断' }
})

/** 作业状态徽标（运行中 / 成功 / 失败）。 */
const algoJobStatus = computed(() => {
  const job = algoJob.value
  if (!job) return null
  if (job.status === 'running') return { label: '运行中', tone: 'is-运行中' }
  if (job.status === 'succeeded') return { label: '成功', tone: 'is-成功' }
  return { label: '失败', tone: 'is-阻断' }
})

function initAlgoParams(algorithmId: string): void {
  const def = GRAPH_ALGORITHMS.find((item) => item.id === algorithmId)
  const values: Record<string, number | string | boolean> = {}
  for (const param of def?.params ?? []) {
    if (param.default !== undefined) values[param.key] = param.default
  }
  algoParamValues.value[algorithmId] = values
}

initAlgoParams(selectedAlgorithm.value)

const { showToast } = useToast()

const activeService = computed(() => modules.find((item) => item.key === activeServiceKey.value) ?? modules[0])
const activeRequestJson = computed(() => JSON.stringify(activeService.value.requestExample, null, 2))
const activeResponseJson = computed(() => JSON.stringify({
  code: 0,
  message: 'success',
  data: activeService.value.responseExample.data ?? activeService.value.responseExample,
}, null, 2))
const activeRequestEntries = computed(() =>
  activeService.value.requestFields.map((field) => ({
    label: field.description,
    key: field.name,
    required: field.required ?? false,
    value: Array.isArray(activeService.value.requestExample[field.name])
      ? (activeService.value.requestExample[field.name] as string[]).join(', ')
      : String(activeService.value.requestExample[field.name] ?? '-'),
  })),
)
const serviceConsoleStats = computed(() => [
  { label: '服务标识', value: activeService.value.key },
  { label: '请求方法', value: activeService.value.method },
  { label: '接口路径', value: activeService.value.endpoint },
  { label: '参数数量', value: String(activeService.value.requestFields.length) },
])
const serviceCallLogs = computed(() => [
  { time: '10:30:12', level: 'SUCCESS', message: `已完成 ${activeService.value.title} 调用，返回 code=0。` },
  { time: '10:30:11', level: 'INFO', message: `请求参数已标准化，准备发送到 ${activeService.value.endpoint}。` },
  { time: '10:30:09', level: 'INFO', message: `命中服务路由 ${activeService.value.key}，开始装配请求体。` },
])

watch(
  () => props.initialTab,
  (tab) => {
    if (tab) {
      activeTab.value = tab
    }
  },
)

watch(
  () => props.initialServiceKey,
  (serviceKey) => {
    if (serviceKey) {
      activeServiceKey.value = serviceKey
    }
  },
)

const overviewMeta = ref({
  platformStatus: '正在加载平台状态',
  pendingBatchCount: 0,
  updatedAt: '--',
  dataMode: 'mock' as PlatformOverviewData['dataMode'],
  warnings: [] as string[],
})
const assetOverviewGroups = ref<AssetOverviewGroup[]>([])
const selectedAssetChange = ref<AssetOverviewKey | null>(null)
const assetChangeRows = ref<Record<AssetOverviewKey, AssetChangeRow[]>>({
  entity: [],
  relation: [],
  property: [],
})
const entityStructure = ref<StructureItem[]>([])
const relationStructure = ref<StructureItem[]>([])

// 总览两卡片：直连任务/审核队列真实数据（不进 platform_overview 的 60s 缓存），各自容错
const overviewJobs = ref<WorkflowJob[]>([])
const overviewJobsState = ref<'loading' | 'ready' | 'error'>('loading')
const overviewJobsError = ref('')
const overviewReviews = ref<ProductionReviewCase[]>([])
const overviewReviewsTotal = ref(0)
const overviewReviewsState = ref<'loading' | 'ready' | 'empty' | 'forbidden' | 'error'>('loading')
const overviewReviewsError = ref('')

const overviewJobStats = computed(() => {
  const counts = countJobUnifiedStatuses(overviewJobs.value)
  return [
    { label: '运行中', value: counts['运行中'], tone: JOB_STATUS_TONE['运行中'] },
    { label: '已完成', value: counts['已完成'], tone: JOB_STATUS_TONE['已完成'] },
    { label: '运行失败', value: counts['运行失败'], tone: JOB_STATUS_TONE['运行失败'] },
    { label: '已暂停', value: counts['已暂停'], tone: JOB_STATUS_TONE['已暂停'] },
  ]
})

const recentOverviewJobs = computed(() =>
  [...overviewJobs.value]
    .sort((a, b) => String(b.lastRunAt || b.createdAt || '').localeCompare(String(a.lastRunAt || a.createdAt || '')))
    .slice(0, 5),
)

function isForbiddenError(error: unknown): boolean {
  const status = (error as { response?: { status?: number } })?.response?.status
  if (status === 403) return true
  // 兜底：部分错误路径只剩文案
  return /403|权限|无权/.test(getErrorMessage(error))
}

async function loadOverviewCards(): Promise<void> {
  overviewJobsState.value = 'loading'
  overviewReviewsState.value = 'loading'
  try {
    const data = await listJobs()
    overviewJobs.value = data.items
    overviewJobsState.value = 'ready'
  } catch (error) {
    overviewJobsError.value = getErrorMessage(error)
    overviewJobsState.value = 'error'
  }
  try {
    const data = await getProductionReviews({ statusGroup: 'pending', page: 1, pageSize: 5 })
    overviewReviews.value = data.items
    overviewReviewsTotal.value = data.total
    overviewReviewsState.value = data.items.length ? 'ready' : 'empty'
  } catch (error) {
    overviewReviewsError.value = getErrorMessage(error)
    overviewReviewsState.value = isForbiddenError(error) ? 'forbidden' : 'error'
  }
}
const activeAssetOverview = computed(() => assetOverviewGroups.value.find((item) => item.key === selectedAssetChange.value))
const entityAssetOverview = computed(() => assetOverviewGroups.value.find((item) => item.key === 'entity'))
const relationAssetOverview = computed(() => assetOverviewGroups.value.find((item) => item.key === 'relation'))

const sourceRows = [
  { object: '专家人才基础信息', table: 'expert_profile', domain: '人才域', schedule: '每日定时', frequency: '02:00', latest: '2026-07-13 02:04', status: '正常', task: 'DP-20260713-0150' },
  { object: '专家教育经历', table: 'expert_education', domain: '人才域', schedule: '每日定时', frequency: '02:10', latest: '2026-07-13 02:12', status: '正常', task: 'DP-20260713-0150' },
  { object: '专家任职经历', table: 'expert_employment', domain: '人才域', schedule: '每日定时', frequency: '02:20', latest: '2026-07-13 02:22', status: '正常', task: 'DP-20260713-0150' },
  { object: '论文成果记录', table: 'paper_record', domain: '论文域', schedule: '每日定时', frequency: '02:00', latest: '2026-07-13 02:08', status: '异常', task: 'DP-20260713-0200' },
  { object: '论文作者与机构', table: 'paper_author_org', domain: '论文域', schedule: '每日定时', frequency: '02:15', latest: '2026-07-13 02:18', status: '正常', task: 'DP-20260713-0200' },
  { object: '论文引用关系', table: 'paper_citation', domain: '论文域', schedule: '每日定时', frequency: '02:30', latest: '2026-07-13 02:33', status: '正常', task: 'DP-20260713-0200' },
  { object: '项目与专利主题', table: 'project_patent', domain: '专利域', schedule: '周期定时', frequency: '每 6 小时', latest: '2026-07-13 08:01', status: '正常', task: 'DP-20260713-0100' },
  { object: '专利发明人信息', table: 'patent_inventor', domain: '专利域', schedule: '周期定时', frequency: '每 6 小时', latest: '2026-07-13 08:05', status: '正常', task: 'DP-20260713-0100' },
  { object: '企业工商要素', table: 'enterprise_profile', domain: '企业域', schedule: '实时增量', frequency: '事件触发', latest: '2026-07-13 10:30', status: '更新中', task: 'DP-20260713-1030' },
  { object: '企业产品与技术', table: 'enterprise_product', domain: '企业域', schedule: '实时增量', frequency: '事件触发', latest: '2026-07-13 10:28', status: '正常', task: 'DP-20260713-1030' },
  { object: '企业投融资事件', table: 'enterprise_financing', domain: '企业域', schedule: '周期定时', frequency: '每 2 小时', latest: '2026-07-13 10:02', status: '正常', task: 'DP-20260713-1030' },
]

const dataProcessingSteps = [
  { id: 'source', name: '连接科技要素库', status: '完成', desc: '校验数据服务、库表结构和增量游标' },
  { id: 'incremental', name: '检查更新', status: '完成', desc: '按 last_update_time 识别新增与变更记录' },
  { id: 'normalize', name: '清洗标准化', status: '完成', desc: '统一日期、枚举、空值、编码和字段命名' },
  { id: 'quality', name: '质量检验', status: '阻断', desc: '生成完整性、唯一性、一致性检验日志' },
  { id: 'write', name: '写入标准表', status: '待执行', desc: '写入处理后的标准库表，供图谱构建使用' },
]

const processingTaskRows = [
  { batch: 'DP-20260713-0200', source: '科技要素数据库.paper_record', domain: '论文域', type: '定时调度', time: '2026-07-13 02:00', input: '12,604', target: 'kg_stage.std_paper_record', status: '阻断', progress: 72 },
  { batch: 'DP-20260713-1030', source: '科技要素数据库.enterprise_profile', domain: '企业域', type: '人工紧急', time: '2026-07-13 10:30', input: '1,248', target: 'kg_stage.std_enterprise_profile', status: '运行中', progress: 43 },
  { batch: 'DP-20260713-0150', source: '科技要素数据库.expert_profile', domain: '人才域', type: '定时调度', time: '2026-07-13 01:50', input: '8,426', target: 'kg_stage.std_expert_profile', status: '成功', progress: 100 },
  { batch: 'DP-20260713-0100', source: '科技要素数据库.project_patent', domain: '专利域', type: '定时调度', time: '2026-07-13 01:00', input: '3,261', target: 'kg_stage.std_project_patent', status: '成功', progress: 100 },
]

const processingDomainOptions = ['全部业务域', '人才域', '论文域', '专利域', '企业域']
const processingStatusOptions = ['全部状态', '成功', '运行中', '阻断', '排队']
const processingTaskDomainOptions = ['人才域', '论文域', '专利域', '企业域']
const processingScopeOptions = ['自上次成功点增量', '指定时间范围', '全量重建']
const processingPriorityOptions = ['普通', '紧急']

const filteredProcessingTaskRows = computed(() => processingTaskRows.filter((row) => (
  (processingStatusFilter.value === '全部状态' || row.status === processingStatusFilter.value)
  && (processingDomainFilter.value === '全部业务域' || row.domain.includes(processingDomainFilter.value.replace('域', '')))
)))

const qualityLogRows = [
  { rule: 'Q-001 必填完整性', object: 'paper_record.title', batch: 'DP-20260713-0200', checked: '12,604', failed: '18', rate: '99.86%', status: '告警' },
  { rule: 'Q-014 唯一性检验', object: 'paper_record.paper_id', batch: 'DP-20260713-0200', checked: '12,604', failed: '326', rate: '97.41%', status: '阻断' },
  { rule: 'Q-027 枚举一致性', object: 'paper_record.source_type', batch: 'DP-20260713-0200', checked: '12,604', failed: '41', rate: '99.67%', status: '告警' },
]

const buildStats = [
  { label: '本次输入', value: '1,260.4 万', note: '标准结构化记录' },
  { label: '自动入库', value: '1,183.6 万', note: '高置信度实体关系' },
  { label: '隔离异常', value: '326', note: '冲突与低置信度对象' },
  { label: 'Schema 覆盖', value: '7 / 42', note: '实体类型 / 关系类型' },
]

const readonlySchemaRows = [
  { type: '实体', name: 'Expert', fields: 'id, name, aliases, organization, research_fields', rule: '姓名 + 机构 + 成果证据联合消歧' },
  { type: '实体', name: 'Paper', fields: 'id, title, authors, venue, publish_date', rule: 'DOI / 标题指纹唯一约束' },
  { type: '关系', name: 'CO_AUTHOR', fields: 'source, target, paper_ids, confidence', rule: '共同论文 + 单位交叉验证' },
  { type: '关系', name: 'WORKS_AT', fields: 'expert_id, organization_id, start, end', rule: '时间段不冲突、来源可追溯' },
]

const buildPipelineSteps = [
  { id: 'read', name: '读取结构化数据', count: '12,604 条', status: '完成', desc: '从 kg_stage 标准表读取专家、论文、企业、项目等记录' },
  { id: 'schema', name: '字段映射入 Schema', count: '7 类实体', status: '完成', desc: '字段映射到统一实体、属性和关系类型' },
  { id: 'llm', name: '大模型抽取', count: '3,261 实体 / 8,942 关系', status: '阻断', desc: '展示模型版本、Prompt、输入输出、置信度和评估结果' },
  { id: 'align', name: '实体对齐消歧', count: '42 个待确认', status: '待执行', desc: '候选实体与存量图谱召回、消歧与合并，低置信转入人工处理' },
  { id: 'validate', name: '规则验证与证据回链', count: '1,203 属性 / 326 异常', status: '待执行', desc: '用 Schema 约束、存量图谱和原始来源交叉验证抽取结果' },
  { id: 'persist', name: '结果入库与异常分流', count: '326 条待处理', status: '待执行', desc: '高置信度结果自动入库，低置信度与冲突对象转入独立人工处理平台' },
]


const taskRows = [
  { batch: 'KG-INC-20260713-018', source: '论文增量批次', domain: '论文 / 人才', stage: '大模型抽取', status: '阻断', progress: 46, entities: '3,261', relations: '8,942', properties: '1,203', autoStored: '0', conflicts: '326', quality: '0.76', next: '异常已隔离，校正后从失败节点重跑' },
  { batch: 'KG-INC-20260713-016', source: '专利项目主题库', domain: '专利域', stage: '实体对齐', status: '运行中', progress: 68, entities: '2,418', relations: '5,206', properties: '864', autoStored: '0', conflicts: '42', quality: '0.88', next: '继续执行证据回链与冲突校验' },
  { batch: 'KG-FULL-20260712-008', source: '科技专家人才库', domain: '人才域', stage: '图谱入库', status: '成功', progress: 100, entities: '18,420', relations: '62,117', properties: '6,410', autoStored: '86,947', conflicts: '0', quality: '0.94', next: '已完成入库，可进入查询服务' },
]


async function runWithLoading(message: string, action?: () => void) {
  isActionLoading.value = true
  await new Promise((resolve) => window.setTimeout(resolve, 420))
  action?.()
  showToast(message)
  isActionLoading.value = false
}

function formatNgqlCell(value: unknown): string {
  if (value === null || value === undefined) return 'NULL'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

async function handleNgqlQuery(): Promise<void> {
  const statement =
    ngqlStatement.value.trim()

  if (!statement) {
    showToast(
      '请输入 nGQL 语句',
      'info',
    )

    return
  }

  ngqlLoading.value = true
  ngqlResult.value = null
  resetNgqlPage()

  try {
    // 图空间跟随右上角全局选择器（后端按 X-Graph-Space 路由）
    ngqlResult.value =
      await runNgql(
        currentGraphSpace(),
        statement,
      )
  } catch (error) {
    showToast(
      getErrorMessage(error, 'nGQL 执行失败'),
      'warning',
    )
  } finally {
    ngqlLoading.value = false
  }
}

// ---------- 图算法：元数据 / 提交 / 轮询 ----------

let algoMetadataLoadedFor = ''

async function loadAlgoMetadata(force = false): Promise<void> {
  if (!algoSpace.value) return
  if (!force && algoMetadataLoadedFor === algoSpace.value) return
  algoMetadataLoading.value = true
  try {
    algoMetadata.value = await fetchGraphAlgorithmMetadata(algoSpace.value)
    algoMetadataLoadedFor = algoSpace.value
  } catch (error) {
    showToast(getErrorMessage(error, '图算法元数据加载失败'), 'warning')
  } finally {
    algoMetadataLoading.value = false
  }
}

// 全局图空间切换：清空既有查询结果，防止跨空间陈旧数据继续展示
watch(
  () => graphSpaceStore.current,
  () => {
    ngqlResult.value = null
    resetNgqlPage()
    // 图算法作业与结果绑定提交时的空间：停轮询并清空展示，避免跨空间陈旧数据
    stopAlgoPoll()
    algoJob.value = null
    algoJobSpace.value = ''
    algoResult.value = null
    resetAlgoPage()
  },
)

async function refreshAlgoEngine(): Promise<void> {
  if (!algoSpace.value) return
  try {
    const engine = await fetchGraphAlgorithmEngine(algoSpace.value)
    algoMetadata.value = { edgeTypes: algoMetadata.value?.edgeTypes ?? [], engine }
  } catch (error) {
    showToast(getErrorMessage(error, '算法引擎状态检测失败'), 'warning')
  }
}

function stopAlgoPoll(): void {
  if (algoPollTimer !== undefined) {
    window.clearTimeout(algoPollTimer)
    algoPollTimer = undefined
  }
}

function scheduleAlgoPoll(): void {
  stopAlgoPoll()
  algoPollTimer = window.setTimeout(() => {
    void pollAlgoJob()
  }, 3000)
}

async function pollAlgoJob(): Promise<void> {
  algoPollTimer = undefined
  // 离开图算法面板或查询页签即停轮询
  if (!algoJob.value || !algoJobSpace.value) return
  if (queryMode.value !== 'algo' || activeTab.value !== 'query') return
  try {
    const job = await getAlgorithmJob(algoJobSpace.value, algoJob.value.jobId)
    algoJob.value = job
    algoPollFailures = 0
    if (job.status === 'succeeded') {
      await fetchAlgoResult()
    } else if (job.status === 'failed') {
      showToast('算法作业执行失败，详情见作业状态面板', 'warning')
    } else {
      scheduleAlgoPoll()
    }
  } catch (error) {
    showToast(getErrorMessage(error, '算法作业状态查询失败'), 'warning')
    // 连续 3 次轮询失败即停止，避免页面后台空转打接口
    algoPollFailures += 1
    if (algoPollFailures < 3) scheduleAlgoPoll()
  }
}

async function fetchAlgoResult(): Promise<void> {
  if (!algoJob.value || !algoJobSpace.value) return
  try {
    algoResult.value = await getAlgorithmJobResult(algoJobSpace.value, algoJob.value.jobId)
    resetAlgoPage()
  } catch (error) {
    showToast(getErrorMessage(error, '算法结果获取失败'), 'warning')
  }
}

/** 手动刷新作业状态；仍在运行则重新挂上轮询。 */
async function refreshAlgoJob(): Promise<void> {
  if (!algoJob.value || !algoJobSpace.value) return
  try {
    const job = await getAlgorithmJob(algoJobSpace.value, algoJob.value.jobId)
    algoJob.value = job
    if (job.status === 'succeeded') await fetchAlgoResult()
    else if (job.status === 'running') scheduleAlgoPoll()
  } catch (error) {
    showToast(getErrorMessage(error, '算法作业状态查询失败'), 'warning')
  }
}

/** 收集当前算法的参数：只带有值的键，空值交由服务端默认值兜底。 */
function collectAlgoParams(): Record<string, number | string | boolean> {
  const values = algoParamValues.value[selectedAlgorithm.value] ?? {}
  const params: Record<string, number | string | boolean> = {}
  for (const def of algoParamDefs.value) {
    const value = values[def.key]
    if (value === '' || value === undefined || value === null) continue
    params[def.key] = value
  }
  return params
}

async function handleAlgoSubmit(): Promise<void> {
  if (!algoSpace.value) {
    showToast('请选择图空间', 'warning')
    return
  }
  const def = selectedAlgorithmDef.value
  // 必填与数值范围校验（与目录元数据一致，后端注册表再兜底一层）
  for (const param of def.params) {
    const value = (algoParamValues.value[def.id] ?? {})[param.key]
    if (value === undefined || value === '' || value === null) {
      if (param.required) {
        showToast(`请填写参数「${param.label}」`, 'warning')
        return
      }
      continue
    }
    if ((param.type === 'int' || param.type === 'float') && typeof value === 'number') {
      if (param.min !== undefined && value < param.min) {
        showToast(`参数「${param.label}」不能小于 ${param.min}`, 'warning')
        return
      }
      if (param.max !== undefined && value > param.max) {
        showToast(`参数「${param.label}」不能大于 ${param.max}`, 'warning')
        return
      }
    }
  }
  if (!algoLabels.value.length) {
    showToast('请选择至少一个边类型', 'warning')
    return
  }
  const weightCols = algoHasWeight.value
    ? algoLabels.value.map((label) => algoWeightCols.value[label]?.trim() ?? '')
    : null
  if (algoHasWeight.value && weightCols?.some((col) => !col)) {
    showToast('开启加权后，每个已选边类型都需填写权重属性', 'warning')
    return
  }

  algoSubmitLoading.value = true
  stopAlgoPoll()
  try {
    const job = await submitAlgorithmJob({
      space: algoSpace.value,
      algorithm: def.id,
      labels: [...algoLabels.value],
      params: collectAlgoParams(),
      hasWeight: algoHasWeight.value,
      weightCols,
      encodeId: algoEncodeId.value,
      partitionNum: algoPartitionNum.value,
    })
    algoJob.value = job
    // 冻结提交时的图空间：轮询与取结果固定使用，中途切空间不受影响
    algoJobSpace.value = algoSpace.value
    algoResult.value = null
    resetAlgoPage()
    if (job.status === 'running') {
      scheduleAlgoPoll()
    } else if (job.status === 'succeeded') {
      await fetchAlgoResult()
    } else {
      showToast('算法作业执行失败，详情见作业状态面板', 'warning')
    }
  } catch (error) {
    showToast(getErrorMessage(error, '算法作业提交失败'), 'warning')
  } finally {
    algoSubmitLoading.value = false
  }
}

// 切换算法：初始化该算法的参数桶（watch 默认 pre flush，重渲染前生效）
watch(selectedAlgorithm, (id) => {
  if (!algoParamValues.value[id]) initAlgoParams(id)
})

// 进入图算法模式：懒加载元数据；离开：停轮询
watch(queryMode, (mode) => {
  if (mode === 'algo') void loadAlgoMetadata()
  else stopAlgoPoll()
})

// 切换图空间：边类型与引擎状态按空间重新加载
watch(algoSpace, () => {
  algoMetadataLoadedFor = ''
  if (queryMode.value === 'algo') void loadAlgoMetadata()
})

onUnmounted(stopAlgoPoll)

async function loadPlatformOverview(): Promise<void> {
  try {
    const data = await getPlatformOverview()

    overviewMeta.value = {
      platformStatus: data.platformStatus,
      pendingBatchCount: data.pendingBatchCount,
      updatedAt: data.updatedAt,
      dataMode: data.dataMode,
      warnings: data.warnings,
    }
    // 属性值数据卡片（key=property）为占位统计（待接入），总览页不展示
    assetOverviewGroups.value = data.assetOverviewGroups.filter((item) => item.key !== 'property')
    assetChangeRows.value = data.assetChangeRows
    entityStructure.value = data.entityStructure
    relationStructure.value = data.relationStructure
  } catch (error) {
    const message = error instanceof Error ? error.message : '未知错误'
    showToast(`首页总览数据加载失败：${message}`, 'warning')
  }
}


// 总览数据只在 overview tab 首次可见时加载：/graph-query 等其他 tab 挂载时
// 不渲染总览内容，提前拉取是纯浪费（listJobs 还会触发后端 Temporal 复核级联）
const overviewDataLoaded = ref(false)
watch(activeTab, (tab) => {
  if (tab === 'overview' && !overviewDataLoaded.value) {
    overviewDataLoaded.value = true
    void loadPlatformOverview()
    void loadOverviewCards()
  }
}, { immediate: true })


function handleStartTask() {
  const priority = processingPriority.value === '紧急' ? '紧急优先' : '普通优先级'
  if (processingScope.value === '全量重建') {
    void runWithLoading(`已生成全量重建确认单：${processingTaskDomain.value} / ${priority}，需二次确认后执行`)
    return
  }
  const range = processingScope.value === '指定时间范围' ? ` / ${processingStartDate.value} 至 ${processingEndDate.value}` : ''
  void runWithLoading(`已创建人工触发任务：${processingTaskDomain.value} / ${processingScope.value}${range} / ${priority}`)
}

const processingActionLabel = computed(() => processingScope.value === '全量重建' ? '生成确认单' : '创建并执行')

function openProcessDetail(area: 'processing' | 'construction', taskId: string, step?: string) {
  void router.push({
    name: 'task-detail',
    params: { area, taskId },
    query: step ? { step } : undefined,
  })
}

function handleExecuteService() {
  void runWithLoading(`${activeService.value.title} 调用成功，已刷新请求与响应结果`)
}

function handleCopyEndpoint() {
  void navigator.clipboard.writeText(`${activeService.value.method} ${activeService.value.endpoint}`)
  showToast('接口信息已复制到剪贴板', 'info')
}

const pageMeta = computed(() => {
  const map: Record<PlatformTab, { title: string }> = {
    overview: { title: '亿级科技知识图谱平台' },
    processing: { title: '数据处理与结构化输出' },
    construction: { title: '图谱构建与治理' },
    query: { title: '综合查询' },
    service: { title: activeService.value.title },
  }
  return map[activeTab.value]
})

</script>

<template>
  <div class="platform-page">
    <header v-if="activeTab === 'overview'" class="platform-hero">
      <div class="platform-hero__main">
        <h1>{{ pageMeta.title }}</h1>
      </div>
      <div class="platform-hero__actions"><span :title="overviewMeta.warnings.join('\n')"><i></i>{{ overviewMeta.platformStatus }} · {{ overviewMeta.pendingBatchCount }} 个批次待处理 · {{ overviewMeta.dataMode === 'live' ? '实时数据' : overviewMeta.dataMode === 'partial' ? '部分实时' : '降级数据' }}</span><RouterLink to="/graph-build">查看任务</RouterLink><RouterLink to="/manual-review">进入人工处理</RouterLink></div>
    </header>

    <header v-else-if="activeTab !== 'query'" class="platform-page-head">
      <div>
        <h1>{{ pageMeta.title }}</h1>
      </div>
    </header>

    <main v-if="activeTab === 'overview'" class="platform-content platform-overview">
      <section class="platform-summary-grid" aria-label="实体与关系数据总览">
        <article v-for="group in assetOverviewGroups" :key="group.key" :class="['kg-panel', 'platform-summary-card', `is-${group.key}`]">
          <header><div><strong>{{ group.title }}</strong><span><i />数据已更新</span></div><button type="button" @click="selectedAssetChange = group.key">查看今日新增 →</button></header>
          <div class="platform-summary-card__main"><section><strong>{{ group.total }}</strong><span>{{ group.totalLabel }}</span></section><section class="is-added"><strong>{{ group.added }}</strong><span>{{ group.addedLabel }}</span></section></div>
        </article>
      </section>

      <section class="kg-panel platform-structure-overview">
        <div class="kg-panel__header"><div><h2 class="kg-panel__title">当前图谱资产</h2></div><span>实体 {{ entityAssetOverview?.total ?? '--' }} · 关系 {{ relationAssetOverview?.total ?? '--' }} · 数据截至 {{ overviewMeta.updatedAt }}</span></div>
        <div class="platform-structure-grid">
          <div class="platform-structure-chart"><header><strong>实体分类占比</strong></header><div class="platform-donut-layout"><div class="platform-donut is-entity"><span><strong>{{ entityAssetOverview?.total ?? '--' }}</strong><em>{{ entityAssetOverview?.totalLabel ?? '实体总量' }}</em></span></div><div class="platform-structure-legend"><article v-for="item in entityStructure" :key="item.schema"><span><i :style="{ background: item.tone }" />{{ item.label }}<em>{{ item.schema }}</em></span><strong>{{ item.count }}<em>{{ item.ratio }}%</em></strong></article></div></div></div>
          <div class="platform-structure-chart"><header><strong>关系分类占比</strong></header><div class="platform-donut-layout"><div class="platform-donut is-relation"><span><strong>{{ relationAssetOverview?.total ?? '--' }}</strong><em>{{ relationAssetOverview?.totalLabel ?? '关系总量' }}</em></span></div><div class="platform-structure-legend"><article v-for="item in relationStructure" :key="item.schema"><span><i :style="{ background: item.tone }" />{{ item.label }}<em>{{ item.schema }}</em></span><strong>{{ item.count }}<em>{{ item.ratio }}%</em></strong></article></div></div></div>
        </div>
      </section>

      <section class="platform-overview-main">
        <div class="kg-panel platform-jobs-panel">
          <div class="kg-panel__header"><div><h2 class="kg-panel__title">图谱构建</h2></div><RouterLink to="/graph-build">查看全部任务 →</RouterLink></div>
          <template v-if="overviewJobsState === 'ready'">
            <div class="platform-jobs-stats">
              <article v-for="stat in overviewJobStats" :key="stat.label"><span :class="`is-${stat.tone}`">{{ stat.value }}</span><em>{{ stat.label }}</em></article>
            </div>
            <div class="platform-jobs-list" v-if="recentOverviewJobs.length">
              <RouterLink v-for="job in recentOverviewJobs" :key="job.id" :to="`/graph-build/jobs/${job.id}`">
                <strong>{{ job.name }}</strong>
                <span :class="JOB_STATUS_TONE[deriveJobUnifiedStatus(job)]">{{ deriveJobUnifiedStatus(job) }}</span>
                <em>{{ job.lastRunAt || job.createdAt }}</em>
              </RouterLink>
            </div>
            <div v-else class="platform-card-empty">
              <strong>暂无构建任务</strong>
              <p>创建一次性 / 周期性任务，触发脚本抽取写入图空间。</p>
              <RouterLink class="primary" to="/graph-build">去新建任务</RouterLink>
            </div>
          </template>
          <div v-else-if="overviewJobsState === 'loading'" class="platform-card-empty"><strong>任务数据加载中…</strong></div>
          <div v-else class="platform-card-empty"><strong>任务数据暂不可用</strong><p>{{ overviewJobsError }}</p><RouterLink to="/graph-build">前往图谱构建 →</RouterLink></div>
        </div>

        <aside class="kg-panel platform-review-panel">
          <div class="kg-panel__header"><div><h2 class="kg-panel__title">人工审核</h2></div><RouterLink to="/manual-review">查看处理队列 →</RouterLink></div>
          <template v-if="overviewReviewsState === 'ready'">
            <div class="platform-review-count">待处理 <strong>{{ overviewReviewsTotal }}</strong> 条</div>
            <div class="platform-review-list">
              <RouterLink v-for="item in overviewReviews" :key="item.id" :to="`/manual-review/task/${item.id}`">
                <strong>{{ item.objectName || item.objectId }}</strong>
                <em>{{ item.category }}</em>
                <span class="is-risk">风险 {{ item.riskLevel }}</span>
              </RouterLink>
            </div>
          </template>
          <div v-else-if="overviewReviewsState === 'empty'" class="platform-card-empty">
            <strong>当前没有待审核任务</strong>
            <p>构建流程发现的低置信度候选会进入这里等待人工决策。</p>
            <RouterLink to="/manual-review">前往人工审核</RouterLink>
          </div>
          <div v-else-if="overviewReviewsState === 'loading'" class="platform-card-empty"><strong>审核队列加载中…</strong></div>
          <div v-else-if="overviewReviewsState === 'forbidden'" class="platform-card-empty"><strong>暂无审核权限</strong><p>需要审核角色（reviewer / 数据质量 / 图谱治理）后才能查看队列。</p><RouterLink to="/manual-review">前往人工审核</RouterLink></div>
          <div v-else class="platform-card-empty"><strong>审核队列暂不可用</strong><p>{{ overviewReviewsError }}</p><RouterLink to="/manual-review">前往人工审核 →</RouterLink></div>
        </aside>
      </section>
    </main>

    <main v-else-if="activeTab === 'processing'" class="platform-content platform-processing">
      <section class="kg-panel platform-source-panel">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">科技要素数据库更新</h2>
          <span>自动更新：每日 02:00</span>
        </div>
        <div class="platform-processing-controls">
          <label>
            <span>业务域</span>
            <select aria-label="选择或输入内容" v-model="processingTaskDomain">
              <option v-for="item in processingTaskDomainOptions" :key="item">{{ item }}</option>
            </select>
          </label>
          <label>
            <span>数据范围</span>
            <select aria-label="选择或输入内容" v-model="processingScope">
              <option v-for="item in processingScopeOptions" :key="item">{{ item }}</option>
            </select>
          </label>
          <label>
            <span>执行优先级</span>
            <select aria-label="选择或输入内容" v-model="processingPriority">
              <option v-for="item in processingPriorityOptions" :key="item">{{ item }}</option>
            </select>
          </label>
          <label v-if="processingScope === '指定时间范围'" class="platform-range-fields">
            <span>时间范围</span>
            <i><input aria-label="processingStartDate" v-model="processingStartDate" type="date" /><b>至</b><input aria-label="processingEndDate" v-model="processingEndDate" type="date" /></i>
          </label>
          <label v-if="processingPriority === '紧急'">
            <span>紧急原因</span>
            <input aria-label="必填，用于审计与排队依据" v-model="processingReason" placeholder="必填，用于审计与排队依据" />
          </label>
          <button class="kg-button" type="button" :disabled="isActionLoading || (processingPriority === '紧急' && !processingReason.trim())" @click="handleStartTask">{{ processingActionLabel }}</button>
        </div>
        <div class="platform-update-help"><span><b>普通：</b>按提交顺序排队。</span><span><b>紧急：</b>优先排队，需填写原因。</span></div>

        <div class="platform-sticky-table"><table aria-label="数据表" class="platform-table">
          <thead>
            <tr><th>业务域</th><th>数据对象</th><th>物理表</th><th>调度方式</th><th>更新频率</th><th>最近成功</th><th>状态</th><th>追溯</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in sourceRows" :key="row.table" class="is-clickable" tabindex="0" @click="openProcessDetail('processing', row.task, 'source')" @keydown.enter="openProcessDetail('processing', row.task, 'source')">
              <td>{{ row.domain }}</td>
              <td>{{ row.object }}</td>
              <td><code>{{ row.table }}</code></td>
              <td>{{ row.schedule }}</td>
              <td>{{ row.frequency }}</td>
              <td>{{ row.latest }}</td>
              <td><span :class="['platform-status', `is-${row.status}`]">{{ row.status }}</span></td>
              <td><button class="platform-trace-link" type="button" @click.stop="openProcessDetail('processing', row.task, 'source')">查看详情 →</button></td>
            </tr>
          </tbody>
        </table></div>
      </section>

      <section class="kg-panel platform-cleaning-flow">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">数据处理流程</h2>
        </div>
        <div class="platform-cleaning-steps">
          <button v-for="(item, index) in dataProcessingSteps" :key="item.name" class="is-clickable-card" type="button" @click="openProcessDetail('processing', 'DP-20260713-0200', item.id)">
            <i>{{ index + 1 }}</i>
            <div>
              <strong>{{ item.name }}</strong>
              <p>{{ item.desc }}</p>
            </div>
            <span>{{ item.status }}</span>
            <b class="platform-card-arrow">查看详情 →</b>
          </button>
        </div>
      </section>

      <section class="kg-panel platform-quality-log">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">质量检验日志</h2>
        </div>
        <table aria-label="数据表" class="platform-table">
          <thead><tr><th>质检规则</th><th>检验对象</th><th>来源批次</th><th>检验数</th><th>异常数</th><th>通过率</th><th>状态</th><th>操作</th></tr></thead>
          <tbody><tr v-for="row in qualityLogRows" :key="row.rule" class="is-clickable" tabindex="0" @click="openProcessDetail('processing', row.batch, 'quality')" @keydown.enter="openProcessDetail('processing', row.batch, 'quality')"><td>{{ row.rule }}</td><td>{{ row.object }}</td><td>{{ row.batch }}</td><td>{{ row.checked }}</td><td>{{ row.failed }}</td><td>{{ row.rate }}</td><td><span :class="['platform-status', `is-${row.status}`]">{{ row.status }}</span></td><td><button class="platform-trace-link" type="button" @click.stop="openProcessDetail('processing', row.batch, 'quality')">查看详情 →</button></td></tr></tbody>
        </table>
      </section>

      <section class="platform-review-notice is-warning" aria-label="数据处理异常提示">
        <div class="platform-review-notice__icon" aria-hidden="true">!</div>
        <div>
          <strong>发现 385 条数据质量异常</strong>
          <p>必填缺失 18 条 · 唯一性冲突 326 条 · 枚举异常 41 条</p>
        </div>
        <div class="platform-review-notice__actions"><RouterLink to="/graph-build?module=图谱构建&amp;batch=UPD-20260714">查看处理实例</RouterLink><RouterLink to="/manual-review?batch=UPD-20260714">进入人工处理 →</RouterLink></div>
      </section>

      <section class="kg-panel platform-task-list">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">最近数据处理任务</h2>
          <div class="platform-task-filters">
            <select v-model="processingDomainFilter" aria-label="处理领域"><option v-for="item in processingDomainOptions" :key="item">{{ item }}</option></select>
            <select v-model="processingStatusFilter" aria-label="处理状态"><option v-for="item in processingStatusOptions" :key="item">{{ item }}</option></select>
            <span>{{ filteredProcessingTaskRows.length }} 个任务</span>
            <RouterLink to="/graph-build?module=数据处理">全部任务 →</RouterLink>
          </div>
        </div>
        <table aria-label="数据表" class="platform-table platform-progress-table">
          <thead>
            <tr><th>处理批次</th><th>源库表</th><th>触发方式</th><th>触发时间</th><th>输入记录</th><th>进度</th><th>目标库表</th><th>状态</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in filteredProcessingTaskRows" :key="row.batch" class="is-clickable" tabindex="0" @click="openProcessDetail('processing', row.batch)" @keydown.enter="openProcessDetail('processing', row.batch)">
              <td>{{ row.batch }}</td>
              <td>{{ row.source }}</td>
              <td>{{ row.type }}</td>
              <td>{{ row.time }}</td>
              <td>{{ row.input }}</td>
              <td>
                <div class="platform-progress-cell">
                  <b><i :style="{ width: `${row.progress}%` }" /></b>
                  <span>{{ row.progress }}%</span>
                </div>
              </td>
              <td>{{ row.target }}</td>
              <td><span :class="['platform-status', `is-${row.status}`]">{{ row.status }}</span></td>
            </tr>
          </tbody>
        </table>
      </section>
    </main>

    <main v-else-if="activeTab === 'construction'" class="platform-content platform-construction">
      <section class="platform-build-stats" aria-label="图谱构建统计">
        <button v-for="item in buildStats" :key="item.label" class="is-clickable-card" type="button" @click="openProcessDetail('construction', 'KG-INC-20260713-018')"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><em>{{ item.note }}</em><b class="platform-card-arrow">查看 →</b></button>
      </section>

      <section class="kg-panel platform-build-pipeline">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">结构化数据建图过程</h2>
        </div>
        <div class="platform-build-pipeline__body">
          <button v-for="(item, index) in buildPipelineSteps" :key="item.name" class="is-clickable-card" type="button" @click="openProcessDetail('construction', 'KG-INC-20260713-018', item.id)">
            <i>{{ index + 1 }}</i>
            <div>
              <span>{{ item.name }}</span>
              <strong>{{ item.count }}</strong>
              <p>{{ item.desc }}</p>
            </div>
            <em>{{ item.status }}</em>
            <b class="platform-card-arrow">详情 →</b>
          </button>
        </div>
      </section>

      <section class="kg-panel platform-build-progress platform-build-progress--list">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">最近图谱构建任务</h2>
          <div class="platform-task-filters"><RouterLink to="/graph-build?module=图谱构建">全部任务 →</RouterLink></div>
        </div>
        <table aria-label="数据表" class="platform-table platform-progress-table">
          <thead>
            <tr><th>构建批次</th><th>数据域</th><th>当前阶段</th><th>实体</th><th>关系</th><th>属性</th><th>进度</th><th>隔离异常</th><th>状态</th></tr>
          </thead>
          <tbody>
            <tr v-for="row in taskRows" :key="row.batch" tabindex="0" @click="openProcessDetail('construction', row.batch)" @keydown.enter="openProcessDetail('construction', row.batch)">
              <td>{{ row.batch }}</td><td>{{ row.domain }}</td><td>{{ row.stage }}</td><td>{{ row.entities }}</td><td>{{ row.relations }}</td><td>{{ row.properties }}</td>
              <td><div class="platform-progress-cell"><b><i :style="{ width: `${row.progress}%` }" /></b><span>{{ row.progress }}%</span></div></td>
              <td>{{ row.conflicts }}</td><td><span :class="['platform-status', `is-${row.status}`]">{{ row.status }}</span></td>
            </tr>
          </tbody>
        </table>
      </section>

      <section class="kg-panel platform-schema-readonly">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">当前 Schema 摘要（只读）</h2>
          <div class="platform-schema-head"><span>v1.8</span></div>
        </div>
        <table aria-label="数据表" class="platform-table">
          <thead><tr><th>类型</th><th>Schema 名称</th><th>字段 / 属性</th><th>映射与生成规则</th><th>权限</th></tr></thead>
          <tbody><tr v-for="row in readonlySchemaRows" :key="row.name" class="is-clickable" tabindex="0" @click="openProcessDetail('construction', 'KG-INC-20260713-018', 'schema')" @keydown.enter="openProcessDetail('construction', 'KG-INC-20260713-018', 'schema')"><td>{{ row.type }}</td><td><code>{{ row.name }}</code></td><td>{{ row.fields }}</td><td>{{ row.rule }}</td><td><button class="platform-trace-link" type="button" @click.stop="openProcessDetail('construction', 'KG-INC-20260713-018', 'schema')">查看 →</button></td></tr></tbody>
        </table>
      </section>

      <section class="platform-review-notice" aria-label="图谱构建人工处理提示">
        <div class="platform-review-notice__icon" aria-hidden="true">!</div>
        <div>
          <strong>326 个候选对象需要人工确认</strong>
          <p>实体冲突 86 个 · 低置信度关系 198 条 · 属性异常 42 项</p>
        </div>
        <div class="platform-review-notice__actions"><RouterLink to="/graph-build?module=图谱构建&amp;batch=UPD-20260714">查看处理实例</RouterLink><RouterLink to="/manual-review?batch=UPD-20260714">进入人工处理 →</RouterLink></div>
      </section>

    </main>

    <!-- nGQL 模式 is-fixed-result：结果区常驻并占满剩余高度（对齐图谱构建页固定表格版式），
         图算法模式表单较长仍走整页滚动 -->
    <main
      v-else-if="activeTab === 'query'"
      :class="['platform-content', 'platform-query', { 'is-fixed-result': queryMode === 'ngql' }]"
    >
      <section class="kg-panel platform-query-form">
        <div class="kg-panel__header">
          <div class="platform-query-mode-group">
            <div class="platform-query-mode-toggle" role="tablist" aria-label="查询模式切换">
              <button
                type="button"
                :class="['platform-query-mode-toggle__item', { 'is-active': queryMode === 'ngql' }]"
                @click="queryMode = 'ngql'"
              >
                nGQL 模式
              </button>
              <button
                type="button"
                :class="['platform-query-mode-toggle__item', { 'is-active': queryMode === 'algo' }]"
                @click="queryMode = 'algo'"
              >
                图算法
              </button>
            </div>
            <div v-if="queryMode === 'ngql'" class="platform-ngql-permission-hint" role="note">
              <IconInfoCircle aria-hidden="true" />
              <span>只读语句所有用户可执行</span>
              <i aria-hidden="true"></i>
              <span>写语句仅平台管理员</span>
              <i aria-hidden="true"></i>
              <span>DDL 禁止执行</span>
            </div>
          </div>
          <div v-if="queryMode === 'ngql'" class="platform-ngql-header-actions">
            <button
              class="kg-button"
              type="button"
              :disabled="ngqlLoading || !ngqlStatement.trim()"
              @click="handleNgqlQuery"
            >
              {{ ngqlLoading ? '执行中…' : '执行 nGQL' }}
            </button>
          </div>
        </div>
        <div v-if="queryMode === 'ngql'" class="platform-ngql-input">
          <textarea
            v-model="ngqlStatement"
            aria-label="nGQL 查询语句"
            class="platform-ngql-input__textarea"
            rows="5"
            spellcheck="false"
            placeholder="MATCH (v:专家) RETURN v LIMIT 10"
            @keydown.ctrl.enter="handleNgqlQuery"
            @keydown.meta.enter="handleNgqlQuery"
          />
        </div>
      </section>

      <!-- 结果区常驻：未执行时空数据占位，执行后填充（不再整块隐藏/出现引起布局跳动） -->
      <section v-if="queryMode === 'ngql'" class="platform-query-result">
        <header class="platform-query-result__head">
          <h2 class="platform-query-result__title">nGQL 执行结果</h2>
          <span v-if="ngqlResult" class="platform-query-result__meta">{{ ngqlResult.records.length }} 行记录</span>
        </header>
        <div class="platform-query-result__body">
          <div class="platform-query-result__table">
            <table v-if="ngqlResult && ngqlResult.records.length" aria-label="nGQL 查询结果">
              <thead>
                <tr>
                  <th v-for="column in ngqlResult.columns" :key="column">{{ column }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(record, index) in pagedNgqlRecords" :key="index">
                  <td v-for="column in ngqlResult.columns" :key="column">
                    <pre>{{ formatNgqlCell(record[column]) }}</pre>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="platform-query-result__empty">
              {{ ngqlResult ? '语句执行成功，无返回记录' : '暂无数据，执行 nGQL 语句后在此查看结果' }}
            </div>
          </div>
          <ListPagination
            v-if="ngqlTotal > 0"
            :total="ngqlTotal"
            :page="ngqlPage"
            :page-size="ngqlPageSize"
            :disabled="ngqlLoading"
            @change="changeNgqlPage"
            @change-size="changeNgqlPageSize"
          />
        </div>
      </section>

      <section v-if="queryMode === 'algo'" class="kg-panel platform-query-algo">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">图算法</h2>
          <div class="platform-query-algo__engine">
            <span
              :class="['platform-status', algoEngineStatus.tone]"
              :title="algoMetadata?.engine?.message ?? undefined"
            >算法引擎{{ algoEngineStatus.label }}</span>
            <button
              class="kg-button kg-button--text"
              type="button"
              :disabled="algoMetadataLoading || !algoSpace"
              @click="refreshAlgoEngine"
            >
              重新检测
            </button>
          </div>
        </div>
        <div class="platform-query-algo__body">
          <!-- 算法切换页签：版式对齐人工审核「抽取失败重跑」二级子页签（纯文字 + 蓝色下划线动效） -->
          <nav class="platform-query-algo__tabs" aria-label="算法切换">
            <button
              v-for="algo in GRAPH_ALGORITHMS"
              :key="algo.id"
              type="button"
              :class="{ 'is-active': selectedAlgorithm === algo.id }"
              @click="selectedAlgorithm = algo.id"
            >{{ algo.label }}</button>
          </nav>
          <p v-if="algoMetadata?.engine?.status === 'DOWN'" class="platform-query-algo__engine-hint" role="note">
            算法引擎当前不可用（{{ algoMetadata.engine.message ?? 'Spark 运行器未就绪' }}），提交可能失败，可稍后重试
          </p>
          <p class="platform-query-algo__desc">{{ selectedAlgorithmDef.label }}：{{ selectedAlgorithmDef.description }}</p>
          <div class="platform-form-grid">
            <div class="platform-form-field platform-query-algo__labels">
              <label class="platform-form-label">边类型（可多选）</label>
              <a-select
                v-model="algoLabels"
                multiple
                allow-clear
                placeholder="选择参与计算的边类型"
                :scrollbar="false"
              >
                <a-option v-for="item in algoMetadata?.edgeTypes ?? []" :key="item" :value="item">
                  {{ item }}
                </a-option>
              </a-select>
            </div>
            <div v-for="param in algoParamDefs" :key="param.key" class="platform-form-field">
              <label class="platform-form-label" :for="`algo-param-${param.key}`">
                {{ param.label }}<i v-if="param.required" class="platform-query-algo__required">*</i>
              </label>
              <a-select
                v-if="param.type === 'enum'"
                :id="`algo-param-${param.key}`"
                v-model="algoParamValues[selectedAlgorithm][param.key]"
                :scrollbar="false"
              >
                <a-option
                  v-for="option in param.options ?? []"
                  :key="option.value"
                  :value="option.value"
                >{{ option.label }}</a-option>
              </a-select>
              <label v-else-if="param.type === 'bool'" class="platform-query-algo__check">
                <input
                  :id="`algo-param-${param.key}`"
                  v-model="algoParamValues[selectedAlgorithm][param.key]"
                  type="checkbox"
                />
                <span>{{ param.hint ?? '启用' }}</span>
              </label>
              <input
                v-else-if="param.type === 'int' || param.type === 'float'"
                :id="`algo-param-${param.key}`"
                v-model.number="algoParamValues[selectedAlgorithm][param.key]"
                class="platform-query-algo__input"
                type="number"
                :min="param.min"
                :max="param.max"
                :step="param.type === 'float' ? (param.step ?? 0.01) : 1"
                :placeholder="param.placeholder"
              />
              <input
                v-else
                :id="`algo-param-${param.key}`"
                v-model="algoParamValues[selectedAlgorithm][param.key]"
                class="platform-query-algo__input"
                type="text"
                :placeholder="param.placeholder"
              />
              <span v-if="param.hint && param.type !== 'bool'" class="platform-query-algo__param-hint">{{ param.hint }}</span>
            </div>
            <div class="platform-form-field">
              <label class="platform-form-label">边权重</label>
              <label class="platform-query-algo__check">
                <input v-model="algoHasWeight" type="checkbox" />
                <span>按边属性加权计算</span>
              </label>
            </div>
            <template v-for="label in algoLabels" :key="label">
              <div v-if="algoHasWeight" class="platform-form-field">
                <label class="platform-form-label">{{ label }} 权重属性</label>
                <input
                  v-model="algoWeightCols[label]"
                  class="platform-query-algo__input"
                  type="text"
                  placeholder="边上的权重属性名，如 weight"
                />
              </div>
            </template>
            <div class="platform-form-field">
              <label class="platform-form-label">VID 编码</label>
              <label class="platform-query-algo__check">
                <input v-model="algoEncodeId" type="checkbox" />
                <span>字符串 VID 编码（图库 VID 为字符串，建议保持开启）</span>
              </label>
            </div>
            <div class="platform-form-field">
              <label class="platform-form-label" for="algo-partition">Spark 分区数</label>
              <input
                id="algo-partition"
                v-model.number="algoPartitionNum"
                class="platform-query-algo__input"
                type="number"
                min="1"
                max="10000"
              />
            </div>
          </div>
          <div class="platform-query-algo__actions">
            <button
              class="kg-button"
              type="button"
              :disabled="algoSubmitLoading"
              @click="handleAlgoSubmit"
            >
              {{ algoSubmitLoading ? '提交中…' : '提交算法作业' }}
            </button>
            <span class="platform-query-algo__actions-hint">作业在 Spark 引擎执行，同一时刻仅允许一个作业</span>
          </div>
          <div v-if="algoJob" class="platform-query-algo__job">
            <div class="platform-query-algo__job-meta">
              <span :class="['platform-status', algoJobStatus?.tone]">{{ algoJobStatus?.label }}</span>
              <span class="platform-query-algo__job-id">作业 {{ algoJob.jobId }}</span>
              <span v-if="algoJob.startedAt">开始 {{ algoJob.startedAt }}</span>
              <span v-if="algoJob.finishedAt">完成 {{ algoJob.finishedAt }}</span>
              <button class="kg-button kg-button--text" type="button" @click="refreshAlgoJob">刷新状态</button>
            </div>
            <div v-if="algoJob.status === 'failed'" class="platform-query-algo__job-error">
              <p><strong>失败原因：</strong>{{ algoJob.error ?? '（服务端未返回原因）' }}</p>
              <pre v-if="algoJob.logTail">{{ algoJob.logTail }}</pre>
            </div>
          </div>
        </div>
      </section>

      <section v-if="queryMode === 'algo' && algoResult" class="platform-query-result platform-query-algo-result">
        <header class="platform-query-result__head">
          <h2 class="platform-query-result__title">算法执行结果</h2>
          <span class="platform-query-result__meta">{{ algoRows.length }} 行记录</span>
        </header>
        <p v-if="algoResult.truncated" class="platform-query-algo__truncated">
          结果已达服务端上限 10000 行，已截断展示
        </p>
        <div class="platform-query-result__body">
          <div class="platform-query-result__table">
            <table v-if="algoRows.length" aria-label="图算法执行结果">
              <thead>
                <tr>
                  <th v-for="column in algoResultColumns" :key="column">{{ column }}</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="(row, index) in pagedAlgoRows" :key="index">
                  <td v-for="column in algoResultColumns" :key="column">
                    <pre>{{ row[column] ?? '' }}</pre>
                  </td>
                </tr>
              </tbody>
            </table>
            <div v-else class="platform-query-result__empty">算法执行成功，无返回记录</div>
          </div>
          <ListPagination
            v-if="algoTotal > 0"
            :total="algoTotal"
            :page="algoPage"
            :page-size="algoPageSize"
            @change="changeAlgoPage"
            @change-size="changeAlgoPageSize"
          />
        </div>
      </section>

    </main>

    <main v-else :class="['platform-content', 'platform-service', { 'platform-service--api': activeServiceMode === 'api' }]">
      <section class="kg-panel platform-service-console">
        <div class="platform-service-console__top">
          <div class="platform-service-tabs">
            <button type="button" :class="{ 'is-active': activeServiceMode === 'test' }" @click="activeServiceMode = 'test'">
              服务调用
            </button>
            <button type="button" :class="{ 'is-active': activeServiceMode === 'api' }" @click="activeServiceMode = 'api'">
              接口文档
            </button>
          </div>
        </div>

        <div class="platform-service-console__body">
          <label>
            <span>当前模块</span>
            <input aria-label="input-field" :value="activeService.title" readonly />
          </label>
          <template v-if="activeServiceMode === 'test'">
            <label v-for="field in activeService.requestFields.slice(0, 3)" :key="field.name">
              <span>{{ field.name }}</span>
              <input aria-label="input-field" :value="activeService.requestExample[field.name] ?? ''" />
            </label>
          </template>
          <template v-else>
            <label>
            <span>接口路径</span>
            <input aria-label="input-field" :value="activeService.endpoint" readonly />
            </label>
            <label>
            <span>请求方法</span>
            <input aria-label="input-field" :value="activeService.method" readonly />
            </label>
          </template>
          <div class="platform-service-console__actions">
            <button v-if="activeServiceMode === 'test'" type="button" :disabled="isActionLoading" @click="handleExecuteService">
              执行调用
            </button>
            <button v-else type="button" @click="handleCopyEndpoint">复制接口</button>
          </div>
        </div>
      </section>

      <template v-if="activeServiceMode === 'test'">
        <section class="kg-panel platform-service-run">
          <div class="kg-panel__header">
            <h2 class="kg-panel__title">调用结果概览</h2>
            <span>{{ activeService.title }} / {{ activeService.method }}</span>
          </div>
          <div class="platform-service-run__body">
            <div class="platform-service-summary">
              <div v-for="item in serviceConsoleStats" :key="item.label">
                <span>{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </div>
            </div>
            <div class="platform-service-request">
              <strong>请求摘要</strong>
              <dl>
                <div v-for="item in activeRequestEntries" :key="item.key">
                  <dt>{{ item.label }}</dt>
                  <dd>
                    <span>{{ item.value }}</span>
                    <em v-if="item.required">必填</em>
                  </dd>
                </div>
              </dl>
            </div>
            <div class="platform-result-grid">
              <div v-for="row in activeService.resultRows" :key="row.label">
                <span>{{ row.label }}</span>
                <strong>{{ row.value }}</strong>
              </div>
            </div>
            <dl class="platform-service-info">
              <div><dt>命中服务</dt><dd>{{ activeService.title }}</dd></div>
              <div><dt>状态码</dt><dd>0 / success</dd></div>
              <div><dt>更新时间</dt><dd>2026-07-13 10:30</dd></div>
            </dl>
          </div>
        </section>

        <aside aria-label="辅助区域 3" class="kg-panel platform-service-debug">
          <div class="kg-panel__header">
            <h2 class="kg-panel__title">请求与响应</h2>
          </div>
          <div class="platform-service-debug__body">
            <div class="platform-service-payload">
              <strong>请求体</strong>
              <pre>{{ activeRequestJson }}</pre>
            </div>
            <div class="platform-service-payload">
              <strong>响应体</strong>
              <pre>{{ activeResponseJson }}</pre>
            </div>
            <div class="platform-evidence">
              <strong>结果依据</strong>
              <ul>
                <li v-for="(line, index) in activeService.evidence.slice(0, 3)" :key="index">{{ line }}</li>
              </ul>
            </div>
            <div class="platform-service-log">
              <strong>调用日志</strong>
              <ul>
                <li v-for="item in serviceCallLogs" :key="`${item.time}-${item.message}`">
                  <span>{{ item.time }}</span>
                  <b>{{ item.level }}</b>
                  <p>{{ item.message }}</p>
                </li>
              </ul>
            </div>
          </div>
        </aside>
      </template>

      <template v-else>
        <section class="kg-panel platform-api-doc">
          <div class="kg-panel__header">
            <h2 class="kg-panel__title">开发者接口文档</h2>
            <span>{{ activeService.method }} {{ activeService.endpoint }}</span>
          </div>
          <div class="platform-api-doc__grid">
            <article>
              <h3>请求参数</h3>
              <table aria-label="数据表" class="platform-table">
                <thead><tr><th>字段名</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
                <tbody>
                  <tr v-for="field in activeService.requestFields.slice(0, 6)" :key="field.name">
                    <td>{{ field.name }}</td>
                    <td>{{ field.type }}</td>
                    <td>{{ field.required ?? '否' }}</td>
                    <td>{{ field.description }}</td>
                  </tr>
                </tbody>
              </table>
            </article>
            <article>
              <h3>返回字段</h3>
              <table aria-label="数据表" class="platform-table">
                <thead><tr><th>字段名</th><th>类型</th><th>说明</th></tr></thead>
                <tbody>
                  <tr v-for="field in activeService.responseFields" :key="field.name">
                    <td>{{ field.name }}</td>
                    <td>{{ field.type }}</td>
                    <td>{{ field.description }}</td>
                  </tr>
                </tbody>
              </table>
            </article>
          </div>
          <div class="platform-api-examples">
            <article>
              <h3>请求示例</h3>
              <pre>{{ activeRequestJson }}</pre>
            </article>
            <article>
              <h3>响应示例</h3>
              <pre>{{ activeResponseJson }}</pre>
            </article>
          </div>
          <div class="platform-code-sample">
            <div>
              <strong>代码示例</strong>
              <span>Python</span>
              <span>Node.js</span>
              <span>cURL</span>
            </div>
            <pre>import requests

url = "https://api.example.com{{ activeService.endpoint }}"
payload = {{ activeRequestJson }}
response = requests.post(url, json=payload)
print(response.json())</pre>
          </div>
        </section>
      </template>
    </main>

    <button v-if="selectedAssetChange" class="asset-change-mask" type="button" aria-label="关闭新增数据详情" @click="selectedAssetChange = null" />
    <aside aria-label="辅助区域 4" v-if="selectedAssetChange && activeAssetOverview" class="asset-change-drawer">
      <header><div><span>今日图谱数据变化</span><h2>{{ activeAssetOverview.title }}新增明细</h2><p>{{ activeAssetOverview.addedLabel }} {{ activeAssetOverview.added }} · 数据更新至 {{ overviewMeta.updatedAt }}</p></div><button type="button" @click="selectedAssetChange = null">×</button></header>
      <section class="asset-change-summary"><article><span>当前总量</span><strong>{{ activeAssetOverview.total }}</strong></article><article><span>{{ activeAssetOverview.addedLabel }}</span><strong>{{ activeAssetOverview.added }}</strong></article></section>
      <div class="asset-change-table"><table aria-label="数据表"><thead><tr><th>数据类型</th><th>具体对象</th><th>变更内容</th><th>来源</th><th>识别时间</th></tr></thead><tbody><tr v-for="row in assetChangeRows[selectedAssetChange]" :key="`${row.object}-${row.time}`"><td>{{ row.type }}</td><td><strong>{{ row.object }}</strong></td><td>{{ row.change }}</td><td><code>{{ row.source }}</code></td><td>{{ row.time }}</td></tr></tbody></table></div>
      <footer><span>{{ assetChangeRows[selectedAssetChange].length }} 条变化</span><RouterLink to="/graph-build">查看对应更新任务 →</RouterLink></footer>
    </aside>

  </div>
</template>

<style scoped>
.platform-page {
  display: grid;
  grid-template-rows: auto minmax(0, 1fr);
  gap: 16px;
  height: 100%;
  min-width: 0;
  color: var(--text-primary);
  font-size: 16px;
}

.platform-hero {
  position: relative;
  overflow: hidden;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 14px;
  min-height: 62px;
  padding: 11px 18px;
  border: 1px solid rgba(132, 178, 246, 0.86);
  border-radius: 12px;
  background:
    linear-gradient(135deg, rgba(216, 235, 255, 0.98) 0%, rgba(237, 247, 255, 0.98) 48%, rgba(211, 242, 255, 0.94) 100%),
    #e5f1ff;
  box-shadow:
    0 8px 22px rgba(48, 105, 194, 0.13),
    inset 0 1px 0 rgba(255, 255, 255, 0.96);
}

.platform-hero::before {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(90deg, rgba(22, 93, 255, 0.075) 1px, transparent 1px),
    linear-gradient(rgba(22, 93, 255, 0.075) 1px, transparent 1px);
  background-size: 34px 34px;
  mask-image: linear-gradient(90deg, rgba(0, 0, 0, 0.62), transparent 72%);
  pointer-events: none;
  content: "";
}

.platform-hero > * {
  position: relative;
}

.platform-hero h1 {
  margin: 0;
  color: #10264c;
  font-size: 22px;
  line-height: 28px;
  font-weight: 700;
}

.platform-hero__main {
  display: grid;
  gap: 1px;
  min-width: 0;
}

.platform-hero__subtitle {
  margin: 0;
  color: #4b6288;
  font-size: 12px;
  line-height: 18px;
}

.platform-hero__flow { display:flex;align-items:center;gap:6px;margin-top:4px;color:#607493;font-size:10px; }
.platform-hero__flow span { padding:2px 7px;border:1px solid rgba(126,168,229,.65);border-radius:99px;background:rgba(255,255,255,.58); }
.platform-hero__flow i { color:#004ecc;font-style:normal; }

.platform-hero__actions { display:flex;align-items:center;gap:8px;margin-left:auto; }
.platform-hero__actions span { display:inline-flex;align-items:center;gap:7px;margin-right:4px;color:#526783;font-size:12px; }
.platform-hero__actions span i { width:8px;height:8px;border-radius:50%;background:#067647;box-shadow:0 0 0 4px rgba(18,183,106,.12); }
.platform-hero__actions a { height:32px;padding:0 12px;border:1px solid #9ec2f7;border-radius:6px;background:rgba(255,255,255,.72);color:#004ecc;font-size:12px;line-height:32px;text-decoration:none; }
.platform-hero__actions a:last-child { border-color:#004ecc;background:#004ecc;color:#fff; }

.platform-page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  padding: 0 2px 2px;
}

.platform-page-head__action { height:30px;padding:0 11px;border:1px solid #9ec2f7;border-radius:6px;background:#fff;color:#004ecc;font-size:11px;line-height:30px;text-decoration:none; }

.platform-page-head h1 {
  margin: 0;
  color: #10264c;
  font-size: 20px;
  line-height: 28px;
  font-weight: 700;
}

.platform-page-head p {
  margin: 2px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-content {
  min-height: 0;
  overflow: auto;
  padding-bottom: 2px;
  /* 总览内容常超一屏（资产卡+任务/审核卡+分布图），外层工作区滚动条被隐藏，
     这里必须露出自己的滚动条，否则底部扇形图"看不到" */
  scrollbar-width: thin;
  scrollbar-color: #b8ccec transparent;
}

.platform-content::-webkit-scrollbar {
  width: 8px;
}

.platform-content::-webkit-scrollbar-thumb {
  border-radius: 4px;
  background: #b8ccec;
}

.platform-content::-webkit-scrollbar-thumb:hover {
  background: #9db9e0;
}

.platform-overview {
  /* 不用 grid auto 行：.platform-content 高度确定（内滚容器），auto 行 + stretch 会
     形成循环依赖，行高忽略内容退化成 min-height（未设的区块塌成 header 高度被
     overflow:hidden 裁掉，饼图因此"看不见"）。flex 纵向堆叠高度纯内容驱动。 */
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.platform-overview > * {
  flex-shrink: 0;
}

.platform-metrics {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
}

.platform-stage-overview__groups { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px; }
.platform-stage-group { overflow:hidden;border:1px solid #d6e5f8;border-radius:8px;background:#f8fbff; }
.platform-stage-group>header { display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #dce8f8;background:#fff; }
.platform-stage-group>header strong { color:#20324e;font-size:13px; }
.platform-stage-group>header a { color:#004ecc;font-size:11px;text-decoration:none; }
.platform-stage-group>div { display:grid;grid-template-columns:repeat(4,minmax(0,1fr)); }
.platform-stage-group section { display:grid;gap:4px;padding:13px 14px;border-right:1px solid #e1ebf7; }
.platform-stage-group section:last-child { border-right:0; }
.platform-stage-group section span { color:#475467;font-size:11px; }
.platform-stage-group section strong { color:#10264c;font-size:20px; }
.platform-stage-group section em { overflow:hidden;color:#52627a;font-size:10px;font-style:normal;text-overflow:ellipsis;white-space:nowrap; }

.platform-metric {
  position: relative;
  overflow: hidden;
  display: grid;
  gap: 5px;
  min-height: 104px;
  padding: 18px;
  border: 1px solid #bed8ff;
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(239, 247, 255, 0.94)),
    #f3f8ff;
  box-shadow: 0 8px 18px rgba(48, 105, 194, 0.1);
}

.platform-metric::after {
  position: absolute;
  right: 12px;
  bottom: 10px;
  width: 52px;
  height: 3px;
  border-radius: 999px;
  background: currentColor;
  opacity: 0.18;
  content: "";
}

.platform-metric span {
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-metric strong {
  font-size: 32px;
  line-height: 40px;
  font-weight: 700;
}

.platform-metric em {
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 16px;
  font-style: normal;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-metric>b { position:absolute;right:17px;top:17px;color:#7890b5;font-size:11px;font-weight:600; }

.platform-metric.is-blue strong { color: #004ecc; }
.platform-metric.is-green strong { color: #00a870; }
.platform-metric.is-purple strong { color: #722ed1; }
.platform-metric.is-orange strong { color: #ff7d00; }
.platform-metric.is-red strong { color: #b42318; }

/* 加载态预留就绪高度（3 卡实测 202px）：避免数据到达撑高后把下方资产饼图挤出视口闪现 */
.platform-summary-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;min-height:202px; }
.platform-summary-card { position:relative;min-width:0;overflow:hidden; }
.platform-summary-card::after { position:absolute;right:-35px;bottom:-55px;width:130px;height:130px;border-radius:50%;background:rgba(22,93,255,.045);content:"";pointer-events:none; }
.platform-summary-card>header { display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 15px;border-bottom:1px solid #dce8f8;background:rgba(255,255,255,.75); }
.platform-summary-card>header>div { display:grid;gap:4px; }.platform-summary-card>header>div>strong { color:#263b5a;font-size:13px; }
.platform-summary-card>header span { display:flex;align-items:center;gap:5px;color:#067647;font-size:9px; }.platform-summary-card>header span i { width:6px;height:6px;border-radius:50%;background:#067647;box-shadow:0 0 0 3px #dcfae6; }
.platform-summary-card>header span.warning { color:#b42318; }.platform-summary-card>header span.warning i { background:#b42318;box-shadow:0 0 0 3px #fee4e2; }
.platform-summary-card>header a,.platform-summary-card>header button { padding:0;border:0;background:transparent;color:#004ecc;font-size:10px;text-decoration:none;white-space:nowrap;cursor:pointer; }
.platform-summary-card__main { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));min-height:112px;background:#fff; }
.platform-summary-card__main section { display:flex;justify-content:center;gap:5px;padding:20px 18px;border-right:1px solid #e3ebf6;flex-direction:column; }.platform-summary-card__main section:last-child { border-right:0; }
.platform-summary-card__main strong { color:#004ecc;font-size:34px;line-height:40px;letter-spacing:-.5px; }.platform-summary-card.is-relation .platform-summary-card__main strong { color:#7a5af8; }.platform-summary-card.is-property .platform-summary-card__main strong { color:#f79009; }.platform-summary-card .platform-summary-card__main .is-added strong { color:#067647; }
.platform-summary-card__main span { color:#475467;font-size:12px; }
.platform-summary-card__items { position:relative;z-index:1;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:10px 8px;background:#f8fbff; }
.platform-summary-card__items>a { display:grid;gap:3px;padding:2px 8px;border-right:1px solid #e1eaf5;color:inherit;text-decoration:none;transition:background-color .2s ease; }.platform-summary-card__items>a:last-child { border-right:0; }.platform-summary-card__items>a:hover { background:#eef5ff; }
.platform-summary-card__items em { overflow:hidden;color:#8290a5;font-size:8px;font-style:normal;text-overflow:ellipsis;white-space:nowrap; }.platform-summary-card__items strong { overflow:hidden;color:#344861;font-size:10px;text-overflow:ellipsis;white-space:nowrap; }

/* 同上：任务/审核面板加载中只占小高度，预留就绪高度防止布局跳动 */
.platform-overview-main { display:grid;grid-template-columns:minmax(0,1.65fr) minmax(360px,.72fr);gap:14px;min-height:340px; }
.platform-jobs-panel,.platform-review-panel { min-width:0;overflow:hidden; }
.platform-jobs-panel .kg-panel__header>div,.platform-review-panel .kg-panel__header>div { display:grid;gap:2px; }
.platform-jobs-panel .kg-panel__header span,.platform-review-panel .kg-panel__header span { color:#7b8aa1;font-size:10px; }
.platform-jobs-panel .kg-panel__header>a,.platform-review-panel .kg-panel__header>a { color:#004ecc;font-size:11px;text-decoration:none; }
.platform-jobs-stats { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid #e4ecf6; }
.platform-jobs-stats article { display:grid;gap:2px;padding:12px 8px;text-align:center;border-right:1px solid #edf2f8; }
.platform-jobs-stats article:last-child { border-right:0; }
.platform-jobs-stats article span { font-size:18px;font-weight:600; }
.platform-jobs-stats article span.is-run { color:#004ecc; }.platform-jobs-stats article span.is-ok { color:#067647; }.platform-jobs-stats article span.is-err { color:#b42318; }.platform-jobs-stats article span.is-warn { color:#b54708; }
.platform-jobs-stats article em { color:#52627a;font-size:10px;font-style:normal; }
.platform-jobs-list { display:grid; }
.platform-jobs-list a { display:grid;grid-template-columns:minmax(0,1fr) auto auto;align-items:center;gap:10px;min-height:44px;padding:9px 14px;border-bottom:1px solid #e4ecf6;background:#fff;color:#344761;text-decoration:none; }
.platform-jobs-list a:last-child { border-bottom:0; }
.platform-jobs-list a:hover { background:#f4f8ff; }
.platform-jobs-list strong { overflow:hidden;color:#253752;font-size:11px;text-overflow:ellipsis;white-space:nowrap; }
.platform-jobs-list a>span { padding:2px 8px;border-radius:999px;background:#eaf2ff;color:#004ecc;font-size:9px;white-space:nowrap; }
.platform-jobs-list a>span.ok { color:#067647;background:#e9f8ef; }.platform-jobs-list a>span.err { color:#b42318;background:#fee4e2; }.platform-jobs-list a>span.warn { color:#b54708;background:#fff3df; }
.platform-jobs-list em { color:#59636f;font-size:9px;font-style:normal;white-space:nowrap; }
.platform-review-count { padding:11px 14px;border-bottom:1px solid #e4ecf6;color:#62728a;font-size:11px; }
.platform-review-count strong { margin:0 4px;color:#10264c;font-size:18px; }
.platform-review-list { display:grid; }
.platform-review-list a { display:grid;grid-template-columns:minmax(0,1fr) auto;gap:3px 10px;align-items:center;padding:9px 14px;border-bottom:1px solid #e4ecf6;background:#fff;color:#344761;text-decoration:none; }
.platform-review-list a:last-child { border-bottom:0; }
.platform-review-list a:hover { background:#f4f8ff; }
.platform-review-list strong { overflow:hidden;color:#253752;font-size:11px;text-overflow:ellipsis;white-space:nowrap; }
.platform-review-list em { overflow:hidden;color:#8a97aa;font-size:9px;font-style:normal;text-overflow:ellipsis;white-space:nowrap; }
.platform-review-list .is-risk { justify-self:end;color:#b54708;font-size:9px;white-space:nowrap; }
.platform-card-empty { display:grid;gap:6px;justify-items:center;align-content:center;min-height:170px;padding:20px;text-align:center; }
.platform-card-empty strong { color:#253752;font-size:12px; }
.platform-card-empty p { margin:0;color:#8a97aa;font-size:10px;line-height:16px; }
.platform-card-empty a.primary { margin-top:6px;padding:7px 14px;border-radius:5px;background:#004ecc;color:#fff;font-size:11px;text-decoration:none; }
.platform-card-empty a:not(.primary) { margin-top:6px;color:#004ecc;font-size:11px;text-decoration:none; }

.platform-management-focus { display:grid;grid-template-columns:minmax(0,1.65fr) minmax(340px,.72fr);gap:14px; }
.platform-change-panel,.platform-risk-panel,.platform-trend-panel { min-width:0;overflow:hidden; }
.platform-change-panel .kg-panel__header>div,.platform-risk-panel .kg-panel__header>div,.platform-trend-panel .kg-panel__header>div,.platform-recent-tasks .kg-panel__header>div { display:grid;gap:2px; }
.platform-change-panel .kg-panel__header span,.platform-risk-panel .kg-panel__header span,.platform-trend-panel .kg-panel__header span,.platform-recent-tasks .kg-panel__header span { color:#7b8aa1;font-size:10px; }
.platform-change-panel .kg-panel__header>a,.platform-risk-panel .kg-panel__header>a { color:#004ecc;font-size:11px;text-decoration:none; }
.platform-change-stats { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid #dde8f5; }
.platform-change-stats article { position:relative;display:grid;gap:4px;padding:13px 15px;border-right:1px solid #e2eaf5;background:#fff; }
.platform-change-stats article:last-child { border-right:0; }
.platform-change-stats article::before { position:absolute;top:14px;left:0;width:3px;height:30px;border-radius:0 3px 3px 0;background:#2e90fa;content:""; }
.platform-change-stats article.is-purple::before { background:#7a5af8; }.platform-change-stats article.is-green::before { background:#067647; }.platform-change-stats article.is-orange::before { background:#f79009; }
.platform-change-stats span { color:#66758e;font-size:10px; }.platform-change-stats strong { color:#183153;font-size:20px; }.platform-change-stats em { color:#8a97aa;font-size:9px;font-style:normal; }
.platform-change-body { display:grid;grid-template-columns:minmax(0,1.25fr) minmax(270px,.75fr);min-height:210px; }
.platform-change-body>section { padding:13px 15px; }.platform-change-body>aside { padding:13px 14px;border-left:1px solid #e1eaf5;background:#f9fbfe; }
.platform-change-body header { display:flex;align-items:center;justify-content:space-between;margin-bottom:10px; }.platform-change-body header>strong { color:#344661;font-size:11px; }.platform-change-body header>span,.platform-change-body header>a { color:#8290a5;font-size:9px;text-decoration:none; }
.platform-change-ranking { display:grid;gap:8px; }.platform-change-ranking article { display:grid;grid-template-columns:minmax(150px,.8fr) minmax(170px,1fr);align-items:center;gap:12px; }
.platform-change-ranking article>span { display:grid;grid-template-columns:7px minmax(0,1fr);column-gap:8px; }.platform-change-ranking article>span>i { grid-row:1/3;width:7px;height:7px;margin-top:5px;border-radius:50%; }.platform-change-ranking article>span b { font-size:10px; }.platform-change-ranking article>span em { color:#8491a5;font-size:8px;font-style:normal; }
.platform-change-ranking article>div { display:grid;grid-template-columns:minmax(70px,1fr) 62px;align-items:center;gap:8px; }.platform-change-ranking article>div>i { height:6px;overflow:hidden;border-radius:99px;background:#eaf0f8; }.platform-change-ranking article>div>i b { display:block;height:100%;border-radius:inherit; }.platform-change-ranking article>div strong { color:#40536f;font-size:10px;text-align:right; }
.platform-change-body>aside article { display:grid;grid-template-columns:25px minmax(0,1fr);gap:9px;padding:9px 0;border-bottom:1px solid #e6edf6; }.platform-change-body>aside article:last-child { border-bottom:0; }
.platform-change-body>aside article>i { display:grid;place-items:center;width:23px;height:23px;border-radius:50%;background:#eaf2ff;color:#004ecc;font-size:10px;font-style:normal; }.platform-change-body>aside article>i.success { background:#dcfae6;color:#067647; }.platform-change-body>aside article>i.warning { background:#fef0c7;color:#b54708; }
.platform-change-body>aside article>span { display:grid;gap:3px; }.platform-change-body>aside article strong { color:#344661;font-size:10px; }.platform-change-body>aside article em { color:#7b899e;font-size:9px;font-style:normal; }

.platform-monitor-grid { display:grid;grid-template-columns:minmax(0,1fr) minmax(480px,1fr);gap:14px; }
.platform-trend-legend { display:flex!important;align-items:center;gap:10px!important; }.platform-trend-legend span { display:flex;align-items:center;gap:5px; }.platform-trend-legend i { width:7px;height:7px;border-radius:2px;background:#2e90fa; }.platform-trend-legend span:last-child i { background:#7a5af8; }
.platform-trend-chart { display:grid;grid-template-columns:repeat(7,1fr);align-items:end;height:225px;padding:20px 18px 13px;background:linear-gradient(to top,rgba(220,232,248,.7) 1px,transparent 1px);background-size:100% 25%; }
.platform-trend-chart article { display:grid;grid-template-rows:160px auto auto;justify-items:center;gap:4px;height:100%; }.platform-trend-chart article>div { display:flex;align-items:end;justify-content:center;gap:5px;width:100%;height:100%; }.platform-trend-chart article>div i { width:14px;min-height:8px;border-radius:4px 4px 1px 1px;background:linear-gradient(180deg,#2e90fa,#84caff); }.platform-trend-chart article>div i:last-child { background:linear-gradient(180deg,#7a5af8,#bdb4fe); }.platform-trend-chart article strong { color:#4e607a;font-size:9px; }.platform-trend-chart article span { color:#8290a5;font-size:9px; }
.platform-monitor-grid .platform-recent-tasks .platform-table th,.platform-monitor-grid .platform-recent-tasks .platform-table td { padding:9px 11px;font-size:10px; }.platform-monitor-grid .platform-recent-tasks td small { font-size:8px; }

.platform-service-graph .kg-panel__header span,
.platform-processing-flow .kg-panel__header span,
.platform-config .kg-panel__header span {
  color: var(--text-tertiary);
  font-size: 14px;
}

.platform-status {
  display: inline-flex;
  align-items: center;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  background: var(--primary-subtle);
  color: var(--primary);
  font-size: 13px;
  white-space: nowrap;
}

.platform-operations-grid { display:grid;grid-template-columns:minmax(0,1.7fr) minmax(320px,.8fr);gap:14px; }
.platform-recent-tasks,.platform-alert-overview { min-width:0;overflow:hidden; }
.platform-recent-tasks .kg-panel__header a,.platform-alert-overview .kg-panel__header a { color:#004ecc;font-size:12px;text-decoration:none; }
.platform-recent-tasks td small { display:block;margin-top:2px;color:#52627a;font-size:10px; }
.platform-status.is-阻断 { background:#fee4e2;color:#b42318; }
.platform-status.is-成功,.platform-status.is-完成,.platform-status.is-正常 { background:#dcfae6;color:#067647; }
.platform-status.is-运行中 { background:#eaf2ff;color:#004ecc; }
.platform-status.is-异常,.platform-status.is-告警 { background:#fef0c7;color:#b54708; }
.platform-status.is-更新中,.platform-status.is-排队 { background:#eaf2ff;color:#004ecc; }
.platform-alert-overview { display:grid;grid-template-rows:auto repeat(3,auto) 1fr; }
.platform-alert-overview>button { display:grid;grid-template-columns:8px minmax(0,1fr) 14px;align-items:start;gap:10px;padding:12px 14px;border:0;border-bottom:1px solid #e3ebf7;background:rgba(255,255,255,.64);text-align:left;cursor:pointer; }
.platform-alert-overview>button:hover { background:#f4f8ff; }
.platform-alert-overview>button>i { width:7px;height:7px;margin-top:5px;border-radius:50%;background:#f79009; }
.platform-alert-overview>button>i.is-严重 { background:#b42318;box-shadow:0 0 0 4px #fee4e2; }
.platform-alert-overview>button>span { display:grid;gap:3px;min-width:0; }
.platform-alert-overview>button b { color:#8a97aa;font-size:10px; }
.platform-alert-overview>button strong { overflow:hidden;color:#253752;font-size:12px;text-overflow:ellipsis;white-space:nowrap; }
.platform-alert-overview>button em { color:#52627a;font-size:10px;font-style:normal; }
.platform-alert-overview>button u { align-self:center;color:#8da0ba;font-size:20px;text-decoration:none; }
.platform-alert-overview__review { align-self:end;justify-self:center;margin:12px;color:#004ecc;font-size:12px;text-decoration:none; }

.platform-structure-overview { overflow:hidden; }
.platform-structure-overview>.kg-panel__header>span { color:#52627a;font-size:11px; }
.platform-structure-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr)); }
.platform-structure-chart { padding:15px 18px; }
.platform-structure-chart:first-child { border-right:1px solid #dce8f8; }
.platform-structure-chart header { display:flex;align-items:center;justify-content:space-between;margin-bottom:8px; }
.platform-structure-chart header>strong { color:#253752;font-size:13px; }
.platform-structure-chart header>a { color:#004ecc;font-size:11px;text-decoration:none; }
.platform-donut-layout { display:grid;grid-template-columns:170px minmax(0,1fr);align-items:center;gap:20px;min-height:150px; }
.platform-donut { position:relative;display:grid;place-items:center;width:154px;height:154px;border-radius:50%; }
.platform-donut::after { position:absolute;inset:25px;border-radius:50%;background:#fff;box-shadow:0 0 0 1px #e5edf8;content:""; }
.platform-donut.is-entity { background:conic-gradient(#2e90fa 0 34%,#7a5af8 34% 57%,#067647 57% 74%,#f79009 74% 85%,#59636f 85% 100%); }
.platform-donut.is-relation { background:conic-gradient(#004ecc 0 32%,#2e90fa 32% 52%,#06aed4 52% 70%,#7a5af8 70% 84%,#59636f 84% 100%); }
.platform-donut>span { position:relative;z-index:1;display:grid;gap:2px;text-align:center; }
.platform-donut>span strong { color:#10264c;font-size:19px; }
.platform-donut>span em { color:#52627a;font-size:10px;font-style:normal; }
.platform-structure-legend article { display:grid;grid-template-columns:minmax(0,1fr) 160px;align-items:center;gap:14px;min-height:34px;border-bottom:1px solid #edf2f8; }
.platform-structure-legend article:last-child { border-bottom:0; }
.platform-structure-legend article>span { display:flex;align-items:center;gap:7px;min-width:0;overflow:hidden;color:#40516c;font-size:11px;white-space:nowrap; }
.platform-structure-legend article>span>i { flex:0 0 auto;width:8px;height:8px;border-radius:50%; }
.platform-structure-legend article em { overflow:hidden;color:#59636f;font-size:9px;font-style:normal;text-overflow:ellipsis;white-space:nowrap; }
.platform-structure-legend article>strong { display:grid;grid-template-columns:minmax(82px,1fr) 44px;align-items:center;gap:12px;color:#40516c;font-size:11px;text-align:right;white-space:nowrap; }
.platform-structure-legend article>strong em { overflow:visible;text-overflow:clip; }

.platform-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: auto;
}

.platform-table th,
.platform-table td {
  height: 36px;
  min-width: 110px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 20px;
  text-align: left;
  overflow-wrap: anywhere;
}

.platform-table th {
  background: linear-gradient(180deg, #eef5ff, #f8fbff);
  color: var(--text-secondary);
  font-weight: 600;
}

.platform-table td {
  background: rgba(255, 255, 255, 0.54);
}

.platform-table tbody tr {
  transition: background 0.16s ease;
}

.platform-table tbody tr:hover {
  background: #f8fbff;
}

.platform-table tbody tr.platform-task-row--active td {
  background: #eef5ff;
}

.platform-icon-action {
  height: 28px;
  padding: 0 8px;
  border: 1px solid #bdd7ff;
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--primary);
  font-size: 13px;
  cursor: pointer;
}

.platform-icon-action:hover {
  background: var(--primary-subtle);
}

.platform-build-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  padding: 12px 14px;
  border-top: 1px solid var(--border);
  background:
    linear-gradient(90deg, rgba(22, 93, 255, 0.06), rgba(20, 184, 166, 0.04)),
    #fbfdff;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 18px;
}

.platform-processing {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 380px;
  grid-template-rows: auto auto minmax(520px, 1fr);
  gap: 16px;
  padding: 14px;
  border: 1px solid rgba(191, 215, 250, 0.96);
  border-radius: 12px;
  background:
    linear-gradient(180deg, rgba(245, 250, 255, 0.98), rgba(232, 242, 255, 0.86)),
    #eef5ff;
  box-shadow:
    0 14px 30px rgba(48, 105, 194, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.92);
  align-content: start;
}

.platform-cleaning-input {
  grid-column: 1 / -1;
}

.platform-source-panel {
  grid-column: 1 / -1;
  display: flex;
  flex-direction: column;
  height: 500px;
  min-height: 500px;
  overflow: hidden;
}

.platform-processing-overview {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}

.platform-processing-overview article {
  position: relative;
  overflow: hidden;
  min-height: 118px;
  padding: 18px 20px;
  border: 1px solid #bdd7ff;
  border-radius: 10px;
  background:
    linear-gradient(135deg, rgba(22, 93, 255, 0.1), rgba(20, 184, 166, 0.05)),
    rgba(255, 255, 255, 0.92);
  box-shadow: 0 10px 22px rgba(48, 105, 194, 0.08);
}

.platform-processing-overview article::after {
  position: absolute;
  right: -20px;
  bottom: -26px;
  width: 96px;
  height: 96px;
  border-radius: 50%;
  background: rgba(22, 93, 255, 0.08);
  content: "";
}

.platform-processing-overview span {
  display: inline-flex;
  margin-bottom: 10px;
  padding: 2px 9px;
  border-radius: 999px;
  background: #eef5ff;
  color: var(--primary);
  font-size: 14px;
}

.platform-processing-overview strong {
  display: block;
  color: #10264c;
  font-size: 22px;
  line-height: 30px;
}

.platform-processing-overview p {
  max-width: 94%;
  margin: 8px 0 0;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 24px;
}

.platform-cleaning-editor {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 280px;
  gap: 14px;
  padding: 16px;
}

.platform-cleaning-editor textarea {
  width: 100%;
  min-height: 172px;
  resize: vertical;
  padding: 14px 16px;
  border: 1px solid var(--border-strong);
  border-radius: 8px;
  background: #fff;
  color: var(--text-primary);
  font-family: inherit;
  font-size: 16px;
  line-height: 28px;
}

.platform-cleaning-options {
  display: grid;
  gap: 12px;
  align-content: start;
}

.platform-cleaning-options label {
  display: grid;
  gap: 6px;
}

.platform-cleaning-options span {
  color: var(--text-secondary);
  font-size: 14px;
}

.platform-cleaning-options input,
.platform-cleaning-options select {
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
  font-size: 14px;
}

.platform-processing-controls {
  display: flex;
  flex-wrap: wrap;
  align-items: end;
  gap: 10px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  background: rgba(248, 251, 255, 0.72);
}

.platform-quality-log {
  grid-column: 1 / -1;
  overflow: auto;
}

.platform-trace-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--primary);
  font: inherit;
  text-decoration: none;
  cursor: pointer;
}

.platform-table tr.is-clickable { cursor: pointer; }
.platform-table tr.is-clickable:hover td { background: #f0f6ff; }
.platform-table tr.is-clickable:focus-visible { outline: 2px solid #004ecc; outline-offset: -2px; }
.is-clickable-card { color: inherit; font: inherit; text-align: left; cursor: pointer; transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease; }
.is-clickable-card:hover,.is-clickable-card:focus-visible { border-color: #7aa9ee!important; box-shadow: 0 8px 20px rgba(22,93,255,.12)!important; transform: translateY(-1px); outline: none; }
.platform-card-arrow { color: #004ecc!important; font-size: 11px!important; font-weight: 600!important; white-space: nowrap; }
.platform-cleaning-steps .platform-card-arrow,.platform-build-pipeline__body .platform-card-arrow { grid-column: 2; justify-self: end; }
.platform-build-stats .platform-card-arrow { justify-self: end; }

.platform-task-filters {
  display: inline-flex;
  align-items: center;
  gap: 10px;
}

.platform-task-filters select {
  height: 30px;
  padding: 0 9px;
  border: 1px solid #bdd7ff;
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
}
.platform-task-filters a { color:#004ecc;font-size:11px;text-decoration:none;white-space:nowrap; }

.platform-review-notice {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  min-height: 86px;
  padding: 15px 18px;
  border: 1px solid #b2ccff;
  border-radius: 9px;
  background: linear-gradient(90deg, #eff4ff, #f8fbff);
  box-shadow: 0 8px 20px rgba(48, 105, 194, .08);
}

.platform-review-notice.is-warning {
  border-color: #fedf89;
  background: linear-gradient(90deg, #fffaeb, #fffdf7);
}

.platform-review-notice__icon {
  display: inline-grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  background: #004ecc;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
}

.platform-review-notice.is-warning .platform-review-notice__icon { background: #f79009; }
.platform-review-notice strong { color: #10264c; font-size: 15px; }
.platform-review-notice p { margin: 5px 0 0; color: var(--text-secondary); font-size: 13px; line-height: 20px; }
.platform-review-notice__actions { display: flex; align-items: center; gap: 8px; }
.platform-review-notice__actions button,.platform-review-notice__actions a { display: inline-flex; align-items: center; height: 34px; padding: 0 13px; border: 1px solid #004ecc; border-radius: 6px; background: #fff; color: #004ecc; font-size: 12px; font-weight: 600; text-decoration: none; white-space: nowrap; cursor: pointer; }
.platform-review-notice__actions a { background: #004ecc; color: #fff; }
.platform-review-notice.is-warning .platform-review-notice__actions button { border-color: #93370d; color: #b54708; }
.platform-review-notice.is-warning .platform-review-notice__actions a { border-color: #93370d; background: #93370d; }

.platform-processing-controls label {
  display: grid;
  flex: 1 1 190px;
  gap: 5px;
  min-width: 0;
}

.platform-processing-controls .platform-range-fields { flex-basis:300px; }
.platform-processing-controls>.kg-button { flex:0 0 auto; }

.platform-processing-controls span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-processing-controls select,
.platform-processing-controls input {
  width: 100%;
  height: 32px;
  padding: 0 9px;
  border: 1px solid #bdd7ff;
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
  font-size: 13px;
}

.platform-range-fields>i { display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:6px;font-style:normal; }
.platform-range-fields>i b { color:#52627a;font-size:10px;font-weight:400; }

.platform-update-help { display:flex;flex-wrap:wrap;gap:8px 20px;padding:9px 14px;border-bottom:1px solid #dce8f8;background:#f8fbff;color:#65738b;font-size:10px;line-height:17px; }
.platform-update-help b { color:#344766; }
.platform-sticky-table { flex:1 1 auto;min-height:0;overflow:auto; }
.platform-sticky-table .platform-table th { position:sticky;z-index:2;top:0; }
.platform-sticky-table code { color:#40516c;font:11px Consolas,monospace; }

.platform-cleaning-flow {
  grid-column: 1 / -1;
}

.platform-cleaning-steps {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 18px;
  padding: 16px;
}

.platform-cleaning-steps button {
  position: relative;
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr);
  grid-template-rows: auto auto;
  gap: 8px 12px;
  align-items: start;
  min-height: 118px;
  padding: 14px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: linear-gradient(145deg, #fff, #f6fbff);
}

.platform-cleaning-steps button:not(:last-child)::after {
  position: absolute;
  top: 50%;
  right: -17px;
  width: 16px;
  height: 2px;
  background: #9cc3ff;
  content: "";
}

.platform-cleaning-steps button:not(:last-child)::before {
  position: absolute;
  top: calc(50% - 4px);
  right: -18px;
  width: 0;
  height: 0;
  border-top: 5px solid transparent;
  border-bottom: 5px solid transparent;
  border-left: 7px solid #9cc3ff;
  content: "";
}

.platform-cleaning-steps i {
  display: inline-grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 15px;
  font-style: normal;
  font-weight: 700;
  box-shadow: 0 0 0 5px rgba(22, 93, 255, 0.12);
}

.platform-cleaning-steps strong {
  font-size: 17px;
  line-height: 24px;
}

.platform-cleaning-steps p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 22px;
}

.platform-cleaning-steps span {
  grid-column: 2;
  justify-self: start;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef5ff;
  color: var(--primary);
  font-size: 13px;
  white-space: nowrap;
}

.platform-cleaning-result {
  grid-column: 1;
  min-height: 0;
  overflow: auto;
}

.platform-cleaning-relations {
  grid-column: 2;
  min-height: 0;
}

.platform-cleaning-relation-list {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.platform-cleaning-relation-list article {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #e2ebf8;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-cleaning-relation-list article div {
  display: grid;
  gap: 4px;
}

.platform-cleaning-relation-list strong {
  color: var(--text-primary);
  font-size: 15px;
  line-height: 22px;
}

.platform-cleaning-relation-list span {
  color: var(--primary);
  font-size: 13px;
  line-height: 20px;
}

.platform-cleaning-relation-list em {
  color: var(--text-secondary);
  font-size: 13px;
  font-style: normal;
}

.platform-task-list {
  min-height: 0;
  overflow: auto;
}

.platform-processing > .platform-task-list {
  grid-column: 1 / -1;
  min-height: 520px;
}

.platform-processing > .platform-task-list .platform-table th,
.platform-processing > .platform-task-list .platform-table td {
  height: 56px;
  padding: 13px 18px;
  font-size: 16px;
  line-height: 24px;
}

.platform-processing > .platform-task-list .platform-table th {
  font-size: 15px;
}

.platform-processing > .platform-task-list .platform-status {
  min-height: 26px;
  padding: 0 11px;
  font-size: 15px;
}

.platform-review {
  display: grid;
  grid-template-rows: auto 1fr;
  align-content: start;
}

.platform-config {
  grid-column: 1 / -1;
}

.platform-discovery {
  grid-column: 1 / -1;
}

.platform-gates {
  grid-column: 1 / -1;
}

.platform-form-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(130px, 1fr));
  gap: 10px;
  padding: 12px 14px;
}

.platform-form-grid label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.platform-form-grid span {
  color: var(--text-secondary);
  font-size: 14px;
}

.platform-form-grid input,
.platform-form-grid select,
.platform-form-grid textarea {
  width: 100%;
  height: 32px;
  min-width: 0;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--text-primary);
  font-size: 14px;
}

.platform-form-grid textarea { height:58px;padding:8px 10px;line-height:20px;resize:vertical; }

.platform-timeline {
  display: grid;
  gap: 10px;
  padding: 14px;
  align-content: start;
}

.platform-timeline article {
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid #e2ebf8;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-timeline i {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: var(--primary);
  box-shadow: 0 0 0 5px rgba(22, 93, 255, 0.12);
}

.platform-timeline strong,
.platform-timeline p {
  margin: 0;
}

.platform-timeline strong {
  font-size: 14px;
}

.platform-timeline p {
  color: var(--text-secondary);
  font-size: 13px;
}

.platform-timeline span {
  color: var(--primary);
  font-weight: 600;
}

.platform-modal-mask {
  position: fixed;
  inset: 0;
  z-index: 40;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(16, 38, 76, 0.28);
}

.platform-trace-modal {
  width: min(760px, 100%);
  max-height: min(720px, calc(100vh - 48px));
  display: grid;
  grid-template-rows: auto 1fr;
  overflow: hidden;
}

.platform-modal-close {
  height: 28px;
  padding: 0 10px;
  border: 1px solid #bdd7ff;
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--primary);
  cursor: pointer;
}

.platform-review__body {
  display: grid;
  gap: 12px;
  padding: 14px;
  align-content: start;
}

.platform-review article {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #e8edf6;
  border-radius: var(--radius-lg);
  background: #fbfdff;
}

.platform-review__item {
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.platform-review__item:hover,
.platform-review__item:focus-visible {
  outline: 0;
  border-color: #bdd7ff;
  background: #f3f8ff;
}

.platform-review strong,
.platform-review p {
  margin: 0;
}

.platform-review p {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-review div div {
  display: flex;
  gap: 8px;
}

.platform-review button {
  height: 28px;
  padding: 0 10px;
  border: 1px solid #bdd7ff;
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--primary);
  cursor: pointer;
}

.platform-discovery__grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  padding: 14px;
}

.platform-discovery__grid article {
  display: grid;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #e2ebf8;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-discovery__grid article div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.platform-discovery__grid span {
  color: var(--text-secondary);
  font-size: 13px;
}

.platform-discovery__grid strong {
  color: var(--primary);
  font-size: 20px;
  line-height: 24px;
}

.platform-discovery__grid p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-gates__grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  padding: 12px 14px;
}

.platform-gates__grid article {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid #dfeafe;
  border-radius: 8px;
  background: linear-gradient(135deg, #f8fbff, #fff);
}

.platform-gates__grid span {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-gates__grid strong {
  color: var(--primary);
  font-size: 24px;
  line-height: 28px;
}

.platform-gates__grid p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-overview-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}

.platform-schema-list,
.platform-relation-list {
  display: grid;
  gap: 12px;
  padding: 20px;
}

.platform-schema-list article,
.platform-relation-list article {
  display: grid;
  grid-template-columns: 14px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  min-height: 56px;
  padding: 12px 14px;
  border: 1px solid #e2ebf8;
  border-radius: 6px;
  background: #fbfdff;
}

.platform-relation-list article {
  grid-template-columns: minmax(0, 1fr) auto;
}

.platform-schema-list i {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: #4080ff;
  box-shadow: 0 0 0 4px rgba(64, 128, 255, 0.1);
}

.platform-schema-list article.is-expert i { background: #1e8ff3; box-shadow: 0 0 0 4px rgba(30, 143, 243, 0.1); }
.platform-schema-list article.is-org i { background: #48c914; box-shadow: 0 0 0 4px rgba(72, 201, 20, 0.1); }
.platform-schema-list article.is-paper i { background: #762bd7; box-shadow: 0 0 0 4px rgba(118, 43, 215, 0.1); }
.platform-schema-list article.is-project i { background: #ffad17; box-shadow: 0 0 0 4px rgba(255, 173, 23, 0.13); }
.platform-schema-list article.is-event i { background: #eb2aa3; box-shadow: 0 0 0 4px rgba(235, 42, 163, 0.1); }
.platform-schema-list article.is-chain i { background: #14b8a6; box-shadow: 0 0 0 4px rgba(20, 184, 166, 0.11); }
.platform-schema-list article.is-field i { background: #2f6bff; box-shadow: 0 0 0 4px rgba(47, 107, 255, 0.1); }

.platform-schema-list div,
.platform-relation-list div {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.platform-schema-list strong,
.platform-relation-list strong {
  overflow: hidden;
  font-size: 17px;
  line-height: 25px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-schema-list span,
.platform-relation-list span {
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 14px;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-schema-list em,
.platform-relation-list em {
  color: var(--text-secondary);
  font-size: 15px;
  font-style: normal;
  white-space: nowrap;
}

.platform-schema-list b,
.platform-relation-list b {
  grid-column: 2 / -1;
  height: 7px;
  overflow: hidden;
  border-radius: 999px;
  background: #e8f1ff;
}

.platform-relation-list b {
  grid-column: 1 / -1;
}

.platform-schema-list b span,
.platform-relation-list b span {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(180deg, #14b8a6, #004ecc);
}

.platform-construction {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  grid-template-rows: auto auto minmax(620px, 1fr);
  gap: 14px;
  min-height: 0;
  align-items: stretch;
}

.platform-build-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.platform-build-stats button {
  display: grid;
  gap: 5px;
  padding: 15px 17px;
  border: 1px solid #bdd7ff;
  border-radius: 9px;
  background: linear-gradient(145deg, #fff, #f2f8ff);
  box-shadow: 0 8px 20px rgba(48, 105, 194, .08);
}

.platform-build-stats span { color: var(--text-secondary); font-size: 13px; }
.platform-build-stats strong { color: #10264c; font-size: 24px; line-height: 31px; }
.platform-build-stats em { color: var(--text-tertiary); font-size: 12px; font-style: normal; }
.platform-schema-readonly { grid-column: 1 / -1; overflow: auto; }
.platform-schema-readonly code { padding: 2px 7px; border-radius: 4px; background: #eef5ff; color: var(--primary); }
.platform-schema-head{display:flex;align-items:center;gap:14px}.platform-schema-head a{color:var(--primary);font-size:12px;text-decoration:none;white-space:nowrap}

.platform-build-results {
  grid-column: 1 / -1;
}

.platform-build-progress {
  grid-column: 1 / -1;
  min-height: 210px;
  overflow: auto;
}

.platform-build-progress--list .platform-table tr {
  cursor: pointer;
}

.platform-build-progress--list .platform-table tr.is-active td {
  background: #eef5ff;
}

.platform-progress-cell {
  display: grid;
  grid-template-columns: minmax(80px, 1fr) auto;
  align-items: center;
  gap: 8px;
  min-width: 140px;
}

.platform-progress-cell b {
  overflow: hidden;
  height: 8px;
  border-radius: 999px;
  background: #dce9ff;
}

.platform-progress-cell i {
  display: block;
  height: 100%;
  border-radius: inherit;
  background: linear-gradient(90deg, #004ecc, #22d3ee);
}

.platform-progress-cell span {
  color: var(--primary);
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
}

.platform-build-results__body,
.platform-audit-reasons {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  padding: 12px;
}

.platform-build-results__body {
  padding-bottom: 6px;
}

.platform-audit-reasons {
  padding-top: 6px;
}

.platform-build-results__body article,
.platform-audit-reasons article {
  position: relative;
  overflow: hidden;
  min-height: 76px;
  padding: 12px 14px;
  border: 1px solid #dce9ff;
  border-radius: 9px;
  background: linear-gradient(145deg, rgba(255,255,255,0.96), rgba(240,247,255,0.9));
}

.platform-build-results__body article::after {
  position: absolute;
  right: -18px;
  bottom: -18px;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: rgba(22, 93, 255, 0.1);
  content: "";
}

.platform-build-results__body article.is-success::after {
  background: rgba(22, 163, 74, 0.12);
}

.platform-build-results__body article.is-warning::after {
  background: rgba(245, 158, 11, 0.16);
}

.platform-build-results__body span,
.platform-audit-reasons span {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-build-results__body strong,
.platform-audit-reasons strong {
  display: block;
  margin-top: 4px;
  color: var(--primary);
  font-size: 20px;
  line-height: 28px;
}

.platform-audit-reasons strong {
  color: var(--warning);
}

.platform-build-results__body p,
.platform-audit-reasons p {
  margin: 6px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 18px;
}

.platform-construction-kpis {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.platform-construction-kpis article {
  min-height: 88px;
  padding: 15px 16px;
  border: 1px solid #bdd7ff;
  border-radius: 10px;
  background:
    linear-gradient(135deg, rgba(255,255,255,0.96), rgba(238,247,255,0.9));
  box-shadow: 0 10px 22px rgba(48, 105, 194, 0.08);
}

.platform-construction-kpis span {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-construction-kpis strong {
  display: block;
  margin-top: 6px;
  color: var(--primary);
  font-size: 26px;
  line-height: 34px;
}

.platform-construction-kpis p {
  margin: 6px 0 0;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 18px;
}

.platform-build-pipeline {
  grid-column: 1 / -1;
}

.platform-build-pipeline__body {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 14px;
  padding: 14px;
}

.platform-build-pipeline__body button {
  position: relative;
  display: grid;
  grid-template-columns: 30px minmax(0, 1fr);
  gap: 8px;
  min-height: 108px;
  padding: 13px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 249, 255, 0.9));
}

.platform-build-pipeline__body button:not(:last-child)::after {
  position: absolute;
  top: 50%;
  right: -15px;
  width: 14px;
  height: 2px;
  background: #9cc3ff;
  content: "";
}

.platform-build-pipeline__body i {
  display: inline-grid;
  place-items: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--primary);
  color: #fff;
  font-size: 12px;
  font-style: normal;
  font-weight: 700;
}

.platform-build-pipeline__body span,
.platform-schema-mapping__body span {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-build-pipeline__body strong {
  display: block;
  margin-top: 4px;
  color: var(--primary);
  font-size: 19px;
  line-height: 26px;
}

.platform-build-pipeline__body em {
  grid-column: 2;
  justify-self: start;
  padding: 2px 8px;
  border-radius: 999px;
  background: #eef5ff;
  color: var(--primary);
  font-size: 12px;
  font-style: normal;
}

.platform-build-pipeline__body p,
.platform-schema-mapping__body p {
  margin: 6px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-schema-mapping {
  min-height: 0;
}

.platform-schema-mapping__body {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.platform-schema-mapping__body article {
  padding: 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-schema-mapping__body strong {
  display: block;
  margin-top: 6px;
  color: #10264c;
  font-size: 18px;
  line-height: 26px;
}

.platform-batch-list,
.platform-build-rules__body {
  display: grid;
  gap: 10px;
  padding: 12px;
}

.platform-batch-list article,
.platform-build-rules__body article {
  display: grid;
  gap: 8px;
  padding: 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-batch-list article.is-active {
  border-color: #84b2f6;
  background: #eef5ff;
}

.platform-batch-list article > button:first-child {
  justify-self: start;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
}

.platform-batch-list article > span,
.platform-build-rules__body span {
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-batch-list dl {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  margin: 0;
}

.platform-batch-list dl div {
  display: grid;
  gap: 2px;
}

.platform-batch-list dt,
.platform-batch-list dd {
  margin: 0;
  font-size: 12px;
}

.platform-batch-list dt {
  color: var(--text-tertiary);
}

.platform-batch-list dd {
  color: var(--text-primary);
  font-weight: 600;
}

.platform-batch-list__next {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-build-rules__body strong {
  color: #10264c;
  font-size: 17px;
  line-height: 24px;
}

.platform-build-rules__body p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-build,
.platform-graph-summary {
  min-height: 0;
  height: 100%;
}

.platform-build {
  grid-column: 1;
  grid-row: 3;
  min-height: 620px;
  display: flex;
  flex-direction: column;
  overflow: auto;
}

.platform-graph-summary {
  display: grid;
  align-content: start;
  gap: 12px;
  padding-bottom: 14px;
}

.platform-graph-summary__hint {
  margin: -4px 14px 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-build-footer {
  margin-top: auto;
}

.platform-segmented {
  display: inline-flex;
  gap: 4px;
  padding: 3px;
  border: 1px solid rgba(125, 211, 252, 0.42);
  border-radius: 999px;
  background: rgba(232, 241, 255, 0.92);
}

.platform-segmented button {
  height: 28px;
  padding: 0 14px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-secondary);
  cursor: pointer;
}

.platform-segmented button.is-active {
  background: linear-gradient(135deg, #004ecc, #22d3ee);
  color: #fff;
  box-shadow: 0 6px 16px rgba(22, 93, 255, 0.26);
}

.platform-manual-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(180deg, rgba(248,251,255,0.92), rgba(240,247,255,0.8));
}

.platform-manual-toolbar button {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  height: 32px;
  padding: 0 14px;
  border: 1px solid #bdd7ff;
  border-radius: 999px;
  background: #fff;
  color: var(--primary);
  font-size: 13px;
  line-height: 1;
  cursor: pointer;
}

.platform-manual-toolbar button:first-child {
  border-color: transparent;
  background: linear-gradient(135deg, #004ecc, #0ea5e9);
  color: #fff;
  box-shadow: 0 8px 18px rgba(22, 93, 255, 0.22);
}

.platform-manual-toolbar span {
  min-width: 0;
  margin-left: 6px;
  overflow: hidden;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-manage-filter {
  display: grid;
  grid-template-columns: minmax(260px, 1.4fr) minmax(160px, 0.8fr) minmax(160px, 0.8fr) minmax(200px, 1fr) 92px;
  align-items: end;
  gap: 10px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: rgba(248, 251, 255, 0.72);
}

.platform-manage-filter label {
  display: grid;
  gap: 5px;
  min-width: 0;
}

.platform-manage-filter span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-manage-filter input,
.platform-manage-filter select {
  width: 100%;
  height: 30px;
  min-width: 0;
  padding: 0 9px;
  border: 1px solid #bdd7ff;
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
  font-size: 13px;
}

.platform-manage-filter button {
  height: 30px;
  padding: 0 16px;
  border: 0;
  border-radius: 6px;
  background: var(--primary);
  color: #fff;
  font-size: 13px;
  cursor: pointer;
}

.platform-build-context {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 14px 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-build-context strong {
  color: var(--text-primary);
  font-size: 14px;
}

.platform-row-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.platform-row-actions button {
  height: 24px;
  padding: 0 8px;
  border: 1px solid #bdd7ff;
  border-radius: 5px;
  background: #fff;
  color: var(--primary);
  font-size: 12px;
  line-height: 22px;
  cursor: pointer;
}

.platform-row-actions button:last-child {
  border-color: #ffd6d6;
  color: #b42318;
  background: #fffafa;
}

.platform-impact {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 14px;
  padding-bottom: 0;
}

.platform-impact div {
  position: relative;
  overflow: hidden;
  display: grid;
  gap: 6px;
  min-height: 74px;
  padding: 10px 12px;
  border: 1px solid rgba(191, 219, 254, 0.9);
  border-radius: 8px;
  background: linear-gradient(145deg, rgba(255,255,255,0.92), rgba(236,246,255,0.88));
}

.platform-impact div::after {
  position: absolute;
  right: -14px;
  bottom: -20px;
  width: 58px;
  height: 58px;
  border-radius: 50%;
  background: rgba(22, 93, 255, 0.08);
  content: "";
}

.platform-impact span {
  color: var(--text-secondary);
  font-size: 13px;
}

.platform-impact strong {
  font-size: 24px;
  color: var(--primary);
}

.platform-rule-note {
  margin: 0 14px;
  padding: 12px;
  border: 1px solid #ffe0b2;
  border-radius: 8px;
  background: linear-gradient(135deg, #fff8ed, #fffdf8);
}

.platform-rule-note p {
  margin: 8px 0 0;
  color: #7a4a00;
  font-size: 13px;
  line-height: 20px;
}

.platform-rule-note--manual {
  border-color: #cce5d8;
  background: linear-gradient(135deg, #edfff7, #f8fffb);
}

.platform-rule-note--manual p {
  color: #12643b;
}

.platform-governance-flow {
  margin: 0 14px;
  padding: 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(255,255,255,0.94), rgba(247,251,255,0.88));
}

.platform-governance-flow > strong {
  display: block;
  margin-bottom: 10px;
  color: var(--text-primary);
  font-size: 14px;
}

.platform-governance-flow ol {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.platform-governance-flow li {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 8px;
  align-items: start;
}

.platform-governance-flow li span {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: #e8f1ff;
  color: var(--primary);
  font-size: 11px;
  font-weight: 600;
}

.platform-governance-flow li p {
  margin: 2px 0 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-query,
.platform-service {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  grid-template-rows: auto auto minmax(0, 1fr);
  gap: 12px;
}

.platform-service {
  grid-template-columns: minmax(0, 1fr) 360px;
  grid-template-rows: auto minmax(0, 1fr);
  align-items: stretch;
}

.platform-service--api {
  grid-template-columns: minmax(0, 1fr);
}

.platform-query-form,
.platform-service-console {
  grid-column: 1 / -1;
}

.platform-query {
  /* flex 纵向布局：表单按内容撑开，不被父网格行拉伸/挤压，超出部分
     由上层 .app-workspace（overflow:auto）滚动 */
  display: flex;
  flex-direction: column;
  gap: 16px;
  align-self: start;
  min-height: max-content;
  overflow: visible;
}

.platform-query > * {
  flex-shrink: 0;
}
.platform-service-run,
.platform-service-debug,
.platform-api-doc {
  min-height: 0;
}

.platform-service-console {
  overflow: hidden;
}

.platform-service-console__top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 42px;
  padding: 0 16px;
  border-bottom: 1px solid rgba(191, 215, 250, 0.96);
  background:
    linear-gradient(90deg, rgba(22, 93, 255, 0.08), transparent 48%),
    rgba(248, 252, 255, 0.9);
}

.platform-service-tabs {
  display: inline-flex;
  align-items: center;
  gap: 18px;
}

.platform-service-tabs button {
  position: relative;
  height: 42px;
  border: 0;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.platform-service-tabs button.is-active {
  color: var(--primary);
  font-weight: 600;
}

.platform-service-tabs button.is-active::after {
  position: absolute;
  right: 0;
  bottom: 0;
  left: 0;
  height: 2px;
  border-radius: 999px;
  background: var(--primary);
  content: "";
}

.platform-service-console__body {
  display: grid;
  grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(170px, 0.8fr)) auto;
  align-items: end;
  gap: 12px;
  padding: 12px 16px 14px;
}

.platform-service--api .platform-service-console__body {
  grid-template-columns: minmax(260px, 0.9fr) minmax(360px, 1.4fr) 140px auto;
}

.platform-service-console__body label {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.platform-service-console__body label span {
  color: var(--text-secondary);
  font-size: 12px;
}

.platform-service-console__body input,
.platform-service-console__body select {
  width: 100%;
  height: 32px;
  min-width: 0;
  padding: 0 10px;
  border: 1px solid #bdd7ff;
  border-radius: 6px;
  background: #fff;
  color: var(--text-primary);
  font-size: 13px;
}

.platform-service-console__actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
}

.platform-service-console__actions button {
  height: 32px;
  padding: 0 14px;
  border: 1px solid #bdd7ff;
  border-radius: 6px;
  background: #fff;
  color: var(--primary);
  font-size: 13px;
  cursor: pointer;
}

.platform-service-console__actions button:last-child {
  border-color: transparent;
  background: linear-gradient(135deg, #004ecc, #0ea5e9);
  color: #fff;
  box-shadow: 0 8px 18px rgba(22, 93, 255, 0.2);
}

.platform-svg {
  width: 100%;
  height: calc(100% - 45px);
  min-height: 340px;
  display: block;
  background:
    linear-gradient(#e8f1ff 1px, transparent 1px),
    linear-gradient(90deg, #e8f1ff 1px, transparent 1px),
    linear-gradient(135deg, rgba(22, 93, 255, 0.06), rgba(20, 184, 166, 0.04)),
    #fbfdff;
  background-size: 28px 28px, 28px 28px, auto, auto;
}

.platform-service-run {
  overflow: auto;
}

.platform-service-run__body,
.platform-service-debug__body {
  display: grid;
  gap: 12px;
  padding: 14px;
}

.platform-service-summary {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}

.platform-service-summary div {
  display: grid;
  gap: 6px;
  min-height: 72px;
  padding: 10px 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 249, 255, 0.92));
}

.platform-service-summary span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-service-summary strong {
  color: var(--text-primary);
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 14px;
  line-height: 20px;
}

.platform-service-request {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-service-request strong,
.platform-service-payload strong,
.platform-service-log strong {
  color: var(--text-primary);
  font-size: 13px;
}

.platform-service-request dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.platform-service-request dl div {
  display: grid;
  grid-template-columns: 160px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 8px 0;
  border-bottom: 1px solid #eef3fb;
}

.platform-service-request dl div:last-child {
  border-bottom: 0;
}

.platform-service-request dt,
.platform-service-request dd {
  margin: 0;
  min-width: 0;
  font-size: 12px;
  line-height: 18px;
}

.platform-service-request dt {
  color: var(--text-secondary);
}

.platform-service-request dd {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  color: var(--text-primary);
}

.platform-service-request dd em {
  padding: 1px 6px;
  border-radius: 999px;
  background: #eef5ff;
  color: var(--primary);
  font-size: 11px;
  font-style: normal;
  line-height: 18px;
}
.platform-evidence ul {
  display: grid;
  gap: 8px;
  margin: 0;
  padding-left: 18px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.platform-result-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  padding: 14px;
}

.platform-result-grid div {
  display: grid;
  gap: 6px;
  min-height: 68px;
  padding: 10px 12px;
  border: 1px solid #e2ebf8;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-result-grid span {
  color: var(--text-secondary);
  font-size: 13px;
}

.platform-result-grid strong {
  color: var(--primary);
  font-size: 22px;
}

.platform-evidence {
  display: grid;
  gap: 8px;
  margin: 0 14px 14px;
  padding: 12px;
  border: 1px solid #e2ebf8;
  border-radius: 8px;
  background: #fff;
}

.platform-evidence strong {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.platform-service-info {
  display: grid;
  gap: 8px;
  margin: 0 14px 14px;
  padding: 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #f8fbff;
}

.platform-service-info strong {
  color: var(--text-primary);
  font-size: 13px;
}

.platform-service-info dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.platform-service-info dl div {
  display: grid;
  grid-template-columns: 108px minmax(0, 1fr);
  gap: 10px;
  padding: 8px 0;
  border-bottom: 1px solid #e2ebf8;
}

.platform-service-info dl div:last-child {
  border-bottom: 0;
}

.platform-service-info dt,
.platform-service-info dd {
  margin: 0;
  min-width: 0;
  font-size: 12px;
  line-height: 18px;
  overflow-wrap: anywhere;
}

.platform-service-info dt {
  color: var(--primary);
  font-family: "SFMono-Regular", Consolas, monospace;
}

.platform-service-info dd {
  color: var(--text-secondary);
}

.platform-service-debug {
  overflow: auto;
}

.platform-service-payload {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-service-payload pre {
  min-height: 140px;
  max-height: 220px;
  margin: 0;
  padding: 12px 14px;
  overflow: auto;
  color: #344054;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  line-height: 20px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  border-radius: 6px;
  background: #f3f8ff;
}

.platform-service-log {
  display: grid;
  gap: 10px;
  padding: 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-service-log ul {
  display: grid;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.platform-service-log li {
  display: grid;
  grid-template-columns: 56px 56px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
  padding: 10px 0;
  border-bottom: 1px solid #eef3fb;
}

.platform-service-log li:last-child {
  border-bottom: 0;
  padding-bottom: 0;
}

.platform-service-log span,
.platform-service-log b,
.platform-service-log p {
  margin: 0;
  font-size: 12px;
  line-height: 18px;
}

.platform-service-log span {
  color: var(--text-tertiary);
  font-family: "SFMono-Regular", Consolas, monospace;
}

.platform-service-log b {
  color: #00a870;
}

.platform-service-log p {
  color: var(--text-secondary);
}

.platform-api-doc {
  overflow: hidden;
}

.platform-service--api .platform-api-doc {
  grid-column: 1 / -1;
  overflow: auto;
}

.platform-api-doc .kg-panel__header span {
  min-width: 0;
  overflow: hidden;
  color: var(--text-tertiary);
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.platform-api-doc__grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 14px;
}

.platform-api-doc__grid .platform-table {
  table-layout: auto;
}

.platform-api-doc__grid .platform-table th,
.platform-api-doc__grid .platform-table td {
  height: auto;
  min-height: 38px;
  vertical-align: top;
  white-space: normal;
}

.platform-api-doc__grid article {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.72);
}

.platform-api-doc__grid h3 {
  margin: 0;
  padding: 10px 12px;
  border-bottom: 1px solid #e2ebf8;
  color: var(--text-primary);
  font-size: 14px;
  line-height: 20px;
}

.platform-code-sample {
  margin: 0 14px 14px;
  overflow: hidden;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-api-examples {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  padding: 0 14px 14px;
}

.platform-api-examples article {
  min-width: 0;
  overflow: hidden;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #fbfdff;
}

.platform-api-examples h3 {
  margin: 0;
  padding: 10px 12px;
  border-bottom: 1px solid #e2ebf8;
  color: var(--text-primary);
  font-size: 14px;
}

.platform-api-examples pre {
  min-height: 180px;
  max-height: 260px;
  margin: 0;
  padding: 14px 16px;
  overflow: auto;
  color: #344054;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  line-height: 20px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

.platform-code-sample div {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border-bottom: 1px solid #e2ebf8;
}

.platform-code-sample strong {
  margin-right: auto;
  color: var(--text-primary);
  font-size: 14px;
}

.platform-code-sample span {
  min-width: 56px;
  padding: 4px 8px;
  border-radius: 5px;
  background: #eef5ff;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: center;
}

.platform-code-sample span:first-of-type {
  background: #fff;
  color: var(--primary);
  box-shadow: inset 0 0 0 1px #bdd7ff;
}

.platform-code-sample pre {
  min-height: 180px;
  max-height: 280px;
  margin: 0;
  padding: 16px 18px;
  overflow: auto;
  color: #344054;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
  line-height: 20px;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
}

@media (max-width: 1280px) {
  .platform-summary-grid,.platform-overview-main { grid-template-columns:minmax(0,1fr); }
  .platform-metrics { grid-template-columns:repeat(3,minmax(0,1fr)); }
  .platform-management-focus,.platform-monitor-grid { grid-template-columns:minmax(0,1fr); }
  .platform-operations-grid { grid-template-columns:minmax(0,1fr); }
  .platform-structure-grid { grid-template-columns:minmax(0,1fr); }
  .platform-structure-chart:first-child { border-right:0;border-bottom:1px solid #dce8f8; }
  .platform-hero__actions span { display:none; }
  .platform-service:not(.platform-service--api) {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto auto auto minmax(0, 1fr);
  }

  .platform-construction,
  .platform-processing {
    grid-template-columns: minmax(0, 1fr);
  }

  .platform-cleaning-editor {
    grid-template-columns: minmax(0, 1fr);
  }

  .platform-cleaning-relations,
  .platform-structured-output,
  .platform-construction-side,
  .platform-build {
    grid-column: 1;
  }

  .platform-cleaning-steps {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .platform-processing-overview,
  .platform-construction-kpis,
  .platform-build-stats,
  .platform-stage-overview__groups,
  .platform-build-results__body,
  .platform-audit-reasons,
  .platform-processing-controls,
  .platform-build-pipeline__body,
  .platform-schema-mapping__body {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .platform-stage-group>div { grid-template-columns:repeat(2,minmax(0,1fr)); }

  .platform-graph-summary,
  .platform-service-debug,
  .platform-review {
    max-height: 360px;
  }

  .platform-service-console__body {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .platform-service-summary {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .platform-overview-grid {
    grid-template-columns: minmax(0, 1fr);
  }
}

@media (max-width: 980px) {
  .platform-metrics { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .platform-change-stats { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .platform-change-body { grid-template-columns:minmax(0,1fr); }
  .platform-change-body>aside { border-top:1px solid #e1eaf5;border-left:0; }
  .platform-hero__actions { display:none; }
  .platform-donut-layout { grid-template-columns:150px minmax(0,1fr);gap:12px; }
  .platform-donut { width:138px;height:138px; }
  .platform-review-notice {
    grid-template-columns: 34px minmax(0, 1fr);
  }

  .platform-review-notice__actions {
    grid-column: 2;
    justify-self: start;
    flex-wrap: wrap;
  }

  .platform-query {
    grid-template-columns: minmax(0, 1fr);
    grid-template-rows: auto auto auto;
  }

  .platform-jobs-stats { grid-template-columns:repeat(2,minmax(0,1fr)); }
  .platform-jobs-stats article:nth-child(2n) { border-right:0; }
  .platform-jobs-stats article:nth-child(-n+2) { border-bottom:1px solid #edf2f8; }

  .platform-build-context {
    flex-direction: column;
    align-items: flex-start;
  }
}

.platform-link-button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--primary);
  font: inherit;
  cursor: pointer;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.platform-review-summary {
  display: grid;
  gap: 6px;
  margin: 12px 12px 0;
  padding: 10px 12px;
  border: 1px solid #dce9ff;
  border-radius: 8px;
  background: #f8fbff;
}

.platform-review-summary strong {
  color: var(--text-primary);
  font-size: 13px;
  line-height: 20px;
}

.platform-review-summary p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-review__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.platform-review__tag {
  flex: 0 0 auto;
  height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  font-size: 11px;
  line-height: 22px;
}

.platform-review__tag.is-处理中 {
  color: var(--primary);
  background: var(--primary-subtle);
}

.platform-review__tag.is-已通过 {
  color: var(--success);
  background: var(--success-subtle);
}

.platform-query-empty {
  display: grid;
  place-content: center;
  gap: 8px;
  min-height: 180px;
  padding: 28px 18px;
  text-align: center;
}

.platform-query-empty strong {
  color: var(--text-primary);
  font-size: 15px;
}

.platform-query-empty p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 22px;
}

.asset-change-mask{position:fixed;z-index:49;inset:0;border:0;background:rgba(16,36,76,.22)}
.asset-change-drawer{position:fixed;z-index:50;top:0;right:0;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;width:min(820px,78vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 42px rgba(34,74,132,.22)}
.asset-change-drawer>header{display:flex;align-items:flex-start;justify-content:space-between;padding:20px;border-bottom:1px solid #dce8f8;background:#fff}.asset-change-drawer>header span{color:#004ecc;font-size:11px}.asset-change-drawer h2{margin:6px 0 3px;font-size:20px}.asset-change-drawer header p{margin:0;color:#718098;font-size:12px}.asset-change-drawer header>button{width:31px;height:31px;border:0;border-radius:5px;background:#f0f4fa;color:#52647f;font-size:20px;cursor:pointer}
.asset-change-summary{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;padding:14px}.asset-change-summary article{display:grid;gap:5px;padding:14px;border:1px solid #c7dcfb;border-radius:7px;background:#fff}.asset-change-summary span{color:#718098;font-size:11px}.asset-change-summary strong{color:#004ecc;font-size:24px}.asset-change-summary article:last-child strong{color:#067647}
.asset-change-table{min-height:0;overflow:auto;padding:0 14px 14px}.asset-change-table table{width:100%;border-collapse:collapse;border:1px solid #dce8f8;background:#fff;font-size:12px}.asset-change-table th,.asset-change-table td{height:48px;padding:10px 12px;border-bottom:1px solid #e3ebf6;text-align:left}.asset-change-table th{position:sticky;top:0;background:#f3f7fc;color:#62728a}.asset-change-table td{color:#344861}.asset-change-table code{color:#004ecc;font-family:inherit}
.asset-change-drawer>footer{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.asset-change-drawer>footer span{color:#718098;font-size:11px}.asset-change-drawer>footer a{height:32px;padding:0 12px;border-radius:5px;background:#004ecc;color:#fff;font-size:11px;line-height:32px;text-decoration:none}
@media(max-width:760px){.asset-change-drawer{width:94vw}.asset-change-table table{min-width:700px}}
</style>
<style scoped>
/* DESIGN_RULES: graph query branch only. */
.platform-query{gap:16px;margin:0;padding:0}
.platform-query .kg-panel{border-color:#e5e6eb!important;border-radius:6px!important;background:#fff!important;box-shadow:none!important}
.platform-query .kg-panel__header{min-height:40px;padding:8px 16px;border-color:#e5e6eb;background:#f7f8fa}
.platform-query .kg-panel__title{font-size:16px;line-height:24px;font-weight:600}
.platform-query .platform-query-form{margin:0;overflow:visible;border:0!important;border-bottom:1px dashed #c9cdd4!important;border-radius:0!important;background:transparent!important}.platform-query-form .kg-panel__header{box-sizing:border-box;height:40px;min-height:40px;padding:0;border:0!important;background:transparent!important}
.platform-query .platform-form-grid{grid-template-columns:repeat(6,minmax(0,1fr));column-gap:16px;row-gap:16px;padding:16px 0}
.platform-query .platform-form-grid :deep(.arco-form-item){width:100%;min-width:0;margin-bottom:0}
.platform-query .platform-form-field :deep(.arco-form-item-wrapper-col),.platform-query .platform-form-field :deep(.arco-form-item-content-wrapper),.platform-query .platform-form-field :deep(.arco-form-item-content){box-sizing:border-box;width:100%;min-width:0;max-width:100%;flex:1 1 0%}
.platform-query .platform-form-field :deep(.arco-form-item-content-flex){display:flex;width:100%;min-width:0;max-width:100%;flex:1 1 0%}
.platform-query .platform-form-grid label{display:grid;min-width:0;gap:8px}
.platform-query .platform-form-field{display:flex;box-sizing:border-box;width:100%;min-width:0;margin:0!important;gap:0;flex-direction:column;justify-self:stretch}
.platform-query .platform-form-grid :deep(.arco-form-item-label-col){margin-bottom:8px;padding:0;line-height:22px}
.platform-query .platform-form-grid>label>span:first-child,.platform-query .platform-form-label{color:var(--text-secondary);font-size:14px;line-height:22px}
.platform-query .platform-form-grid>label>input{height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px}
.platform-query .platform-form-field :deep(.arco-select){display:block;box-sizing:border-box;width:100%!important;min-width:0;max-width:100%;flex:1 1 0%}
.platform-query .platform-form-field :deep(.arco-select-view){display:flex!important;box-sizing:border-box;width:100%!important;min-width:0;max-width:100%;height:32px!important}
.platform-query .platform-form-field :deep(.arco-select-view-input){box-sizing:border-box;height:100%!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background-color:transparent!important;box-shadow:none!important}
.platform-query .platform-form-field :deep(.arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;outline:0!important;opacity:0!important;pointer-events:none!important}
.platform-query .platform-form-field :deep(.arco-select-view-value){width:0!important;min-width:0;overflow:hidden;line-height:30px;text-overflow:ellipsis;white-space:nowrap;flex:1 1 0%!important}
.platform-query .kg-button{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px}

/* 综合图谱展示 / 查询结果：复用科技专家同事关系页的预览与详情布局。 */
.platform-query{grid-row:1/-1;height:100%;min-height:0;align-self:stretch;overflow:auto}
.platform-query .platform-status{display:inline-flex;align-items:center;gap:6px;min-height:22px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}.platform-query .platform-status::before{display:block;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}
.platform-query .platform-table th,.platform-query .platform-table td{height:40px;padding:0 16px;font-size:14px;line-height:22px}.platform-query .platform-table th{background:#f7f8fa;font-weight:500}
.platform-query-empty{gap:8px;padding:24px 16px}.platform-query-empty strong{font-size:16px;line-height:24px;font-weight:600}.platform-query-empty p{font-size:14px;line-height:22px}
@media(max-width:1100px){.platform-query .platform-form-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}
.platform-query .platform-form-field :deep(.arco-select-view){box-sizing:border-box;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important}
.platform-query .platform-form-field :deep(.arco-select-view:hover){border-color:#c9cdd4!important}
.platform-query .platform-form-field :deep(.arco-select-view-focus){border-color:#004ecc!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
@media(max-width:768px){.platform-query .platform-form-grid{grid-template-columns:1fr}}
/* nGQL 查询模式 */
.platform-query-mode-group{display:flex;min-width:0;align-items:center;gap:16px;margin-right:auto}
.platform-query-mode-toggle{display:inline-flex;box-sizing:border-box;height:40px;gap:0;margin-right:0;padding:4px;border:0;border-radius:4px;background:#f2f3f5;overflow:visible;flex:0 0 auto}
.platform-ngql-permission-hint{display:inline-flex;min-width:0;align-items:center;gap:8px;color:#86909c;font-size:12px;line-height:20px;font-weight:400;letter-spacing:0;white-space:nowrap}
.platform-ngql-permission-hint>svg{width:16px;height:16px;color:#86909c;font-size:16px;flex:0 0 auto}
.platform-ngql-permission-hint>i{width:1px;height:12px;background:#c9cdd4;flex:0 0 auto}
.platform-query-mode-toggle__item{display:inline-flex;box-sizing:border-box;align-items:center;justify-content:center;width:120px;height:32px!important;min-height:32px!important;padding:5px 16px!important;border:0;background:transparent;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;text-align:center;cursor:pointer}
.platform-query-mode-toggle__item+.platform-query-mode-toggle__item{border-left:1px solid #c9cdd4}
.platform-query-mode-toggle__item.is-active{border-left-color:transparent;background:#fff;color:#004ecc;font-weight:500}
.platform-query-mode-toggle__item.is-active+.platform-query-mode-toggle__item{border-left-color:transparent}
.platform-query-mode-toggle__item:hover:not(.is-active){background:#fff;color:#004ecc}
.platform-ngql-input{display:grid;gap:16px;padding:16px 0}
.platform-ngql-header-actions{display:flex;align-items:center;gap:16px;flex:0 0 auto}
.platform-ngql-input__textarea{box-sizing:border-box;width:100%;padding:10px 12px;border:1px solid #e5e6eb;border-radius:4px;background:#0d1117;color:#e6edf3;font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;resize:vertical;outline:0}
.platform-ngql-input__textarea:focus{border-color:#004ecc;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
/* 执行结果（nGQL / 图算法共用）：版式对齐原「综合图谱展示」区（左蓝条标题 + 白底描边内容盒），
   表格对齐图谱构建任务列表（40px 行高、#e5edf8 分隔线、hover 高亮）。 */
.platform-query-result{display:flex;flex-direction:column;gap:16px}
.platform-query-result__head{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:16px;min-height:24px}
.platform-query-result__title{position:relative;padding-left:11px;margin:0;color:#1d2129;font-size:16px;line-height:24px;font-weight:600}
.platform-query-result__title::before{position:absolute;top:5px;left:0;width:3px;height:14px;border-radius:1px;background:#004ecc;content:""}
.platform-query-result__meta{color:#86909c;font-size:12px;line-height:20px;white-space:nowrap}
.platform-query-result__body{display:flex;flex-direction:column;overflow:hidden;border:1px solid #e5e6eb;border-radius:6px;background:#fff}
.platform-query-result__table{max-height:320px;overflow:auto}
.platform-query-result table{width:100%;margin:0;border-collapse:collapse;font-size:14px;line-height:22px}
.platform-query-result th{position:sticky;z-index:2;top:0;height:40px;padding:0 16px;background:#f7f8fa;color:#1d2129;font-size:14px;line-height:22px;font-weight:500;text-align:left;white-space:nowrap}
.platform-query-result td{height:40px;padding:0 16px;border-bottom:1px solid #e5edf8;color:#344763;font-size:14px;line-height:22px;font-weight:400;vertical-align:middle}
.platform-query-result tbody tr:hover td{background:#f4f8ff}
.platform-query-result td pre{max-width:420px;margin:0;overflow:auto;color:#1d2129;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.platform-query-result__empty{display:grid;place-content:center;min-height:160px;padding:24px;color:#86909c;font-size:13px;line-height:22px;text-align:center}
/* nGQL 模式固定版式（对齐图谱构建页 gb-jobs-panel）：页面不滚动，结果区占满剩余高度，
   表格在固定尺寸面板内滚动；未执行/空结果占位居中展示 */
.platform-query.is-fixed-result{overflow:hidden}
.platform-query.is-fixed-result .platform-query-result{flex:1 1 0;min-height:0}
.platform-query.is-fixed-result .platform-query-result__body{flex:1;min-height:0}
.platform-query.is-fixed-result .platform-query-result__table{flex:1;min-height:0;max-height:none;overflow:auto}
.platform-query.is-fixed-result .platform-query-result__empty{height:100%}
/* 图算法 tab */
.platform-query-algo__engine{display:flex;align-items:center;gap:12px}
.platform-query-algo__body{display:grid;padding:0 16px 16px;gap:12px}
/* 算法切换页签：对齐人工审核「抽取失败重跑」二级子页签（纯文字按钮 + 蓝色下划线动效，负 margin 抵消 body 内边距） */
.platform-query-algo__tabs{display:flex;flex:0 0 auto;margin:0 -16px}
.platform-query-algo__tabs button{position:relative;height:36px;padding:0 16px;border:0;background:transparent;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;cursor:pointer;transition:color .2s cubic-bezier(0,0,1,1)}
.platform-query-algo__tabs button::after{position:absolute;right:0;bottom:0;left:0;height:2px;background:#165dff;content:"";opacity:0;transform:scaleX(0);transition:opacity .2s cubic-bezier(0,0,1,1),transform .2s cubic-bezier(.34,.69,.1,1)}
.platform-query-algo__tabs button:hover{color:#1d2129}
.platform-query-algo__tabs button.is-active{color:#165dff;font-weight:500}
.platform-query-algo__tabs button.is-active::after{opacity:1;transform:scaleX(1)}
.platform-query-algo__tabs button:focus-visible{border-radius:2px;outline:2px solid rgba(22,93,255,.28);outline-offset:2px}
.platform-query-algo__engine-hint{margin:0;padding:8px 12px;border:1px solid #ffd6c6;border-radius:4px;background:#fff3ea;color:#b42318;font-size:12px;line-height:20px}
.platform-query-algo__desc{margin:0;color:#4e5969;font-size:12px;line-height:20px}
.platform-query-algo__required{margin-left:2px;color:#b42318;font-style:normal}
.platform-query-algo__input{box-sizing:border-box;width:100%;height:32px;padding:0 12px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;color:#1d2129;font-size:14px;line-height:22px;outline:0}
.platform-query-algo__input:focus{border-color:#004ecc;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.platform-query-algo__check{display:inline-flex;align-items:center;gap:8px;min-height:32px;color:#1d2129;font-size:14px;line-height:22px;cursor:pointer}
.platform-query-algo__check input{width:14px;height:14px;accent-color:#004ecc}
.platform-query-algo__param-hint{color:#86909c;font-size:12px;line-height:20px}
/* 边类型多选：解除上面单选裁剪规则（.platform-form-field 的 width:0/overflow:hidden 会毁掉多选 tag） */
.platform-query .platform-query-algo__labels :deep(.arco-select-view){height:auto!important;min-height:32px;padding:2px 12px!important;align-items:center}
.platform-query .platform-query-algo__labels :deep(.arco-select-view-value){display:flex;width:auto!important;min-width:0;overflow:visible;flex:1 1 auto!important;flex-wrap:wrap;gap:2px 0;line-height:20px;text-overflow:clip;white-space:normal}
.platform-query .platform-query-algo__labels :deep(.arco-tag){margin:2px 4px 2px 0}
.platform-query-algo__actions{display:flex;align-items:center;gap:12px}
.platform-query-algo__actions-hint{color:#86909c;font-size:12px;line-height:20px}
.platform-query-algo__job{display:grid;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa;padding:10px 12px;gap:8px}
.platform-query-algo__job-meta{display:flex;align-items:center;gap:12px;color:#4e5969;font-size:13px;line-height:20px;flex-wrap:wrap}
.platform-query-algo__job-id{color:#1d2129;font-weight:500}
.platform-query-algo__job-error{display:grid;border:1px solid #ffd6c6;border-radius:4px;background:#fff;padding:8px 12px;gap:8px}
.platform-query-algo__job-error p{margin:0;color:#b42318;font-size:13px;line-height:20px;overflow-wrap:anywhere}
.platform-query-algo__job-error pre{max-height:160px;margin:0;overflow:auto;padding:8px;border-radius:4px;background:#0d1117;color:#e6edf3;font:12px/1.5 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;word-break:break-all}
.platform-query-algo__truncated{margin:12px 16px 0;padding:8px 12px;border:1px solid #ffe3bd;border-radius:4px;background:#fff7e8;color:#b26b00;font-size:12px;line-height:20px}
/* 窄屏（此前该宽度区间对分布图无任何处理）：donut 与图例上下堆叠，避免固定列挤压 */
@media(max-width:760px){
  .platform-donut-layout{grid-template-columns:minmax(0,1fr);justify-items:center;gap:12px;min-height:0;padding-bottom:8px}
  .platform-donut{width:120px;height:120px}
  .platform-donut::after{inset:20px}
  .platform-donut>span strong{font-size:15px}
  .platform-structure-legend{width:100%}
  .platform-structure-legend article>strong{grid-template-columns:minmax(60px,1fr) 40px}
  .platform-jobs-list a{grid-template-columns:minmax(0,1fr) auto}
  .platform-jobs-list em{display:none}
  .platform-review-list a{grid-template-columns:minmax(0,1fr)}
  .platform-review-list .is-risk{justify-self:start}
}
</style>
<style>
/* The SelectView owns the only visible shell; its readonly input must never paint over the selected value. */
</style>
