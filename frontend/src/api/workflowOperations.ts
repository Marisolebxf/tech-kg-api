import { http } from './http'
import { unwrapApiResponse, type ApiResponse } from './graphSearch'

export type TaskStatus = '执行中' | '执行出错' | '等待人工审核' | '执行完成'
export type ReviewStatus = '待处理' | '已完成' | '已撤销' | '已驳回'

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
  output?: Record<string, unknown>
  error?: string
  attempt?: number
}

export interface SourceUpdate {
  change: string
  type: string
  domain: string
  id: string
  content: string
  time: string
  detectedAt: string
  source: string
  field: string
  before: string
  after: string
  result: string
}

export interface UpdatePolicy {
  id: string
  enabled: boolean
  frequency: string
  executionTime: string
  timezone: string
  cron: string
  nextRunAt: string
  skipWhenNoChanges: boolean
}

export interface ReviewRecord {
  id: string
  batch: string
  module: string
  node: string
  type: string
  category: string
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
  modifiedResult?: Record<string, unknown>
  flow?: ProcessStep[]
}

export interface TaskOverview {
  summary: { label: string; value: string; hint: string }[]
  latestBatch: UpdateBatch | null
  changeSummary: { total: number; added: number; updated: number; deleted: number; detectedAt: string; completedAt: string }
  updatePolicy: UpdatePolicy
  sourceHealth: { id: string; name: string; status: string; message: string; lastCheckedAt: string }[]
}

const unwrap = async <T>(request: Promise<unknown>) => unwrapApiResponse((await request) as ApiResponse<T>)

export const getTaskOverview = () => unwrap(http.get('/v1/task-center/overview')) as Promise<TaskOverview>
export const getTaskBatches = () => unwrap(http.get('/v1/task-center/batches')) as Promise<{ items: UpdateBatch[]; total: number }>
export const getTasks = (params: Record<string, unknown> = {}) => unwrap(http.get('/v1/task-center/tasks', { params })) as Promise<{ items: ProcessingInstance[]; total: number }>
export const getTask = (id: string) => unwrap(http.get(`/v1/task-center/tasks/${id}`)) as Promise<ProcessingInstance>
export const getSourceUpdates = (params: Record<string, unknown> = {}) => unwrap(http.get('/v1/task-center/data-sources/updates', { params })) as Promise<{ items: SourceUpdate[]; total: number }>
export const saveUpdatePolicy = (data: { enabled: boolean; frequency: string; executionTime: string; timezone: string; skipWhenNoChanges: boolean }) => unwrap(http.put('/v1/task-center/update-policy', data)) as Promise<{ policy: UpdatePolicy }>
export const triggerGraphBuild = (data: Record<string, unknown> = {}) => unwrap(http.post('/v1/task-center/trigger', data)) as Promise<{ task: ProcessingInstance }>

export const getManualReviews = (params: Record<string, unknown> = {}) => unwrap(http.get('/v1/manual-reviews', { params })) as Promise<{ items: ReviewRecord[]; total: number; statusCounts: Record<string, number> }>
export const getManualReview = (id: string) => unwrap(http.get(`/v1/manual-reviews/${id}`)) as Promise<ReviewRecord>
export const submitManualReview = (id: string, data: { actionId: string; note: string; result: Record<string, unknown>; rerun: boolean }) => unwrap(http.post(`/v1/manual-reviews/${id}/actions`, data)) as Promise<{ review: ReviewRecord }>
export const retryManualReview = (id: string, payload: Record<string, unknown> = {}) => unwrap(http.post(`/v1/manual-reviews/${id}/retry`, { payload })) as Promise<{ id: string; status: string }>

/** 失败任务重试：调 Temporal ResetWorkflowExecution，回放到失败 step 之前。 */
export const retryTask = (taskId: string, reason = 'manual retry') => unwrap(http.post(`/v1/task-center/tasks/${taskId}/retry`, { reason })) as Promise<{ taskId: string; workflowId: string; newRunId: string }>
export const modifyManualReviewResult = (id: string, result: Record<string, unknown>, note = '') => unwrap(http.put(`/v1/manual-reviews/${id}/result`, { result, note })) as Promise<ReviewRecord>
export const revokeManualReview = (id: string, reason: string) => unwrap(http.post(`/v1/manual-reviews/${id}/revoke`, { reason })) as Promise<ReviewRecord>

// ---- 生产级人工处理 API ----

export type ProductionReviewStatus = 'OPEN' | 'CLAIMED' | 'IN_REVIEW' | 'PENDING_APPROVAL' | 'APPLYING' | 'RERUNNING' | 'VERIFYING' | 'RESOLVED' | 'REJECTED' | 'CANCELLED' | 'APPLY_FAILED' | 'RERUN_FAILED' | 'EXPIRED'
export interface ProductionReviewCase {
  id: string; sourceTaskId: string; batchId?: string; nodeId: string; objectId: string; objectType: string; objectName: string
  errorType: string; category: string; templateId: string; domain: string; phase: string; riskLevel: 'P0'|'P1'|'P2'; scope: string
  status: ProductionReviewStatus; assigneeId?: string; assigneeName?: string; version: number; slaClaimAt: string; slaResolveAt: string
  diagnosis: string; sourceTable?: string; sourceRecordId?: string; createdAt: string; updatedAt: string
  draft?: Record<string, unknown>; input?: Record<string, unknown>; candidate?: Record<string, unknown>; evidence?: Record<string, unknown>[]; executions?: Record<string, unknown>[]
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
export const claimProductionReview = (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/claim`, { version })) as Promise<ProductionReviewCase>
export const heartbeatProductionReview = (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/heartbeat`, { version })) as Promise<ProductionReviewCase>
export const releaseProductionReview = (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/release`, { version })) as Promise<ProductionReviewCase>
export const saveProductionReviewDraft = (id: string, version: number, payload: Record<string, unknown>) => unwrap(http.put(`/v1/manual-reviews/production/${id}/draft`, { version, payload })) as Promise<ProductionReviewCase>
export const submitProductionReview = (id: string, data: { version:number; actionId:string; result:Record<string,unknown>; note?:string }) => unwrap(http.post(`/v1/manual-reviews/production/${id}/submit`, data)) as Promise<ProductionReviewCase>
export const approveProductionReview = (id: string, version:number, note='') => unwrap(http.post(`/v1/manual-reviews/production/${id}/approve`, { version, note })) as Promise<ProductionReviewCase>
export const rejectProductionReview = (id: string, version:number, note='') => unwrap(http.post(`/v1/manual-reviews/production/${id}/reject`, { version, note })) as Promise<ProductionReviewCase>
export const retryProductionReview = (id: string, version:number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/retry`, { version })) as Promise<ProductionReviewCase>

/** kg.custom.steps T_DIRECT 案例直接决策：accept 写图，reject 丢弃。不走 4-eyes claim/submit 流程。 */
export const directDecideProductionReview = (id: string, version: number, accepted: boolean, note = '') => unwrap(http.post(`/v1/manual-reviews/production/${id}/direct-decide`, { version, accepted, note })) as Promise<ProductionReviewCase>

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
}

export interface WorkflowSchedule {
  id: string
  definitionId: string
  cron: string
  timezone: string
  active: boolean
  payload?: Record<string, unknown>
  dispatchStatus?: string
  message?: string
  [key: string]: unknown
}

export interface ScheduleCreateInput {
  id: string
  cron: string
  timezone?: string
  active?: boolean
  payload?: Record<string, unknown>
}

export const listDefinitions = () =>
  unwrap(http.get('/v1/workflow-system/definitions')) as Promise<{ items: WorkflowDefinition[]; total: number }>

export const getDefinition = (id: string) =>
  unwrap(http.get(`/v1/workflow-system/definitions/${id}`)) as Promise<WorkflowDefinition>

export const uploadPythonDefinition = (
  file: File,
  functionName = 'workflow',
  options: { definitionId?: string; name?: string; timeoutSeconds?: number } = {},
) => {
  const form = new FormData()
  form.append('file', file)
  form.append('function_name', functionName)
  if (options.definitionId) form.append('definition_id', options.definitionId)
  if (options.name) form.append('name', options.name)
  if (options.timeoutSeconds) form.append('timeoutSeconds', String(options.timeoutSeconds))
  return unwrap(http.post('/v1/workflow-system/definitions/python', form)) as Promise<WorkflowDefinition>
}

export interface ExecuteDefinitionSelectors {
  workflowId?: string
  llmConfigId?: string
  embeddingConfigId?: string
  mysqlDatasourceId?: string
  mysqlDatabase?: string
  graphSpace?: string
  milvusConfigId?: string
  milvusDatabase?: string
}

export const executeDefinition = (
  id: string,
  payload: Record<string, unknown> = {},
  selectors: ExecuteDefinitionSelectors = {},
) =>
  unwrap(
    http.post(`/v1/workflow-system/definitions/${id}/execute`, { payload, ...selectors }),
  ) as Promise<WorkflowExecution>

export const getExecution = (executionId: string) =>
  unwrap(http.get(`/v1/workflow-system/executions/${executionId}`)) as Promise<WorkflowExecution>

export const listExecutions = (limit = 100) =>
  unwrap(http.get('/v1/workflow-system/executions', { params: { limit } })) as Promise<{ items: WorkflowExecution[]; total: number }>

// ---- 工作流调度（定期执行） ----

export const listSchedules = () =>
  unwrap(http.get('/v1/workflow-system/schedules')) as Promise<{ items: WorkflowSchedule[]; total: number }>

export const createSchedule = (definitionId: string, schedule: ScheduleCreateInput) =>
  unwrap(http.post(`/v1/workflow-system/definitions/${definitionId}/schedules`, schedule)) as Promise<WorkflowSchedule>

export const updateScheduleState = (scheduleId: string, active: boolean) =>
  unwrap(http.put(`/v1/workflow-system/schedules/${scheduleId}/state`, { active })) as Promise<WorkflowSchedule>

export const triggerSchedule = (scheduleId: string) =>
  unwrap(http.post(`/v1/workflow-system/schedules/${scheduleId}/trigger`)) as Promise<{ id: string; dispatchStatus: string }>

export const deleteSchedule = (scheduleId: string) =>
  unwrap(http.delete(`/v1/workflow-system/schedules/${scheduleId}`)) as Promise<{ id: string }>
