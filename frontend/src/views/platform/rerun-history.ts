import type { WorkflowExecution } from '../../api/workflowOperations'
import type { ReviewStatus } from './manual-review-data'

/** 重跑记录行：由 triggerSource=RERUN 执行记录映射，字段全部 optional 兜底（历史执行可能缺 payload 字段）。 */
export type RerunExecutionRow = {
  executionId: string
  schemaId: string
  startedAt: string
  status: string
  statusLabel: string
  caseCount: number | null
  recordCount: number | null
  failureCount: number | null
  rerunOfExecutionId: string | null
}

const EXECUTION_STATUS_LABEL: Record<string, string> = {
  RUNNING: '执行中',
  QUEUED: '排队中',
  COMPLETED: '已完成',
  FAILED: '失败',
  CANCELLED: '已取消',
}

export const executionStatusLabel = (status: string): string =>
  EXECUTION_STATUS_LABEL[status] ?? status

export const isRerunExecutionRunning = (row: Pick<RerunExecutionRow, 'status'>): boolean =>
  row.status === 'RUNNING' || row.status === 'QUEUED'

export const mapRerunExecutionRow = (execution: WorkflowExecution): RerunExecutionRow => {
  const payload = (execution.payload ?? {}) as Record<string, unknown>
  const recordIdsBySource = payload.recordIdsBySource as Record<string, unknown> | undefined
  const output = execution.output as { failures?: { count?: unknown } } | undefined
  return {
    executionId: execution.id,
    schemaId: typeof payload.schemaId === 'string' ? payload.schemaId : '—',
    startedAt: execution.startedAt,
    status: execution.status,
    statusLabel: executionStatusLabel(execution.status),
    caseCount: Array.isArray(payload.rerunCaseIds) ? payload.rerunCaseIds.length : null,
    recordCount: recordIdsBySource
      ? (Object.values(recordIdsBySource) as unknown[]).reduce<number>(
        (sum, ids) => sum + (Array.isArray(ids) ? ids.length : 0),
        0,
      )
      : null,
    failureCount: typeof output?.failures?.count === 'number' ? output.failures.count : null,
    rerunOfExecutionId: typeof payload.rerunOfExecutionId === 'string' ? payload.rerunOfExecutionId : null,
  }
}

/** C 类队列状态徽标：在既有映射上细化 RERUNNING/RERUN_FAILED（此前都 fallback 到"待处理"）。 */
export const extractCaseStatusBadge = (rawStatus: string): ReviewStatus => {
  if (rawStatus === 'RERUNNING') return '重跑中'
  if (rawStatus === 'RERUN_FAILED') return '重跑失败'
  if (rawStatus === 'RESOLVED') return '已完成'
  if (rawStatus === 'REJECTED') return '已驳回'
  if (rawStatus === 'CANCELLED') return '已撤销'
  return '待处理'
}
