import { http } from './http'
import { unwrapApiResponse, type ApiResponse } from './graphSearch'

export type TaskStatus = '执行中' | '执行出错' | '等待人工审核' | '执行完成'

export interface UpdateBatch {
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
  status: string
  startedAt: string
  completedAt: string
}

export interface ProcessStep {
  id: string
  phase: '数据处理' | '图谱构建'
  name: string
  status: '成功' | '运行中' | '需人工处理' | '待执行'
  count: string
  abnormal: string
  duration: string
  description: string
  risk?: '低风险' | '中风险' | '高风险'
  engine?: string
  rawStatus?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  error?: string
  /** chain（kg.schema.extract.chain）任务：抽屉内该 Schema 脚本各转换步（STEPS）聚合。 */
  activities?: Record<string, PipelineActivityInfo>
}

export interface ProcessingInstance {
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
  rule: string
  confidence: string
  result: string
  status: string
  taskStatus: TaskStatus
  dataDomain: string
  processedAt: string
  reviewType?: string
  currentStep: string
  steps: ProcessStep[]
  workflowType: string
  workflowId: string
  runId?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  logs?: string[]
  batch?: UpdateBatch
  /** kg.custom.steps 工作流专用：实时 step 状态（@workflow.query get_steps）。 */
  pipeline?: PipelineStepState
}

export interface PipelineStepState {
  /** 当前正在执行/暂停的 step id。 */
  current: string | null
  /** step_id → 该 step 的运行状态。 */
  steps: Record<string, PipelineStepInfo>
}

export interface PipelineStepInfo {
  status: 'COMPLETED' | 'RUNNING' | 'FAILED'
  /** 执行序（Temporal JSON 编码按 key 排序，步序必须显式携带） */
  position?: number
  startedAt?: string
  finishedAt?: string
  /** 该 step 的输入 payload（kg.custom.steps / kg.custom.chain 的 get_steps 返回）。 */
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  error?: string
  attempt?: number
  name?: string
  /** 脚本运行期实际访问的资源（观测式溯源；旧执行记录无此字段）。 */
  access?: AccessReport
  /** kg.custom.chain 专用：该脚本内部的 activity steps（Temporal activity 真实状态）。 */
  activities?: Record<string, PipelineActivityInfo>
  /** kg.schema.extract.chain 专用：该 Schema 抽取的读取/写图/失败行数与阶段描述。 */
  description?: string
  records?: number
  written?: number
  failed?: number
}

export interface PipelineActivityInfo {
  status: 'COMPLETED' | 'RUNNING' | 'FAILED'
  name?: string
  input?: Record<string, unknown>
  output?: Record<string, unknown>
  error?: string
  attempt?: number
  access?: AccessReport
  /** chain 任务：该转换步的读取行数 / 写图条数 / 失败行数。 */
  records?: number
  written?: number
  failed?: number
}

/** 脚本数据访问溯源报告（后端 sdk/access.py 渲染）。各桶 key 以 `_` 开头的是元信息（_unparsed/_ngql）。 */
export interface AccessEntry {
  ops?: string[]
  count?: number
  statements?: number
  calls?: number
  failures?: number
  queries?: string[]
  last?: string
}

export interface AccessReport {
  mysql?: Record<string, Record<string, AccessEntry>>
  graph?: Record<string, Record<string, AccessEntry>>
  milvus?: Record<string, AccessEntry>
  llm?: Record<string, AccessEntry>
  embedding?: Record<string, AccessEntry>
}

const unwrap = async <T>(request: Promise<unknown>) => unwrapApiResponse((await request) as ApiResponse<T>)

export const getTask = (id: string) => unwrap(http.get(`/v1/task-center/tasks/${id}`)) as Promise<ProcessingInstance>

/** 失败任务重试：调 Temporal ResetWorkflowExecution，回放到失败 step 之前。 */
export const retryTask = (taskId: string, reason = 'manual retry') => unwrap(http.post(`/v1/task-center/tasks/${taskId}/retry`, { reason })) as Promise<{ taskId: string; workflowId: string; newRunId: string }>

// ---- 生产级人工处理 API ----

/** 无移交通道：submit/direct-decide 只记录决议即落终态；RERUNNING/RERUN_FAILED 属 T_EXTRACT_FAIL 重跑生命周期。 */
export type ProductionReviewStatus = 'OPEN' | 'CLAIMED' | 'IN_REVIEW' | 'PENDING_APPROVAL' | 'RERUNNING' | 'RESOLVED' | 'REJECTED' | 'CANCELLED' | 'RERUN_FAILED' | 'EXPIRED'
export interface ProductionReviewCase {
  id: string; sourceTaskId: string; batchId?: string; nodeId: string; objectId: string; objectType: string; objectName: string
  /** 图谱构建ID：产生该 case 的抽取执行（EXEC-xxx，跳 /processing-instance 用）；缺省看 workflowId。 */
  executionId?: string
  /** 图谱构建任务（job-xxx，「来源记录」跳 /graph-build/jobs 用）；后端快照/执行关联解析。 */
  jobId?: string
  /** 建案时绑定的图空间（产生该 case 的抽取任务所在空间；队列按其过滤）。 */
  graphSpace?: string
  errorType: string; category: string; templateId: string; domain: string; phase: string; riskLevel: 'P0'|'P1'|'P2'; scope: string
  status: ProductionReviewStatus; assigneeId?: string; assigneeName?: string; version: number; slaClaimAt: string; slaResolveAt: string
  diagnosis: string; sourceTable?: string; sourceRecordId?: string; createdAt: string; updatedAt: string
  draft?: Record<string, unknown>; input?: Record<string, unknown>; candidate?: Record<string, unknown>; evidence?: Record<string, unknown>[]
  pipelineStepId?: string; pipelineStepName?: string; exceptionCode?: string; isolationScope?: string; workflowType?: string; workflowId?: string; workflowRunId?: string
  template?: { id:string; version:string; title:string; displaySchema:{ sections:Array<{type:string;source?:string;target?:string;field?:string;options?:string[]}> }; resultSchema:Record<string,unknown>; allowedActions:string[] }
  data?: {
    input?: Record<string, unknown>
    candidate?: Record<string, unknown>
    evidence?: unknown[]
    source_record?: Record<string, unknown> | null
    llm_input?: { system: string; user: string } | null
    llm_output?: string | null
  }; consequence?: { writeTarget:string; rerunStepId:string; scope:string }
}
export const getProductionReviews = (params: Record<string, unknown> = {}) => unwrap(http.get('/v1/manual-reviews/production/queue', { params })) as Promise<{ items: ProductionReviewCase[]; total: number; page: number; pageSize: number }>
export const getProductionReview = (id: string) => unwrap(http.get(`/v1/manual-reviews/production/${id}`)) as Promise<ProductionReviewCase>
export const heartbeatProductionReview = (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/heartbeat`, { version })) as Promise<ProductionReviewCase>
export const releaseProductionReview = (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/release`, { version })) as Promise<ProductionReviewCase>
export const saveProductionReviewDraft = (id: string, version: number, payload: Record<string, unknown>) => unwrap(http.put(`/v1/manual-reviews/production/${id}/draft`, { version, payload })) as Promise<ProductionReviewCase>
export const submitProductionReview = (id: string, data: { version:number; actionId:string; result:Record<string,unknown>; note?:string }) => unwrap(http.post(`/v1/manual-reviews/production/${id}/submit`, data)) as Promise<ProductionReviewCase>

/** case 审计日志（建案/领取/提交/重跑等事件时间线）。 */
export interface ProductionReviewAuditEntry {
  eventType: string; actorId?: string; actorName?: string; requestId?: string
  oldStatus?: string | null; newStatus?: string | null; detail?: Record<string, unknown> | null; createdAt: string
}
export const getProductionReviewAuditLogs = (id: string) =>
  unwrap(http.get(`/v1/manual-reviews/production/${id}/audit-logs`)) as Promise<{ items: ProductionReviewAuditEntry[] }>

/** 物理删除未处理 case（review_admin；已终态的后端 409）。 */
export const deleteProductionReview = (id: string) =>
  unwrap(http.delete(`/v1/manual-reviews/production/${id}`)) as Promise<{ id: string; deleted: boolean }>

/** T_EXTRACT_FAIL 抽取失败记录重跑：所选 case 按 schema 合并为新执行（triggerSource=RERUN）。
 *  skipped = 校验失败被跳过的 schema 组（已删/不在当前控制面/缺来源绑定），不阻断其余重跑。 */
export const rerunExtractFailures = (data: { caseIds?: string[]; executionId?: string; batchSize?: number }) =>
  unwrap(http.post('/v1/manual-reviews/production/rerun-extract-failures', data)) as Promise<{
    executions: Array<{ executionId: string; schemaId: string; records: number; cases: number }>
    cases: number
    skipped: Array<{ schemaId: string; schemaKey?: string | null; cases: number; reason: string }>
  }>

/** case 事件流水（audit-logs）：创建/领取/重跑/状态变迁，含操作人与时间。 */
export interface ProductionReviewLogEntry {
  eventType: string; actorId?: string; actorName?: string; requestId?: string
  oldStatus?: string; newStatus?: string; detail?: Record<string, unknown>; createdAt: string
}
export const getProductionReviewLogs = (id: string) =>
  unwrap(http.get(`/v1/manual-reviews/production/${id}/audit-logs`)) as Promise<{ items: ProductionReviewLogEntry[] }>

/** kg.custom.steps T_DIRECT 案例直接决策：accept 写图，reject 丢弃。不走 4-eyes claim/submit 流程。
 * candidate 为"修正后的完整候选"（仅 accepted 时有意义）：覆盖候选快照后写图并记审计。 */
export const directDecideProductionReview = (
  id: string,
  version: number,
  accepted: boolean,
  note = '',
  candidate?: Record<string, unknown>,
) =>
  unwrap(http.post(`/v1/manual-reviews/production/${id}/direct-decide`, {
    version,
    accepted,
    note,
    ...(candidate !== undefined ? { candidate } : {}),
  })) as Promise<ProductionReviewCase>

// ---- 工作流定义、Python 脚本上传与执行（任务中心提交脚本用） ----

export interface WorkflowDefinition {
  id: string
  name: string
  workflowType: string
  category?: string
  sourceKind?: string
  functionName?: string
  scriptPath?: string
  timeoutSeconds?: number
  active?: boolean
  steps?: unknown[]
  createdAt?: string
}

export interface WorkflowExecution {
  id: string
  definitionId: string
  workflowId: string
  runId?: string
  status: string
  startedAt: string
  completedAt?: string
  payload?: Record<string, unknown>
  dispatchMode?: string
  message?: string
  output?: unknown
  steps?: ProcessStep[]
  taskId?: string
  scheduleId?: string
  jobId?: string
  stepsState?: Record<string, unknown>
  triggerSource?: TriggerSource
}

/** 执行触发方式：MANUAL 手动 / SCHEDULE 定期 / RERUN 重新执行（失败记录重跑）。 */
export type TriggerSource = 'MANUAL' | 'SCHEDULE' | 'RERUN'
export const TRIGGER_SOURCE_LABEL: Record<TriggerSource, string> = {
  MANUAL: '手动触发',
  SCHEDULE: '定期触发',
  RERUN: '重新执行',
}

export const listDefinitions = (category?: string) =>
  unwrap(http.get('/v1/workflow-system/definitions', { params: category ? { category } : {} })) as Promise<{ items: WorkflowDefinition[]; total: number }>

export const getExecution = (executionId: string) =>
  unwrap(http.get(`/v1/workflow-system/executions/${executionId}`)) as Promise<WorkflowExecution>

export const listExecutions = (
  limit = 100,
  filters: { definitionId?: string; scheduleId?: string; jobId?: string; triggerSource?: TriggerSource } = {},
) =>
  unwrap(http.get('/v1/workflow-system/executions', { params: { limit, ...filters } })) as Promise<{ items: WorkflowExecution[]; total: number }>

// ---- 任务中心 Job ----

export interface JobScheduleSpec {
  kind: 'once' | 'cron'
  cron?: string
  timezone?: string
}

export interface WorkflowJob {
  id: string
  name: string
  /** single/upload 已随 D2 停止新建；chain 现为 Schema 串行（kg.schema.extract.chain）。存量旧 chain 触发会被服务端拦截。 */
  taskType: 'single' | 'chain' | 'upload' | 'extract'
  definitionIds: string[]
  schemaId?: string
  /** chain：按序串联的 Schema id 列表（顺序即执行顺序）。 */
  schemaIds?: string[]
  /** chain：各串联 Schema 展示名（与 schemaIds 一一对应）。 */
  schemaLabels?: string[]
  batchSize?: number
  definitionId: string
  definitionName?: string
  schedule: JobScheduleSpec
  owner: string
  status: string
  scheduleId?: string
  lastRunAt?: string | null
  lastExecutionId?: string | null
  lastExecutionStatus?: string | null
  createdAt: string
  updatedAt?: string
  dispatchStatus?: string
  message?: string
  llmConfigId?: string
  embeddingConfigId?: string
  mysqlDatasourceId?: string
  mysqlDatabase?: string
  milvusConfigId?: string
  milvusDatabase?: string
  graphSpace?: string
  since?: string
  [key: string]: unknown
}

export interface JobCreateInput {
  name: string
  /** extract 数据抽取（单 Schema）/ chain 多脚本串行（≥2 个 Schema 按序串联） */
  taskType: 'extract' | 'chain'
  schemaId?: string
  /** chain：按序串联的 Schema 列表（≥2，顺序即执行顺序）。 */
  schemaIds?: string[]
  batchSize?: number
  schedule?: JobScheduleSpec
  runNow?: boolean
  llmConfigId?: string
  embeddingConfigId?: string
  mysqlDatasourceId?: string
  mysqlDatabase?: string
  milvusConfigId?: string
  milvusDatabase?: string
  graphSpace?: string
  since?: string
}

export const listJobs = (
  filters: { name?: string; status?: string; taskType?: string } = {},
) =>
  unwrap(http.get('/v1/workflow-system/jobs', { params: filters })) as Promise<{ items: WorkflowJob[]; total: number }>

/** 任务统一状态：列表页/总览卡共用同一派生口径。 */
export type JobUnifiedStatus = '未运行' | '运行中' | '已暂停' | '已完成' | '运行失败'

const JOB_RUNNING_STATUSES = new Set(['RUNNING'])
const JOB_FAILED_STATUSES = new Set(['FAILED', 'CANCELED', 'TERMINATED', 'TIMED_OUT'])

export function deriveJobUnifiedStatus(job: Pick<WorkflowJob, 'status' | 'lastExecutionStatus'>): JobUnifiedStatus {
  // 已暂停优先于运行中：暂停是任务级开关（步间挂起当前执行），用户暂停后
  // 状态列必须立即反映；执行实况仍在「最近执行」列如实展示
  if (job.status === '暂停') return '已暂停'
  if (job.lastExecutionStatus && JOB_RUNNING_STATUSES.has(job.lastExecutionStatus)) return '运行中'
  if (job.lastExecutionStatus === 'COMPLETED') return '已完成'
  if (job.lastExecutionStatus && JOB_FAILED_STATUSES.has(job.lastExecutionStatus)) return '运行失败'
  // QUEUED = Temporal 不可用时的本地待下发记录，不会自愈，按未运行处理（可重新触发）
  return '未运行'
}

/** 统一状态 → 状态点色调（对应 GraphBuildView/总览卡的 span.ok/.err/.warn/.run）。 */
export const JOB_STATUS_TONE: Record<JobUnifiedStatus, 'ok' | 'err' | 'warn' | 'run'> = {
  未运行: 'warn',
  运行中: 'run',
  已暂停: 'warn',
  已完成: 'ok',
  运行失败: 'err',
}

export function countJobUnifiedStatuses(
  jobs: Array<Pick<WorkflowJob, 'status' | 'lastExecutionStatus'>>,
): Record<JobUnifiedStatus, number> {
  const counts: Record<JobUnifiedStatus, number> = { 未运行: 0, 运行中: 0, 已暂停: 0, 已完成: 0, 运行失败: 0 }
  for (const job of jobs) counts[deriveJobUnifiedStatus(job)] += 1
  return counts
}

/** 任务归属空间（列表页/总览卡共用同一口径）：payload 未带 graphSpace 的历史任务
 *  落默认业务空间（空间列表首位恒为默认）。 */
export function jobGraphSpace(
  job: Pick<WorkflowJob, 'graphSpace'>,
  defaultSpace: string,
  current: string,
): string {
  return job.graphSpace || defaultSpace || current
}

export const createJob = (input: JobCreateInput) =>
  unwrap(http.post('/v1/workflow-system/jobs', input)) as Promise<WorkflowJob>

export const getJob = (jobId: string) =>
  unwrap(http.get(`/v1/workflow-system/jobs/${jobId}`)) as Promise<{ job: WorkflowJob; executions: WorkflowExecution[] }>

export const triggerJob = (jobId: string) =>
  unwrap(http.post(`/v1/workflow-system/jobs/${jobId}/trigger`)) as Promise<WorkflowExecution>

export const updateJobState = (jobId: string, active: boolean) =>
  unwrap(http.put(`/v1/workflow-system/jobs/${jobId}/state`, { active })) as Promise<WorkflowJob>

export const deleteJob = (jobId: string) =>
  unwrap(http.delete(`/v1/workflow-system/jobs/${jobId}`)) as Promise<{ id: string }>
