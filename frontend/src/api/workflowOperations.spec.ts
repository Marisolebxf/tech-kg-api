import { describe, expect, it } from 'vitest'

import {
  countJobUnifiedStatuses,
  deriveJobUnifiedStatus,
  JOB_STATUS_TONE,
  type WorkflowJob,
} from './workflowOperations'

type JobSeed = Pick<WorkflowJob, 'status' | 'lastExecutionStatus'>

const job = (status: string, lastExecutionStatus?: string | null): JobSeed => ({
  status,
  lastExecutionStatus: lastExecutionStatus ?? null,
})

describe('deriveJobUnifiedStatus 统一状态推导', () => {
  it('优先级：RUNNING 最高（暂停的任务仍有实例在跑 → 运行中）', () => {
    // 后端语义：暂停不杀运行中实例（workflow_jobs.py set_job_state 注释）
    expect(deriveJobUnifiedStatus(job('暂停', 'RUNNING'))).toBe('运行中')
  })

  it('暂停其次：已完成后再暂停显示已暂停', () => {
    expect(deriveJobUnifiedStatus(job('暂停', 'COMPLETED'))).toBe('已暂停')
  })

  it('终态映射：COMPLETED→已完成；FAILED/CANCELED/TERMINATED/TIMED_OUT→运行失败', () => {
    expect(deriveJobUnifiedStatus(job('启用', 'COMPLETED'))).toBe('已完成')
    for (const status of ['FAILED', 'CANCELED', 'TERMINATED', 'TIMED_OUT']) {
      expect(deriveJobUnifiedStatus(job('启用', status))).toBe('运行失败')
    }
  })

  it('QUEUED 按未运行处理（本地待下发不自愈，可重新触发）', () => {
    expect(deriveJobUnifiedStatus(job('启用', 'QUEUED'))).toBe('未运行')
  })

  it('CONTINUED_AS_NEW 落入未运行分支（后端声明本系统从不 continue-as-new）', () => {
    // 若未来出现该状态会显示「未运行」，与运行中事实不符——记录现状
    expect(deriveJobUnifiedStatus(job('启用', 'CONTINUED_AS_NEW'))).toBe('未运行')
  })

  it('无执行记录的启用任务 → 未运行', () => {
    expect(deriveJobUnifiedStatus(job('启用', null))).toBe('未运行')
    expect(deriveJobUnifiedStatus(job('启用', ''))).toBe('未运行')
  })

  it('五种统一状态都有色调映射', () => {
    const all = ['未运行', '运行中', '已暂停', '已完成', '运行失败'] as const
    for (const status of all) expect(JOB_STATUS_TONE[status]).toBeTruthy()
  })
})

describe('countJobUnifiedStatuses 统计卡', () => {
  it('五态计数齐备，统计卡与列表行同源同口径', () => {
    const counts = countJobUnifiedStatuses([
      job('启用', 'RUNNING'),
      job('启用', 'RUNNING'),
      job('启用', 'COMPLETED'),
      job('暂停', 'COMPLETED'),
      job('启用', 'FAILED'),
      job('启用', null),
      job('启用', 'QUEUED'),
    ])
    expect(counts).toEqual({
      未运行: 2, // 无记录 + QUEUED
      运行中: 2,
      已暂停: 1,
      已完成: 1,
      运行失败: 1,
    })
  })

  it('空列表 → 全 0（而非 undefined 键缺失）', () => {
    expect(countJobUnifiedStatuses([])).toEqual({
      未运行: 0,
      运行中: 0,
      已暂停: 0,
      已完成: 0,
      运行失败: 0,
    })
  })
})
