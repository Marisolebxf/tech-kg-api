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
  getSedimentHint,
  type ReviewRecord,
  type PipelineStepId,
} from '../manual-review-data'

// graph-build 移交通道与 6 个休眠模板删除后：前端目录只认三个产活模板
const LIVE_TEMPLATE_IDS = ['T_LINK', 'T_DIRECT', 'T_EXTRACT_FAIL'] as const

const rec = (id: string) => getReviewRecord(id) as ReviewRecord

/** 生产行的 ruleId 即服务端 templateId（队列映射 row.templateId → ruleId）。
 *  node/type 用中性值（manifest 自定义 step 语义），避免 ALIGN 演示语义误命中。 */
const byRuleId = (ruleId: string): ReviewRecord => ({
  ...rec('PI-20260714-0104'),
  id: `PI-SYN-${ruleId}`,
  ruleId,
  node: 'step-1',
  type: '低置信候选',
})

describe('七节点稳定编码', () => {
  it('PIPELINE_STEPS 恰为七个稳定 stepId', () => {
    expect(PIPELINE_STEPS.map((s) => s.id)).toEqual([
      'source', 'normalize', 'schema', 'extract', 'align', 'validate', 'persist',
    ])
    expect(PIPELINE_STEPS.every((s) => s.phase === '数据处理' || s.phase === '图谱构建')).toBe(true)
  })
})

describe('三模板识别（templateId 直传 + ALIGN- 前缀 + 兜底）', () => {
  it.each(LIVE_TEMPLATE_IDS)('%s：ruleId 即模板 id，直传命中', (tid) => {
    expect(getReviewTemplateId(byRuleId(tid))).toBe(tid)
  })

  it('演示种子 ALIGN- 前缀 → T_LINK', () => {
    expect(getReviewTemplateId(rec('PI-20260714-0104'))).toBe('T_LINK') // ALIGN-AMBIGUITY-004
    expect(getReviewTemplateId(rec('PI-20260714-0012'))).toBe('T_LINK') // ALIGN-ENTITY-017
    expect(getReviewTemplateId(rec('PI-20260713-0008'))).toBe('T_LINK') // ALIGN-CONFIDENCE-003
  })

  it('无前缀旧记录统一按实体对齐裁决（T_LINK）展示', () => {
    expect(getReviewTemplateId(byRuleId('LEGACY-0001'))).toBe('T_LINK')
  })

  it('目录收敛为三模板，休眠模板 id 不再是可命中值（兜底为 T_LINK）', () => {
    const produced = new Set([
      ...LIVE_TEMPLATE_IDS.map((tid) => getReviewTemplateId(byRuleId(tid))),
      ...reviewRecords.map((r) => getReviewTemplateId(r)),
    ])
    expect(produced).toEqual(new Set(['T_LINK', 'T_DIRECT', 'T_EXTRACT_FAIL']))
    expect(getReviewTemplateId(byRuleId('T_MAP'))).toBe('T_LINK')
  })
})

describe('模板动作目录与后端契约一致', () => {
  it('T_LINK 含 entity-confirm / reject-candidate', () => {
    const actions = getReviewTemplate(byRuleId('T_LINK')).actions.map((a) => a.id)
    expect(actions).toContain('entity-confirm')
    expect(actions).toContain('reject-candidate')
  })
  it('T_DIRECT 含 accept / reject', () => {
    const actions = getReviewTemplate(byRuleId('T_DIRECT')).actions.map((a) => a.id)
    expect(actions).toEqual(expect.arrayContaining(['accept', 'reject']))
  })
  it('T_EXTRACT_FAIL 含 rerun-record / discard-record', () => {
    const actions = getReviewTemplate(byRuleId('T_EXTRACT_FAIL')).actions.map((a) => a.id)
    expect(actions).toEqual(expect.arrayContaining(['rerun-record', 'discard-record']))
  })
})

describe('阻断节点推导（提交前节点与影响范围确认）', () => {
  const STEP_BY_TEMPLATE: Record<string, PipelineStepId> = {
    T_LINK: 'align',
    T_DIRECT: 'validate', // T_LINK/T_EXTRACT_FAIL 固定；T_DIRECT step id 是 manifest 自定义的，语义不命中时归并到质量校验
    T_EXTRACT_FAIL: 'extract',
  }
  it.each(Object.entries(STEP_BY_TEMPLATE))('%s → 阻断节点 %s', (tid, stepId) => {
    const r = byRuleId(tid)
    expect(resolvePipelineStep(r).id).toBe(stepId)
    const con = getReviewConsequence(r)
    expect(con.rerunStepId).toBe(stepId)
    expect(con.writeTarget).toBeTruthy()
    expect(con.rerunAnchor).toBe(resolvePipelineStep(r).name)
  })

  it('T_DIRECT 语义归并：node/type 含入库字样 → persist，含抽取字样 → extract', () => {
    expect(resolvePipelineStep({ ...byRuleId('T_DIRECT'), node: '图谱入库', type: '候选待入库' }).id).toBe('persist')
    expect(resolvePipelineStep({ ...byRuleId('T_DIRECT'), node: '抽取 step-3', type: '大模型输出格式错误' }).id).toBe('extract')
  })
})

describe('回写目标', () => {
  it('三模板 writeTarget 与移交通道删除后的回写语义一致', () => {
    expect(getReviewConsequence(byRuleId('T_LINK')).writeTarget).toBe('实体对齐结果')
    expect(getReviewConsequence(byRuleId('T_DIRECT')).writeTarget).toBe('图数据库直写')
    expect(getReviewConsequence(byRuleId('T_EXTRACT_FAIL')).writeTarget).toBe('失败记录重跑')
  })
})

describe('P1/任务级 风险与影响范围', () => {
  it('三模板均为 P1 任务级（隔离当前任务，不阻断批次）', () => {
    for (const tid of LIVE_TEMPLATE_IDS) {
      const r = byRuleId(tid)
      expect(getReviewPriority(r).level).toBe('P1')
      expect(getImpactScope(r)).toBe('任务级')
    }
  })
})

describe('置信度展示', () => {
  it('score < 0.9 展示值与“低于阈值”标签', () => {
    const c = getReviewConfidence(rec('PI-20260714-0104')) // score 0.81, module 图谱构建
    expect(c.value).toBe('0.81')
    expect(c.label).toBe('低于阈值')
  })
  it('score >= 0.9 不提示低于阈值', () => {
    const r = { ...rec('PI-20260714-0104'), score: '0.93' }
    expect(getReviewConfidence(r).value).toBe('—')
  })
  it('无 score 不展示', () => {
    const r = { ...rec('PI-20260714-0104'), score: '' }
    expect(getReviewConfidence(r).value).toBe('—')
  })
})

describe('业务分类（顶部 chips）', () => {
  it('三模板映射到实体对齐 / 抽取配置 / 质量校验，不出现 source/persist', () => {
    expect(getHandleCategory(byRuleId('T_LINK'))).toBe('实体对齐')
    expect(getHandleCategory(byRuleId('T_EXTRACT_FAIL'))).toBe('抽取配置')
    expect(['清洗标准化', 'Schema 映射', '抽取配置', '实体对齐', '质量校验'])
      .toContain(getHandleCategory(byRuleId('T_DIRECT')))
  })
})

describe('规则沉淀提示', () => {
  it('仅 T_LINK 提供沉淀提示', () => {
    expect(getSedimentHint(byRuleId('T_LINK'))).toContain('别名')
    expect(getSedimentHint(byRuleId('T_DIRECT'))).toBe('')
    expect(getSedimentHint(byRuleId('T_EXTRACT_FAIL'))).toBe('')
  })
})

describe('演示数据标识（生产模式门控的前置契约）', () => {
  it('reviewRecords 为演示种子：3 条 T_LINK 演示记录，id 统一 PI- 前缀', () => {
    expect(reviewRecords.length).toBe(3)
    expect(reviewRecords.every((r) => r.id.startsWith('PI-'))).toBe(true)
    expect(reviewRecords.every((r) => getReviewTemplateId(r) === 'T_LINK')).toBe(true)
  })
})
