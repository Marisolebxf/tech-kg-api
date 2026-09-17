export type ReviewStatus = '待处理' | '已完成' | '已撤销' | '已驳回' | '重跑中' | '重跑失败'
export type ReviewPriority = 'P0' | 'P1' | 'P2'

/** C 类队列状态徽标：在既有映射上细化 RERUNNING/RERUN_FAILED（此前都 fallback 到"待处理"）。 */
export const extractCaseStatusBadge = (rawStatus: string): ReviewStatus => {
  if (rawStatus === 'RERUNNING') return '重跑中'
  if (rawStatus === 'RERUN_FAILED') return '重跑失败'
  if (rawStatus === 'RESOLVED') return '已完成'
  if (rawStatus === 'REJECTED') return '已驳回'
  if (rawStatus === 'CANCELLED') return '已撤销'
  return '待处理'
}

export type ReviewRecord = {
  id: string
  batch: string
  module: string
  node: string
  type: string
  /** 后端原始分类；展示统一用 getHandleCategory */
  category?: string
  domain: string
  objectType: string
  objectId: string
  object: string
  ruleId: string
  evidence: string
  score: string
  handler: string
  status: ReviewStatus
  updatedAt: string
  sourceResult: string
  suggestion: string
  sourceTable: string
  sourceRecordId: string
  decision?: string
  decisionNote?: string
  completedAt?: string
  dataWindow?: string
  confidenceValue?: string
  confidenceLabel?: string
}

export const reviewRecords: ReviewRecord[] = [
  {
    id: 'PI-20260714-0104', batch: 'UPD-20260714', module: '图谱构建', node: '实体对齐消歧', type: '专家实体对齐歧义', domain: '人才',
    objectType: '专家实体', objectId: 'expert_id=EXPERT_20566', object: '李晓峰 / Li Xiaofeng（中国科学院自动化研究所）', ruleId: 'ALIGN-AMBIGUITY-004',
    evidence: '召回 3 个高相似存量专家，无法自动消歧合并', score: '0.81', handler: '王审核', status: '待处理', updatedAt: '07-14 10:08',
    sourceResult: '候选已隔离，等待人工确认合并目标', suggestion: '核对候选与存量后合并或新建', sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-20566',
  },
  {
    id: 'PI-20260714-0012', batch: 'UPD-20260714', module: '图谱构建', node: '实体结果校验', type: '专家实体重复冲突', domain: '人才',
    objectType: '专家实体', objectId: 'EXPERT_TMP_20372', object: '周启航 / Zhou Qihang（深圳先进技术研究院）', ruleId: 'ALIGN-ENTITY-017',
    evidence: '候选实体与存量实体同名，任职机构别名未归一', score: '0.81', handler: '陈治理', status: '已完成', updatedAt: '07-14 10:02',
    sourceResult: '已归一机构别名并合并至 Expert_20372', suggestion: '机构别名确认后通过', sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-20372',
    decision: '修正后重跑并通过', decisionNote: '确认两个机构名称为同一机构别名，从实体对齐节点重跑后完成合并。', completedAt: '2026-07-14 10:02:08',
  },
  {
    id: 'PI-20260713-0008', batch: 'UPD-20260713', module: '图谱构建', node: '实体结果校验', type: '专家实体置信度不足', domain: '专利',
    objectType: '专利发明人实体', objectId: 'EXPERT_TMP_19882', object: '陈卓 / Chen Zhuo（专利发明人）', ruleId: 'ALIGN-CONFIDENCE-003',
    evidence: '姓名和专利发明人一致，机构别名经人工确认后完成合并', score: '0.72', handler: '陈治理', status: '已完成', updatedAt: '07-12 19:16',
    sourceResult: '已合并至 Expert_88102', suggestion: '审核完成',
    sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-19882', decision: '修正后重跑并通过', decisionNote: '已核对机构别名与专利发明人信息，从实体对齐节点重跑并合并至 Expert_88102。', completedAt: '2026-07-13 19:16:00',
  },
]

export const getReviewRecord = (instanceId: string) => reviewRecords.find((item) => item.id === instanceId)

export const getReviewConfidence = (record: ReviewRecord) => {
  if (record.module === '数据处理') return { value: '—', label: '', source: '' }
  if (!record.score) return { value: '—', label: '', source: '' }
  const score = Number(record.score)
  if (score >= 0.9) return { value: '—', label: '', source: '' }
  return {
    value: record.score,
    label: '低于阈值',
    source: '',
  }
}

export const getReviewPriority = (record: ReviewRecord): { level: ReviewPriority; reason: string; policy: string; scope: string; strategy: string } => {
  const common = { level: 'P1' as const, policy: 'REVIEW-PRIORITY-v1.1', scope: '中风险', strategy: '隔离当前任务，其他任务继续执行；修正后从当前节点重跑' }
  if (record.type.includes('实体重复冲突')) return { ...common, reason: '单个候选实体合并冲突，当前结果已隔离' }
  return { ...common, reason: '当前异常结果已隔离，未进入下游' }
}

/**
 * 处置模式（3 个产活模板；graph-build 移交通道与 6 个休眠模板已删除）。
 * T_DIRECT=入库直判写图 · T_LINK=实体对齐裁决 · T_EXTRACT_FAIL=抽取失败重跑
 */
export type ReviewTemplateId =
  | 'T_LINK'
  | 'T_DIRECT'
  | 'T_EXTRACT_FAIL'

export type ReviewAction = {
  id: string
  label: string
  kind: 'primary' | 'secondary' | 'danger'
  rerun?: boolean
  actionKind?: 'apply_and_rerun' | 'isolate' | 'reject_upstream' | 'discard' | 'escalate'
}

export type ReviewTemplateMeta = {
  id: ReviewTemplateId
  title: string
  question: string
  actions: ReviewAction[]
}

const templateCatalog: Record<ReviewTemplateId, ReviewTemplateMeta> = {
  T_LINK: {
    id: 'T_LINK',
    title: '实体对齐裁决',
    question: '候选与存量是否为同一实体？',
    actions: [
      { id: 'entity-confirm', label: '确认实体裁决', kind: 'primary', actionKind: 'apply_and_rerun' },
      { id: 'reject-candidate', label: '驳回候选', kind: 'secondary', actionKind: 'isolate' },
    ],
  },
  T_DIRECT: {
    id: 'T_DIRECT',
    title: '入库决策',
    question: '该候选实体/关系能否进图？通过直接写图，驳回丢弃。',
    actions: [
      { id: 'accept', label: '通过·入库', kind: 'primary', actionKind: 'apply_and_rerun' },
      { id: 'reject', label: '驳回·丢弃', kind: 'danger', actionKind: 'discard' },
    ],
  },
  T_EXTRACT_FAIL: {
    id: 'T_EXTRACT_FAIL',
    title: '抽取失败重跑',
    question: '该源记录在批次抽取中解析失败，点击重跑只重读该记录（新执行 · 类别=重新执行）。',
    actions: [
      { id: 'rerun-record', label: '重跑该记录', kind: 'primary', rerun: true, actionKind: 'apply_and_rerun' },
      { id: 'discard-record', label: '忽略该记录', kind: 'secondary', actionKind: 'discard' },
    ],
  },
}

const modeByRulePrefix = (ruleId: string): ReviewTemplateId | null => {
  const id = ruleId.toUpperCase()
  // 生产行 ruleId 即服务端 templateId（队列映射 row.templateId → ruleId）；
  // 演示种子走 ALIGN- 前缀
  if (id === 'T_DIRECT' || id === 'T_EXTRACT_FAIL' || id === 'T_LINK') return id
  if (/^ALIGN-/.test(id)) return 'T_LINK'
  return null
}

export const getReviewTemplateId = (record: ReviewRecord): ReviewTemplateId => {
  const fromRule = modeByRulePrefix(record.ruleId || '')
  if (fromRule) return fromRule
  // 旧演示种子/无前缀记录统一按实体对齐裁决展示
  return 'T_LINK'
}

export const getReviewTemplate = (record: ReviewRecord): ReviewTemplateMeta => {
  const id = getReviewTemplateId(record)
  return templateCatalog[id]
}

export type PipelineStepId =
  | 'source'
  | 'normalize'
  | 'schema'
  | 'extract'
  | 'align'
  | 'validate'
  | 'persist'

export type PipelineStep = {
  id: PipelineStepId
  name: string
  phase: '数据处理' | '图谱构建'
}

export const PIPELINE_STEPS: PipelineStep[] = [
  { id: 'source', name: '数据接入', phase: '数据处理' },
  { id: 'normalize', name: '清洗标准化', phase: '数据处理' },
  { id: 'schema', name: 'Schema 映射', phase: '图谱构建' },
  { id: 'extract', name: '实体关系抽取', phase: '图谱构建' },
  { id: 'align', name: '实体对齐消歧', phase: '图谱构建' },
  { id: 'validate', name: '质量校验', phase: '图谱构建' },
  { id: 'persist', name: '图谱入库', phase: '图谱构建' },
]

const pipelineStepById = Object.fromEntries(
  PIPELINE_STEPS.map((step) => [step.id, step]),
) as Record<PipelineStepId, PipelineStep>

export const getPipelineStep = (id: PipelineStepId): PipelineStep => pipelineStepById[id]

/** 阻断节点由工单语义推导；T_LINK 固定 align，T_EXTRACT_FAIL 固定 extract，
 *  T_DIRECT 的 step id 是 manifest 自定义的，按 node/type 语义归并展示。 */
export const resolvePipelineStep = (record: ReviewRecord): PipelineStep => {
  const tid = getReviewTemplateId(record)
  const type = record.type
  const node = record.node || ''

  if (tid === 'T_EXTRACT_FAIL') return getPipelineStep('extract')
  if (tid === 'T_LINK') return getPipelineStep('align')

  if (/入库|写入|persist/i.test(node) || /入库|写入/.test(type)) return getPipelineStep('persist')
  if (/接入|source/i.test(node)) return getPipelineStep('source')
  if (/质量校验|关系证据|属性校验|证据校验/.test(node) || /关系证据|属性冲突|关系类型置信/.test(type)) {
    return getPipelineStep('validate')
  }
  if (/对齐|消歧|实体结果|align/i.test(node) || /对齐|消歧|实体重复|实体置信/.test(type)) {
    return getPipelineStep('align')
  }
  if (/抽取|大模型|extract|llm/i.test(node) || /抽取|大模型/.test(type)) {
    return getPipelineStep('extract')
  }
  if (/Schema|映射|分类/.test(node) || /Schema|映射|类型判断/.test(type)) {
    return getPipelineStep('schema')
  }
  if (/清洗|标准|必填|唯一|枚举|normalize|quality/i.test(node) || /标准|必填|唯一|枚举/.test(type)) {
    return getPipelineStep('normalize')
  }
  return getPipelineStep('validate')
}

/** 人工处理业务分类（短名；仅顶部 chips 筛选，列表展示阻断节点） */
export type HandleCategory =
  | '清洗标准化'
  | 'Schema 映射'
  | '抽取配置'
  | '实体对齐'
  | '质量校验'

export const HANDLE_CATEGORIES: HandleCategory[] = [
  '清洗标准化',
  'Schema 映射',
  '抽取配置',
  '实体对齐',
  '质量校验',
]

const categoryByStep: Partial<Record<PipelineStepId, HandleCategory>> = {
  normalize: '清洗标准化',
  schema: 'Schema 映射',
  extract: '抽取配置',
  align: '实体对齐',
  validate: '质量校验',
}

export const getHandleCategory = (record: ReviewRecord): HandleCategory => {
  const step = resolvePipelineStep(record)
  if (step.id === 'source' || step.id === 'persist') return '质量校验'
  return categoryByStep[step.id] ?? '质量校验'
}

export const getReviewCategory = (record: ReviewRecord): HandleCategory => getHandleCategory(record)

export const getDecisionQuestion = (record: ReviewRecord): string => {
  switch (getReviewTemplateId(record)) {
    case 'T_LINK':
      return '候选与存量是否为同一实体？'
    case 'T_DIRECT':
      return '该候选实体/关系能否进图？'
    case 'T_EXTRACT_FAIL':
      return '该源记录是否重跑？'
    default:
      return '如何临时处置本条异常？'
  }
}

export type ReviewConsequence = {
  writeTarget: string
  rerunAnchor: string
  rerunStepId: PipelineStepId
  phase: PipelineStep['phase']
  preferStep?: PipelineStepId
}

export const getReviewConsequence = (record: ReviewRecord): ReviewConsequence => {
  const step = resolvePipelineStep(record)
  const tid = getReviewTemplateId(record)
  let writeTarget = '处理结果'
  if (tid === 'T_LINK') writeTarget = '实体对齐结果'
  else if (tid === 'T_DIRECT') writeTarget = '图数据库直写'
  else if (tid === 'T_EXTRACT_FAIL') writeTarget = '失败记录重跑'

  return {
    writeTarget,
    rerunAnchor: step.name,
    rerunStepId: step.id,
    phase: step.phase,
  }
}

export const getSedimentHint = (record: ReviewRecord): string => {
  if (getReviewTemplateId(record) === 'T_LINK') {
    return '将别名写入别名表，同类候选自动归一'
  }
  return ''
}

export const getImpactScope = (record: ReviewRecord): '批次级' | '任务级' => (
  getReviewPriority(record).level === 'P0' ? '批次级' : '任务级'
)

/** 图标签/边类型 → 中文名（标题/标签展示用；未命中回退英文原值） */
const LABEL_ZH: Record<string, string> = {
  // 实体标签
  Paper: '论文', Scholar: '学者', Expert: '专家', Person: '人才',
  Organization: '机构', Patent: '专利', PatentFamily: '专利家族',
  Project: '项目', Product: '产品', Journal: '期刊', Keyword: '关键词',
  Event: '事件', News: '新闻', Report: '报告', Datasource: '数据源',
  IndustryNode: '产业链节点', IndustryChain: '产业链',
  // 关系边类型
  CITES: '引用', EMPLOYED_BY: '任职', COOPERATE_WITH: '合作',
  AUTHORED_BY: '著作', INVENTED_BY: '发明', PUBLISHED_IN: '发表',
  FUNDED_BY: '资助', INVESTS_IN: '投资', ACQUIRES: '收购',
  SUBSIDIARY_OF: '隶属', AFFILIATED_WITH: '关联',
  ACTUAL_CONTROLLER_OF: '实际控制', BENEFICIAL_OWNER_OF: '受益所有',
  LEGAL_REP_OF: '法代', EXECUTIVE_OF: '任职', LEADS: '领导',
  MEMBER_OF_FAMILY: '家族成员', CHILD_OF: '子女', INVOLVED_IN: '参与',
  PRODUCES: '生产', HAS_OUTPUT: '产出', HAS_PARTICIPANT: '参与者',
  HAS_NEWS: '新闻', HAS_NODE: '节点', BELONGS_TO_NODE: '归属节点',
  COVERS_CHAIN: '覆盖链条', DOWNSTREAM_OF: '下游',
  REFERENCED_BY: '被引用', APPLIED_BY: '申请', SHAREHOLDER_OF: '持股',
}

export const labelZh = (key: string | undefined | null): string => {
  if (!key) return ''
  return LABEL_ZH[key] ?? key
}
