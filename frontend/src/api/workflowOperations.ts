import { http } from './http'
import { unwrapApiResponse, type ApiResponse } from './graphSearch'

export type TaskStatus = '执行中' | '执行出错' | '等待人工审核' | '执行完成'
export type ReviewStatus = '待处理' | '已完成' | '已撤销'

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
export const submitManualReview = (id: string, data: { actionId: string; note: string; result: Record<string, unknown>; handler?: string; rerun: boolean }) => unwrap(http.post(`/v1/manual-reviews/${id}/actions`, data)) as Promise<{ review: ReviewRecord }>
export const retryManualReview = (id: string, payload: Record<string, unknown> = {}) => unwrap(http.post(`/v1/manual-reviews/${id}/retry`, { payload })) as Promise<{ id: string; status: string }>
export const modifyManualReviewResult = (id: string, result: Record<string, unknown>, note = '') => unwrap(http.put(`/v1/manual-reviews/${id}/result`, { result, note })) as Promise<ReviewRecord>
export const revokeManualReview = (id: string, reason: string) => unwrap(http.post(`/v1/manual-reviews/${id}/revoke`, { reason })) as Promise<ReviewRecord>

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

export const executeDefinition = (id: string, payload: Record<string, unknown> = {}, workflowId?: string) =>
  unwrap(http.post(`/v1/workflow-system/definitions/${id}/execute`, { payload, workflow_id: workflowId })) as Promise<WorkflowExecution>

export const getExecution = (executionId: string) =>
  unwrap(http.get(`/v1/workflow-system/executions/${executionId}`)) as Promise<WorkflowExecution>
