import { describe, it, expect } from 'vitest'
import {
  PIPELINE_STEPS,
  reviewRecords,
  getReviewRecord,
  getReviewTemplateId,
  getReviewTemplate,
  resolvePipelineStep,
  getReviewConsequence,
  getReviewPriority,
  getImpactScope,
  getReviewConfidence,
  getHandleCategory,
  isMapTypeFix,
  type ReviewRecord,
  type PipelineStepId,
} from '../manual-review-data'

// 七模板 ↔ 演示记录（ruleId 前缀驱动）映射
const TEMPLATE_RECORD_ID: Record<string, string> = {
  T_MAP: 'PI-20260714-0102', // Schema 字段映射失败 / SCHEMA-MAP-FAIL-006
  T_DQ_FILL: 'PI-20260714-0008', // 论文标题缺失 / DQ-REQUIRED-001
  T_DQ_MERGE: 'PI-20260714-0007', // 论文唯一性冲突 / DQ-UNIQUE-003
  T_LINK: 'PI-20260714-0104', // 专家实体对齐歧义 / ALIGN-AMBIGUITY-004
  T_EVIDENCE: 'PI-20260714-0003', // 关系类型置信度不足 / REL-CONFIDENCE-003
  T_ATTR: 'PI-20260714-0006', // 任职机构属性冲突 / ATTR-TIME-012
  T_RUNTIME: 'PI-20260714-0101', // 大模型输出格式错误 / LLM-SCHEMA-FAIL-001
}

const rec = (id: string) => getReviewRecord(id) as ReviewRecord

describe('七节点稳定编码', () => {
  it('PIPELINE_STEPS 恰为七个稳定 stepId', () => {
    expect(PIPELINE_STEPS.map((s) => s.id)).toEqual([
      'source', 'normalize', 'schema', 'extract', 'align', 'validate', 'persist',
    ])
    expect(PIPELINE_STEPS.every((s) => s.phase === '数据处理' || s.phase === '图谱构建')).toBe(true)
  })
})

describe('七模板分类（ruleId 前缀 + 语义兜底）', () => {
  it.each(Object.entries(TEMPLATE_RECORD_ID))('%s 命中正确模板', (tid, rid) => {
    expect(getReviewTemplateId(rec(rid))).toBe(tid)
  })

  it('T_ENTITY/T_RELATION 旧名不在前端目录（前端仅认七模板）', () => {
    // 前端模板目录与后端 canonical 后的七模板一致，无旧别名
    const allTids = new Set(Object.values(TEMPLATE_RECORD_ID).map((rid) => getReviewTemplateId(rec(rid))))
    expect(allTids.size).toBe(7)
  })
})

describe('模板动作目录与后端契约一致', () => {
  it('T_LINK 含 entity-confirm / reject-candidate', () => {
    const actions = getReviewTemplate(rec(TEMPLATE_RECORD_ID.T_LINK)).actions.map((a) => a.id)
    expect(actions).toContain('entity-confirm')
    expect(actions).toContain('reject-candidate')
  })
  it('T_EVIDENCE 含 pass-rerun / reject-extract / force-pass（reject-extract 是唯一回退 extract 的动作）', () => {
    const actions = getReviewTemplate(rec(TEMPLATE_RECORD_ID.T_EVIDENCE)).actions.map((a) => a.id)
    expect(actions).toEqual(expect.arrayContaining(['pass-rerun', 'reject-extract', 'force-pass']))
  })
  it('T_RUNTIME 含 rerun-batch / retry-task / skip-task / escalate', () => {
    const actions = getReviewTemplate(rec(TEMPLATE_RECORD_ID.T_RUNTIME)).actions.map((a) => a.id)
    expect(actions).toEqual(expect.arrayContaining(['rerun-batch', 'retry-task', 'skip-task', 'escalate']))
  })
  it('高风险动作（force-pass/skip-task）标记 danger/escalate', () => {
    const ev = getReviewTemplate(rec(TEMPLATE_RECORD_ID.T_EVIDENCE)).actions.find((a) => a.id === 'force-pass')
    expect(ev?.kind).toBe('danger')
  })
})

describe('阻断节点推导（提交前节点与影响范围确认）', () => {
  const STEP_BY_TEMPLATE: Record<string, PipelineStepId> = {
    T_MAP: 'schema',
    T_DQ_FILL: 'normalize',
    T_DQ_MERGE: 'normalize',
    T_LINK: 'align',
    T_EVIDENCE: 'validate',
    T_ATTR: 'validate',
    T_RUNTIME: 'extract',
  }
  it.each(Object.entries(STEP_BY_TEMPLATE))('%s → 阻断节点 %s', (tid, stepId) => {
    const r = rec(TEMPLATE_RECORD_ID[tid])
    expect(resolvePipelineStep(r).id).toBe(stepId)
    const con = getReviewConsequence(r)
    expect(con.rerunStepId).toBe(stepId)
    expect(con.writeTarget).toBeTruthy()
    expect(con.rerunAnchor).toBe(resolvePipelineStep(r).name)
  })

  it('MAP 子形态（实体类型判断错误）落到 schema 且走 confirm-type', () => {
    const typeFix = rec('PI-20260714-0004') // 实体类型判断错误
    expect(isMapTypeFix(typeFix)).toBe(true)
    expect(resolvePipelineStep(typeFix).id).toBe('schema')
    expect(getReviewTemplate(typeFix).actions.map((a) => a.id)).toContain('confirm-type')
  })
})

describe('P0/批次 vs P1/任务 风险与影响范围', () => {
  it('大模型输出格式错误 → P0 批次级（阻断当前节点及下游）', () => {
    const p = getReviewPriority(rec(TEMPLATE_RECORD_ID.T_RUNTIME))
    expect(p.level).toBe('P0')
    expect(p.strategy).toContain('阻断')
    expect(getImpactScope(rec(TEMPLATE_RECORD_ID.T_RUNTIME))).toBe('批次级')
  })
  it('其余单对象异常 → P1 任务级（隔离当前任务）', () => {
    for (const tid of ['T_LINK', 'T_EVIDENCE', 'T_ATTR', 'T_DQ_FILL', 'T_DQ_MERGE', 'T_MAP']) {
      const r = rec(TEMPLATE_RECORD_ID[tid])
      expect(getReviewPriority(r).level).toBe('P1')
      expect(getImpactScope(r)).toBe('任务级')
    }
  })
})

describe('置信度展示', () => {
  it('数据处理类不展示置信度', () => {
    const r = rec(TEMPLATE_RECORD_ID.T_DQ_FILL) // module 数据处理
    expect(getReviewConfidence(r).value).toBe('—')
  })
  it('score >= 0.9 不提示低于阈值', () => {
    const r = { ...rec(TEMPLATE_RECORD_ID.T_DQ_FILL), module: '图谱构建', score: '0.93' }
    expect(getReviewConfidence(r).value).toBe('—')
  })
  it('score < 0.9 展示值与“低于阈值”标签', () => {
    const r = rec(TEMPLATE_RECORD_ID.T_LINK) // score 0.81, module 图谱构建
    const c = getReviewConfidence(r)
    expect(c.value).toBe('0.81')
    expect(c.label).toBe('低于阈值')
  })
})

describe('业务分类（顶部 chips）', () => {
  it('七模板映射到五类 handle category，且不出现 source/persist', () => {
    const cats = new Set(
      Object.values(TEMPLATE_RECORD_ID).map((rid) => getHandleCategory(rec(rid))),
    )
    for (const c of cats) {
      expect(['清洗标准化', 'Schema 映射', '抽取配置', '实体对齐', '质量校验']).toContain(c)
    }
  })
})

describe('演示数据标识（生产模式门控的前置契约）', () => {
  // 场景 7：硬编码演示候选/证据须在生产模式移除。这里锁定演示种子可被识别，
  // 生产模式（VITE_REVIEW_PRODUCTION_ENABLED=true）下视图改用服务端 dynamic form，
  // 不消费这些演示记录（见 ManualReviewDynamicForm.spec.ts）。
  it('reviewRecords 为演示种子，id 统一 PI- 前缀', () => {
    expect(reviewRecords.length).toBeGreaterThan(0)
    expect(reviewRecords.every((r) => r.id.startsWith('PI-'))).toBe(true)
  })
})
