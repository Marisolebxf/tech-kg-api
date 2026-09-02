import { describe, it, expect } from 'vitest'
import {
  mapRerunExecutionRow,
  extractCaseStatusBadge,
  executionStatusLabel,
  isRerunExecutionRunning,
} from '../rerun-history'
import type { WorkflowExecution } from '../../../api/workflowOperations'

const execution = (overrides: Partial<WorkflowExecution> = {}): WorkflowExecution => ({
  id: 'EXEC-TEST-1',
  definitionId: 'extract-paper',
  workflowId: 'wf-1',
  status: 'RUNNING',
  startedAt: '2026-09-02 10:00:00',
  triggerSource: 'RERUN',
  ...overrides,
})

describe('mapRerunExecutionRow', () => {
  it('从 payload 映射 case 数/记录数/来源执行/schema', () => {
    const row = mapRerunExecutionRow(execution({
      status: 'COMPLETED',
      payload: {
        schemaId: 'SCHEMA-1',
        rerunCaseIds: ['CASE-1', 'CASE-2'],
        recordIdsBySource: { bindingA: ['R1', 'R2'], bindingB: ['R3'] },
        rerunOfExecutionId: 'EXEC-ORIG-9',
      },
      output: { failures: { count: 1 } },
    }))
    expect(row.caseCount).toBe(2)
    expect(row.recordCount).toBe(3)
    expect(row.failureCount).toBe(1)
    expect(row.rerunOfExecutionId).toBe('EXEC-ORIG-9')
    expect(row.schemaId).toBe('SCHEMA-1')
    expect(row.statusLabel).toBe('已完成')
  })

  it('历史执行缺 payload/output 字段时全部兜底（null / —）', () => {
    const row = mapRerunExecutionRow(execution({ payload: undefined, output: undefined }))
    expect(row.caseCount).toBeNull()
    expect(row.recordCount).toBeNull()
    expect(row.failureCount).toBeNull()
    expect(row.rerunOfExecutionId).toBeNull()
    expect(row.schemaId).toBe('—')
  })

  it('rerunOfExecutionId 为 null（case 无原执行）时不误判为字符串', () => {
    const row = mapRerunExecutionRow(execution({ payload: { rerunOfExecutionId: null } }))
    expect(row.rerunOfExecutionId).toBeNull()
  })

  it('未知执行状态回退原始值', () => {
    expect(executionStatusLabel('WEIRD')).toBe('WEIRD')
    expect(isRerunExecutionRunning({ status: 'QUEUED' })).toBe(true)
    expect(isRerunExecutionRunning({ status: 'COMPLETED' })).toBe(false)
  })
})

describe('extractCaseStatusBadge', () => {
  it('RERUNNING/RERUN_FAILED 细化，其余维持既有映射', () => {
    expect(extractCaseStatusBadge('RERUNNING')).toBe('重跑中')
    expect(extractCaseStatusBadge('RERUN_FAILED')).toBe('重跑失败')
    expect(extractCaseStatusBadge('RESOLVED')).toBe('已完成')
    expect(extractCaseStatusBadge('REJECTED')).toBe('已驳回')
    expect(extractCaseStatusBadge('CANCELLED')).toBe('已撤销')
    expect(extractCaseStatusBadge('OPEN')).toBe('待处理')
    expect(extractCaseStatusBadge('CLAIMED')).toBe('待处理')
  })
})
