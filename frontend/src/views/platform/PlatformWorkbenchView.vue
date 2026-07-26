<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import KgGraphCanvas from '../../components/kg-graph-canvas.vue'
import { useToast } from '../../composables/use-toast'
import {
  getEdgeProvenance,
  getNodeProvenance,
  queryGraphPreset,
  relationCategoryMap,
  type GraphEdgeData,
  type GraphNodeData,
} from '../../data/graph-presets'

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
      { name: 'path_depth', type: 'number', required: false, description: '路径分析深度' },
      { name: 'min_strength', type: 'number', required: false, description: '最小关联强度阈值' },
    ],
    responseFields: commonResponseFields,
    requestExample: { core_node_id: 'E10001', relation_types: ['学术关联', '机构关联'], path_depth: 2, min_strength: 0.65 },
    responseExample: { data: { indirect_nodes: 36, paths: 58, average_strength: 0.76 } },
    resultRows: [{ label: '间接节点', value: '36' }, { label: '路径数量', value: '58' }, { label: '关系类型', value: '4' }, { label: '平均强度', value: '0.76' }],
    evidence: ['路径：张明远 -> 李佳宁 -> 专家C。', '路径深度为 2，命中学术关联和机构关联。', '每条间接关系均返回传递路径和强度。'],
  },
  {
    key: 'two-point-achievement',
    title: '科技两点合作成果',
    endpoint: '/api/v1/kg-service/two-point-achievements',
    method: 'POST',
    requestFields: [
      { name: 'source_expert_id', type: 'string', required: true, description: '第一个专家唯一标识' },
      { name: 'target_expert_id', type: 'string', required: true, description: '第二个专家唯一标识' },
      { name: 'achievement_type', type: 'string', required: false, description: '成果类型' },
      { name: 'time_range', type: 'string', required: false, description: '成果时间范围' },
    ],
    responseFields: commonResponseFields,
    requestExample: { source_expert_id: 'E10001', target_expert_id: 'E10002', achievement_type: '论文/专利/项目', time_range: '2020-2026' },
    responseExample: { data: { papers: 8, patents: 3, projects: 2, contribution: '共同算法模型' } },
    resultRows: [{ label: '合作论文', value: '8' }, { label: '合作专利', value: '3' }, { label: '共同项目', value: '2' }, { label: '价值评分', value: '91' }],
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
    endpoint: '/api/v1/kg-service/expert-alumni-relation',
    method: 'POST',
    requestFields: [
      { name: 'expert_id', type: 'string', required: true, description: '专家唯一标识' },
      { name: 'school', type: 'string', required: false, description: '院校筛选条件' },
      { name: 'education_stage', type: 'string', required: false, description: '教育阶段筛选' },
      { name: 'major', type: 'string', required: false, description: '专业或院系筛选' },
    ],
    responseFields: commonResponseFields,
    requestExample: { expert_id: 'E10001', school: '北京大学', education_stage: '博士', major: '计算机科学' },
    responseExample: { data: { alumni: 26, dimensions: ['同校', '同院系', '同导师'], interactions: 9 } },
    resultRows: [{ label: '校友数量', value: '26' }, { label: '关系维度', value: '3' }, { label: '学术互动', value: '9' }, { label: '最高置信度', value: '0.89' }],
    evidence: ['基于教育经历匹配校友关系。', '细分同校、同院系、同导师等关联维度。', '关联后续学术交流与合作互动。'],
  },
  {
    key: 'paper-cooperation',
    title: '科技专家论文合作关系',
    endpoint: '/api/v1/kg-service/paper-cooperation-relation',
    method: 'POST',
    requestFields: [
      { name: 'expert_id', type: 'string', required: true, description: '专家唯一标识' },
      { name: 'coauthor_id', type: 'string', required: false, description: '合作者唯一标识' },
      { name: 'topic', type: 'string', required: false, description: '论文主题筛选' },
      { name: 'venue_level', type: 'string', required: false, description: '期刊或会议级别' },
    ],
    responseFields: commonResponseFields,
    requestExample: { expert_id: 'E10001', coauthor_id: 'E10002', topic: '人工智能', venue_level: 'A类会议' },
    responseExample: { data: { papers: 14, citations: 1260, stable_team: true, topics: ['人工智能', '先进计算'] } },
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
const selectedQueryType = ref('全部图谱')
const queryKeyword = ref('张明远')
const queryRelationFilter = ref('全部关系')
const queryEntityConfidence = ref('>= 0.75')
const queryRelationConfidence = ref('>= 0.75')
const queryApplied = ref(true)
const processingDomainFilter = ref('全部业务域')
const processingStatusFilter = ref('全部状态')
const processingTaskDomain = ref('论文域')
const processingScope = ref('自上次成功点增量')
const processingPriority = ref('普通')
const processingReason = ref('')
const processingStartDate = ref('2026-07-12')
const processingEndDate = ref('2026-07-13')
const isActionLoading = ref(false)
const selectedGraphNodeId = ref<string | null>(null)
const selectedGraphEdgeId = ref<string | null>(null)
const queryDetailMode = ref<'summary' | 'entity' | 'relation' | 'provenance'>('summary')

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

const assetOverviewGroups = [
  { key: 'entity', title: '实体数据', total: '1.28 亿', totalLabel: '实体总量', added: '+1,183.6 万', addedLabel: '今日新增' },
  { key: 'relation', title: '关系数据', total: '6.42 亿', totalLabel: '关系总量', added: '+2,040 万', addedLabel: '今日新增' },
  { key: 'property', title: '属性值数据', total: '18.76 亿', totalLabel: '属性值总量', added: '+3,264 万', addedLabel: '今日新增及更新' },
] as const

type AssetOverviewKey = (typeof assetOverviewGroups)[number]['key']
const selectedAssetChange = ref<AssetOverviewKey | null>(null)
const assetChangeRows = {
  entity: [
    { type: '机构 / 企业', object: '华南智能芯片有限公司', change: '新增 Organization', source: 'enterprise_profile', time: '10:30:13' },
    { type: '专家 / 人才', object: '周启航', change: '新增 Expert', source: 'expert_profile', time: '10:30:18' },
    { type: '论文成果', object: '《多模态大模型知识推理方法研究》', change: '新增 Paper', source: 'paper_record', time: '10:30:21' },
    { type: '产品 / 技术产品', object: '边缘推理芯片 X7', change: '新增 Product', source: 'enterprise_product', time: '10:30:26' },
  ],
  relation: [
    { type: '任职关系', object: '周启航 → 中国科学院自动化研究所', change: '新增 WORKS_AT', source: 'expert_employment', time: '10:30:22' },
    { type: '成果关系', object: '周启航 → 多模态大模型知识推理方法研究', change: '新增 PUBLISH', source: 'paper_author', time: '10:30:25' },
    { type: '产品关系', object: '华南智能芯片 → 边缘推理芯片 X7', change: '新增 HAS_PRODUCT', source: 'enterprise_product', time: '10:30:29' },
  ],
  property: [
    { type: '企业属性', object: '华南智能芯片·注册资本', change: '新增 registered_capital', source: 'enterprise_profile', time: '10:30:14' },
    { type: '企业属性', object: '华南智能芯片·上市状态', change: '更新 listing_status', source: 'enterprise_profile', time: '10:30:16' },
    { type: '论文属性', object: 'P202607140018·发表时间', change: '新增 publish_date', source: 'paper_record', time: '10:30:23' },
    { type: '关系属性', object: 'WORKS_AT_20418·置信度', change: '更新 confidence', source: 'graph_alignment', time: '10:30:31' },
  ],
} satisfies Record<AssetOverviewKey, Array<{ type: string; object: string; change: string; source: string; time: string }>>
const activeAssetOverview = computed(() => assetOverviewGroups.find((item) => item.key === selectedAssetChange.value))

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

const latestChanges = [
  { time: '10:30', type: '更新', domain: '机构域', title: '清华大学机构属性更新完成', detail: '机构简称与统一标识已完成标准化更新', impact: '处理实例 PI-20260714-0002', to: '/processing-instance/PI-20260714-0002' },
  { time: '10:18', type: '对齐', domain: '人才域', title: '陈卓候选专家实体完成对齐', detail: '机构别名经人工确认后，候选实体已合并至标准专家实体', impact: '处理实例 PI-20260713-0008', to: '/processing-instance/PI-20260713-0008' },
  { time: '10:13', type: '新增', domain: '人才域', title: '张明远标准专家实体构建完成', detail: '完成来源读取、Schema 映射、实体标准化与图谱入库', impact: '处理实例 PI-20260714-0001', to: '/processing-instance/PI-20260714-0001' },
  { time: '09:48', type: '质量', domain: '论文域', title: '重复论文成果记录等待确认', detail: '同一 paper_id 对应三条来源记录，需要人工确认主记录', impact: '处理实例 PI-20260714-0007', to: '/processing-instance/PI-20260714-0007' },
  { time: '昨日', type: 'Schema', domain: '全域', title: '统一 Schema v1.8 已发布', detail: '确认 11 个首版必落实体、42 个标准事实关系和 9 类候选实体', impact: '所有新建批次使用 v1.8', to: '/schema' },
]

const managementRisks = [
  { title: '大模型抽取流程已阻断', detail: 'PI-20260714-0101 · 326 条受影响 · 张建图', detailTo: '/processing-instance/PI-20260714-0101', reviewTo: '/manual-review/task/PI-20260714-0101' },
  { title: 'Schema 批量映射失败', detail: 'PI-20260714-0102 · 1,284 条任务受影响 · 张建图', detailTo: '/processing-instance/PI-20260714-0102', reviewTo: '/manual-review/task/PI-20260714-0102' },
  { title: '张明远候选实体存在冲突', detail: 'PI-20260714-0004 · 实体对齐 · 王审核', detailTo: '/processing-instance/PI-20260714-0004', reviewTo: '/manual-review/task/PI-20260714-0004' },
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
  { id: 'validate', name: '规则验证与证据回链', count: '1,203 属性 / 326 异常', status: '待执行', desc: '用 Schema 约束、存量图谱和原始来源交叉验证抽取结果' },
  { id: 'persist', name: '结果入库与异常分流', count: '326 条待处理', status: '待执行', desc: '高置信度结果自动入库，低置信度与冲突对象转入独立人工处理平台' },
]


const entityStructure = [
  { label: '专家 / 人才', schema: 'Expert', count: '4,286 万', ratio: 34, tone: '#2e90fa' },
  { label: '论文成果', schema: 'Paper', count: '2,931 万', ratio: 23, tone: '#7a5af8' },
  { label: '机构 / 企业', schema: 'Organization', count: '2,164 万', ratio: 17, tone: '#12b76a' },
  { label: '项目 / 专利', schema: 'Project / Patent', count: '1,438 万', ratio: 11, tone: '#f79009' },
  { label: '其他实体', schema: 'Event / Product / Field', count: '1,901 万', ratio: 15, tone: '#98a2b3' },
]

const relationStructure = [
  { label: '发表 / 引用 / 成果', schema: 'PUBLISH / CITES / OUTPUT', count: '2.04 亿', ratio: 32, tone: '#165dff' },
  { label: '任职 / 就读 / 作者单位', schema: 'WORKS_AT / STUDY_AT', count: '1.28 亿', ratio: 20, tone: '#2e90fa' },
  { label: '项目 / 专利参与', schema: 'LEAD_PROJECT / INVENT_PATENT', count: '1.16 亿', ratio: 18, tone: '#06aed4' },
  { label: '企业 / 产品 / 事件', schema: 'HAS_PRODUCT / HAS_EVENT', count: '0.92 亿', ratio: 14, tone: '#7a5af8' },
  { label: '其他关系', schema: '产业链 / 推理关系', count: '1.02 亿', ratio: 16, tone: '#98a2b3' },
]

const taskRows = [
  { batch: 'KG-INC-20260713-018', source: '论文增量批次', domain: '论文 / 人才', stage: '大模型抽取', status: '阻断', progress: 46, entities: '3,261', relations: '8,942', properties: '1,203', autoStored: '0', conflicts: '326', quality: '0.76', next: '异常已隔离，校正后从失败节点重跑' },
  { batch: 'KG-INC-20260713-016', source: '专利项目主题库', domain: '专利域', stage: '实体对齐', status: '运行中', progress: 68, entities: '2,418', relations: '5,206', properties: '864', autoStored: '0', conflicts: '42', quality: '0.88', next: '继续执行证据回链与冲突校验' },
  { batch: 'KG-FULL-20260712-008', source: '科技专家人才库', domain: '人才域', stage: '图谱入库', status: '成功', progress: 100, entities: '18,420', relations: '62,117', properties: '6,410', autoStored: '86,947', conflicts: '0', quality: '0.94', next: '已完成入库，可进入查询服务' },
]

const queryTypes = ['全部图谱', '专家人才子图', '科研成果子图', '机构企业子图', '产业链事件子图', '入库候选子图']
const relationFilters = ['全部关系', '直接关系', '间接关系', '同事', '校友', '论文合作', '企业关联', '产业事件']
const confidenceOptions = ['不限', '>= 0.60', '>= 0.75', '>= 0.85', '>= 0.90']
const queryScopeDescriptions: Record<string, string> = {
  全部图谱: '按统一 Schema 汇总专家、机构、成果、项目、企业、事件和产业链节点。',
  专家人才子图: '围绕 Expert / Person 节点展开教育、任职、成果、合作与社交关系。',
  科研成果子图: '围绕 Paper / Patent / Project / Achievement 展示成果产出和引用链路。',
  机构企业子图: '围绕 Organization / Product 展示任职、工商、产品、项目和专家关联。',
  产业链事件子图: '围绕 IndustryChainNode / Event 展示产业环节、TOP-N 事件和影响关系。',
  入库候选子图: '展示候选实体、候选关系、规则命中和异常隔离状态。',
}

const entityLegendItems = [
  { label: '专家/人才', schema: 'Expert', tone: 'expert' },
  { label: '机构/企业', schema: 'Organization', tone: 'org' },
  { label: '论文成果', schema: 'Paper', tone: 'paper' },
  { label: '项目/专利', schema: 'Project / Patent', tone: 'project' },
  { label: '政策/事件', schema: 'Policy / Event', tone: 'event' },
  { label: '产业链节点', schema: 'IndustryChainNode', tone: 'chain' },
  { label: '产品/技术领域', schema: 'Product / ResearchField', tone: 'field' },
]

const graphEntitySummary = computed(() => {
  return Array.from(new Set(queryGraphPreset.nodes.map((node) => node.entityType))).join(' · ')
})

const queryGraphStats = computed(() => `${queryGraphPreset.nodes.length} 个节点 / ${queryGraphPreset.edges.length} 条关系`)

const selectedQueryScopeDescription = computed(() => (
  queryScopeDescriptions[selectedQueryType.value] ?? queryScopeDescriptions.全部图谱
))

const querySummary = computed(() => {
  if (!queryApplied.value) return '输入关键词后展示专家、企业、论文、机构、项目和事件的一张综合图'
  return `${selectedQueryType.value} / ${queryKeyword.value || '全部实体'} / ${queryRelationFilter.value}`
})

const queryActiveCategories = computed(() => {
  if (!queryApplied.value || queryRelationFilter.value === '全部关系') return null
  return relationCategoryMap[queryRelationFilter.value] ?? [queryRelationFilter.value]
})

const selectedQueryNode = computed(() => {
  if (!selectedGraphNodeId.value) return null
  return queryGraphPreset.nodes.find((node) => node.id === selectedGraphNodeId.value) ?? null
})

const selectedQueryEdge = computed(() => {
  if (!selectedGraphEdgeId.value) return null
  return queryGraphPreset.edges.find((edge) => edge.id === selectedGraphEdgeId.value) ?? null
})

const selectedQueryEdgeNodes = computed(() => {
  const edge = selectedQueryEdge.value
  if (!edge) return { from: undefined, to: undefined }
  return {
    from: queryGraphPreset.nodes.find((node) => node.id === edge.from),
    to: queryGraphPreset.nodes.find((node) => node.id === edge.to),
  }
})

const selectedQueryRelationConfidence = computed(() => {
  const from = selectedQueryEdgeNodes.value.from
  const to = selectedQueryEdgeNodes.value.to
  const edge = selectedQueryEdge.value
  if (!from || !to || !edge) return '0.00'
  const categoryWeight: Record<string, number> = {
    论文合作: 0.03,
    同事: 0.01,
    企业关联: -0.02,
    产业事件: -0.04,
    直接关系: 0.02,
    间接关系: -0.05,
  }
  const baseConfidence = (from.confidence + to.confidence) / 2
  const confidence = Math.min(0.99, Math.max(0.6, baseConfidence + (categoryWeight[edge.category] ?? 0)))
  return confidence.toFixed(2)
})

const selectedQueryEdgeRows = computed(() => {
  const from = selectedQueryEdgeNodes.value.from
  const to = selectedQueryEdgeNodes.value.to
  const edge = selectedQueryEdge.value
  if (!from || !to || !edge) return []
  return [
    ['源实体', `${from.label} / ${from.entityType}`] as const,
    ['目标实体', `${to.label} / ${to.entityType}`] as const,
    ['关系类型', edge.label] as const,
    ['关系分类', edge.category] as const,
    ['关系置信度', selectedQueryRelationConfidence.value] as const,
    ['来源说明', from.evidence[0] ?? to.evidence[0] ?? '来自图谱关系来源聚合'] as const,
  ]
})

const selectedQueryNodeRows = computed(() => {
  const node = selectedQueryNode.value
  if (!node) return []
  return [
    ['实体名称', node.label] as const,
    ['实体类型', node.entityType] as const,
    ['关系数', node.relations] as const,
    ['实体置信度', node.confidence.toFixed(2)] as const,
    ['判断依据', '实体对齐、名称消歧、类型归一、多源交叉校验'] as const,
    ['更新时间', '2026-07-13 10:30'] as const,
  ]
})

const selectedQueryProvenance = computed(() => {
  if (selectedQueryNode.value) return getNodeProvenance(selectedQueryNode.value)
  if (selectedQueryEdge.value) {
    return getEdgeProvenance(
      selectedQueryEdge.value,
      selectedQueryEdgeNodes.value.from,
      selectedQueryEdgeNodes.value.to,
    )
  }
  return null
})

const selectedQueryProvenanceTarget = computed(() => {
  const node = selectedQueryNode.value
  if (node) {
    return {
      kind: '实体',
      name: node.label,
      type: node.entityType,
      id: node.id,
      confidence: node.confidence.toFixed(2),
    }
  }
  const edge = selectedQueryEdge.value
  const from = selectedQueryEdgeNodes.value.from
  const to = selectedQueryEdgeNodes.value.to
  if (!edge || !from || !to) return null
  return {
    kind: '关系',
    name: `${from.label} → ${to.label}`,
    type: edge.label,
    id: edge.id,
    confidence: selectedQueryRelationConfidence.value,
  }
})


async function runWithLoading(message: string, action?: () => void) {
  isActionLoading.value = true
  await new Promise((resolve) => window.setTimeout(resolve, 420))
  action?.()
  showToast(message)
  isActionLoading.value = false
}

function openNodeDetail(node: GraphNodeData) {
  selectedGraphNodeId.value = node.id
  selectedGraphEdgeId.value = null
  queryDetailMode.value = 'entity'
}

function openEdgeDetail(edge: GraphEdgeData) {
  selectedGraphEdgeId.value = edge.id
  selectedGraphNodeId.value = null
  queryDetailMode.value = 'relation'
}

function openSelectedProcessingInstance() {
  const provenance = selectedQueryProvenance.value
  const target = selectedQueryProvenanceTarget.value
  if (!provenance || !target) return
  void router.push({
    name: 'processing-instance-detail',
    params: { instanceId: provenance.task.instanceId },
    query: {
      stage: '图谱构建',
      objectName: target.name,
      objectId: target.id,
      objectType: target.type,
      kind: target.kind,
      confidence: target.confidence,
      sourceTable: provenance.evidences[0]?.technicalTable,
      sourceRecordId: provenance.evidences[0]?.fieldIdentifier,
      rule: provenance.result.ruleName,
    },
  })
}

function handleQuery() {
  void runWithLoading(`查询完成：${selectedQueryType.value} / ${queryKeyword.value}`, () => {
    queryApplied.value = true
    selectedGraphNodeId.value = null
    selectedGraphEdgeId.value = null
    queryDetailMode.value = 'summary'
  })
}

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

watch(activeServiceKey, () => {
  selectedGraphNodeId.value = null
  selectedGraphEdgeId.value = null
})

const pageMeta = computed(() => {
  const map: Record<PlatformTab, { title: string }> = {
    overview: { title: '亿级科技知识图谱平台' },
    processing: { title: '数据处理与结构化输出' },
    construction: { title: '图谱构建与治理' },
    query: { title: '综合图谱查询' },
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
      <div class="platform-hero__actions"><span><i></i>平台服务正常 · 2 个批次待处理</span><!-- <RouterLink to="/tasks?module=图谱版本">当前图谱 KG-2026.07.12.008</RouterLink> --><RouterLink to="/tasks">查看任务</RouterLink><RouterLink to="/manual-review">进入人工处理</RouterLink></div>
    </header>

    <header v-else class="platform-page-head">
      <div>
        <h1>{{ pageMeta.title }}</h1>
      </div>
    </header>

    <main v-if="activeTab === 'overview'" class="platform-content platform-overview">
      <section class="platform-summary-grid" aria-label="实体、关系与属性值数据总览">
        <article v-for="group in assetOverviewGroups" :key="group.key" :class="['kg-panel', 'platform-summary-card', `is-${group.key}`]">
          <header><div><strong>{{ group.title }}</strong><span><i />数据已更新</span></div><button type="button" @click="selectedAssetChange = group.key">查看今日新增 →</button></header>
          <div class="platform-summary-card__main"><section><strong>{{ group.total }}</strong><span>{{ group.totalLabel }}</span></section><section class="is-added"><strong>{{ group.added }}</strong><span>{{ group.addedLabel }}</span></section></div>
        </article>
      </section>

      <section class="platform-overview-main">
        <div class="kg-panel platform-latest-changes">
          <div class="kg-panel__header"><div><h2 class="kg-panel__title">今日新增与变化</h2></div><RouterLink to="/tasks">查看全部任务 →</RouterLink></div>
          <div class="platform-change-feed"><RouterLink v-for="item in latestChanges" :key="`${item.time}-${item.title}`" :to="item.to"><time>{{ item.time }}</time><span :class="`is-${item.type}`">{{ item.type }}</span><div><strong>{{ item.title }}</strong><p>{{ item.detail }}</p><em>{{ item.domain }} · {{ item.impact }}</em></div><b>查看详情 →</b></RouterLink></div>
        </div>

        <aside class="kg-panel platform-risk-panel">
          <div class="kg-panel__header"><div><h2 class="kg-panel__title">需要人工审核的任务</h2></div><RouterLink to="/manual-review">查看处理队列 →</RouterLink></div>
          <div class="platform-risk-list"><article v-for="item in managementRisks" :key="item.title"><i /><div><strong>{{ item.title }}</strong><p>{{ item.detail }}</p><nav><RouterLink :to="item.detailTo">查看详情</RouterLink><RouterLink class="primary" :to="item.reviewTo">人工处理</RouterLink></nav></div></article></div>
        </aside>
      </section>

      <section class="kg-panel platform-structure-overview">
        <div class="kg-panel__header"><div><h2 class="kg-panel__title">当前图谱资产</h2></div><span>实体 1.28 亿 · 关系 6.42 亿 · 数据截至 10:30</span></div>
        <div class="platform-structure-grid">
          <div class="platform-structure-chart"><header><strong>实体分类占比</strong></header><div class="platform-donut-layout"><div class="platform-donut is-entity"><span><strong>1.28 亿</strong><em>实体总量</em></span></div><div class="platform-structure-legend"><article v-for="item in entityStructure" :key="item.schema"><span><i :style="{ background: item.tone }" />{{ item.label }}<em>{{ item.schema }}</em></span><strong>{{ item.count }}<em>{{ item.ratio }}%</em></strong></article></div></div></div>
          <div class="platform-structure-chart"><header><strong>关系分类占比</strong></header><div class="platform-donut-layout"><div class="platform-donut is-relation"><span><strong>6.42 亿</strong><em>关系总量</em></span></div><div class="platform-structure-legend"><article v-for="item in relationStructure" :key="item.schema"><span><i :style="{ background: item.tone }" />{{ item.label }}<em>{{ item.schema }}</em></span><strong>{{ item.count }}<em>{{ item.ratio }}%</em></strong></article></div></div></div>
        </div>
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
            <select v-model="processingTaskDomain">
              <option v-for="item in processingTaskDomainOptions" :key="item">{{ item }}</option>
            </select>
          </label>
          <label>
            <span>数据范围</span>
            <select v-model="processingScope">
              <option v-for="item in processingScopeOptions" :key="item">{{ item }}</option>
            </select>
          </label>
          <label>
            <span>执行优先级</span>
            <select v-model="processingPriority">
              <option v-for="item in processingPriorityOptions" :key="item">{{ item }}</option>
            </select>
          </label>
          <label v-if="processingScope === '指定时间范围'" class="platform-range-fields">
            <span>时间范围</span>
            <i><input v-model="processingStartDate" type="date" /><b>至</b><input v-model="processingEndDate" type="date" /></i>
          </label>
          <label v-if="processingPriority === '紧急'">
            <span>紧急原因</span>
            <input v-model="processingReason" placeholder="必填，用于审计与排队依据" />
          </label>
          <button class="kg-button" type="button" :disabled="isActionLoading || (processingPriority === '紧急' && !processingReason.trim())" @click="handleStartTask">{{ processingActionLabel }}</button>
        </div>
        <div class="platform-update-help"><span><b>普通：</b>按提交顺序排队。</span><span><b>紧急：</b>优先排队，需填写原因。</span></div>

        <div class="platform-sticky-table"><table class="platform-table">
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
          <article v-for="(item, index) in dataProcessingSteps" :key="item.name" class="is-clickable-card" tabindex="0" role="button" @click="openProcessDetail('processing', 'DP-20260713-0200', item.id)" @keydown.enter="openProcessDetail('processing', 'DP-20260713-0200', item.id)">
            <i>{{ index + 1 }}</i>
            <div>
              <strong>{{ item.name }}</strong>
              <p>{{ item.desc }}</p>
            </div>
            <span>{{ item.status }}</span>
            <b class="platform-card-arrow">查看详情 →</b>
          </article>
        </div>
      </section>

      <section class="kg-panel platform-quality-log">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">质量检验日志</h2>
        </div>
        <table class="platform-table">
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
        <div class="platform-review-notice__actions"><RouterLink to="/tasks?module=图谱构建&amp;batch=UPD-20260714">查看处理实例</RouterLink><RouterLink to="/manual-review?batch=UPD-20260714">进入人工处理 →</RouterLink></div>
      </section>

      <section class="kg-panel platform-task-list">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">最近数据处理任务</h2>
          <div class="platform-task-filters">
            <select v-model="processingDomainFilter"><option v-for="item in processingDomainOptions" :key="item">{{ item }}</option></select>
            <select v-model="processingStatusFilter"><option v-for="item in processingStatusOptions" :key="item">{{ item }}</option></select>
            <span>{{ filteredProcessingTaskRows.length }} 个任务</span>
            <RouterLink to="/tasks?module=数据处理">全部任务 →</RouterLink>
          </div>
        </div>
        <table class="platform-table platform-progress-table">
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
        <article v-for="item in buildStats" :key="item.label" class="is-clickable-card" tabindex="0" role="button" @click="openProcessDetail('construction', 'KG-INC-20260713-018')" @keydown.enter="openProcessDetail('construction', 'KG-INC-20260713-018')"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><em>{{ item.note }}</em><b class="platform-card-arrow">查看 →</b></article>
      </section>

      <section class="kg-panel platform-build-pipeline">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">结构化数据建图过程</h2>
        </div>
        <div class="platform-build-pipeline__body">
          <article v-for="(item, index) in buildPipelineSteps" :key="item.name" class="is-clickable-card" tabindex="0" role="button" @click="openProcessDetail('construction', 'KG-INC-20260713-018', item.id)" @keydown.enter="openProcessDetail('construction', 'KG-INC-20260713-018', item.id)">
            <i>{{ index + 1 }}</i>
            <div>
              <span>{{ item.name }}</span>
              <strong>{{ item.count }}</strong>
              <p>{{ item.desc }}</p>
            </div>
            <em>{{ item.status }}</em>
            <b class="platform-card-arrow">详情 →</b>
          </article>
        </div>
      </section>

      <section class="kg-panel platform-build-progress platform-build-progress--list">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">最近图谱构建任务</h2>
          <div class="platform-task-filters"><RouterLink to="/tasks?module=图谱构建">全部任务 →</RouterLink></div>
        </div>
        <table class="platform-table platform-progress-table">
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
          <div class="platform-schema-head"><span>v1.8</span><!-- <RouterLink to="/schema">打开 Schema 浏览器 →</RouterLink> --></div>
        </div>
        <table class="platform-table">
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
        <div class="platform-review-notice__actions"><RouterLink to="/tasks?module=图谱构建&amp;batch=UPD-20260714">查看处理实例</RouterLink><RouterLink to="/manual-review?batch=UPD-20260714">进入人工处理 →</RouterLink></div>
      </section>

    </main>

    <main v-else-if="activeTab === 'query'" class="platform-content platform-query">
      <section class="kg-panel platform-query-form">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">图谱查询条件</h2>
          <button class="kg-button" type="button" :disabled="isActionLoading" @click="handleQuery">查询图谱</button>
        </div>
        <div class="platform-form-grid">
          <label class="platform-query-question">
            <span>实体名称或关键词</span>
            <input v-model="queryKeyword" type="search" placeholder="请输入实体名称或关键词，例如：张明远" />
          </label>
          <label>
            <span>图谱范围</span>
            <select v-model="selectedQueryType">
              <option v-for="item in queryTypes" :key="item">{{ item }}</option>
            </select>
          </label>
          <label>
            <span>关系类型</span>
            <select v-model="queryRelationFilter">
              <option v-for="item in relationFilters" :key="item">{{ item }}</option>
            </select>
          </label>
          <label>
            <span>实体置信度</span>
            <select v-model="queryEntityConfidence">
              <option v-for="item in confidenceOptions" :key="`entity-${item}`">{{ item }}</option>
            </select>
          </label>
          <label>
            <span>关系置信度</span>
            <select v-model="queryRelationConfidence">
              <option v-for="item in confidenceOptions" :key="`relation-${item}`">{{ item }}</option>
            </select>
          </label>
        </div>
      </section>

      <section class="kg-panel platform-query-graph">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">综合图谱展示</h2>
          <span>{{ querySummary }} · {{ queryGraphStats }}</span>
        </div>
        <div class="platform-graph-legend" aria-label="实体类型图例">
          <span
            v-for="item in entityLegendItems"
            :key="item.schema"
            :class="['platform-graph-legend__item', `is-${item.tone}`]"
            :title="item.schema"
          >
            <i />
            {{ item.label }}
          </span>
        </div>
        <KgGraphCanvas
          :nodes="queryGraphPreset.nodes"
          :edges="queryGraphPreset.edges"
          :active-categories="queryActiveCategories"
          :selected-node-id="selectedGraphNodeId"
          :selected-edge-id="selectedGraphEdgeId"
          aria-label="图谱查询结果"
          @select-node="openNodeDetail"
          @select-edge="openEdgeDetail"
        />
      </section>

      <aside class="kg-panel platform-detail">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">
            {{ queryDetailMode === 'provenance' ? '数据溯源' : queryDetailMode === 'relation' ? '关系结构化结果' : queryDetailMode === 'entity' ? '实体结构化结果' : '查询结果' }}
          </h2>
          <div class="platform-detail__tabs" aria-label="图谱详情类型">
            <button :class="{ 'is-active': queryDetailMode === 'summary' }" type="button" @click="queryDetailMode = 'summary'">摘要</button>
            <button :class="{ 'is-active': queryDetailMode === 'entity' }" type="button" @click="queryDetailMode = 'entity'">实体</button>
            <button :class="{ 'is-active': queryDetailMode === 'relation' }" type="button" @click="queryDetailMode = 'relation'">关系</button>
            <button :class="{ 'is-active': queryDetailMode === 'provenance' }" type="button" @click="queryDetailMode = 'provenance'">溯源</button>
          </div>
        </div>
        <div v-if="queryDetailMode === 'summary'" class="platform-detail__body">
          <dl>
            <div><dt>图谱范围</dt><dd>{{ selectedQueryScopeDescription }}</dd></div>
            <div><dt>覆盖实体</dt><dd>{{ graphEntitySummary }}</dd></div>
            <div><dt>查询条件</dt><dd>{{ querySummary }}</dd></div>
            <div><dt>图谱规模</dt><dd>{{ queryGraphStats }}</dd></div>
            <div><dt>关系筛选</dt><dd>{{ queryRelationFilter }}</dd></div>
            <div><dt>实体置信度</dt><dd>{{ queryEntityConfidence }}</dd></div>
            <div><dt>关系置信度</dt><dd>{{ queryRelationConfidence }}</dd></div>
          </dl>
          <div class="platform-evidence">
            <ul>
              <li>点击实体节点查看实体属性、命中关系与来源信息。</li>
              <li>点击关系线查看两端实体之间的关系类型、置信度与来源说明。</li>
            </ul>
          </div>
        </div>
        <div v-else-if="queryDetailMode === 'entity' && selectedQueryNode" class="platform-detail__body">
          <dl>
            <div v-for="([label, value], index) in selectedQueryNodeRows" :key="`${label}-${index}`">
              <dt>{{ label }}</dt>
              <dd>{{ value }}</dd>
            </div>
          </dl>
          <div v-if="selectedQueryNode.evidence.length" class="platform-evidence">
            <strong>对齐依据</strong>
            <ul>
              <li v-for="(line, index) in selectedQueryNode.evidence.slice(0, 3)" :key="index">{{ line }}</li>
            </ul>
          </div>
        </div>
        <div v-else-if="queryDetailMode === 'relation' && selectedQueryEdge" class="platform-detail__body">
          <dl>
            <div v-for="([label, value], index) in selectedQueryEdgeRows" :key="`${label}-${index}`">
              <dt>{{ label }}</dt>
              <dd>{{ value }}</dd>
            </div>
          </dl>
        </div>
        <div v-else-if="queryDetailMode === 'provenance' && selectedQueryProvenance && selectedQueryProvenanceTarget" class="platform-detail__body">
          <section class="platform-provenance" aria-label="图谱数据溯源">
            <div class="platform-provenance__title">
              <span>当前追溯对象</span>
              <em>{{ selectedQueryProvenanceTarget.kind }}</em>
            </div>
            <div class="platform-provenance__target">
              <strong>{{ selectedQueryProvenanceTarget.name }}</strong>
              <span>{{ selectedQueryProvenanceTarget.kind }}</span>
            </div>
            <template v-if="selectedQueryNode">
              <h3 class="platform-provenance__section-title">实体溯源</h3>
              <dl class="platform-provenance__source">
                <div><dt>实体类型</dt><dd>{{ selectedQueryProvenanceTarget.type }}</dd></div>
                <div><dt>源数据表</dt><dd><code>{{ selectedQueryProvenance.evidences[0]?.technicalTable }}</code></dd></div>
                <div><dt>字段标识 ID</dt><dd><code>{{ selectedQueryProvenance.evidences[0]?.fieldIdentifier }}</code></dd></div>
                <div><dt>构建任务 ID</dt><dd><code>{{ selectedQueryProvenance.task.instanceId }}</code></dd></div>
              </dl>
              <div class="platform-provenance__task-meta"><button type="button" @click="openSelectedProcessingInstance">查看构建详情 →</button></div>
            </template>
            <template v-else-if="selectedQueryProvenance.relationEndpoints?.length">
              <h3 class="platform-provenance__section-title">关系溯源</h3>
              <dl class="platform-provenance__source"><div><dt>关系类型</dt><dd>{{ selectedQueryProvenanceTarget.type }}</dd></div></dl>
              <h3 class="platform-provenance__section-title">两端实体来源</h3>
              <div class="platform-provenance__evidence-list">
                <article v-for="endpoint in selectedQueryProvenance.relationEndpoints" :key="endpoint.role">
                  <header><strong>{{ endpoint.role }} · {{ endpoint.name }}</strong></header>
                  <p><b>实体类型：{{ endpoint.entityType }}</b></p>
                  <span>源数据表：<code>{{ endpoint.technicalTable }}</code></span>
                  <span>字段标识 ID：<code>{{ endpoint.fieldIdentifier }}</code></span>
                </article>
              </div>
              <dl class="platform-provenance__source"><div><dt>构建任务 ID</dt><dd><code>{{ selectedQueryProvenance.task.instanceId }}</code></dd></div></dl>
              <div class="platform-provenance__task-meta"><button type="button" @click="openSelectedProcessingInstance">查看构建详情 →</button></div>
            </template>
          </section>
        </div>
      </aside>
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
            <input :value="activeService.title" readonly />
          </label>
          <template v-if="activeServiceMode === 'test'">
            <label v-for="field in activeService.requestFields.slice(0, 3)" :key="field.name">
              <span>{{ field.name }}</span>
              <input :value="activeService.requestExample[field.name] ?? ''" />
            </label>
          </template>
          <template v-else>
            <label>
            <span>接口路径</span>
            <input :value="activeService.endpoint" readonly />
            </label>
            <label>
            <span>请求方法</span>
            <input :value="activeService.method" readonly />
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

        <aside class="kg-panel platform-service-debug">
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
              <table class="platform-table">
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
              <table class="platform-table">
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
    <aside v-if="selectedAssetChange && activeAssetOverview" class="asset-change-drawer">
      <header><div><span>今日图谱数据变化</span><h2>{{ activeAssetOverview.title }}新增明细</h2><p>{{ activeAssetOverview.addedLabel }} {{ activeAssetOverview.added }} · 数据更新至 10:30</p></div><button type="button" @click="selectedAssetChange = null">×</button></header>
      <section class="asset-change-summary"><article><span>当前总量</span><strong>{{ activeAssetOverview.total }}</strong></article><article><span>{{ activeAssetOverview.addedLabel }}</span><strong>{{ activeAssetOverview.added }}</strong></article></section>
      <div class="asset-change-table"><table><thead><tr><th>数据类型</th><th>具体对象</th><th>变更内容</th><th>来源</th><th>识别时间</th></tr></thead><tbody><tr v-for="row in assetChangeRows[selectedAssetChange]" :key="`${row.object}-${row.time}`"><td>{{ row.type }}</td><td><strong>{{ row.object }}</strong></td><td>{{ row.change }}</td><td><code>{{ row.source }}</code></td><td>{{ row.time }}</td></tr></tbody></table></div>
      <footer><span>{{ assetChangeRows[selectedAssetChange].length }} 条变化</span><RouterLink to="/tasks">查看对应更新任务 →</RouterLink></footer>
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
.platform-hero__flow i { color:#165dff;font-style:normal; }

.platform-hero__actions { display:flex;align-items:center;gap:8px;margin-left:auto; }
.platform-hero__actions span { display:inline-flex;align-items:center;gap:7px;margin-right:4px;color:#526783;font-size:12px; }
.platform-hero__actions span i { width:8px;height:8px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12); }
.platform-hero__actions a { height:32px;padding:0 12px;border:1px solid #9ec2f7;border-radius:6px;background:rgba(255,255,255,.72);color:#165dff;font-size:12px;line-height:32px;text-decoration:none; }
.platform-hero__actions a:last-child { border-color:#165dff;background:#165dff;color:#fff; }

.platform-page-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 36px;
  padding: 0 2px 2px;
}

.platform-page-head__action { height:30px;padding:0 11px;border:1px solid #9ec2f7;border-radius:6px;background:#fff;color:#165dff;font-size:11px;line-height:30px;text-decoration:none; }

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
}

.platform-overview {
  display: grid;
  grid-template-rows: repeat(3, auto);
  gap: 14px;
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
.platform-stage-group>header a { color:#165dff;font-size:11px;text-decoration:none; }
.platform-stage-group>div { display:grid;grid-template-columns:repeat(4,minmax(0,1fr)); }
.platform-stage-group section { display:grid;gap:4px;padding:13px 14px;border-right:1px solid #e1ebf7; }
.platform-stage-group section:last-child { border-right:0; }
.platform-stage-group section span { color:#687892;font-size:11px; }
.platform-stage-group section strong { color:#10264c;font-size:20px; }
.platform-stage-group section em { overflow:hidden;color:#8290a7;font-size:10px;font-style:normal;text-overflow:ellipsis;white-space:nowrap; }

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

.platform-metric.is-blue strong { color: #165dff; }
.platform-metric.is-green strong { color: #00a870; }
.platform-metric.is-purple strong { color: #722ed1; }
.platform-metric.is-orange strong { color: #ff7d00; }
.platform-metric.is-red strong { color: #d92d20; }

.platform-summary-grid { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px; }
.platform-summary-card { position:relative;min-width:0;overflow:hidden; }
.platform-summary-card::after { position:absolute;right:-35px;bottom:-55px;width:130px;height:130px;border-radius:50%;background:rgba(22,93,255,.045);content:"";pointer-events:none; }
.platform-summary-card>header { display:flex;align-items:center;justify-content:space-between;gap:10px;padding:12px 15px;border-bottom:1px solid #dce8f8;background:rgba(255,255,255,.75); }
.platform-summary-card>header>div { display:grid;gap:4px; }.platform-summary-card>header>div>strong { color:#263b5a;font-size:13px; }
.platform-summary-card>header span { display:flex;align-items:center;gap:5px;color:#067647;font-size:9px; }.platform-summary-card>header span i { width:6px;height:6px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 3px #dcfae6; }
.platform-summary-card>header span.warning { color:#b42318; }.platform-summary-card>header span.warning i { background:#d92d20;box-shadow:0 0 0 3px #fee4e2; }
.platform-summary-card>header a,.platform-summary-card>header button { padding:0;border:0;background:transparent;color:#165dff;font-size:10px;text-decoration:none;white-space:nowrap;cursor:pointer; }
.platform-summary-card__main { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));min-height:112px;background:#fff; }
.platform-summary-card__main section { display:flex;justify-content:center;gap:5px;padding:20px 18px;border-right:1px solid #e3ebf6;flex-direction:column; }.platform-summary-card__main section:last-child { border-right:0; }
.platform-summary-card__main strong { color:#165dff;font-size:34px;line-height:40px;letter-spacing:-.5px; }.platform-summary-card.is-relation .platform-summary-card__main strong { color:#7a5af8; }.platform-summary-card.is-property .platform-summary-card__main strong { color:#f79009; }.platform-summary-card .platform-summary-card__main .is-added strong { color:#079455; }
.platform-summary-card__main span { color:#66758f;font-size:12px; }
.platform-summary-card__items { position:relative;z-index:1;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));padding:10px 8px;background:#f8fbff; }
.platform-summary-card__items>a { display:grid;gap:3px;padding:2px 8px;border-right:1px solid #e1eaf5;color:inherit;text-decoration:none;transition:background-color .2s ease; }.platform-summary-card__items>a:last-child { border-right:0; }.platform-summary-card__items>a:hover { background:#eef5ff; }
.platform-summary-card__items em { overflow:hidden;color:#8290a5;font-size:8px;font-style:normal;text-overflow:ellipsis;white-space:nowrap; }.platform-summary-card__items strong { overflow:hidden;color:#344861;font-size:10px;text-overflow:ellipsis;white-space:nowrap; }

.platform-overview-main { display:grid;grid-template-columns:minmax(0,1.65fr) minmax(360px,.72fr);gap:14px; }
.platform-latest-changes,.platform-risk-panel { min-width:0;overflow:hidden; }
.platform-latest-changes .kg-panel__header>div,.platform-risk-panel .kg-panel__header>div { display:grid;gap:2px; }.platform-latest-changes .kg-panel__header span,.platform-risk-panel .kg-panel__header span { color:#7b8aa1;font-size:10px; }.platform-latest-changes .kg-panel__header>a,.platform-risk-panel .kg-panel__header>a { color:#165dff;font-size:10px;text-decoration:none; }
.platform-change-feed { display:grid; }
.platform-change-feed>a { display:grid;grid-template-columns:48px 44px minmax(0,1fr) 70px;align-items:center;gap:10px;min-height:70px;padding:10px 14px;border-bottom:1px solid #e4ecf6;background:#fff;color:#344761;text-decoration:none; }
.platform-change-feed>a:last-child { border-bottom:0; }.platform-change-feed>a:hover { background:#f4f8ff; }
.platform-change-feed time { color:#71819a;font-size:10px; }.platform-change-feed>a>span { justify-self:start;padding:3px 7px;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:8px; }.platform-change-feed>a>span.is-新增 { background:#e9f8ef;color:#067647; }.platform-change-feed>a>span.is-对齐 { background:#f0edff;color:#6941c6; }.platform-change-feed>a>span.is-质量 { background:#fff3df;color:#b54708; }.platform-change-feed>a>span.is-Schema { background:#edf2f7;color:#475467; }
.platform-change-feed>a>div { display:grid;gap:3px;min-width:0; }.platform-change-feed>a>div strong { overflow:hidden;color:#253752;font-size:11px;text-overflow:ellipsis;white-space:nowrap; }.platform-change-feed>a>div p { margin:0;color:#62728a;font-size:9px;line-height:15px; }.platform-change-feed>a>div em { color:#8a97aa;font-size:8px;font-style:normal; }.platform-change-feed>a>b { color:#165dff;font-size:9px;font-weight:500;white-space:nowrap; }

.platform-management-focus { display:grid;grid-template-columns:minmax(0,1.65fr) minmax(340px,.72fr);gap:14px; }
.platform-change-panel,.platform-risk-panel,.platform-trend-panel { min-width:0;overflow:hidden; }
.platform-change-panel .kg-panel__header>div,.platform-risk-panel .kg-panel__header>div,.platform-trend-panel .kg-panel__header>div,.platform-recent-tasks .kg-panel__header>div { display:grid;gap:2px; }
.platform-change-panel .kg-panel__header span,.platform-risk-panel .kg-panel__header span,.platform-trend-panel .kg-panel__header span,.platform-recent-tasks .kg-panel__header span { color:#7b8aa1;font-size:10px; }
.platform-change-panel .kg-panel__header>a,.platform-risk-panel .kg-panel__header>a { color:#165dff;font-size:11px;text-decoration:none; }
.platform-change-stats { display:grid;grid-template-columns:repeat(4,minmax(0,1fr));border-bottom:1px solid #dde8f5; }
.platform-change-stats article { position:relative;display:grid;gap:4px;padding:13px 15px;border-right:1px solid #e2eaf5;background:#fff; }
.platform-change-stats article:last-child { border-right:0; }
.platform-change-stats article::before { position:absolute;top:14px;left:0;width:3px;height:30px;border-radius:0 3px 3px 0;background:#2e90fa;content:""; }
.platform-change-stats article.is-purple::before { background:#7a5af8; }.platform-change-stats article.is-green::before { background:#12b76a; }.platform-change-stats article.is-orange::before { background:#f79009; }
.platform-change-stats span { color:#66758e;font-size:10px; }.platform-change-stats strong { color:#183153;font-size:20px; }.platform-change-stats em { color:#8a97aa;font-size:9px;font-style:normal; }
.platform-change-body { display:grid;grid-template-columns:minmax(0,1.25fr) minmax(270px,.75fr);min-height:210px; }
.platform-change-body>section { padding:13px 15px; }.platform-change-body>aside { padding:13px 14px;border-left:1px solid #e1eaf5;background:#f9fbfe; }
.platform-change-body header { display:flex;align-items:center;justify-content:space-between;margin-bottom:10px; }.platform-change-body header>strong { color:#344661;font-size:11px; }.platform-change-body header>span,.platform-change-body header>a { color:#8290a5;font-size:9px;text-decoration:none; }
.platform-change-ranking { display:grid;gap:8px; }.platform-change-ranking article { display:grid;grid-template-columns:minmax(150px,.8fr) minmax(170px,1fr);align-items:center;gap:12px; }
.platform-change-ranking article>span { display:grid;grid-template-columns:7px minmax(0,1fr);column-gap:8px; }.platform-change-ranking article>span>i { grid-row:1/3;width:7px;height:7px;margin-top:5px;border-radius:50%; }.platform-change-ranking article>span b { font-size:10px; }.platform-change-ranking article>span em { color:#8491a5;font-size:8px;font-style:normal; }
.platform-change-ranking article>div { display:grid;grid-template-columns:minmax(70px,1fr) 62px;align-items:center;gap:8px; }.platform-change-ranking article>div>i { height:6px;overflow:hidden;border-radius:99px;background:#eaf0f8; }.platform-change-ranking article>div>i b { display:block;height:100%;border-radius:inherit; }.platform-change-ranking article>div strong { color:#40536f;font-size:10px;text-align:right; }
.platform-change-body>aside article { display:grid;grid-template-columns:25px minmax(0,1fr);gap:9px;padding:9px 0;border-bottom:1px solid #e6edf6; }.platform-change-body>aside article:last-child { border-bottom:0; }
.platform-change-body>aside article>i { display:grid;place-items:center;width:23px;height:23px;border-radius:50%;background:#eaf2ff;color:#165dff;font-size:10px;font-style:normal; }.platform-change-body>aside article>i.success { background:#dcfae6;color:#067647; }.platform-change-body>aside article>i.warning { background:#fef0c7;color:#b54708; }
.platform-change-body>aside article>span { display:grid;gap:3px; }.platform-change-body>aside article strong { color:#344661;font-size:10px; }.platform-change-body>aside article em { color:#7b899e;font-size:9px;font-style:normal; }

.platform-risk-list { display:grid; }.platform-risk-list article { position:relative;display:grid;grid-template-columns:9px minmax(0,1fr);gap:10px;min-height:88px;padding:14px;border-bottom:1px solid #e3ebf6;background:#fff; }.platform-risk-list article:last-child { border-bottom:0; }
.platform-risk-list article>i { width:8px;height:8px;margin-top:5px;border-radius:50%;background:#2e90fa;box-shadow:0 0 0 4px #d6e9ff; }
.platform-risk-list article>div { display:grid;gap:3px; }
.platform-risk-list article strong { color:#253752;font-size:11px; }.platform-risk-list article p { margin:0;color:#7b899e;font-size:9px;line-height:15px; }
.platform-risk-list article nav { display:flex;justify-content:flex-end;gap:8px;margin-top:7px; }
.platform-risk-list article a { display:inline-flex;align-items:center;height:28px;padding:0 9px;border:1px solid #cbdaf0;border-radius:5px;background:#fff;color:#165dff;font-size:11px;text-decoration:none;white-space:nowrap; }
.platform-risk-list article a.primary { border-color:#165dff;background:#165dff;color:#fff; }

.platform-monitor-grid { display:grid;grid-template-columns:minmax(0,1fr) minmax(480px,1fr);gap:14px; }
.platform-trend-legend { display:flex!important;align-items:center;gap:10px!important; }.platform-trend-legend span { display:flex;align-items:center;gap:5px; }.platform-trend-legend i { width:7px;height:7px;border-radius:2px;background:#2e90fa; }.platform-trend-legend span:last-child i { background:#7a5af8; }
.platform-trend-chart { display:grid;grid-template-columns:repeat(7,1fr);align-items:end;height:225px;padding:20px 18px 13px;background:linear-gradient(to top,rgba(220,232,248,.7) 1px,transparent 1px);background-size:100% 25%; }
.platform-trend-chart article { display:grid;grid-template-rows:160px auto auto;justify-items:center;gap:4px;height:100%; }.platform-trend-chart article>div { display:flex;align-items:end;justify-content:center;gap:5px;width:100%;height:100%; }.platform-trend-chart article>div i { width:14px;min-height:8px;border-radius:4px 4px 1px 1px;background:linear-gradient(180deg,#2e90fa,#84caff); }.platform-trend-chart article>div i:last-child { background:linear-gradient(180deg,#7a5af8,#bdb4fe); }.platform-trend-chart article strong { color:#4e607a;font-size:9px; }.platform-trend-chart article span { color:#8290a5;font-size:9px; }
.platform-monitor-grid .platform-recent-tasks .platform-table th,.platform-monitor-grid .platform-recent-tasks .platform-table td { padding:9px 11px;font-size:10px; }.platform-monitor-grid .platform-recent-tasks td small { font-size:8px; }

.platform-query-graph .kg-panel__header span,
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
.platform-recent-tasks .kg-panel__header a,.platform-alert-overview .kg-panel__header a { color:#165dff;font-size:12px;text-decoration:none; }
.platform-recent-tasks td small { display:block;margin-top:2px;color:#8290a7;font-size:10px; }
.platform-status.is-阻断 { background:#fee4e2;color:#b42318; }
.platform-status.is-成功,.platform-status.is-完成,.platform-status.is-正常 { background:#dcfae6;color:#067647; }
.platform-status.is-运行中 { background:#eaf2ff;color:#165dff; }
.platform-status.is-异常,.platform-status.is-告警 { background:#fef0c7;color:#b54708; }
.platform-status.is-更新中,.platform-status.is-排队 { background:#eaf2ff;color:#165dff; }
.platform-alert-overview { display:grid;grid-template-rows:auto repeat(3,auto) 1fr; }
.platform-alert-overview>button { display:grid;grid-template-columns:8px minmax(0,1fr) 14px;align-items:start;gap:10px;padding:12px 14px;border:0;border-bottom:1px solid #e3ebf7;background:rgba(255,255,255,.64);text-align:left;cursor:pointer; }
.platform-alert-overview>button:hover { background:#f4f8ff; }
.platform-alert-overview>button>i { width:7px;height:7px;margin-top:5px;border-radius:50%;background:#f79009; }
.platform-alert-overview>button>i.is-严重 { background:#d92d20;box-shadow:0 0 0 4px #fee4e2; }
.platform-alert-overview>button>span { display:grid;gap:3px;min-width:0; }
.platform-alert-overview>button b { color:#8a97aa;font-size:10px; }
.platform-alert-overview>button strong { overflow:hidden;color:#253752;font-size:12px;text-overflow:ellipsis;white-space:nowrap; }
.platform-alert-overview>button em { color:#71809a;font-size:10px;font-style:normal; }
.platform-alert-overview>button u { align-self:center;color:#8da0ba;font-size:20px;text-decoration:none; }
.platform-alert-overview__review { align-self:end;justify-self:center;margin:12px;color:#165dff;font-size:12px;text-decoration:none; }

.platform-structure-overview { overflow:hidden; }
.platform-structure-overview>.kg-panel__header>span { color:#71809a;font-size:11px; }
.platform-structure-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr)); }
.platform-structure-chart { padding:15px 18px; }
.platform-structure-chart:first-child { border-right:1px solid #dce8f8; }
.platform-structure-chart header { display:flex;align-items:center;justify-content:space-between;margin-bottom:8px; }
.platform-structure-chart header>strong { color:#253752;font-size:13px; }
.platform-structure-chart header>a { color:#165dff;font-size:11px;text-decoration:none; }
.platform-donut-layout { display:grid;grid-template-columns:170px minmax(0,1fr);align-items:center;gap:20px;min-height:190px; }
.platform-donut { position:relative;display:grid;place-items:center;width:154px;height:154px;border-radius:50%; }
.platform-donut::after { position:absolute;inset:25px;border-radius:50%;background:#fff;box-shadow:0 0 0 1px #e5edf8;content:""; }
.platform-donut.is-entity { background:conic-gradient(#2e90fa 0 34%,#7a5af8 34% 57%,#12b76a 57% 74%,#f79009 74% 85%,#98a2b3 85% 100%); }
.platform-donut.is-relation { background:conic-gradient(#165dff 0 32%,#2e90fa 32% 52%,#06aed4 52% 70%,#7a5af8 70% 84%,#98a2b3 84% 100%); }
.platform-donut>span { position:relative;z-index:1;display:grid;gap:2px;text-align:center; }
.platform-donut>span strong { color:#10264c;font-size:19px; }
.platform-donut>span em { color:#8290a7;font-size:10px;font-style:normal; }
.platform-structure-legend article { display:grid;grid-template-columns:minmax(0,1fr) 160px;align-items:center;gap:14px;min-height:38px;border-bottom:1px solid #edf2f8; }
.platform-structure-legend article:last-child { border-bottom:0; }
.platform-structure-legend article>span { display:flex;align-items:center;gap:7px;min-width:0;overflow:hidden;color:#40516c;font-size:11px;white-space:nowrap; }
.platform-structure-legend article>span>i { flex:0 0 auto;width:8px;height:8px;border-radius:50%; }
.platform-structure-legend article em { overflow:hidden;color:#98a2b3;font-size:9px;font-style:normal;text-overflow:ellipsis;white-space:nowrap; }
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
.platform-table tr.is-clickable:focus-visible { outline: 2px solid #165dff; outline-offset: -2px; }
.is-clickable-card { cursor: pointer; transition: border-color .15s ease, box-shadow .15s ease, transform .15s ease; }
.is-clickable-card:hover,.is-clickable-card:focus-visible { border-color: #7aa9ee!important; box-shadow: 0 8px 20px rgba(22,93,255,.12)!important; transform: translateY(-1px); outline: none; }
.platform-card-arrow { color: #165dff!important; font-size: 11px!important; font-weight: 600!important; white-space: nowrap; }
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
.platform-task-filters a { color:#165dff;font-size:11px;text-decoration:none;white-space:nowrap; }

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
  background: #165dff;
  color: #fff;
  font-size: 18px;
  font-weight: 800;
}

.platform-review-notice.is-warning .platform-review-notice__icon { background: #f79009; }
.platform-review-notice strong { color: #10264c; font-size: 15px; }
.platform-review-notice p { margin: 5px 0 0; color: var(--text-secondary); font-size: 13px; line-height: 20px; }
.platform-review-notice__actions { display: flex; align-items: center; gap: 8px; }
.platform-review-notice__actions button,.platform-review-notice__actions a { display: inline-flex; align-items: center; height: 34px; padding: 0 13px; border: 1px solid #165dff; border-radius: 6px; background: #fff; color: #165dff; font-size: 12px; font-weight: 600; text-decoration: none; white-space: nowrap; cursor: pointer; }
.platform-review-notice__actions a { background: #165dff; color: #fff; }
.platform-review-notice.is-warning .platform-review-notice__actions button { border-color: #dc6803; color: #b54708; }
.platform-review-notice.is-warning .platform-review-notice__actions a { border-color: #dc6803; background: #dc6803; }

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
.platform-range-fields>i b { color:#71809a;font-size:10px;font-weight:400; }

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

.platform-cleaning-steps article {
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

.platform-cleaning-steps article:not(:last-child)::after {
  position: absolute;
  top: 50%;
  right: -17px;
  width: 16px;
  height: 2px;
  background: #9cc3ff;
  content: "";
}

.platform-cleaning-steps article:not(:last-child)::before {
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
  grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
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
.platform-query-question { grid-column:1/-1; }

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
  background: linear-gradient(180deg, #14b8a6, #165dff);
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

.platform-build-stats article {
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
  background: linear-gradient(90deg, #165dff, #22d3ee);
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

.platform-build-pipeline__body article {
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

.platform-build-pipeline__body article:not(:last-child)::after {
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
  background: linear-gradient(135deg, #165dff, #22d3ee);
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
  background: linear-gradient(135deg, #165dff, #0ea5e9);
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
  color: #d92d20;
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
  grid-template-columns: minmax(0, 1fr) 340px;
  grid-template-rows: auto minmax(460px, 1fr);
  align-items: stretch;
}

.platform-query-graph {
  grid-column: 1;
  grid-row: 2;
  min-height: 480px;
  overflow: hidden;
}

.platform-query-graph :deep(.kg-graph-viewport) {
  height: calc(100% - 100px);
}

.platform-graph-legend {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-start;
  gap: 8px 14px;
  min-height: 46px;
  padding: 8px 12px;
  border-bottom: 1px solid rgba(191, 215, 250, 0.96);
  background: rgba(248, 252, 255, 0.86);
}

.platform-graph-legend__item {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
  white-space: nowrap;
}

.platform-graph-legend__item i {
  display: inline-block;
  width: 13px;
  height: 13px;
  border: 2px solid #fff;
  border-radius: 50%;
  box-shadow: 0 1px 4px rgba(53, 77, 112, 0.16);
}

.platform-graph-legend__item.is-expert i { background: #1e8ff3; }
.platform-graph-legend__item.is-org i { background: #48c914; }
.platform-graph-legend__item.is-paper i { background: #762bd7; }
.platform-graph-legend__item.is-project i { background: #ffad17; }
.platform-graph-legend__item.is-event i { background: #eb2aa3; }
.platform-graph-legend__item.is-chain i { background: #14b8a6; }
.platform-graph-legend__item.is-field i { background: #2f6bff; }

.platform-query > .platform-detail {
  grid-column: 2;
  grid-row: 2;
  overflow: auto;
}

.platform-service-run,
.platform-detail,
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
  background: linear-gradient(135deg, #165dff, #0ea5e9);
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

.platform-node circle {
  fill: #21c1c3;
  stroke: #fff;
  stroke-width: 1.8;
  filter: drop-shadow(0 3px 6px rgba(53, 77, 112, 0.12));
}

.platform-node--main circle {
  fill: #1e8ff3;
  stroke: #fff;
}

.platform-node.is-expert circle { fill: #20bfc2; }
.platform-node.is-org circle { fill: #48c914; }
.platform-node.is-company circle { fill: #ffad17; }
.platform-node.is-paper circle { fill: #762bd7; }
.platform-node.is-topic circle { fill: #1f8ff1; }
.platform-node.is-project circle { fill: #eb2aa3; }
.platform-node.is-event circle { fill: var(--graph-gold, #f59e0b); }

.platform-node text {
  fill: #4f5d70;
  font-size: 12px;
  font-weight: 500;
  text-anchor: middle;
  dominant-baseline: hanging;
  transform: translateY(18px);
  paint-order: stroke;
  stroke: rgba(255, 255, 255, 0.9);
  stroke-width: 3px;
  stroke-linejoin: round;
}

.platform-node--main text {
  fill: #fff;
  font-size: 15px;
  font-weight: 600;
  dominant-baseline: middle;
  transform: none;
  stroke: transparent;
}

.platform-network-lines line,
.platform-network-line {
  stroke: #b8c1ce;
  stroke-width: 1.4;
  marker-end: url(#platform-arrow);
}

.platform-network-lines--service line {
  marker-end: url(#service-arrow);
}

.platform-network-line.is-primary { stroke: #4080ff; stroke-width: 1.8; }
.platform-network-line.is-green { stroke: #00b42a; stroke-width: 1.8; }
.platform-network-line.is-orange { stroke: #ff7d00; stroke-width: 1.8; }
.platform-network-line.is-purple { stroke: #722ed1; stroke-width: 1.8; }

.platform-detail__body {
  display: grid;
  gap: 14px;
  padding: 14px;
}

.platform-detail__tabs {
  display: inline-flex;
  flex: 0 0 auto;
  gap: 0;
  padding: 2px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: rgba(255, 255, 255, 0.66);
}

.platform-detail__tabs button {
  height: 28px;
  padding: 0 10px;
  border: 0;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.platform-detail__tabs button.is-active {
  background: var(--surface);
  color: var(--primary);
  font-weight: 600;
  box-shadow: 0 1px 4px rgba(22, 93, 255, 0.12);
}

.platform-detail dl {
  display: grid;
  gap: 8px;
  margin: 0;
}

.platform-detail dl div {
  display: grid;
  grid-template-columns: 98px minmax(0, 1fr);
  gap: 10px;
  padding: 9px 10px;
  border-radius: 6px;
  background: #f7faff;
}

.platform-detail dt,
.platform-detail dd {
  margin: 0;
  font-size: 14px;
  line-height: 20px;
}

.platform-detail dt {
  color: var(--text-secondary);
}

.platform-detail ul,
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

.platform-provenance {
  display: grid;
  gap: 12px;
  padding: 12px;
  border: 1px solid #cfe0ff;
  border-radius: 8px;
  background: linear-gradient(180deg, #f7faff 0%, #fff 100%);
}

.platform-provenance__title {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.platform-provenance__title span {
  color: #10264c;
  font-size: 14px;
  font-weight: 700;
}

.platform-provenance__title em {
  padding: 2px 8px;
  border-radius: 999px;
  background: #e8f1ff;
  color: var(--primary);
  font-size: 12px;
  font-style: normal;
}

.platform-provenance__target {
  display: grid;
  gap: 4px;
  padding: 11px 12px;
  border-radius: 7px;
  background: #eaf2ff;
}

.platform-provenance__target strong {
  color: #16355f;
  font-size: 14px;
  line-height: 20px;
}

.platform-provenance__target span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-provenance__section-title {
  margin: 2px 0 -4px;
  color: #536987;
  font-size: 12px;
  line-height: 18px;
  font-weight: 600;
}

.platform-detail .platform-provenance__source {
  gap: 6px;
}

.platform-detail .platform-provenance__source div {
  grid-template-columns: 70px minmax(0, 1fr);
  padding: 7px 8px;
  background: rgba(255, 255, 255, 0.8);
}

.platform-provenance code {
  color: #2458a6;
  font-family: Consolas, Monaco, monospace;
  font-size: 12px;
  overflow-wrap: anywhere;
}

.platform-provenance__database {
  margin: 0;
  padding: 7px 9px;
  border-radius: 6px;
  background: #f3f7fd;
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-provenance__evidence-list {
  display: grid;
  gap: 8px;
}

.platform-provenance__evidence-list article {
  display: grid;
  gap: 6px;
  padding: 9px 10px;
  border: 1px solid #e1eaf8;
  border-radius: 7px;
  background: #fff;
}

.platform-provenance__evidence-list header,
.platform-provenance__evidence-list p {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  margin: 0;
}

.platform-provenance__evidence-list header strong,
.platform-provenance__evidence-list p b {
  color: #243b62;
  font-size: 12px;
  line-height: 18px;
}

.platform-provenance__evidence-list article > span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-provenance__task-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  padding: 0 4px;
}

.platform-provenance__task-meta span {
  color: var(--text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.platform-provenance__task-meta button {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--primary);
  font-size: 12px;
  cursor: pointer;
}

.platform-provenance__source b,
.platform-provenance__result b {
  color: #00a870;
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
  .platform-detail,
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

  .platform-query-graph,
  .platform-query > .platform-detail {
    grid-column: 1;
    grid-row: auto;
  }

  .platform-query-graph {
    min-height: 460px;
  }

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

.asset-change-mask{position:fixed;z-index:49;inset:0;border:0;background:rgba(16,36,76,.22)}
.asset-change-drawer{position:fixed;z-index:50;top:0;right:0;display:grid;grid-template-rows:auto auto minmax(0,1fr) auto;width:min(820px,78vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 42px rgba(34,74,132,.22)}
.asset-change-drawer>header{display:flex;align-items:flex-start;justify-content:space-between;padding:20px;border-bottom:1px solid #dce8f8;background:#fff}.asset-change-drawer>header span{color:#165dff;font-size:11px}.asset-change-drawer h2{margin:6px 0 3px;font-size:20px}.asset-change-drawer header p{margin:0;color:#718098;font-size:12px}.asset-change-drawer header>button{width:31px;height:31px;border:0;border-radius:5px;background:#f0f4fa;color:#52647f;font-size:20px;cursor:pointer}
.asset-change-summary{display:grid;grid-template-columns:repeat(2,1fr);gap:10px;padding:14px}.asset-change-summary article{display:grid;gap:5px;padding:14px;border:1px solid #c7dcfb;border-radius:7px;background:#fff}.asset-change-summary span{color:#718098;font-size:11px}.asset-change-summary strong{color:#165dff;font-size:24px}.asset-change-summary article:last-child strong{color:#079455}
.asset-change-table{min-height:0;overflow:auto;padding:0 14px 14px}.asset-change-table table{width:100%;border-collapse:collapse;border:1px solid #dce8f8;background:#fff;font-size:12px}.asset-change-table th,.asset-change-table td{height:48px;padding:10px 12px;border-bottom:1px solid #e3ebf6;text-align:left}.asset-change-table th{position:sticky;top:0;background:#f3f7fc;color:#62728a}.asset-change-table td{color:#344861}.asset-change-table code{color:#165dff;font-family:inherit}
.asset-change-drawer>footer{display:flex;align-items:center;justify-content:space-between;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.asset-change-drawer>footer span{color:#718098;font-size:11px}.asset-change-drawer>footer a{height:32px;padding:0 12px;border-radius:5px;background:#165dff;color:#fff;font-size:11px;line-height:32px;text-decoration:none}
@media(max-width:760px){.asset-change-drawer{width:94vw}.asset-change-table table{min-width:700px}}
</style>
