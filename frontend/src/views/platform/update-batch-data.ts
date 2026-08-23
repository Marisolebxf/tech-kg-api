export type UpdateBatchStatus = '处理中' | '待审核' | '已完成'
export type ProcessingStatus = '已完成' | '待人工处理' | '人工处理完成'

export type UpdateBatch = {
  id: string
  name: string
  updateDate: string
  dataWindow: string
  source: string
  trigger: string
  input: number
  entities: number
  relations: number
  completed: number
  abnormal: number
  progress: number
  status: UpdateBatchStatus
  startedAt: string
  completedAt: string
}

export type ProcessingInstance = {
  id: string
  batchId: string
  stage: '数据处理' | '图谱构建'
  kind: '实体' | '关系' | '属性'
  objectId: string
  objectName: string
  objectType: string
  action: string
  sourceTable: string
  sourceRecordId: string
  sourceEntity?: { name: string; type: string; sourceTable: string; sourceRecordId: string }
  targetEntity?: { name: string; type: string; sourceTable: string; sourceRecordId: string }
  relationEvidence?: string
  rule: string
  confidence: string
  result: string
  status: ProcessingStatus
  processedAt: string
  reviewType?: string
}

export type BatchStageStat = {
  batchId: string
  stage: '数据处理' | '图谱构建'
  input: number
  completed: number
  abnormal: number
  progress: number
  currentStep: string
  status: UpdateBatchStatus
}

export const updateBatches: UpdateBatch[] = [
  {
    id: 'UPD-20260714', name: '2026-07-14 数据更新', updateDate: '2026-07-14',
    dataWindow: '2026-07-13 02:00—2026-07-14 02:00', source: '科技要素数据库', trigger: '每日定时更新',
    input: 25140, entities: 8426, relations: 35620, completed: 43335, abnormal: 711, progress: 99,
    status: '待审核', startedAt: '2026-07-14 02:00:00', completedAt: '等待人工处理完成',
  },
  {
    id: 'UPD-20260713', name: '2026-07-13 数据更新', updateDate: '2026-07-13',
    dataWindow: '2026-07-12 02:00—2026-07-13 02:00', source: '科技要素数据库', trigger: '每日定时更新',
    input: 23876, entities: 7981, relations: 32450, completed: 40431, abnormal: 42, progress: 100,
    status: '已完成', startedAt: '2026-07-13 02:00:00', completedAt: '2026-07-13 02:36:42',
  },
  {
    id: 'UPD-20260712', name: '2026-07-12 数据更新', updateDate: '2026-07-12',
    dataWindow: '2026-07-11 02:00—2026-07-12 02:00', source: '科技要素数据库', trigger: '每日定时更新',
    input: 21942, entities: 7360, relations: 30128, completed: 37488, abnormal: 0, progress: 100,
    status: '已完成', startedAt: '2026-07-12 02:00:00', completedAt: '2026-07-12 02:31:08',
  },
]

export const processingInstances: ProcessingInstance[] = [
  {
    id: 'PI-20260714-0101', batchId: 'UPD-20260714', stage: '图谱构建', kind: '实体', objectId: 'LLM-BATCH-20260714-01', objectName: '大模型抽取批次', objectType: '流程实例', action: '批量实体关系抽取',
    sourceTable: '论文成果批次', sourceRecordId: 'BATCH-0714-LLM-01', rule: 'LLM-SCHEMA-FAIL-001', confidence: '', result: '批量输出异常，流程未产生可验收结果', status: '待人工处理', processedAt: '2026-07-14 10:24:00', reviewType: '模型批量输出异常',
  },
  {
    id: 'PI-20260714-0102', batchId: 'UPD-20260714', stage: '图谱构建', kind: '属性', objectId: 'SCHEMA-BATCH-20260714-02', objectName: 'Schema 映射批次', objectType: '流程实例', action: '批量 Schema 映射',
    sourceTable: '企业基本信息表', sourceRecordId: 'BATCH-0714-SCHEMA-02', rule: 'SCHEMA-MAP-FAIL-006', confidence: '', result: '3 个公共字段映射失败，未产生映射结果', status: '待人工处理', processedAt: '2026-07-14 10:18:00', reviewType: 'Schema 批量映射失败',
  },
  {
    id: 'PI-20260714-0103', batchId: 'UPD-20260714', stage: '数据处理', kind: '属性', objectId: 'DICT-BATCH-20260714-03', objectName: '专利状态标准化批次', objectType: '流程实例', action: '公共字典标准化',
    sourceTable: '专利基本信息表', sourceRecordId: 'BATCH-0714-DICT-03', rule: 'DICT-CONFIG-FAIL-003', confidence: '', result: '公共字典版本异常，未产生标准化结果', status: '待人工处理', processedAt: '2026-07-14 10:12:00', reviewType: '公共字典配置异常',
  },
  {
    id: 'PI-20260714-0104', batchId: 'UPD-20260714', stage: '图谱构建', kind: '实体', objectId: 'EXPERT_TMP_20566', objectName: '李晓峰 / Li Xiaofeng', objectType: '候选专家实体', action: '实体对齐',
    sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-20566', rule: 'ALIGN-RUNTIME-004', confidence: '', result: '单任务执行超时，未产生候选结果', status: '待人工处理', processedAt: '2026-07-14 10:08:00', reviewType: '单任务执行失败',
  },
  {
    id: 'PI-20260714-0001', batchId: 'UPD-20260714', stage: '图谱构建', kind: '实体', objectId: 'expert-10028', objectName: '张明远', objectType: '科技专家', action: '新增实体',
    sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-10286', rule: '专家实体标准化与融合规则', confidence: '0.94', result: '生成标准实体 expert-10028', status: '已完成', processedAt: '2026-07-14 02:14:08',
  },
  {
    id: 'PI-20260714-0002', batchId: 'UPD-20260714', stage: '图谱构建', kind: '实体', objectId: 'org-10018', objectName: '清华大学', objectType: '科技机构', action: '属性更新',
    sourceTable: '科技机构信息表', sourceRecordId: 'ORG-10018', rule: '机构名称标准化规则', confidence: '0.98', result: '更新机构简称与统一标识', status: '已完成', processedAt: '2026-07-14 02:15:26',
  },
  {
    id: 'PI-20260714-0003', batchId: 'UPD-20260714', stage: '图谱构建', kind: '关系', objectId: 'e40', objectName: '数字抽象 → 矩阵分析', objectType: '主题相近', action: '新增关系',
    sourceTable: '实体主题关联表', sourceRecordId: 'TOPIC-DIGITAL-040',
    sourceEntity: { name: '数字抽象', type: '研究方向', sourceTable: '实体主题关联表', sourceRecordId: 'TOPIC-DIGITAL-040' },
    targetEntity: { name: '矩阵分析', type: '研究方向', sourceTable: '实体主题关联表', sourceRecordId: 'TOPIC-MATRIX-018' },
    relationEvidence: '两端主题共同出现在论文关键词和两跳图谱路径中', rule: '两跳路径与主题共现规则', confidence: '0.72', result: '候选关系已隔离，等待人工确认', status: '待人工处理', processedAt: '2026-07-14 02:18:12', reviewType: '低置信度',
  },
  {
    id: 'PI-20260714-0004', batchId: 'UPD-20260714', stage: '图谱构建', kind: '实体', objectId: 'EXPERT_TMP_20418', objectName: '张明远 / Zhang Mingyuan', objectType: '候选专家实体', action: '实体合并',
    sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-20418', rule: '专家实体对齐规则', confidence: '0.82', result: '命中两个存量实体，等待人工确认', status: '待人工处理', processedAt: '2026-07-14 02:21:44', reviewType: '实体冲突',
  },
  {
    id: 'PI-20260714-0005', batchId: 'UPD-20260714', stage: '图谱构建', kind: '关系', objectId: 'REL_TMP_89321', objectName: '华南智能芯片 → 腾讯', objectType: '企业合作', action: '新增关系',
    sourceTable: '企业合作记录表', sourceRecordId: 'COOP-89321-A',
    sourceEntity: { name: '华南智能芯片', type: '科技企业', sourceTable: '科技企业信息表', sourceRecordId: 'ENTERPRISE-01286' },
    targetEntity: { name: '腾讯', type: '科技企业', sourceTable: '科技企业信息表', sourceRecordId: 'ENTERPRISE-00700' },
    relationEvidence: '当前仅命中一条合作公告，未达到双来源证据要求', rule: '关系证据完整性规则', confidence: '0.74', result: '候选关系已隔离', status: '待人工处理', processedAt: '2026-07-14 02:23:18', reviewType: '关系证据不足',
  },
  {
    id: 'PI-20260714-0006', batchId: 'UPD-20260714', stage: '图谱构建', kind: '属性', objectId: 'ATTR_TMP_77102', objectName: '张明远·任职机构', objectType: '实体属性', action: '属性更新',
    sourceTable: '专家任职经历表', sourceRecordId: 'EMPLOYMENT-77102', rule: '任职时间有效性规则', confidence: '0.78', result: '任职时间冲突，等待人工确认', status: '待人工处理', processedAt: '2026-07-14 02:24:09', reviewType: '属性冲突',
  },
  {
    id: 'PI-20260714-0007', batchId: 'UPD-20260714', stage: '数据处理', kind: '实体', objectId: 'paper-P202607130089', objectName: '重复论文成果记录', objectType: '论文成果', action: '记录去重',
    sourceTable: '论文成果表', sourceRecordId: 'P202607130089', rule: '论文唯一性规则', confidence: '0.69', result: '发现三条重复记录，等待确认主记录', status: '待人工处理', processedAt: '2026-07-14 02:25:31', reviewType: '唯一性冲突',
  },
  {
    id: 'PI-20260714-0008', batchId: 'UPD-20260714', stage: '数据处理', kind: '实体', objectId: 'paper-P202607130104', objectName: '论文标题为空', objectType: '论文成果', action: '属性补全',
    sourceTable: '论文成果表', sourceRecordId: 'P202607130104', rule: '论文必填完整性规则', confidence: '0.91', result: '标题缺失，等待人工补全', status: '待人工处理', processedAt: '2026-07-14 02:26:04', reviewType: '必填缺失',
  },
  {
    id: 'PI-20260714-0009', batchId: 'UPD-20260714', stage: '数据处理', kind: '属性', objectId: 'paper-P202607130126', objectName: '来源类型无法映射', objectType: '论文来源类型', action: '枚举映射',
    sourceTable: '论文成果表', sourceRecordId: 'P202607130126', rule: '来源类型枚举规则', confidence: '0.88', result: '未知枚举值等待人工映射', status: '待人工处理', processedAt: '2026-07-14 02:26:38', reviewType: '枚举异常',
  },
  {
    id: 'PI-20260714-0010', batchId: 'UPD-20260714', stage: '数据处理', kind: '属性', objectId: 'paper-P202607130068', objectName: '论文标题缺失', objectType: '论文成果', action: '属性补全', sourceTable: '论文成果表', sourceRecordId: 'P202607130068', rule: '论文必填完整性规则', confidence: '0.93', result: '人工补全标题后校验通过', status: '人工处理完成', processedAt: '2026-07-14 09:18:42', reviewType: '必填缺失',
  },
  {
    id: 'PI-20260714-0011', batchId: 'UPD-20260714', stage: '图谱构建', kind: '关系', objectId: 'REL_TMP_89106', objectName: '深圳先进院 → 华南智能芯片', objectType: '机构合作', action: '新增关系', sourceTable: '企业合作记录表', sourceRecordId: 'COOP-89106-B', rule: '关系证据完整性规则', confidence: '0.76', result: '补充第二条证据后通过', status: '人工处理完成', processedAt: '2026-07-14 09:36:15', reviewType: '关系证据不足',
  },
  {
    id: 'PI-20260714-0012', batchId: 'UPD-20260714', stage: '图谱构建', kind: '实体', objectId: 'expert-20372', objectName: '周启航 / Zhou Qihang', objectType: '科技专家', action: '实体合并', sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-20372', rule: '专家实体对齐规则', confidence: '0.81', result: '机构别名确认后完成合并', status: '人工处理完成', processedAt: '2026-07-14 10:02:08', reviewType: '实体冲突',
  },
  {
    id: 'PI-20260714-0013', batchId: 'UPD-20260714', stage: '数据处理', kind: '属性', objectId: 'patent-CN2026102764', objectName: '专利法律状态无法映射', objectType: '专利数据', action: '枚举映射', sourceTable: '专利基本信息表', sourceRecordId: 'CN2026102764', rule: '专利法律状态字典规则', confidence: '0.89', result: '映射为实质审查后通过', status: '人工处理完成', processedAt: '2026-07-14 10:21:47', reviewType: '枚举异常',
  },
  {
    id: 'PI-20260713-0008', batchId: 'UPD-20260713', stage: '图谱构建', kind: '实体', objectId: 'expert-88102', objectName: '陈卓 / Chen Zhuo', objectType: '科技专家', action: '实体合并',
    sourceTable: '专家基本信息表', sourceRecordId: 'EXPERT-19882', rule: '专家实体对齐规则', confidence: '0.72', result: '人工确认后合并至 expert-88102', status: '人工处理完成', processedAt: '2026-07-13 19:16:00', reviewType: '低置信度',
  },
]

export const batchStageStats: BatchStageStat[] = [
  { batchId: 'UPD-20260714', stage: '数据处理', input: 25140, completed: 24755, abnormal: 385, progress: 100, currentStep: '质量校验完成', status: '待审核' },
  { batchId: 'UPD-20260714', stage: '图谱构建', input: 24755, completed: 43660, abnormal: 326, progress: 99, currentStep: '实体与关系异常处理', status: '待审核' },
  { batchId: 'UPD-20260713', stage: '数据处理', input: 23876, completed: 23876, abnormal: 0, progress: 100, currentStep: '标准数据写入完成', status: '已完成' },
  { batchId: 'UPD-20260713', stage: '图谱构建', input: 23876, completed: 40431, abnormal: 42, progress: 100, currentStep: '人工处理完成', status: '已完成' },
  { batchId: 'UPD-20260712', stage: '数据处理', input: 21942, completed: 21942, abnormal: 0, progress: 100, currentStep: '标准数据写入完成', status: '已完成' },
  { batchId: 'UPD-20260712', stage: '图谱构建', input: 21942, completed: 37488, abnormal: 0, progress: 100, currentStep: '图谱入库完成', status: '已完成' },
]

export const getUpdateBatch = (id: string) => updateBatches.find((item) => item.id === id)
export const getBatchProcessingInstances = (batchId: string) => processingInstances.filter((item) => item.batchId === batchId)
export const getProcessingInstance = (id: string) => processingInstances.find((item) => item.id === id)
export const getBatchStageStat = (batchId: string, stage: BatchStageStat['stage']) => batchStageStats.find((item) => item.batchId === batchId && item.stage === stage)
