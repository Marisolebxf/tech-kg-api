<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import ManualReviewDynamicForm from '../../components/manual-review/ManualReviewDynamicForm.vue'
import { claimProductionReview, directDecideProductionReview, getProductionReview, heartbeatProductionReview, submitProductionReview, type ProductionReviewCase } from '../../api/workflowOperations'

import {
  getHandleCategory,
  getImpactScope,
  getReviewConsequence,
  getReviewTemplate,
  getSedimentHint,
  isMapTypeFix,
  labelZh,
  resolvePipelineStep,
  type ReviewAction,
  type ReviewRecord,
} from './manual-review-data'

const route = useRoute()
const productionCase = ref<ProductionReviewCase>()
const record = ref<ReviewRecord | undefined>()
let heartbeatTimer: number | undefined
const isSupported = computed(() => Boolean(record.value))
const isHistory = computed(() => record.value?.status === '已完成' || record.value?.status === '已撤销' || record.value?.status === '已驳回')
const isDirectCase = computed(() => productionCase.value?.template?.id === 'T_DIRECT' || productionCase.value?.workflowType === 'kg.custom.steps')
// T_DIRECT 候选解析：candidate_snapshot 含 _kind/_nodeLabel/_edgeType/_fromId/_toId + 候选本体字段
const directCandidate = computed<Record<string, unknown>>(() => (productionCase.value?.candidate as Record<string, unknown>) || {})
const directKind = computed<string>(() => String(directCandidate.value._kind || productionCase.value?.objectType || ''))
const directNodeLabel = computed<string>(() => String(directCandidate.value._nodeLabel || ''))
const directEdgeType = computed<string>(() => String(directCandidate.value._edgeType || ''))
const directFromId = computed<string>(() => String(directCandidate.value._fromId || ''))
const directToId = computed<string>(() => String(directCandidate.value._toId || ''))
const directCandidateFields = computed<Array<[string, unknown]>>(() =>
  Object.entries(directCandidate.value).filter(([k]) => !k.startsWith('_'))
)
// 候选字段修正（修正后入库）：编辑态 + 每个字段的输入值；`_` 元字段不可编辑（后端以快照为准）
const directEditing = ref(false)
const directEdits = ref<Record<string, string>>({})
const directOriginalText = (val: unknown) => (typeof val === 'object' && val !== null ? JSON.stringify(val) : String(val))
const directEditedKeys = computed(() =>
  directCandidateFields.value
    .filter(([key, val]) => directEdits.value[key] !== undefined && directEdits.value[key] !== directOriginalText(val))
    .map(([key]) => key),
)
const directPatchedCandidate = computed<Record<string, unknown> | null>(() => {
  if (!directEditedKeys.value.length) return null
  const patched: Record<string, unknown> = {}
  for (const [key, val] of directCandidateFields.value) {
    patched[key] = directEdits.value[key] !== undefined ? directEdits.value[key] : val
  }
  return patched
})
function toggleDirectEdit() {
  directEditing.value = !directEditing.value
  if (directEditing.value) {
    const initial: Record<string, string> = {}
    for (const [key, val] of directCandidateFields.value) initial[key] = directOriginalText(val)
    directEdits.value = initial
  } else {
    directEdits.value = {}
  }
}
const directConfidence = computed<number | null>(() => {
  const c = (productionCase.value?.input as Record<string, unknown>)?.confidence
  return typeof c === 'number' ? c : null
})
// ① 原始记录：source_record（源表完整行）+ sourceTable / sourceRecordId
const directSourceRecord = computed<Record<string, unknown> | null>(() =>
  (productionCase.value?.data as { source_record?: Record<string, unknown> | null } | undefined)?.source_record ?? null,
)
const directSourceTable = computed<string>(() => productionCase.value?.sourceTable || '')
const directSourceRecordId = computed<string>(() => productionCase.value?.sourceRecordId || '')
const directSourceRecordFields = computed<Array<[string, unknown]>>(() =>
  directSourceRecord.value ? Object.entries(directSourceRecord.value) : [],
)
// ② 抽取推理过程：llm_input (system + user) + llm_output (raw JSON string)
const directLlmInput = computed<{ system: string; user: string } | null>(() =>
  (productionCase.value?.data as { llm_input?: { system: string; user: string } | null } | undefined)?.llm_input ?? null,
)
const directLlmOutput = computed<string | null>(() =>
  (productionCase.value?.data as { llm_output?: string | null } | undefined)?.llm_output ?? null,
)
// 溯源 ID（executionId 来自 input.executionId；workflowId / sourceTaskId 直接在 case 上）
const directExecutionId = computed<string>(() =>
  String((productionCase.value?.input as Record<string, unknown> | undefined)?.executionId || ''),
)
// 标题带具体类型：论文实体入库审核 / 引用关系入库审核
const directTitle = computed(() => {
  if (!isDirectCase.value) {
    return isHistory.value ? '处理记录' : '人工处理详情'
  }
  if (directKind.value === 'relation') {
    const subject = `${labelZh(directEdgeType.value)}关系`
    return isHistory.value ? `${subject}审核结果` : `${subject}入库审核`
  }
  const subject = `${labelZh(directNodeLabel.value)}实体`
  return isHistory.value ? `${subject}审核结果` : `${subject}入库审核`
})
const isEditable = computed(() => {
  if (isDirectCase.value) return productionCase.value?.status === 'OPEN'
  return ['CLAIMED','IN_REVIEW'].includes(productionCase.value?.status || '')
})
const canClaim = computed(() => productionCase.value?.status === 'OPEN' && !isDirectCase.value)

const template = computed(() => (record.value ? getReviewTemplate(record.value) : null))
const impactScope = computed(() => (record.value ? getImpactScope(record.value) : '任务级'))
const templateId = computed(() => template.value?.id ?? 'T_RUNTIME')
const handleCategory = computed(() => (record.value ? getHandleCategory(record.value) : '质量校验'))
const consequence = computed(() => {
  if (productionCase.value?.consequence) return { ...productionCase.value.consequence, rerunAnchor: productionCase.value.pipelineStepName || productionCase.value.consequence.rerunStepId, phase: record.value?.module || '图谱构建' }
  return record.value ? getReviewConsequence(record.value) : null
})
const pipelineStep = computed(() => (record.value ? resolvePipelineStep(record.value) : null))
const sedimentHint = computed(() => (record.value ? getSedimentHint(record.value) : ''))
const sedimentRule = ref(false)

const note = ref(record.value?.decisionNote ?? '')
const feedback = ref('')
const submitting = ref(false)
const dynamicResult = ref<Record<string, unknown>>({})
const safeComponentTypes = new Set(['mapping-table','field-editor','record-merge','entity-comparison','evidence-list','attribute-comparison','runtime-config','raw-json-readonly'])
const hasUnknownComponent = computed(() => Boolean(productionCase.value?.template?.displaySchema.sections.some((section) => !safeComponentTypes.has(section.type))))
const actionMeta: Record<string, { label: string; kind: string; rerun?: boolean }> = {
  'save-map-rerun': { label: '保存映射并重跑', kind: 'primary', rerun: true }, 'confirm-type': { label: '确认类型并重跑', kind: 'primary', rerun: true },
  'save-fill-rerun': { label: '保存补录并重跑', kind: 'primary', rerun: true }, 'merge-rerun': { label: '确认合并并重跑', kind: 'primary', rerun: true },
  'entity-confirm': { label: '确认实体裁决并重跑', kind: 'primary', rerun: true }, 'pass-rerun': { label: '确认证据并重跑', kind: 'primary', rerun: true },
  'confirm-attr': { label: '确认属性并重跑', kind: 'primary', rerun: true }, 'retry-task': { label: '重试当前对象', kind: 'primary', rerun: true },
  'rerun-batch': { label: '恢复批次并重跑', kind: 'primary', rerun: true }, 'reject-candidate': { label: '驳回候选', kind: 'danger' },
  'reject-extract': { label: '驳回并退回抽取', kind: 'danger', rerun: true }, 'reject-upstream': { label: '驳回上游', kind: 'danger' },
  'keep-isolated': { label: '保持隔离', kind: 'secondary' }, 'isolate-dup': { label: '保持重复记录隔离', kind: 'secondary' },
  'discard-record': { label: '丢弃记录', kind: 'danger' }, 'rollback-dict': { label: '回滚字典', kind: 'danger', rerun: true },
  'force-pass': { label: '强制通过', kind: 'danger', rerun: true }, 'skip-task': { label: '跳过任务', kind: 'danger' }, 'escalate': { label: '升级治理员', kind: 'secondary' },
  'accept': { label: '通过（写图）', kind: 'primary' }, 'reject': { label: '驳回（丢弃）', kind: 'danger' },
}
const productionActions = computed(() => (productionCase.value?.template?.allowedActions || []).map((id) => ({ id, ...(actionMeta[id] || { label: id, kind: 'secondary' }) })))
const preferredProductionAction = computed(() => {
  const preferred: Record<string, string> = { T_MAP: 'save-map-rerun', T_DQ_FILL: 'save-fill-rerun', T_DQ_MERGE: 'merge-rerun', T_LINK: 'entity-confirm', T_EVIDENCE: 'pass-rerun', T_ATTR: 'confirm-attr', T_RUNTIME: productionCase.value?.isolationScope === 'BATCH' ? 'rerun-batch' : 'retry-task' }
  const expected = preferred[productionCase.value?.template?.id || '']
  return productionActions.value.find((action) => action.id === expected) || productionActions.value.find((action) => action.kind === 'primary')
})

type MappingRow = { source: string; sample: string; target: string; options: { value: string; label: string }[] }
const orgFieldOpts = [
  { value: 'name_zh', label: 'Organization.name_zh' },
  { value: 'credit_code', label: 'Organization.credit_code' },
  { value: 'registered_capital_value', label: 'Organization.registered_capital_value' },
]
const patentFieldOpts = [
  { value: 'legal_status', label: 'Patent.legal_status（实质审查）' },
  { value: 'publication_number', label: 'Patent.publication_number' },
]
const paperEnumOpts = [
  { value: 'conference', label: 'conference（会议）' },
  { value: 'journal', label: 'journal（期刊）' },
  { value: 'preprint', label: 'preprint（预印本）' },
]
const mappingRows = ref<MappingRow[]>([])
const keepRawEnum = ref(true)
const dictVersion = ref('v1.2')

const entityVerdict = ref<'merge' | 'create' | 'retype' | 'reject'>('merge')
const entityTypeFix = ref('Expert')
const entityTypes = [
  { value: 'Expert', label: 'Expert（专家）' },
  { value: 'Person', label: 'Person（人才）' },
  { value: 'Organization', label: 'Organization（机构）' },
]

const evidenceItems = ref([
  { id: '1', label: '', table: '', recordId: '', excerpt: '', trust: '', checked: true },
])
const extraEvidence = ref('')
const relationVerdict = ref<'approve' | 'reject' | 'hold'>('approve')

const attrVerdict = ref<'A' | 'B' | 'manual' | 'split'>('A')
const attrManualOrg = ref('')
const attrManualRange = ref('')

const fillTitleZh = ref('')
const fillTitleEn = ref('')

const mergeMaster = ref(0)
const mergeFields = ref({ authors: true, affiliation: true, source_channel: false })

const runtimeConfig = ref('kg-extract-v2.6.1')
const manualReviewFormRef = ref()
const manualReviewFormModel = computed(() => ({
  entityVerdict: entityVerdict.value,
  entityTypeFix: entityTypeFix.value,
  relationVerdict: relationVerdict.value,
  attrVerdict: attrVerdict.value,
  fillTitleZh: fillTitleZh.value,
  mergeMaster: mergeMaster.value,
  mergeFields: mergeFields.value,
  runtimeConfig: runtimeConfig.value,
  evidenceItems: evidenceItems.value,
  note: note.value,
}))
const manualReviewFormRules = {
  entityVerdict: [{ required: true, message: '请选择实体裁决结果' }],
  relationVerdict: [{ required: true, message: '请选择关系裁决结果' }],
  attrVerdict: [{ required: true, message: '请选择属性裁决结果' }],
  fillTitleZh: [{
    validator: (value: string, callback: (error?: string) => void) =>
      callback(templateId.value !== 'T_DQ_FILL' || value.trim() ? undefined : '请输入论文中文标题'),
  }],
  mergeMaster: [{ required: true, message: '请选择主记录' }],
  runtimeConfig: [{ required: true, message: '请选择重跑 Prompt' }],
}

const initWorkspace = (item?: ReviewRecord) => {
  if (!item) return
  const id = getReviewTemplate(item).id

  if (id === 'T_MAP') {
    if (item.type === 'Schema 字段映射失败' || item.id === 'PI-20260714-0102') {
      mappingRows.value = [
        { source: 'corp_name', sample: '华南智能芯片有限公司', target: 'name_zh', options: orgFieldOpts },
        { source: 'credit_no', sample: '91440300MA5F…', target: 'credit_code', options: orgFieldOpts },
        { source: 'registered_capital', sample: '5000 万元', target: 'registered_capital_value', options: orgFieldOpts },
      ]
    } else if (item.type === '专利状态标准化失败') {
      mappingRows.value = [
        { source: 'legal_status_raw', sample: 'substantive-review', target: 'legal_status', options: patentFieldOpts },
      ]
    } else {
      mappingRows.value = [
        { source: 'source_type', sample: item.sourceResult || 'conference-online', target: 'conference', options: paperEnumOpts },
      ]
    }
  }

  if (id === 'T_MAP' && isMapTypeFix(item)) {
    entityVerdict.value = 'retype'
    entityTypeFix.value = 'Expert'
  }

  if (id === 'T_LINK') {
    entityVerdict.value = item.type === '单任务执行失败' ? 'create' : 'merge'
    entityTypeFix.value = 'Expert'
  }

  if (id === 'T_EVIDENCE') {
    evidenceItems.value = item.type.includes('合作关系')
      ? [
          { id: '1', label: '华南智能芯片官网新闻', table: item.sourceTable, recordId: item.sourceRecordId, excerpt: '双方将围绕智能芯片设计与云端算力平台展开联合技术研发。', trust: '企业官网 · 可信度 0.82', checked: true },
          { id: '2', label: '第二独立来源', table: '—', recordId: '—', excerpt: '尚未获取，需补充合作公告、合同编号或权威媒体报道。', trust: '待补充', checked: false },
        ]
      : [
          { id: '1', label: '参考文献原文片段', table: item.sourceTable, recordId: item.sourceRecordId, excerpt: '文末参考文献中出现《矩阵分析基础》，但未解析到完整 DOI。', trust: '论文原文 · 可信度 0.78', checked: true },
          { id: '2', label: 'DOI / 标题交叉验证', table: '—', recordId: '—', excerpt: '尚未完成被引论文 DOI 与标题一致性校验。', trust: '待补充', checked: false },
        ]
  }

  if (id === 'T_DQ_FILL') {
    fillTitleZh.value = ''
    fillTitleEn.value = ''
  }
}

const mapProductionRecord = (item: ProductionReviewCase): ReviewRecord => ({
  id:item.id, batch:item.batchId || '-', module:item.phase, node:item.nodeId, type:item.errorType, domain:item.domain, objectType:item.objectType, objectId:item.objectId, object:item.objectName, ruleId:item.templateId, evidence:`${item.evidence?.length || 0} 项真实证据`, score:item.riskLevel, handler:item.assigneeName || '待领取', status:item.status === 'RESOLVED' ? '已完成' : item.status === 'REJECTED' ? '已驳回' : item.status === 'CANCELLED' ? '已撤销' : '待处理', updatedAt:item.updatedAt, sourceResult:item.diagnosis, suggestion:item.scope, sourceTable:item.sourceTable || '-', sourceRecordId:item.sourceRecordId || '-',
})

const startHeartbeat = () => {
  if (!productionCase.value || !['CLAIMED','IN_REVIEW'].includes(productionCase.value.status)) return
  window.clearInterval(heartbeatTimer)
  heartbeatTimer = window.setInterval(async () => {
    if (!productionCase.value) return
    try { productionCase.value = await heartbeatProductionReview(productionCase.value.id, productionCase.value.version) }
    catch { window.clearInterval(heartbeatTimer) }
  }, 30000)
}

async function loadReview() {
  try {
    productionCase.value = await getProductionReview(String(route.params.instanceId || ''))
    record.value = mapProductionRecord(productionCase.value)
    note.value = String(productionCase.value.draft?.note || '')
    initWorkspace(record.value)
    startHeartbeat()
  } catch (error) { feedback.value = error instanceof Error ? error.message : '人工处理详情加载失败' }
}

async function claimCase() {
  if (!productionCase.value) return
  try {
    productionCase.value = await claimProductionReview(productionCase.value.id, productionCase.value.version)
    record.value = mapProductionRecord(productionCase.value); startHeartbeat(); feedback.value = '领取成功，系统已开始保持处理心跳。'
  } catch (error) { feedback.value = error instanceof Error ? `${error.message}，请重新加载。` : '领取失败' }
}

onMounted(loadReview)
onBeforeUnmount(() => window.clearInterval(heartbeatTimer))

const candidateCard = computed(() => {
  const item = record.value
  if (!item) return null
  const name = item.object.split('/')[0].trim()
  if (item.type === '单任务执行失败' && (item.node.includes('对齐') || item.objectType.includes('实体'))) {
    return {
      name: item.object,
      type: '源记录（对齐未产出候选）',
      org: `${item.sourceTable} · ${item.sourceRecordId}`,
      score: '—',
      method: 'align-timeout',
      shortName: name,
    }
  }
  return {
    name: item.object,
    type: item.type.includes('实体类型判断错误') ? 'Person' : '候选实体',
    org: item.domain === '人才' || item.domain === '专利' ? '机构待核对 / 别名未归一' : item.domain,
    score: item.score || '—',
    method: item.type.includes('实体类型判断错误') ? 'schema-classify' : 'fuzzy',
    shortName: name,
  }
})

const stockCard = computed(() => {
  const item = record.value
  if (!item) return null
  if (item.type === '单任务执行失败' && (item.node.includes('对齐') || item.objectType.includes('实体'))) {
    return {
      name: '待检索存量实体',
      type: '—',
      org: '对齐任务超时，系统未返回对照候选',
      id: '—',
    }
  }
  if (item.type.includes('实体类型判断错误')) {
    return { name: '建议目标类型 Expert', type: 'Expert', org: '中国科学院自动化研究所', id: '—' }
  }
  if (item.id === 'PI-20260714-0012' || item.object.includes('周启航')) {
    return { name: '周启航', type: 'Expert', org: '深圳先进技术研究院', id: 'Expert_20372' }
  }
  if (item.object.includes('陈卓')) {
    return { name: '陈卓', type: 'Expert', org: '专利发明人对齐', id: 'Expert_88102' }
  }
  if (item.object.includes('李晓峰')) {
    return { name: '李晓峰', type: 'Expert', org: '中国科学院自动化研究所', id: 'Expert_20510' }
  }
  return { name: '张明远', type: 'Expert', org: '中国科学院自动化研究所', id: 'Expert_10028' }
})

const relationSides = computed(() => {
  const parts = (record.value?.object || '').split('→').map((s) => s.trim())
  return { left: parts[0] || '主体', right: parts[1] || '客体' }
})

const attrSides = computed(() => ({
  A: { label: '来源 A（模型）', value: '自动化研究所 2023–至今', updated: '2026-07-10' },
  B: { label: '来源 B（存量）', value: '华南智能芯片 2022–至今', updated: '2026-06-01' },
}))

const dupRecords = [
  { id: '#1', hint: 'DOI 完整 ★建议', detail: '标题一致 · DOI 齐全' },
  { id: '#2', hint: '作者单位更全', detail: '标题一致 · 单位字段更完整' },
  { id: '#3', hint: '来源渠道不同', detail: '标题一致 · 来源渠道补充' },
]

const primaryActionLabel = computed(() => preferredProductionAction.value?.label || '无可用动作')

const isCooperationRelation = computed(() => record.value?.type.includes('合作关系') ?? false)
const relationSchemaLabel = computed(() => isCooperationRelation.value ? 'COOPERATE_WITH\n企业合作' : 'CITES\n论文引用')
const relationRuleSummary = computed(() => isCooperationRelation.value
  ? '系统识别双方存在联合技术研发合作，但当前只有 1 个独立来源。'
  : '系统识别两篇论文存在引用关系，但 DOI 与标题交叉验证不完整。')

const relationEvidenceCount = computed(() => (
  evidenceItems.value.filter((item) => item.checked && item.recordId !== '—').length
  + (extraEvidence.value.trim() ? 1 : 0)
))

const isPrimaryDisabled = computed(() => !isEditable.value || hasUnknownComponent.value || !preferredProductionAction.value)

const footerHint = computed(() => {
  if (isHistory.value) return record.value?.status === '已撤销' ? '任务已撤销' : '处理已完成'
  if (templateId.value === 'T_DQ_FILL' && !fillTitleZh.value.trim()) return '请先补全必填字段，再保存并重跑'
  if (templateId.value === 'T_EVIDENCE' && relationVerdict.value === 'approve' && relationEvidenceCount.value < 2) return '确认入图前需补充第二个独立可信来源'
  const write = consequence.value?.writeTarget ?? '处理结果'
  const anchor = consequence.value?.rerunAnchor ?? record.value?.node
  const scopeHint = impactScope.value === '批次级' ? '并恢复被阻断的公共流程' : '仅重跑本对象'
  const sediment = sedimentRule.value && sedimentHint.value ? ' · 同时沉淀为规则' : ''
  return `确认后：回写「${write}」，从「${anchor}」重跑，${scopeHint}${sediment}`
})

const backPath = computed(() => (
  isHistory.value ? '/manual-review?tab=history' : `/manual-review?batch=${record.value?.batch ?? ''}`
))

const applySuggestedTitle = () => {
  fillTitleZh.value = record.value?.id === 'PI-20260714-0008'
    ? '面向产业链的知识图谱推理研究'
    : '知识图谱增量构建方法研究'
  fillTitleEn.value = record.value?.id === 'PI-20260714-0008'
    ? 'Knowledge Graph Reasoning for Industrial Chains'
    : 'Incremental Knowledge Graph Construction Methods'
}

const handleAction = async (action: ReviewAction | { id: string; label: string; kind: string; rerun?: boolean }) => {
  const reviewRecord = record.value
  if (!reviewRecord || !isEditable.value) return
  if (action.kind === 'primary') {
    const validationErrors = await manualReviewFormRef.value?.validate()
    if (validationErrors) return
  }
  // kg.custom.steps T_DIRECT 案例：accept 直接写图，reject 丢弃，不走 claim/submit/approve 4-eyes 流程
  if (isDirectCase.value && productionCase.value && ['accept', 'accept-fix', 'reject'].includes(action.id)) {
    const patched = action.id === 'accept-fix' ? directPatchedCandidate.value : undefined
    if (action.id === 'accept-fix' && !patched) {
      feedback.value = '请先修改候选字段，再修正后入库'
      return
    }
    // 修改数字要在响应覆盖 candidate 前取（响应里的候选已是修正值，事后取恒为 0）
    const editedCount = directEditedKeys.value.length
    submitting.value = true
    try {
      productionCase.value = await directDecideProductionReview(
        productionCase.value.id,
        productionCase.value.version,
        action.id !== 'reject',
        note.value,
        patched ?? undefined,
      )
      record.value = mapProductionRecord(productionCase.value)
      directEditing.value = false
      directEdits.value = {}
      feedback.value = action.id === 'accept-fix'
        ? `已按修正后候选写入图（修改 ${editedCount} 个字段，已记入审计）`
        : action.id === 'accept' ? '已通过，候选已写入图' : '已驳回，候选丢弃'
    } catch (error) {
      feedback.value = error instanceof Error ? error.message : '决策失败'
    } finally {
      submitting.value = false
    }
    return
  }
  let label = action.label
  if (action.id === 'entity-confirm' || action.id === 'confirm-type' || ((templateId.value === 'T_LINK' || (templateId.value === 'T_MAP' && isMapTypeFix(reviewRecord))) && action.kind === 'primary')) {
    label = primaryActionLabel.value
    if (entityVerdict.value === 'reject') {
      label = '驳回候选'
    }
  }
  const rerun = 'rerun' in action ? action.rerun : label.includes('重跑') || label.includes('重试')
  const result = {
    templateId: templateId.value,
    mode: templateId.value,
    label,
    mappings: mappingRows.value.map((row) => ({ source: row.source, target: row.target })),
    entityVerdict: entityVerdict.value,
    entityType: entityTypeFix.value,
    relationVerdict: relationVerdict.value,
    evidence: evidenceItems.value,
    extraEvidence: extraEvidence.value,
    attrVerdict: attrVerdict.value,
    attrManualOrg: attrManualOrg.value,
    attrManualRange: attrManualRange.value,
    titleZh: fillTitleZh.value,
    titleEn: fillTitleEn.value,
    mergeMaster: mergeMaster.value,
    mergeFields: mergeFields.value,
    runtimeConfig: runtimeConfig.value,
    handleCategory: handleCategory.value,
    rerunStepId: consequence.value?.rerunStepId,
    preferStep: action.id === 'reject-extract' ? 'extract' : undefined,
    writeTarget: consequence.value?.writeTarget,
    sedimentRule: sedimentRule.value,
    actionKind: 'actionKind' in action ? action.actionKind : undefined,
  }
  Object.assign(result, dynamicResult.value)
  const parseJson = (key: string, target: string) => {
    const raw = dynamicResult.value[key]
    if (typeof raw === 'string' && raw.trim()) { try { (result as Record<string, unknown>)[target] = JSON.parse(raw) } catch { throw new Error(`${key} 不是合法 JSON`) } }
  }
  parseJson('mappingsJson', 'mappings'); parseJson('fieldsJson', 'fields'); parseJson('runtimeJson', 'runtimeConfig')
  delete (result as Record<string, unknown>).rerunStepId
  try {
    if (productionCase.value) {
      productionCase.value = await submitProductionReview(reviewRecord.id, { version: productionCase.value.version, actionId: action.id, note: note.value, result })
      record.value = mapProductionRecord(productionCase.value)
      window.clearInterval(heartbeatTimer)
    }
    const messages = [
      rerun
        ? `修正结果已回写到「${consequence.value?.writeTarget}」，系统已从「${consequence.value?.rerunAnchor ?? record.value?.node}」创建重跑。可到图谱构建查看进度。`
        : '处理结果已回写。',
    ]
    if (sedimentRule.value && sedimentHint.value) messages.push('裁决已勾选沉淀为规则。')
    feedback.value = messages.join(' ')
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '人工处理提交失败'
  }
}

const runPrimary = () => {
  if (preferredProductionAction.value && !hasUnknownComponent.value) handleAction(preferredProductionAction.value)
}

const secondaryActions = computed(() => {
  if (hasUnknownComponent.value) return []
  return productionActions.value.filter((action) => action.id !== preferredProductionAction.value?.id)
})
</script>

<template>
  <div v-if="record && isSupported" class="rw">
    <header class="rw-head">
      <div class="rw-head__main">
        <RouterLink :to="backPath">← 返回处理队列</RouterLink>
        <h1>{{ directTitle }}</h1>
        <p>
          <code>{{ record.id }}</code>
          <span v-if="!isDirectCase">{{ record.handler }}</span>
          <em v-if="!isDirectCase">{{ pipelineStep?.name || record.node }} · {{ record.type }} · {{ record.ruleId }}</em>
        </p>
      </div>
      <div v-if="!isDirectCase" class="rw-head__badges">
        <span class="cat-pill">{{ handleCategory }}</span>
        <span :class="['scope', impactScope === '批次级' ? 'is-batch' : 'is-task']">{{ impactScope }}{{ impactScope === '批次级' ? ' · 已阻断' : '' }}</span>
        <span :class="['status', `is-${record.status}`]">{{ record.status }}</span>
      </div>
    </header>

    <section v-if="!isDirectCase" class="rw-sec rw-sec--evidence" aria-label="证据">
      <header class="rw-sec__head"><div><h2>案件信息与证据</h2><p>对象信息、系统结论与证据摘要 · 本屏信息应足够做出决定</p></div></header>
      <div class="rw-diag">
        <div>
          <strong>{{ record.object }}</strong>
          <span>{{ record.objectType }} · {{ record.objectId }}</span>
        </div>
        <div>
          <span>来源</span>
          <em>{{ record.sourceTable }} / {{ record.sourceRecordId }}</em>
        </div>
        <div>
          <span>系统结论</span>
          <em>{{ record.sourceResult }}</em>
        </div>
        <div v-if="record.score">
          <span>置信度</span>
          <em>{{ record.score }}</em>
        </div>
        <p class="rw-diag__evidence">{{ record.evidence }}</p>
      </div>
    </section>

    <main class="rw-body">
      <a-form ref="manualReviewFormRef" :model="manualReviewFormModel" :rules="manualReviewFormRules" class="manual-review-form" layout="vertical">
      <header v-if="!isDirectCase" class="rw-zone-head">
        <div>
          <h2>裁决 · {{ template?.title }}</h2>
          <p>{{ template?.question }} · {{ record.suggestion }}</p>
        </div>
      </header>

      <ManualReviewDynamicForm v-if="productionCase?.template && !isDirectCase" :sections="productionCase.template.displaySchema.sections" :data="productionCase.data || {}" @change="dynamicResult = $event" />
      <template v-else>
      <!-- T_DIRECT：kg.custom.steps 候选入库决策 5 段式布局 -->
      <section v-if="templateId === 'T_DIRECT'" class="zone zone-direct">
        <!-- ① 候选：要审核的实体/关系（最显眼，一上来就让人知道审什么） -->
        <section class="direct-candidate">
          <header class="direct-candidate-head">
            <h3>① 候选</h3>
            <button v-if="isEditable && !directEditing" type="button" class="direct-edit-toggle" @click="toggleDirectEdit">编辑字段</button>
            <button v-else-if="directEditing && isEditable" type="button" class="direct-edit-toggle is-active" @click="toggleDirectEdit">取消编辑</button>
          </header>
          <header class="direct-target">
            <span class="direct-target-tag">{{ directKind === 'relation' ? '审核关系' : '审核实体' }}</span>
            <template v-if="directKind === 'entity'">
              <strong class="direct-target-nodelabel">{{ labelZh(directNodeLabel) || '(未指定标签)' }}</strong>
              <code class="direct-target-id">{{ productionCase?.objectId || '—' }}</code>
              <em class="direct-target-name">{{ productionCase?.objectName || '' }}</em>
            </template>
            <template v-else-if="directKind === 'relation'">
              <code>{{ directFromId || '—' }}</code>
              <em class="direct-target-edge">-[{{ directEdgeType || '?' }}]-&gt;</em>
              <code>{{ directToId || '—' }}</code>
            </template>
            <template v-else>
              <em>未知候选类型 · {{ directKind || 'no kind' }}</em>
            </template>
          </header>
          <table v-if="directCandidateFields.length" class="direct-fields" :class="{ 'is-editing': directEditing }">
            <tbody>
              <tr v-for="[key, val] in directCandidateFields" :key="String(key)" :class="{ 'is-edited': directEditing && directEdits[key] !== undefined && directEdits[key] !== directOriginalText(val) }">
                <th>{{ key }}</th>
                <td v-if="directEditing"><input v-model="directEdits[key]" :placeholder="directOriginalText(val)" /></td>
                <td v-else>{{ directOriginalText(val) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="direct-empty">暂无候选字段</p>
          <p v-if="directEditing" class="direct-edit-hint">发现 schema 映射字段不对时可在此修正；修改后用「修正后入库」提交，修改内容会记入审计日志。</p>
        </section>

        <!-- ② 为什么需要你确认：confidence 追溯 -->
        <section class="direct-why">
          <h3>② 为什么需要你确认</h3>
          <p v-if="directConfidence !== null">
            LLM 输出的 <code class="direct-confidence-inline">confidence = {{ directConfidence.toFixed(2) }}</code>，
            系统阈值 <strong>0.85</strong>。
            <strong>{{ directConfidence.toFixed(2) }} &lt; 0.85</strong>
            → 未达自动入库线 → 候选被隔离在写图前。通过则写入图，驳回则丢弃。
          </p>
          <p v-else>
            系统未给出置信度，候选被隔离在写图前，等待人工决策。
          </p>
          <details class="direct-trace">
            <summary>溯源信息（点击 ID 跳转任务详情）</summary>
            <dl>
              <div><dt>workflow</dt><dd><RouterLink :to="`/processing-instance/${productionCase?.workflowId || ''}`" class="direct-trace-link"><code>{{ productionCase?.workflowId || '—' }}</code></RouterLink></dd></div>
              <div><dt>workflow 类型</dt><dd>{{ productionCase?.workflowType || '—' }}</dd></div>
              <div><dt>执行 ID</dt><dd><RouterLink :to="`/processing-instance/${directExecutionId || ''}`" class="direct-trace-link"><code>{{ directExecutionId || '—' }}</code></RouterLink></dd></div>
              <div><dt>来源任务</dt><dd><RouterLink :to="`/processing-instance/${productionCase?.sourceTaskId || ''}`" class="direct-trace-link"><code>{{ productionCase?.sourceTaskId || '—' }}</code></RouterLink></dd></div>
              <div><dt>产生 step</dt><dd>{{ productionCase?.pipelineStepId || '—' }}</dd></div>
            </dl>
          </details>
        </section>

        <!-- ③ 原始记录：源表完整行（折叠） -->
        <details class="direct-section-details">
          <summary>
            ③ 原始记录
            <span v-if="directSourceTable" class="direct-section-meta">· 来源表 <code>{{ directSourceTable }}</code> / 记录 <code>{{ directSourceRecordId }}</code></span>
            <span v-else class="direct-section-meta">· 暂无</span>
          </summary>
          <div class="direct-section-body">
            <table v-if="directSourceRecordFields.length" class="direct-fields">
              <tbody>
                <tr v-for="[key, val] in directSourceRecordFields" :key="String(key)">
                  <th>{{ key }}</th>
                  <td>{{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}</td>
                </tr>
              </tbody>
            </table>
            <p v-else class="direct-empty">暂无原始记录（旧 case 未存源行）</p>
          </div>
        </details>

        <!-- ④ 抽取推理过程：LLM 输入 + 输出（折叠） -->
        <section class="direct-extraction">
          <h3>④ 抽取推理过程</h3>
          <details v-if="directLlmInput" class="direct-llm-io">
            <summary>LLM 输入（system prompt + user message）</summary>
            <div class="direct-llm-section">
              <h4>system prompt</h4>
              <pre>{{ directLlmInput.system }}</pre>
              <h4>user message</h4>
              <pre>{{ directLlmInput.user }}</pre>
            </div>
          </details>
          <details v-if="directLlmOutput" class="direct-llm-io">
            <summary>LLM 输出（JSON）</summary>
            <pre>{{ directLlmOutput }}</pre>
          </details>
          <p v-if="!directLlmInput && !directLlmOutput" class="direct-empty">暂无 LLM 记录（旧 case 未存 prompt/响应）</p>
        </section>

        <!-- ⑤ 决策：通过入库 / 驳回丢弃 -->
        <section class="direct-decision">
          <h3>⑤ 决策</h3>
          <label v-if="isEditable" class="direct-note">
            <span>备注（可选）</span>
            <input v-model="note" placeholder="审核备注..." />
          </label>
          <div v-if="isEditable" class="direct-actions">
            <button v-if="directEditing" class="direct-accept direct-accept-fix" :disabled="submitting || !directPatchedCandidate" @click="handleAction({ id: 'accept-fix', label: '修正后入库', kind: 'primary' })">
              <strong>修正后入库</strong>
              <em>{{ directPatchedCandidate ? `覆盖 ${directEditedKeys.length} 个字段并写图 · 记入审计` : '请先在①候选中修改字段' }}</em>
            </button>
            <button v-if="!directEditing" class="direct-accept" :disabled="submitting" @click="handleAction({ id: 'accept', label: '通过·入库', kind: 'primary' })">
              <strong>通过·入库</strong>
              <em>{{ directKind === 'relation' ? `创建${labelZh(directEdgeType) || '?'}边` : `创建${labelZh(directNodeLabel) || '?'}节点` }}</em>
            </button>
            <button class="direct-reject" :disabled="submitting" @click="handleAction({ id: 'reject', label: '驳回·丢弃', kind: 'danger' })">
              <strong>驳回·丢弃</strong>
              <em>候选丢弃，不写图</em>
            </button>
          </div>
          <p v-else class="direct-done">已决策 · 状态 {{ record.status }}</p>
        </section>
      </section>

      <!-- T_MAP：选值映射（字段/字典/实体类型） -->
      <section v-else-if="templateId === 'T_MAP'" class="zone zone-map">
        <template v-if="record && isMapTypeFix(record)">
          <p class="zone-banner">系统实体类型判断与源记录特征不一致，请选择正确类型后从 Schema 映射节点重跑。</p>
          <div class="entity-compare">
            <article>
              <span>当前判定</span>
              <strong>{{ candidateCard?.name }}</strong>
              <p>类型：{{ candidateCard?.type }}</p>
              <p>机构：{{ candidateCard?.org }}</p>
              <p>置信度 {{ candidateCard?.score }}</p>
            </article>
            <b>→</b>
            <article>
              <span>建议目标</span>
              <strong>{{ stockCard?.name }}</strong>
              <p>类型：{{ stockCard?.type }}</p>
              <p>机构：{{ stockCard?.org }}</p>
            </article>
          </div>
          <a-form-item field="entityVerdict" hide-label>
          <a-radio-group v-model="entityVerdict" class="verdict" aria-label="类型裁决">
            <a-radio value="retype" :disabled="!isEditable">修正类型为</a-radio>
            <a-select v-model="entityTypeFix" :disabled="!isEditable">
              <a-option v-for="t in entityTypes" :key="t.value" :value="t.value">{{ t.label }}</a-option>
            </a-select>
          </a-radio-group>
          </a-form-item>
        </template>
        <template v-else>
          <p class="zone-banner">{{ impactScope === '批次级' ? '本映射影响公共流程，当前节点及下游已阻断。' : '修正后仅重跑本对象相关任务。' }}</p>
          <div class="map-head"><span>来源字段</span><span>样例值</span><span>Schema / 字典目标</span></div>
          <div v-for="row in mappingRows" :key="row.source" class="map-row">
            <code>{{ row.source }}</code>
            <span>{{ row.sample }}</span>
            <a-select v-model="row.target" :disabled="!isEditable">
              <a-option v-for="opt in row.options" :key="opt.value" :value="opt.value">{{ opt.label }}</a-option>
            </a-select>
          </div>
          <a-checkbox v-if="record.type.includes('标准化失败')" v-model="keepRawEnum" class="check-line" :disabled="!isEditable">保留原始值用于追溯</a-checkbox>
          <label v-if="record.type === '专利状态标准化失败'" class="inline-select">
            <span>字典版本</span>
            <a-select v-model="dictVersion" :disabled="!isEditable">
              <a-option value="v1.2">回滚到 dict-patent-v1.2</a-option>
              <a-option value="v1.3-fix">在 v1.3 新增枚举条目</a-option>
            </a-select>
          </label>
        </template>
      </section>

      <!-- T_LINK -->
      <section v-else-if="templateId === 'T_LINK'" class="zone zone-entity">
        <p v-if="record.type === '单任务执行失败'" class="zone-banner">对齐任务超时未生成候选，请基于源记录人工裁决后重跑。</p>
        <div class="entity-compare">
          <article>
            <span>候选</span>
            <strong>{{ candidateCard?.name }}</strong>
            <p>类型：{{ candidateCard?.type }}</p>
            <p>机构：{{ candidateCard?.org }}</p>
            <p>置信度 {{ candidateCard?.score }} · {{ candidateCard?.method }}</p>
          </article>
          <b>对照</b>
          <article>
            <span>存量 / 建议目标</span>
            <strong>{{ stockCard?.name }}</strong>
            <p>类型：{{ stockCard?.type }}</p>
            <p>机构：{{ stockCard?.org }}</p>
            <p v-if="stockCard?.id !== '—'">ID：{{ stockCard?.id }}</p>
          </article>
        </div>
        <a-form-item field="entityVerdict" hide-label>
        <a-radio-group v-model="entityVerdict" class="verdict" aria-label="实体对齐裁决">
          <a-radio value="merge" :disabled="!isEditable">合并到右侧存量实体</a-radio>
          <a-radio value="create" :disabled="!isEditable">保留为新建实体</a-radio>
          <a-radio value="reject" :disabled="!isEditable">不是同一实体，驳回候选</a-radio>
        </a-radio-group>
        </a-form-item>
      </section>

      <!-- T_EVIDENCE -->
      <section v-else-if="templateId === 'T_EVIDENCE'" class="zone zone-relation">
        <div class="relation-metrics">
          <article><span>当前置信度</span><strong>{{ record.score || '—' }}</strong><em>入图阈值 0.85</em></article>
          <article><span>独立证据</span><strong>{{ relationEvidenceCount }} / 2</strong><em>{{ relationEvidenceCount >= 2 ? '已达人工确认要求' : '未达自动入图要求' }}</em></article>
          <article><span>当前结果</span><strong>已隔离</strong><em>未写入生产图谱</em></article>
        </div>
        <div class="rel-card">
          <strong>{{ relationSides.left }}</strong>
          <em class="relation-schema">{{ relationSchemaLabel }}</em>
          <strong>{{ relationSides.right }}</strong>
          <p>抽取结果：{{ relationRuleSummary }}规则 {{ record.ruleId }} 要求至少 2 个可信证据。</p>
        </div>
        <h3 class="zone-subtitle">关系证据</h3>
        <a-form-item field="evidenceItems" hide-label>
        <div class="evidence-list">
          <a-checkbox v-for="item in evidenceItems" :key="item.id" v-model="item.checked" class="evidence-item" :disabled="!isEditable || item.recordId === '—'">
            <div>
              <strong>{{ item.label }} <em>{{ item.trust }}</em></strong>
              <p>{{ item.excerpt }}</p>
              <span>{{ item.table }} / {{ item.recordId }}</span>
            </div>
          </a-checkbox>
        </div>
        </a-form-item>
        <label v-if="isEditable" class="wide-field">
          <span>补充证据（链接或记录 ID）</span>
          <input v-model="extraEvidence" placeholder="例如：COOP-89321-B 或公告 URL" />
        </label>
        <h3 class="zone-subtitle">处理结论</h3>
        <a-form-item field="relationVerdict" hide-label>
        <a-radio-group v-model="relationVerdict" class="verdict relation-verdict">
          <a-radio value="approve" :disabled="!isEditable"><span><strong>确认关系入图</strong><small>证据充分，允许该关系进入图谱</small></span></a-radio>
          <a-radio value="hold" :disabled="!isEditable"><span><strong>保持隔离</strong><small>暂不入图，等待补充第二独立来源</small></span></a-radio>
          <a-radio value="reject" :disabled="!isEditable"><span><strong>驳回关系</strong><small>认定当前证据不支持该关系，退回抽取节点</small></span></a-radio>
        </a-radio-group>
        </a-form-item>
      </section>

      <!-- T_ATTR -->
      <section v-else-if="templateId === 'T_ATTR'" class="zone zone-attr">
        <p class="attr-name">属性：任职机构（含时间）</p>
        <div class="attr-compare">
          <article>
            <span>{{ attrSides.A.label }}</span>
            <strong>{{ attrSides.A.value }}</strong>
            <em>更新 {{ attrSides.A.updated }}</em>
          </article>
          <article>
            <span>{{ attrSides.B.label }}</span>
            <strong>{{ attrSides.B.value }}</strong>
            <em>更新 {{ attrSides.B.updated }}</em>
          </article>
        </div>
        <a-form-item field="attrVerdict" hide-label>
        <a-radio-group v-model="attrVerdict" class="verdict">
          <a-radio value="A" :disabled="!isEditable">采用来源 A</a-radio>
          <a-radio value="B" :disabled="!isEditable">采用来源 B</a-radio>
          <a-radio value="manual" :disabled="!isEditable">
            手工改写
            <input v-model="attrManualOrg" class="mini" placeholder="机构" :disabled="!isEditable || attrVerdict !== 'manual'" />
            <input v-model="attrManualRange" class="mini" placeholder="起止时间" :disabled="!isEditable || attrVerdict !== 'manual'" />
          </a-radio>
          <a-radio value="split" :disabled="!isEditable">时间切分（两段都保留）</a-radio>
        </a-radio-group>
        </a-form-item>
      </section>

      <!-- T_DQ_FILL -->
      <section v-else-if="templateId === 'T_DQ_FILL'" class="zone zone-fill">
        <p class="zone-banner">必填规则 {{ record.ruleId }} 校验失败：原始记录 <code>title = null</code>，已阻止该记录进入标准表。</p>
        <div class="fill-layout">
          <section class="source-snapshot">
            <header><strong>原始记录</strong><span>{{ record.sourceTable }} / {{ record.sourceRecordId }}</span></header>
            <dl>
              <div class="is-error"><dt>title</dt><dd>null <em>必填缺失</em></dd></div>
              <div><dt>doi</dt><dd>10.2026/kg.104</dd></div>
              <div><dt>authors</dt><dd>陈晓峰，李静，王宇</dd></div>
              <div><dt>publish_year</dt><dd>2026</dd></div>
              <div><dt>journal</dt><dd>情报学报</dd></div>
              <div><dt>abstract</dt><dd>面向产业链多源数据，研究知识图谱构建与关系推理方法…</dd></div>
            </dl>
          </section>
          <section class="doi-suggestion">
            <header><strong>DOI 参考信息</strong><span>可信度 0.98</span></header>
            <h3>《面向产业链的知识图谱推理研究》</h3>
            <p>Knowledge Graph Reasoning for Industrial Chains</p>
            <small>DOI、作者、发表年份与原始记录一致</small>
            <button v-if="isEditable" class="linkish" type="button" @click="applySuggestedTitle">采用此标题</button>
          </section>
        </div>
        <div class="fill-form">
          <h3 class="zone-subtitle">补录结果</h3>
          <a-form-item class="wide-field" field="fillTitleZh" label="title_zh" required><input v-model="fillTitleZh" :disabled="!isEditable" placeholder="论文中文标题" /></a-form-item>
          <a-form-item class="wide-field" field="fillTitleEn" label="title_en"><input v-model="fillTitleEn" :disabled="!isEditable" placeholder="论文英文标题（可选）" /></a-form-item>
          <p class="fill-rerun-note">保存后将从「清洗标准化」节点重跑当前记录，不影响同批次其他数据。</p>
        </div>
      </section>

      <!-- T_DQ_MERGE -->
      <section v-else-if="templateId === 'T_DQ_MERGE'" class="zone zone-merge">
        <p class="zone-banner">同一 paper_id 命中 {{ dupRecords.length }} 条源记录</p>
        <a-form-item field="mergeMaster" hide-label>
        <a-radio-group v-model="mergeMaster" class="verdict">
          <a-radio v-for="(row, index) in dupRecords" :key="row.id" :value="index" :disabled="!isEditable" :class="{ active: mergeMaster === index }">
            主记录 {{ row.id }} · {{ row.hint }}
            <small>{{ row.detail }}</small>
          </a-radio>
        </a-radio-group>
        </a-form-item>
        <div class="merge-fields">
          <span>从非主记录并入字段</span>
          <a-checkbox v-model="mergeFields.authors" :disabled="!isEditable">authors</a-checkbox>
          <a-checkbox v-model="mergeFields.affiliation" :disabled="!isEditable">affiliation</a-checkbox>
          <a-checkbox v-model="mergeFields.source_channel" :disabled="!isEditable">source_channel</a-checkbox>
        </div>
      </section>

      <!-- T_RUNTIME（含未识别工单兜底） -->
      <section v-else class="zone zone-runtime">
        <dl class="runtime-dl">
          <div><dt>影响范围</dt><dd>{{ impactScope }}{{ impactScope === '批次级' ? ' · 已阻断下游' : ' · 仅本任务' }}</dd></div>
          <div><dt>失败摘要</dt><dd>{{ record.evidence }}</dd></div>
          <div><dt>版本信息</dt><dd>模型 Qwen3-32B-Instruct · Prompt kg-extract-v2.6.1 · Schema v1.8</dd></div>
          <div><dt>系统结论</dt><dd>{{ record.sourceResult }}</dd></div>
        </dl>
        <div class="runtime-links">
          <RouterLink :to="`/processing-instance/${record.id}`">打开任务详情日志 →</RouterLink>
        </div>
        <a-form-item v-if="isEditable && impactScope === '批次级'" class="inline-select" field="runtimeConfig" label="重跑使用 Prompt">
          <a-select v-model="runtimeConfig">
            <a-option value="kg-extract-v2.6.1">kg-extract-v2.6.1（当前）</a-option>
            <a-option value="kg-extract-v2.5.0">kg-extract-v2.5.0（回退）</a-option>
            <a-option value="kg-extract-v2.6.2-rc">kg-extract-v2.6.2-rc（试验）</a-option>
          </a-select>
        </a-form-item>
      </section>
      </template>

      <div v-if="!isEditable" class="rw-readonly">
        <strong>{{ record.decision }}</strong>
        <p>{{ record.decisionNote }}</p>
        <em>{{ record.completedAt }}</em>
      </div>

      </a-form>
      <p v-if="feedback" class="rw-feedback">{{ feedback }}</p>
    </main>

    <section v-if="!isDirectCase" class="rw-sec rw-sec--consequence" aria-label="后果">
      <header class="rw-sec__head"><div><h2>决策影响</h2><p>确认前请核对：回写哪里、从哪重跑、影响范围</p></div></header>
      <div class="tri-grid">
        <div><span>回写目标</span><strong>{{ consequence?.writeTarget }}</strong></div>
        <div><span>重跑锚点</span><strong>{{ consequence?.rerunAnchor }}</strong><em v-if="pipelineStep">· {{ pipelineStep.id }}</em></div>
        <div><span>影响范围</span><strong>{{ impactScope }}{{ impactScope === '批次级' ? ' · 恢复公共流程' : ' · 仅本对象' }}</strong></div>
      </div>
      <p v-if="pipelineStep" class="pipeline-hint">流水线：{{ pipelineStep.phase }} · 节点 <code>{{ pipelineStep.id }}</code>（{{ pipelineStep.name }}）· 原始节点「{{ record.node }}」</p>
      <a-checkbox v-if="isEditable && sedimentHint" v-model="sedimentRule" class="sediment-line">
        <span>{{ sedimentHint }}</span>
      </a-checkbox>
    </section>

    <footer v-if="!isDirectCase" class="rw-foot">
      <span>{{ footerHint }}</span>
      <button v-if="canClaim" class="primary" type="button" @click="claimCase">领取任务</button>
      <div v-if="isEditable" class="rw-foot__actions">
        <button
          v-for="action in secondaryActions"
          :key="action.id"
          type="button"
          :class="{ danger: action.kind === 'danger' }"
          @click="handleAction(action)"
        >
          {{ action.label }}
        </button>
        <label class="note-inline"><input v-model="note" placeholder="备注（可选）" /></label>
        <button class="primary" type="button" :disabled="isPrimaryDisabled" @click="runPrimary">{{ primaryActionLabel }}</button>
      </div>
    </footer>
  </div>
  <div v-else class="rw-empty">
    <h1>未找到处理实例</h1>
    <RouterLink to="/manual-review">返回人工处理</RouterLink>
  </div>
</template>

<style scoped>
.rw {
  display: flex;
  height: 100%;
  min-height: 0;
  flex-direction: column;
  overflow: auto;
  color: #17233b;
}

.rw-head {
  display: flex;
  flex: 0 0 auto;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 10px;
}

.rw-head a {
  color: #165dff;
  font-size: 12px;
  text-decoration: none;
}

.rw-head h1 {
  margin: 6px 0 4px;
  font-size: 20px;
}

.rw-head p {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin: 0;
  color: #667085;
  font-size: 12px;
}

.rw-head code {
  padding: 1px 6px;
  border-radius: 4px;
  background: #eef4ff;
  color: #175cd3;
}

.rw-head__badges {
  display: flex;
  gap: 8px;
}

.scope,
.status {
  padding: 4px 10px;
  border-radius: 99px;
  font-size: 11px;
}

.scope.is-batch {
  background: #fee4e2;
  color: #b42318;
}

.scope.is-task {
  background: #eaf2ff;
  color: #175cd3;
}

.status.is-待处理 {
  background: #fff0e8;
  color: #c4320a;
}

.status.is-已完成 {
  background: #e9f8ef;
  color: #067647;
}

.rw-diag {
  display: grid;
  flex: 0 0 auto;
  grid-template-columns: 1.4fr 1fr 1.2fr auto;
  gap: 10px 16px;
  margin-bottom: 10px;
  padding: 12px 14px;
  border: 1px solid #d5e3f5;
  border-radius: 8px;
  background: #f8fbff;
}

.rw-diag strong {
  display: block;
  margin-bottom: 2px;
  font-size: 13px;
}

.rw-diag span {
  color: #7890b5;
  font-size: 10px;
}

.rw-diag em {
  display: block;
  margin-top: 2px;
  color: #344054;
  font-size: 11px;
  font-style: normal;
  line-height: 16px;
}

.rw-diag__evidence {
  grid-column: 1 / -1;
  margin: 0;
  padding: 8px 10px;
  border-left: 3px solid #f04438;
  border-radius: 4px;
  background: #fff6f5;
  color: #344054;
  font-size: 12px;
  line-height: 18px;
}

.rw-body {
  flex: 0 0 auto;
  min-height: 0;
  overflow: visible;
  padding: 14px 16px 18px;
  border: 1px solid #bdd7ff;
  border-radius: 9px;
  background: #fff;
}

.rw-zone-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 14px;
}

.rw-zone-head h2 {
  margin: 0;
  font-size: 15px;
}

.rw-zone-head p {
  margin: 4px 0 0;
  color: #667085;
  font-size: 12px;
}

.rw-step-no,
.rw-sec__head > b {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #165dff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  font-style: normal;
}

.rw-sec {
  flex: 0 0 auto;
  margin-bottom: 10px;
  padding: 12px 14px;
  border: 1px solid #d5e3f5;
  border-radius: 8px;
  background: #f8fbff;
}

.rw-sec__head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 10px;
}

.rw-sec__head h2 {
  margin: 0;
  font-size: 14px;
}

.rw-sec__head p {
  margin: 3px 0 0;
  color: #667085;
  font-size: 11px;
}

.rw-sec .rw-diag {
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
}

.rw-sec--consequence {
  border-color: #a9c6f5;
  background: linear-gradient(160deg, #fdfeff, #f5f9ff);
}

.cat-pill {
  padding: 4px 10px;
  border-radius: 99px;
  background: #eef4ff;
  color: #175cd3;
  font-size: 11px;
}

.tri-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
}

.tri-grid > div {
  display: grid;
  gap: 4px;
  padding: 10px 12px;
  border: 1px solid #d5e3f5;
  border-radius: 7px;
  background: #fff;
}

.tri-grid span {
  color: #7890b5;
  font-size: 10px;
}

.tri-grid strong {
  font-size: 12px;
  line-height: 17px;
}

.tri-grid em {
  color: #7890b5;
  font-size: 10px;
  font-style: normal;
}

.sediment-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  padding: 9px 12px;
  border: 1px solid #a6f4c5;
  border-radius: 6px;
  background: #ecfdf3;
  color: #067647;
  font-size: 12px;
  cursor: pointer;
}

.pipeline-hint {
  margin: 10px 0 0;
  color: #667085;
  font-size: 11px;
}

.pipeline-hint code {
  padding: 1px 6px;
  border-radius: 4px;
  background: #eef4ff;
  color: #175cd3;
  font-size: 11px;
}

.status.is-已撤销 {
  background: #f2f4f7;
  color: #475467;
}

.status.is-已驳回 {
  background: #f2f4f7;
  color: #b42318;
}

@media (max-width: 960px) {
  .tri-grid {
    grid-template-columns: 1fr;
  }
}

.zone-banner {
  margin: 0 0 12px;
  padding: 8px 10px;
  border-radius: 6px;
  background: #f0f5ff;
  color: #344f7a;
  font-size: 11px;
}

.map-head,
.map-row {
  display: grid;
  grid-template-columns: 160px minmax(180px, 1fr) minmax(220px, 1fr);
  gap: 10px;
  align-items: center;
}

.map-head {
  margin-bottom: 6px;
  color: #667085;
  font-size: 10px;
}

.map-row {
  margin-bottom: 8px;
  padding: 10px;
  border: 1px solid #e1e8f2;
  border-radius: 6px;
  background: #fbfcfe;
}

.map-row code {
  color: #175cd3;
  font-size: 11px;
}

.map-row select,
.inline-select select,
.wide-field input,
.verdict select,
.note-inline input,
.mini {
  height: 34px;
  padding: 0 9px;
  border: 1px solid #bdd0ea;
  border-radius: 5px;
  background: #fff;
  color: #263650;
  font: 12px inherit;
}

.entity-compare,
.attr-compare {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 12px;
  align-items: stretch;
  margin-bottom: 14px;
}

.entity-compare article,
.attr-compare article,
.rel-card {
  padding: 14px;
  border: 1px solid #d5e3f5;
  border-radius: 8px;
  background: #f8fbff;
}

.entity-compare > b {
  align-self: center;
  color: #165dff;
  font-size: 12px;
}

.entity-compare span,
.attr-compare span,
.rel-card p {
  color: #7890b5;
  font-size: 10px;
}

.entity-compare strong,
.attr-compare strong,
.rel-card strong {
  display: block;
  margin: 6px 0;
  font-size: 14px;
}

.entity-compare p,
.attr-compare em {
  margin: 4px 0 0;
  color: #475467;
  font-size: 11px;
  font-style: normal;
}

.rel-card {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 8px;
  margin-bottom: 12px;
  text-align: center;
}

.rel-card em {
  align-self: center;
  color: #165dff;
  font-size: 11px;
  font-style: normal;
}

.rel-card .relation-schema {
  line-height: 18px;
  white-space: pre-line;
}

.rel-card p {
  grid-column: 1 / -1;
  margin: 8px 0 0;
  text-align: left;
}

.verdict {
  display: grid;
  gap: 8px;
}

.verdict label,
.evidence-item,
.check-line,
.merge-fields label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid #d4dfed;
  border-radius: 6px;
  background: #fff;
  color: #344054;
  font-size: 12px;
  cursor: pointer;
}

.verdict label.active,
.evidence-item:has(input:checked) {
  border-color: #165dff;
  background: #f5f8ff;
}

.verdict small {
  width: 100%;
  margin-left: 22px;
  color: #7890b5;
  font-size: 10px;
}

.evidence-list {
  display: grid;
  gap: 8px;
  margin-bottom: 12px;
}

.evidence-item div {
  display: grid;
  gap: 2px;
}

.evidence-item span {
  color: #7890b5;
  font-size: 10px;
}

.relation-metrics {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 12px;
}

.relation-metrics article {
  display: grid;
  gap: 4px;
  padding: 11px 13px;
  border: 1px solid #d5e3f5;
  border-radius: 7px;
  background: #f8fbff;
}

.relation-metrics span,
.relation-metrics em {
  color: #7890b5;
  font-size: 10px;
  font-style: normal;
}

.relation-metrics strong {
  color: #263650;
  font-size: 17px;
}

.zone-subtitle {
  margin: 14px 0 8px;
  color: #263650;
  font-size: 12px;
}

.evidence-item {
  align-items: flex-start;
}

.evidence-item div {
  flex: 1;
}

.evidence-item strong {
  display: flex;
  justify-content: space-between;
  gap: 12px;
}

.evidence-item strong em {
  color: #067647;
  font-size: 10px;
  font-style: normal;
  font-weight: 500;
}

.evidence-item p {
  margin: 5px 0;
  color: #475467;
  font-size: 11px;
  line-height: 17px;
}

.relation-verdict {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.relation-verdict label {
  align-items: flex-start;
}

.relation-verdict label > span {
  display: grid;
  flex: 1;
  gap: 4px;
}

.relation-verdict small {
  width: auto;
  margin: 0;
  line-height: 16px;
}

.fill-layout {
  display: grid;
  grid-template-columns: 1.25fr 1fr;
  gap: 12px;
}

.source-snapshot,
.doi-suggestion,
.fill-form {
  overflow: hidden;
  border: 1px solid #d5e3f5;
  border-radius: 8px;
  background: #fff;
}

.source-snapshot header,
.doi-suggestion header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid #e5edf8;
  background: #f8fbff;
}

.source-snapshot header span,
.doi-suggestion header span {
  color: #7890b5;
  font-size: 10px;
}

.source-snapshot dl {
  margin: 0;
}

.source-snapshot dl > div {
  display: grid;
  grid-template-columns: 105px 1fr;
  gap: 10px;
  padding: 8px 12px;
  border-bottom: 1px solid #edf2f7;
}

.source-snapshot dt {
  color: #7890b5;
  font: 10px ui-monospace, SFMono-Regular, Menlo, monospace;
}

.source-snapshot dd {
  margin: 0;
  color: #344054;
  font-size: 11px;
  line-height: 17px;
}

.source-snapshot .is-error {
  background: #fff6f5;
}

.source-snapshot .is-error dd {
  color: #b42318;
}

.source-snapshot dd em {
  margin-left: 8px;
  padding: 2px 6px;
  border-radius: 99px;
  background: #fee4e2;
  font-size: 9px;
  font-style: normal;
}

.doi-suggestion {
  padding-bottom: 14px;
  background: linear-gradient(145deg, #f5f9ff, #fff);
}

.doi-suggestion header {
  margin-bottom: 16px;
}

.doi-suggestion h3,
.doi-suggestion p,
.doi-suggestion small,
.doi-suggestion button {
  margin-right: 14px;
  margin-left: 14px;
}

.doi-suggestion h3 {
  margin-top: 0;
  margin-bottom: 7px;
  font-size: 15px;
}

.doi-suggestion p {
  color: #475467;
  font-size: 11px;
}

.doi-suggestion small {
  display: block;
  margin-bottom: 15px;
  color: #067647;
  font-size: 10px;
}

.fill-form {
  margin-top: 12px;
  padding: 0 13px 13px;
  background: #fbfdff;
}

.fill-form .wide-field span b {
  margin-left: 5px;
  color: #d92d20;
  font-size: 9px;
}

.fill-rerun-note {
  margin: 11px 0 0;
  padding: 8px 10px;
  border-radius: 5px;
  background: #f0f5ff;
  color: #52647f;
  font-size: 10px;
}

.wide-field,
.inline-select {
  display: grid;
  gap: 6px;
  margin-top: 10px;
}

.wide-field span,
.inline-select span {
  color: #596a83;
  font-size: 11px;
}

.attr-name {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
}

.merge-fields {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-top: 12px;
}

.merge-fields > span {
  color: #667085;
  font-size: 11px;
}

.runtime-dl {
  display: grid;
  gap: 10px;
  margin: 0 0 12px;
}

.runtime-dl > div {
  display: grid;
  grid-template-columns: 88px 1fr;
  gap: 8px;
}

.runtime-dl dt {
  color: #7890b5;
  font-size: 11px;
}

.runtime-dl dd {
  margin: 0;
  color: #344054;
  font-size: 12px;
  line-height: 18px;
}

.runtime-links a,
.linkish {
  border: 0;
  background: transparent;
  color: #165dff;
  font-size: 12px;
  cursor: pointer;
  text-decoration: none;
}

.rw-readonly {
  margin-top: 16px;
  padding: 12px;
  border-radius: 6px;
  background: #f5f8ff;
}

.rw-readonly p {
  margin: 6px 0;
  color: #667085;
  font-size: 12px;
}

.rw-readonly em {
  color: #98a2b3;
  font-size: 11px;
  font-style: normal;
}

.rw-feedback {
  margin: 14px 0 0;
  padding: 10px 12px;
  border: 1px solid #a6f4c5;
  border-radius: 6px;
  background: #ecfdf3;
  color: #067647;
  font-size: 12px;
}

.rw-foot {
  display: flex;
  flex: 0 0 auto;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 10px;
  padding: 12px 14px;
  border: 1px solid #dce8f8;
  border-radius: 8px;
  background: #fff;
}

.rw-foot > span {
  color: #667085;
  font-size: 11px;
}

.rw-foot__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
}

.rw-foot button {
  height: 34px;
  padding: 0 12px;
  border: 1px solid #bdd0ea;
  border-radius: 6px;
  background: #fff;
  color: #40516d;
  cursor: pointer;
}

.rw-foot button.primary {
  border-color: #165dff;
  background: #165dff;
  color: #fff;
}

.rw-foot button:disabled {
  border-color: #d0d5dd;
  background: #eaecf0;
  color: #98a2b3;
  cursor: not-allowed;
}

.rw-foot button.danger {
  border-color: #f1b8b3;
  color: #b42318;
}

.note-inline input {
  width: 160px;
}

.rw-empty {
  padding: 48px;
  text-align: center;
}

@media (max-width: 1000px) {
  .relation-metrics,
  .relation-verdict,
  .fill-layout {
    grid-template-columns: 1fr;
  }
}

.rw-empty a {
  color: #165dff;
}

@media (max-width: 960px) {
  .rw-diag {
    grid-template-columns: 1fr 1fr;
  }

  .entity-compare,
  .attr-compare,
  .rel-card,
  .map-head,
  .map-row {
    grid-template-columns: 1fr;
  }

  .entity-compare > b,
  .map-head {
    display: none;
  }

  .rw-foot {
    align-items: stretch;
    flex-direction: column;
  }
}

/* === T_DIRECT 五段式入库决策区（扁平布局，匹配 demo） === */
.zone-direct{display:grid;gap:24px;padding:0;border:0;background:transparent}
.zone-direct h3{margin:0 0 10px;padding-left:10px;border-left:3px solid #165dff;font-size:13px;font-weight:600;color:#344054}
/* 共享字段表（① 原始记录 + ③ 候选）+ 占位 */
.direct-fields{width:100%;border-collapse:collapse;border:1px solid #eef2f7;border-radius:6px;overflow:hidden;font-size:12px}
.direct-fields th,.direct-fields td{padding:8px 12px;border-bottom:1px solid #eef2f7;text-align:left;vertical-align:top}
.direct-fields tr:last-child th,.direct-fields tr:last-child td{border-bottom:0}
.direct-fields th{width:180px;background:#f8fafc;color:#66758f;font-weight:500;font-size:11px}
.direct-fields td{color:#17233b;word-break:break-word}
.direct-empty{margin:0;padding:14px;text-align:center;color:#9aa5b5;font-size:11px}
.direct-candidate-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
.direct-edit-toggle{height:26px;padding:0 12px;border:1px solid #bfd4f0;border-radius:4px;background:#f4f8ff;color:#175cd3;font-size:11px;cursor:pointer;white-space:nowrap}
.direct-edit-toggle:hover{background:#e8f1ff}
.direct-edit-toggle.is-active{border-color:#f6b9b4;background:#fff7f6;color:#b42318}
.direct-fields.is-editing td input{width:100%;padding:5px 8px;border:1px solid #c9d8ee;border-radius:4px;font-size:12px;color:#17233b;box-sizing:border-box}
.direct-fields.is-editing td input:focus{outline:none;border-color:#165dff}
.direct-fields tr.is-edited th{background:#fff8ec;color:#b54708}
.direct-fields tr.is-edited td input{border-color:#f0c877;background:#fffdf5}
.direct-edit-hint{margin:10px 0 0;padding:8px 10px;border:1px dashed #e2c98f;border-radius:6px;background:#fffcf2;color:#8a6512;font-size:11px;line-height:17px}
.direct-accept-fix{border-color:#f79009;background:#f79009}
.direct-accept-fix:disabled{border-color:#f2d5a8;background:#fdeccd}
/* ① 原始记录（折叠块） */
.direct-section-details{padding-left:10px;border-left:3px solid #165dff}
.direct-section-details summary{cursor:pointer;font-size:13px;font-weight:600;color:#344054;list-style:none;margin:0;padding:0}
.direct-section-details summary::-webkit-details-marker{display:none}
.direct-section-details summary::before{content:"▶ ";font-size:10px;color:#9aa5b5;font-weight:400}
.direct-section-details[open] summary::before{content:"▼ "}
.direct-section-meta{font-weight:400;color:#667085;font-size:11px;margin-left:6px}
.direct-section-meta code{padding:2px 6px;border-radius:3px;background:#f1f5fa;color:#344f73;font:11px Consolas,monospace}
.direct-section-body{margin-top:10px}
/* ② 抽取推理过程（LLM I/O 折叠块） */
.direct-llm-io{margin-top:10px;border:1px solid #eef2f7;border-radius:6px;background:#f8fafc}
.direct-llm-io:first-child{margin-top:0}
.direct-llm-io summary{padding:10px 14px;cursor:pointer;color:#667085;font-size:12px;list-style:none}
.direct-llm-io summary::-webkit-details-marker{display:none}
.direct-llm-io summary::before{content:"▶ ";font-size:10px;color:#9aa5b5}
.direct-llm-io[open] summary::before{content:"▼ "}
.direct-llm-io pre{margin:0;padding:12px 14px;border-top:1px solid #eef2f7;background:#fbfcfe;color:#344054;font:12px ui-monospace,SFMono-Regular,Menlo,monospace;line-height:1.5;overflow-x:auto;white-space:pre-wrap}
.direct-llm-section h4{margin:12px 14px 6px;color:#66758f;font-size:10px;text-transform:uppercase;letter-spacing:.5px;font-weight:600}
.direct-llm-section h4:first-child{margin-top:0}
.direct-llm-section pre{margin:0 0 12px}
.direct-llm-section pre:last-child{margin-bottom:0}
/* ③ 候选（header 扁平 inline，无 box） */
.direct-target{display:flex;align-items:baseline;gap:12px;margin-bottom:10px;flex-wrap:wrap;padding:0;border:0;background:transparent}
.direct-target-tag{padding:6px 14px;border-radius:4px;background:#b54708;color:#fff;font-size:13px;font-weight:600;letter-spacing:.5px}
.direct-target-nodelabel{font-size:18px;color:#17233b;font-weight:700}
.direct-target-id{padding:2px 8px;border-radius:4px;background:#f1f5fa;color:#344f73;font:12px Consolas,monospace}
.direct-target-name{color:#718099;font-style:normal;font-size:13px}
.direct-target-edge{color:#7f56d9;font-style:normal;font-size:12px;font-weight:600;padding:3px 8px;border-radius:4px;background:#eee8ff}
/* ④ 为什么需要你确认 */
.direct-why p{margin:0 0 10px;color:#475569;line-height:1.7}
.direct-why strong{color:#b54708;font-weight:600}
.direct-confidence-inline{padding:2px 6px;border-radius:3px;background:#fff0d5;color:#b54708;font:12px Consolas,monospace;font-weight:600}
.direct-trace{margin-top:12px;padding:10px 14px;border:1px solid #eef2f7;border-radius:6px;background:#f8fafc}
.direct-trace summary{cursor:pointer;color:#667085;font-size:12px;list-style:none}
.direct-trace summary::-webkit-details-marker{display:none}
.direct-trace summary::before{content:"▶ ";font-size:10px;color:#9aa5b5}
.direct-trace[open] summary::before{content:"▼ "}
.direct-trace dl{margin:10px 0 0;display:grid;grid-template-columns:120px 1fr;gap:6px 14px}
.direct-trace dt{color:#718099;font-size:11px}
.direct-trace dd{margin:0;color:#344054;font-size:12px}
.direct-trace dd code{padding:2px 6px;border-radius:3px;background:#eef4ff;color:#175cd3;font:11px Consolas,monospace}
.direct-trace-link{text-decoration:none}
.direct-trace-link code{cursor:pointer;transition:background .15s,color .15s}
.direct-trace-link:hover code{background:#165dff;color:#fff}
/* ⑤ 决策（浅色 accent，唯一带 box 的段） */
.direct-decision{padding:18px 20px;border:1px solid #f4d39b;border-radius:9px;background:#fffbf2}
.direct-decision h3{border-left-color:#b54708;color:#b54708}
.direct-note{display:grid;gap:6px;margin-bottom:14px;font-size:11px;color:#718099;font-weight:500}
.direct-note input{padding:8px 10px;border:1px solid #dce8f8;border-radius:5px;font:13px/1.5 inherit;color:#17233b}
.direct-actions{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.direct-accept,.direct-reject{display:grid;gap:4px;padding:14px;border-radius:8px;cursor:pointer;font-size:14px;transition:opacity .15s}
.direct-accept{border:2px solid #12b76a;background:#12b76a;color:#fff}
.direct-reject{border:2px solid #d92d20;background:#d92d20;color:#fff}
.direct-accept strong,.direct-reject strong{font-size:15px;font-weight:700}
.direct-accept em,.direct-reject em{color:rgba(255,255,255,.85);font-style:normal;font-size:11px}
.direct-accept:disabled,.direct-reject:disabled{opacity:.5;cursor:not-allowed}
.direct-accept:hover:not(:disabled),.direct-reject:hover:not(:disabled){opacity:.92}
.direct-done{margin:0;padding:14px;text-align:center;color:#475569;font-size:13px;background:#fff;border-radius:6px;border:1px solid #e4ecf6}
</style>
<style scoped>
/* DESIGN_RULES: manual review detail contract. */
.rw{overflow:hidden;color:#1d2129}.rw-head{align-items:center;gap:16px;margin-bottom:16px}.rw-head h1{margin:4px 0;font-size:20px;line-height:28px;font-weight:600}.rw-head p,.rw-head a{font-size:12px;line-height:20px}
.scope,.status{display:inline-flex;align-items:center;gap:6px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}.scope::before,.status::before{display:block;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}.scope.is-batch,.scope.is-task,.status.is-待处理,.status.is-已完成,.status.is-已撤销,.status.is-已驳回{background:transparent}
.rw-diag{gap:8px 16px;margin-bottom:16px;padding:16px;border-color:#e5e6eb;border-radius:6px;background:#f7f8fa}.rw-diag strong{font-size:14px;line-height:22px}.rw-diag span,.rw-diag em{font-size:12px;line-height:20px}
.rw-body{flex:1;overflow:auto;padding:16px;border-color:#e5e6eb;border-radius:6px}
.rw-zone-head{gap:8px;margin-bottom:16px}.rw-zone-head h2,.rw-sec__head h2{font-size:16px;line-height:24px;font-weight:600}.rw-zone-head p,.rw-sec__head p{font-size:12px;line-height:20px}
.rw-sec{margin-bottom:16px;padding:16px;border:0;border-radius:6px;background:#f7f8fa}.rw-sec__head{gap:8px;margin-bottom:16px}
.cat-pill{padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}.tri-grid{gap:16px}.tri-grid>div{gap:4px;padding:8px 16px;border-color:#e5e6eb;border-radius:4px}.tri-grid span,.tri-grid em{font-size:12px;line-height:20px}.tri-grid strong{font-size:14px;line-height:22px}
.rw :is(button,input,select,textarea){font-size:14px;line-height:22px}.rw :is(button,input,select){min-height:32px;border-radius:4px}.rw textarea{border-radius:4px}
.direct-actions{gap:16px}.direct-accept,.direct-reject{min-height:32px;padding:8px 16px;border-radius:4px;font-size:14px}.direct-accept strong,.direct-reject strong{font-size:14px;line-height:22px}.direct-accept em,.direct-reject em{font-size:12px;line-height:20px}
@media(max-width:960px){.rw{overflow:auto}.rw-body{overflow:visible}.tri-grid{grid-template-columns:1fr}}
</style>
