import { http } from './http'
import { unwrapApiResponse, type ApiResponse } from './graphSearch'

import {
  getReviewRecord,
  reviewRecords,
  type ReviewRecord,
} from '../views/platform/manual-review-data'

export type { ReviewRecord }

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

// ---- 人工处理 API（原型直接返回本地 mock 数据，不调后端） ----

export const getManualReviews = async (_params: Record<string, unknown> = {}): Promise<{ items: ReviewRecord[]; total: number; statusCounts: Record<string, number> }> => {
  const items = reviewRecords.slice()
  const statusCounts: Record<string, number> = { 待处理: 0, 已完成: 0, 已撤销: 0 }
  items.forEach((row) => { statusCounts[row.status] = (statusCounts[row.status] || 0) + 1 })
  return { items, total: items.length, statusCounts }
}

export const getManualReview = async (id: string): Promise<ReviewRecord> => {
  const record = getReviewRecord(id)
  if (!record) throw new Error('未找到处理实例')
  return record
}

export const submitManualReview = async (id: string, data: { actionId: string; note: string; result: Record<string, unknown>; handler?: string; rerun: boolean }): Promise<{ review: ReviewRecord }> => {
  const record = getReviewRecord(id)
  if (!record) throw new Error('未找到处理实例')
  const updated: ReviewRecord = {
    ...record,
    status: data.actionId === 'skip-task' || data.actionId === 'discard-record' ? '已撤销' : '已完成',
    decision: data.result.label as string || '修正后重跑并通过',
    decisionNote: data.note || '人工处理完成，已从阻断节点重跑。',
    completedAt: new Date().toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-'),
  }
  Object.assign(record, updated)
  return { review: updated }
}

export const retryManualReview = async (id: string, _payload: Record<string, unknown> = {}): Promise<{ id: string; status: string }> => {
  return { id, status: '已重试' }
}

export const modifyManualReviewResult = async (id: string, _result: Record<string, unknown>, _note = ''): Promise<ReviewRecord> => {
  const record = getReviewRecord(id)
  if (!record) throw new Error('未找到处理实例')
  return record
}

export const revokeManualReview = async (id: string, reason: string): Promise<ReviewRecord> => {
  const record = getReviewRecord(id)
  if (!record) throw new Error('未找到处理实例')
  const updated: ReviewRecord = { ...record, status: '已撤销', decision: '已撤销', decisionNote: reason, completedAt: new Date().toLocaleString('zh-CN', { hour12: false }).replace(/\//g, '-') }
  Object.assign(record, updated)
  return updated
}

// ---- 生产级人工处理 API（占位；后端未启用时不会被调用） ----

export type ProductionReviewStatus = 'OPEN' | 'CLAIMED' | 'IN_REVIEW' | 'PENDING_APPROVAL' | 'APPLYING' | 'RERUNNING' | 'VERIFYING' | 'RESOLVED' | 'REJECTED' | 'CANCELLED' | 'APPLY_FAILED' | 'RERUN_FAILED' | 'EXPIRED'
export interface ProductionReviewCase {
  id: string; sourceTaskId: string; batchId?: string; nodeId: string; objectId: string; objectType: string; objectName: string
  errorType: string; category: string; templateId: string; domain: string; phase: string; riskLevel: 'P0'|'P1'|'P2'; scope: string
  status: ProductionReviewStatus; assigneeId?: string; assigneeName?: string; version: number; slaClaimAt: string; slaResolveAt: string
  diagnosis: string; sourceTable?: string; sourceRecordId?: string; createdAt: string; updatedAt: string
  draft?: Record<string, unknown>; input?: Record<string, unknown>; candidate?: Record<string, unknown>; evidence?: Record<string, unknown>[]; executions?: Record<string, unknown>[]
  pipelineStepId?: string; pipelineStepName?: string; exceptionCode?: string; isolationScope?: string
  template?: { id:string; version:string; title:string; displaySchema:{ sections:Array<{type:string;source?:string;target?:string;field?:string;options?:string[]}> }; resultSchema:Record<string,unknown>; allowedActions:string[] }
  data?: { input?:Record<string,unknown>; candidate?:Record<string,unknown>; evidence?:unknown[] }; consequence?: { writeTarget:string; rerunStepId:string; scope:string }
}
export const getProductionReviews = async (params: Record<string, unknown> = {}): Promise<{ items: ProductionReviewCase[]; total: number; page: number; pageSize: number }> => {
  try {
    return await unwrap(http.get('/v1/manual-reviews/production/queue', { params, skipErrorToast: true })) as { items: ProductionReviewCase[]; total: number; page: number; pageSize: number }
  } catch {
    return { items: [], total: 0, page: 1, pageSize: 50 }
  }
}
export const getProductionReview = async (id: string): Promise<ProductionReviewCase> => {
  try {
    return await unwrap(http.get(`/v1/manual-reviews/production/${id}`, { skipErrorToast: true })) as ProductionReviewCase
  } catch {
    throw new Error('生产模式未启用或后端不可达')
  }
}
export const claimProductionReview = async (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/claim`, { version })) as Promise<ProductionReviewCase>
export const heartbeatProductionReview = async (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/heartbeat`, { version })) as Promise<ProductionReviewCase>
export const releaseProductionReview = async (id: string, version: number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/release`, { version })) as Promise<ProductionReviewCase>
export const saveProductionReviewDraft = async (id: string, version: number, payload: Record<string, unknown>) => unwrap(http.put(`/v1/manual-reviews/production/${id}/draft`, { version, payload })) as Promise<ProductionReviewCase>
export const submitProductionReview = async (id: string, data: { version:number; actionId:string; result:Record<string,unknown>; note?:string }) => unwrap(http.post(`/v1/manual-reviews/production/${id}/submit`, data)) as Promise<ProductionReviewCase>
export const approveProductionReview = async (id: string, version:number, note='') => unwrap(http.post(`/v1/manual-reviews/production/${id}/approve`, { version, note })) as Promise<ProductionReviewCase>
export const rejectProductionReview = async (id: string, version:number, note='') => unwrap(http.post(`/v1/manual-reviews/production/${id}/reject`, { version, note })) as Promise<ProductionReviewCase>
export const retryProductionReview = async (id: string, version:number) => unwrap(http.post(`/v1/manual-reviews/production/${id}/retry`, { version })) as Promise<ProductionReviewCase>

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
