<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { directDecideProductionReview, getProductionReview, heartbeatProductionReview, rerunExtractFailures, submitProductionReview, type ProductionReviewCase } from '../../api/workflowOperations'

import {
  getHandleCategory,
  getReviewConsequence,
  getReviewTemplate,
  labelZh,
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

// T_EXTRACT_FAIL：抽取失败记录（input_snapshot 带 schemaId/sourceBindingId/attempt/rerunExecutionId）
const extractInput = computed<Record<string, unknown>>(() => ((productionCase.value?.data?.input || productionCase.value?.input || {}) as Record<string, unknown>))
const extractErrorFields = computed(() => {
  const candidate = (productionCase.value?.candidate || {}) as Record<string, unknown>
  return Object.entries(candidate).filter(([key]) => !key.startsWith('_'))
})
const extractAttempt = computed(() => Number(extractInput.value.attempt ?? 1))
const extractRerunExecutionId = computed(() => String(extractInput.value.rerunExecutionId ?? ''))
const extractRerunning = computed(() => productionCase.value?.status === 'RERUNNING')
const extractRerunSubmitting = ref(false)

async function rerunThisRecord() {
  if (!productionCase.value || extractRerunSubmitting.value) return
  extractRerunSubmitting.value = true
  try {
    const result = await rerunExtractFailures({ caseIds: [productionCase.value.id] })
    const executionId = result.executions[0]?.executionId ?? '—'
    window.alert(`已下发重跑（新执行 ${executionId}，类别=重新执行），完成后本条自动关闭；仍失败会生成新的待处理记录。`)
    productionCase.value = await getProductionReview(productionCase.value.id)
  } catch (error) {
    window.alert(error instanceof Error ? error.message : '重跑下发失败')
  } finally {
    extractRerunSubmitting.value = false
  }
}
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
  // 直审模式：OPEN 打开即可裁决（无需领取）；CLAIMED/IN_REVIEW 为存量已领取 case
  return ['OPEN','CLAIMED','IN_REVIEW'].includes(productionCase.value?.status || '')
})

const template = computed(() => (record.value ? getReviewTemplate(record.value) : null))
// 生产 case 的模板以服务端 templateId 为准（T_DIRECT/T_EXTRACT_FAIL/T_LINK
// 专用工作台依赖它路由）；legacy 映射只对旧 demo record 生效
const templateId = computed(
  () => productionCase.value?.templateId ?? template.value?.id ?? '',
)
const handleCategory = computed(() => (record.value ? getHandleCategory(record.value) : '质量校验'))
const consequence = computed(() => {
  if (productionCase.value?.consequence) return { ...productionCase.value.consequence, rerunAnchor: productionCase.value.pipelineStepName || productionCase.value.consequence.rerunStepId, phase: record.value?.module || '图谱构建' }
  return record.value ? getReviewConsequence(record.value) : null
})

const note = ref(record.value?.decisionNote ?? '')
const feedback = ref('')
const submitting = ref(false)
const actionMeta: Record<string, { label: string; kind: string; rerun?: boolean }> = {
  'entity-confirm': { label: '确认实体裁决', kind: 'primary' }, 'reject-candidate': { label: '驳回候选', kind: 'danger' },
  'discard-record': { label: '丢弃记录', kind: 'danger' },
  'accept': { label: '通过（写图）', kind: 'primary' }, 'reject': { label: '驳回（丢弃）', kind: 'danger' },
  'rerun-record': { label: '重跑该记录', kind: 'primary', rerun: true },
}
const productionActions = computed(() => (productionCase.value?.template?.allowedActions || []).map((id) => ({ id, ...(actionMeta[id] || { label: id, kind: 'secondary' }) })))
const preferredProductionAction = computed(() => {
  const preferred: Record<string, string> = { T_LINK: 'entity-confirm' }
  const expected = preferred[productionCase.value?.template?.id || '']
  return productionActions.value.find((action) => action.id === expected) || productionActions.value.find((action) => action.kind === 'primary')
})

const entityVerdict = ref<'merge' | 'create' | 'reject'>('merge')
// T_DIRECT 入库决策（与 T_LINK 裁决框统一布局）：通过写图 / 驳回丢弃
const directVerdict = ref<'accept' | 'reject'>('accept')

/** T_LINK 消歧 v2：候选快照里的真实候选（existingCandidates）与待入库记录（_incoming）。 */
const linkSnapshot = computed<Record<string, unknown> | null>(() => {
  const snapshot = productionCase.value?.candidate
  return snapshot && typeof snapshot === 'object' ? (snapshot as Record<string, unknown>) : null
})
const linkCandidates = computed(() => {
  const raw = linkSnapshot.value?.existingCandidates
  if (!Array.isArray(raw) || !raw.length) return []
  return raw
    .filter((c): c is { vid?: string; name?: string; score?: number } => Boolean(c) && typeof c === 'object')
    .filter((c) => c.vid)
    .map((c) => ({
      vid: String(c.vid),
      name: c.name || '—',
      score: typeof c.score === 'number' ? c.score : null,
    }))
})
const linkIncoming = computed(() => {
  const raw = linkSnapshot.value?._incoming
  return raw && typeof raw === 'object' ? (raw as { vid?: string; sourceTable?: string }) : null
})
const linkResolution = computed(() => {
  const raw = linkSnapshot.value?._resolution
  return raw && typeof raw === 'object'
    ? (raw as { matchScore?: number; margin?: number | null })
    : null
})
/** merge 裁决的并入目标（targetEntityId）——服务端校验必须属于候选集。 */
const selectedTarget = ref('')
watch(
  linkCandidates,
  (list) => {
    if (list.length && !selectedTarget.value) selectedTarget.value = list[0].vid
  },
  { immediate: true },
)
/** T_LINK 空候选（脚本挂实体改道、图库召回无同名）：merge 无目标可选，
 *  降级为 create/reject 两键——服务端 create 会落在挂起 vid（object_id）上。 */
const linkMergeDisabled = computed(
  () => templateId.value === 'T_LINK' && !!linkSnapshot.value && !linkCandidates.value.length,
)
watch(
  linkMergeDisabled,
  (disabled) => {
    if (disabled && entityVerdict.value === 'merge') entityVerdict.value = 'create'
  },
  { immediate: true },
)

const manualReviewFormRef = ref()
const manualReviewFormModel = computed(() => ({
  entityVerdict: entityVerdict.value,
  directVerdict: directVerdict.value,
  note: note.value,
}))
const manualReviewFormRules = {
  entityVerdict: [{ required: true, message: '请选择实体裁决结果' }],
  directVerdict: [{ required: true, message: '请选择入库决策' }],
}

const initWorkspace = (item?: ReviewRecord) => {
  if (!item) return
  if (getReviewTemplate(item).id === 'T_LINK') {
    entityVerdict.value = item.type === '单任务执行失败' ? 'create' : 'merge'
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
    type: '候选实体',
    org: item.domain === '人才' || item.domain === '专利' ? '机构待核对 / 别名未归一' : item.domain,
    score: item.score || '—',
    method: 'fuzzy',
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
  if (item.id === 'PI-20260714-0012' || item.object.includes('周启航')) {
    return { name: '周启航', type: 'Expert', org: '深圳先进技术研究院', id: 'Expert_20372' }
  }
  if (item.object.includes('陈卓')) {
    return { name: '陈卓', type: 'Expert', org: '专利发明人对齐', id: 'Expert_88102' }
  }
  if (item.object.includes('李晓峰')) {
    return { name: '李晓峰', type: 'Expert', org: '中国科学院自动化研究所', id: 'Expert_20510' }
  }
  return { name: '存量对照实体', type: '—', org: '以候选快照 existingCandidates 为准', id: '—' }
})

const primaryActionLabel = computed(() => preferredProductionAction.value?.label || '无可用动作')

const isPrimaryDisabled = computed(() => {
  // T_DIRECT 主按钮由裁决单选驱动（不依赖模板目录回传动作），可编辑即可点
  if (templateId.value === 'T_DIRECT') return !isEditable.value
  return !isEditable.value || !preferredProductionAction.value
})

const backPath = computed(() => (
  isHistory.value ? '/manual-review?tab=history' : `/manual-review?batch=${record.value?.batch ?? ''}`
))

const handleAction = async (action: ReviewAction | { id: string; label: string; kind: string; rerun?: boolean }) => {
  const reviewRecord = record.value
  if (!reviewRecord || !isEditable.value) return
  // T_EXTRACT_FAIL 重跑动作走抽取失败重跑通道（新执行 triggerSource=RERUN），不走 submit
  if (templateId.value === 'T_EXTRACT_FAIL' && action.id === 'rerun-record') {
    await rerunThisRecord()
    return
  }
  if (action.kind === 'primary') {
    const validationErrors = await manualReviewFormRef.value?.validate()
    if (validationErrors) return
  }
  // kg.custom.steps T_DIRECT 案例：accept 直接写图，reject 丢弃，不走 submit 通道
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
  // T_LINK 主按钮跟随裁决值：选「不是同一实体」时按驳回候选提交
  const actionId = action.id === 'entity-confirm' && entityVerdict.value === 'reject' ? 'reject-candidate' : action.id
  // merge 必须指定并入目标（服务端校验 targetEntityId ∈ 候选集，缺失会被 400 拒绝）
  if (entityVerdict.value === 'merge' && linkCandidates.value.length && !selectedTarget.value) {
    feedback.value = '请先选择要并入的候选实体'
    return
  }
  const result: Record<string, unknown> = {
    entityVerdict: entityVerdict.value,
    handleCategory: handleCategory.value,
  }
  if (entityVerdict.value === 'merge' && selectedTarget.value) result.targetEntityId = selectedTarget.value
  try {
    if (productionCase.value) {
      productionCase.value = await submitProductionReview(reviewRecord.id, { version: productionCase.value.version, actionId, note: note.value, result })
      record.value = mapProductionRecord(productionCase.value)
      window.clearInterval(heartbeatTimer)
    }
    feedback.value = `裁决已回写「${consequence.value?.writeTarget ?? '处理结果'}」。`
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '人工处理提交失败'
  }
}

const runPrimary = () => {
  // T_DIRECT：底部「确认」跟随裁决单选 —— 驳回走 reject；通过且有字段修正走 accept-fix
  if (templateId.value === 'T_DIRECT') {
    const actionId = directVerdict.value === 'reject' ? 'reject' : directPatchedCandidate.value ? 'accept-fix' : 'accept'
    handleAction({ id: actionId, label: actionId === 'reject' ? '驳回·丢弃' : '通过·入库', kind: actionId === 'reject' ? 'danger' : 'primary' })
    return
  }
  if (preferredProductionAction.value) handleAction(preferredProductionAction.value)
}
</script>

<template>
  <div v-if="record && isSupported" class="rw">
    <header class="rw-head">
      <div class="rw-head__main">
        <RouterLink :to="backPath">← 返回处理队列</RouterLink>
        <h1>{{ directTitle }}</h1>
        <p>
          <code>{{ record.id }}</code>
        </p>
      </div>
      <div class="rw-head__badges">
        <span :class="['status', `is-${record.status}`]">{{ record.status }}</span>
      </div>
    </header>

    <main class="rw-body">
      <a-form ref="manualReviewFormRef" :model="manualReviewFormModel" :rules="manualReviewFormRules" class="manual-review-form" layout="vertical">
      <!-- T_EXTRACT_FAIL：抽取失败记录重跑 -->
      <section v-if="templateId === 'T_EXTRACT_FAIL'" class="zone zone-direct">
        <section class="direct-candidate">
          <header class="direct-candidate-head"><h3>失败记录</h3></header>
          <header class="direct-target">
            <span class="direct-target-tag">来源记录</span>
            <strong class="direct-target-nodelabel">{{ record.sourceTable || '—' }}</strong>
            <code class="direct-target-id">{{ productionCase?.sourceRecordId || '—' }}</code>
            <em class="direct-target-name">第 {{ extractAttempt }} 次尝试</em>
          </header>
          <table v-if="extractErrorFields.length" class="direct-fields">
            <tbody>
              <tr v-for="[key, val] in extractErrorFields" :key="String(key)">
                <th>{{ key }}</th>
                <td>{{ typeof val === 'object' ? JSON.stringify(val) : String(val) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="direct-empty">暂无记录详情</p>
        </section>

        <section class="direct-why">
          <h3>失败原因</h3>
          <pre class="extract-error-text">{{ record.sourceResult || productionCase?.diagnosis || '—' }}</pre>
          <details class="direct-trace">
            <summary>溯源信息</summary>
            <dl>
              <div><dt>Schema</dt><dd><code>{{ String(extractInput.schemaKey ?? '—') }}</code></dd></div>
              <div><dt>来源绑定</dt><dd><code>{{ String(extractInput.sourceBindingId ?? '—') }}</code></dd></div>
              <div><dt>原执行</dt><dd><RouterLink :to="`/processing-instance/${String(extractInput.executionId ?? '')}`" class="direct-trace-link"><code>{{ String(extractInput.executionId ?? '—') }}</code></RouterLink></dd></div>
              <div v-if="extractRerunExecutionId"><dt>重跑执行</dt><dd><RouterLink :to="`/processing-instance/${extractRerunExecutionId}`" class="direct-trace-link"><code>{{ extractRerunExecutionId }}</code></RouterLink></dd></div>
              <div v-if="extractInput.jobId"><dt>所属任务</dt><dd><code>{{ String(extractInput.jobId) }}</code></dd></div>
            </dl>
          </details>
        </section>

        <section class="direct-decision">
          <h3>操作</h3>
          <div class="direct-actions">
            <!-- 已处理（终态）重跑按钮保留但置灰 -->
            <button type="button"
              class="direct-accept"
              :disabled="extractRerunSubmitting || productionCase?.status !== 'OPEN'"
              @click="rerunThisRecord"
            >
              <strong>{{ extractRerunSubmitting ? '下发中…' : '重跑该记录' }}</strong>
              <em>只重读该记录 · 新执行类别=重新执行</em>
            </button>
            <p v-if="extractRerunning" class="direct-done">重跑执行中（{{ extractRerunExecutionId || '新执行' }}）· 完成后自动关闭，仍失败会生成新记录</p>
            <p v-else-if="productionCase?.status !== 'OPEN'" class="direct-done">已处理 · 状态 {{ record.status }}</p>
          </div>
        </section>
      </section>

      <!-- A 类（T_LINK / T_DIRECT）统一裁决框布局 -->
      <section v-else-if="templateId === 'T_LINK' || templateId === 'T_DIRECT'" class="zone zone-entity">
        <p v-if="record.type === '单任务执行失败'" class="zone-banner">对齐任务超时未生成候选，请基于源记录人工裁决后重跑。</p>

        <!-- 待入库记录卡（T_LINK：消歧扣留记录；T_DIRECT：低置信抽取候选） -->
        <div class="link-incoming">
          <span>待入库记录（已扣留，未写图）</span>
          <strong>{{ record.object }}</strong>
          <template v-if="templateId === 'T_LINK'">
            <p>来源：{{ linkIncoming?.sourceTable || '—' }} · 记录 <code>{{ linkIncoming?.vid || record.objectId }}</code></p>
            <p v-if="linkResolution">消歧得分 {{ linkResolution.matchScore ?? '—' }} · 候选分差 {{ linkResolution.margin ?? '—' }} · 灰区人工裁决</p>
          </template>
          <template v-else>
            <p>来源：{{ directSourceTable || productionCase?.workflowType || '—' }} · 记录 <code>{{ directSourceRecordId || record.objectId }}</code></p>
            <p v-if="directKind === 'relation' && directFromId">关系端点：<code>{{ directFromId }}</code> -[{{ labelZh(directEdgeType) || directEdgeType }}]-&gt; <code>{{ directToId }}</code></p>
            <p>抽取置信度 {{ directConfidence ?? '—' }} · 低于自动入库阈值 0.85，需人工复核</p>
          </template>
        </div>

        <!-- T_LINK：快照带真实候选（existingCandidates + _incoming）时渲染候选选择 -->
        <template v-if="linkCandidates.length">
          <p class="link-candidates-title">选择要并入的候选（merge 时生效）：</p>
          <ul class="link-candidates">
            <li
              v-for="cand in linkCandidates"
              :key="cand.vid"
              :class="{ selected: selectedTarget === cand.vid }"
            >
              <label>
                <input
                  v-model="selectedTarget"
                  type="radio"
                  name="link-target"
                  :value="cand.vid"
                  :disabled="!isEditable || entityVerdict !== 'merge'"
                />
                <strong>{{ cand.name }}</strong>
                <small><code>{{ cand.vid }}</code></small>
                <em v-if="cand.score !== null">得分 {{ cand.score }}</em>
              </label>
            </li>
          </ul>
        </template>

        <!-- T_LINK 空候选（脚本挂实体改道、召回无同名）：无 merge 目标，降级为新建/驳回 -->
        <p v-else-if="templateId === 'T_LINK' && linkSnapshot" class="zone-banner">
          图库无同名候选，无法并入——请「确认为新实体」落图，或驳回丢弃该挂起实体及其暂存边。
        </p>

        <!-- T_DIRECT：待入库候选字段（可修正，确认时按修正后写图） -->
        <div v-else-if="templateId === 'T_DIRECT'" class="direct-fields-block">
          <header class="direct-candidate-head">
            <p class="link-candidates-title">待入库候选字段（{{ directKind === 'relation' ? (labelZh(directEdgeType) || '关系') : (labelZh(directNodeLabel) || '实体') }}）：</p>
            <button v-if="isEditable && !directEditing" type="button" class="direct-edit-toggle" @click="toggleDirectEdit">编辑字段</button>
            <button v-else-if="directEditing && isEditable" type="button" class="direct-edit-toggle is-active" @click="toggleDirectEdit">取消编辑</button>
          </header>
          <table v-if="directCandidateFields.length" class="direct-fields" :class="{ 'is-editing': directEditing }">
            <tbody>
              <tr v-for="[key, val] in directCandidateFields" :key="String(key)" :class="{ 'is-edited': directEditing && directEdits[key] !== undefined && directEdits[key] !== directOriginalText(val) }">
                <th>{{ key }}</th>
                <td v-if="directEditing"><input aria-label="directEdits[key]" v-model="directEdits[key]" :placeholder="directOriginalText(val)" /></td>
                <td v-else>{{ directOriginalText(val) }}</td>
              </tr>
            </tbody>
          </table>
          <p v-else class="direct-empty">暂无候选字段</p>
          <p v-if="directEditing" class="direct-edit-hint">发现 schema 映射字段不对时可在此修正；点底部「确认」将按修正后候选写图（修改 {{ directEditedKeys.length }} 个字段，记入审计）。</p>
        </div>

        <!-- 无候选快照（存量写后 case / 演示数据）沿用原对照卡 -->
        <div v-else class="entity-compare">
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

        <!-- 裁决单选：T_LINK 三选（merge/create/reject）；T_DIRECT 通过或驳回 -->
        <a-form-item v-if="templateId === 'T_LINK'" field="entityVerdict" hide-label>
        <a-radio-group v-model="entityVerdict" class="verdict" aria-label="实体对齐裁决">
          <a-radio value="merge" :disabled="!isEditable || linkMergeDisabled">合并到所选候选（写入图）</a-radio>
          <a-radio value="create" :disabled="!isEditable">确认为新实体（写入图）</a-radio>
          <a-radio value="reject" :disabled="!isEditable">均不匹配，驳回候选（丢弃该记录）</a-radio>
        </a-radio-group>
        </a-form-item>
        <a-form-item v-else field="directVerdict" hide-label>
        <a-radio-group v-model="directVerdict" class="verdict" aria-label="入库决策">
          <a-radio value="accept" :disabled="!isEditable">通过·入库（{{ directKind === 'relation' ? `创建${labelZh(directEdgeType) || '?'}边` : `创建${labelZh(directNodeLabel) || '?'}节点` }}，直接写图）</a-radio>
          <a-radio value="reject" :disabled="!isEditable">驳回·丢弃（候选不写图）</a-radio>
        </a-radio-group>
        </a-form-item>
        <label v-if="isEditable" class="verdict-note">
          <span>备注（可选）</span>
          <input aria-label="审核备注" v-model="note" placeholder="审核备注…" />
        </label>

        <!-- T_DIRECT 溯源 / 原始记录 / 抽取推理过程（折叠保留，不改变裁决框主布局） -->
        <template v-if="templateId === 'T_DIRECT'">
          <details class="direct-trace zone-extra">
            <summary>溯源信息（点击 ID 跳转任务详情）</summary>
            <dl>
              <div><dt>workflow</dt><dd><RouterLink :to="`/processing-instance/${productionCase?.workflowId || ''}`" class="direct-trace-link"><code>{{ productionCase?.workflowId || '—' }}</code></RouterLink></dd></div>
              <div><dt>workflow 类型</dt><dd>{{ productionCase?.workflowType || '—' }}</dd></div>
              <div><dt>执行 ID</dt><dd><RouterLink :to="`/processing-instance/${directExecutionId || ''}`" class="direct-trace-link"><code>{{ directExecutionId || '—' }}</code></RouterLink></dd></div>
              <div><dt>来源任务</dt><dd><RouterLink :to="`/processing-instance/${productionCase?.sourceTaskId || ''}`" class="direct-trace-link"><code>{{ productionCase?.sourceTaskId || '—' }}</code></RouterLink></dd></div>
              <div><dt>产生 step</dt><dd>{{ productionCase?.pipelineStepId || '—' }}</dd></div>
            </dl>
          </details>
          <details class="direct-section-details zone-extra">
            <summary>
              原始记录
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
          <details v-if="directLlmInput" class="direct-llm-io zone-extra">
            <summary>LLM 输入（system prompt + user message）</summary>
            <div class="direct-llm-section">
              <h4>system prompt</h4>
              <pre>{{ directLlmInput.system }}</pre>
              <h4>user message</h4>
              <pre>{{ directLlmInput.user }}</pre>
            </div>
          </details>
          <details v-if="directLlmOutput" class="direct-llm-io zone-extra">
            <summary>LLM 输出（JSON）</summary>
            <pre>{{ directLlmOutput }}</pre>
          </details>
        </template>
      </section>

      <div v-if="!isEditable" class="rw-readonly">
        <strong>{{ record.decision }}</strong>
        <p>{{ record.decisionNote }}</p>
        <em>{{ record.completedAt }}</em>
      </div>

      </a-form>
      <p v-if="feedback" class="rw-feedback">{{ feedback }}</p>
    </main>

    <!-- 底部确认按钮全模板保留；已处理（终态）置灰不可点击；A 类（T_LINK/T_DIRECT）统一为「确认」 -->
    <footer class="rw-foot">
      <div class="rw-foot__actions">
        <button class="primary" type="button" :disabled="isPrimaryDisabled" @click="runPrimary">{{ templateId === 'T_EXTRACT_FAIL' ? primaryActionLabel : '确认' }}</button>
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

.note-inline input {
  height: 34px;
  padding: 0 9px;
  border: 1px solid #bdd0ea;
  border-radius: 5px;
  background: #fff;
  color: #263650;
  font: 12px inherit;
}

.entity-compare {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 12px;
  align-items: stretch;
  margin-bottom: 14px;
}

.entity-compare article {
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

.entity-compare span {
  color: #7890b5;
  font-size: 10px;
}

.entity-compare strong {
  display: block;
  margin: 6px 0;
  font-size: 14px;
}

.entity-compare p {
  margin: 4px 0 0;
  color: #475467;
  font-size: 11px;
  font-style: normal;
}

.verdict {
  display: grid;
  gap: 8px;
}

.verdict label {
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

.verdict label.active {
  border-color: #165dff;
  background: #f5f8ff;
}

/* T_LINK 裁决框内备注（可选） */
.verdict-note {
  display: grid;
  gap: 6px;
  margin-top: 12px;
  color: #718099;
  font-size: 11px;
}

.verdict-note input {
  padding: 8px 10px;
  border: 1px solid #dce8f8;
  border-radius: 5px;
  font: 13px/1.5 inherit;
  color: #17233b;
}

/* T_LINK 消歧 v2：待入库记录卡 + 候选选择列表 */
.link-incoming {
  margin-bottom: 12px;
  padding: 12px 14px;
  border: 1px dashed #b8d0ee;
  border-radius: 8px;
  background: #f7fbff;
}

.link-incoming span {
  color: #7890b5;
  font-size: 10px;
}

.link-incoming strong {
  display: block;
  margin: 6px 0;
  font-size: 14px;
}

.link-incoming p {
  margin: 3px 0 0;
  color: #475467;
  font-size: 11px;
  font-style: normal;
}

.link-candidates-title {
  margin: 0 0 8px;
  color: #475467;
  font-size: 12px;
}

.link-candidates {
  display: grid;
  gap: 8px;
  margin: 0 0 14px;
  padding: 0;
  list-style: none;
}

.link-candidates li {
  border: 1px solid #d4dfed;
  border-radius: 6px;
  background: #fff;
}

.link-candidates li.selected {
  border-color: #165dff;
  background: #f5f8ff;
}

.link-candidates label {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  font-size: 12px;
  cursor: pointer;
}

.link-candidates small {
  color: #7890b5;
}

.link-candidates em {
  margin-left: auto;
  padding: 2px 8px;
  border-radius: 10px;
  background: #eaf2ff;
  color: #175cd3;
  font-size: 11px;
  font-style: normal;
}

/* A 类统一裁决框：T_DIRECT 候选字段表 + 折叠辅助区间距 */
.zone-entity .direct-fields-block {
  margin-bottom: 14px;
}

.zone-entity .direct-fields-block .link-candidates-title {
  margin: 0;
}

.zone-entity .zone-extra {
  display: block;
  margin-top: 12px;
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

.rw-empty a {
  color: #165dff;
}

@media (max-width: 960px) {
  .rw-diag {
    grid-template-columns: 1fr 1fr;
  }

  .entity-compare {
    grid-template-columns: 1fr;
  }

  .entity-compare > b {
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
/* 终态/提交中置灰（与底部 footer 禁用色一致） */
.direct-accept:disabled,.direct-reject:disabled{border-color:#d0d5dd;background:#eaecf0;color:#98a2b3;cursor:not-allowed}
.direct-accept:disabled em,.direct-reject:disabled em{color:#98a2b3}
.direct-actions .direct-done{grid-column:1/-1}
.direct-accept:hover:not(:disabled),.direct-reject:hover:not(:disabled){opacity:.92}
.direct-done{margin:0;padding:14px;text-align:center;color:#475569;font-size:13px;background:#fff;border-radius:6px;border:1px solid #e4ecf6}
.extract-error-text{margin:0;padding:10px 12px;border:1px solid #f6c6b4;border-radius:6px;background:#fff8f5;color:#b42318;font-size:12px;line-height:19px;white-space:pre-wrap;word-break:break-all}
</style>
<style scoped>
/* DESIGN_RULES: manual review detail contract. */
.rw{overflow:visible;height:auto;min-height:100%;color:#1d2129}.rw-head{align-items:center;gap:16px;margin-bottom:16px}.rw-head h1{margin:4px 0;font-size:20px;line-height:28px;font-weight:600}.rw-head p,.rw-head a{font-size:12px;line-height:20px}
.scope,.status{display:inline-flex;align-items:center;gap:6px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}.scope::before,.status::before{display:block;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}.scope.is-batch,.scope.is-task,.status.is-待处理,.status.is-已完成,.status.is-已撤销,.status.is-已驳回{background:transparent}
.rw-diag{gap:8px 16px;margin-bottom:16px;padding:16px;border-color:#e5e6eb;border-radius:6px;background:#f7f8fa}.rw-diag strong{font-size:14px;line-height:22px}.rw-diag span,.rw-diag em{font-size:12px;line-height:20px}
.rw-body{flex:none;overflow:visible;padding:16px;border-color:#e5e6eb;border-radius:6px}
.rw-zone-head{gap:8px;margin-bottom:16px}.rw-zone-head h2,.rw-sec__head h2{font-size:16px;line-height:24px;font-weight:600}.rw-zone-head p,.rw-sec__head p{font-size:12px;line-height:20px}
.rw-sec{margin-bottom:16px;padding:16px;border:0;border-radius:6px;background:#f7f8fa}.rw-sec__head{gap:8px;margin-bottom:16px}
.cat-pill{padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}.tri-grid{gap:16px}.tri-grid>div{gap:4px;padding:8px 16px;border-color:#e5e6eb;border-radius:4px}.tri-grid span,.tri-grid em{font-size:12px;line-height:20px}.tri-grid strong{font-size:14px;line-height:22px}
.rw :is(button,input,select,textarea){font-size:14px;line-height:22px}.rw :is(button,input,select){min-height:32px;border-radius:4px}.rw textarea{border-radius:4px}
.direct-actions{gap:16px}.direct-accept,.direct-reject{min-height:32px;padding:8px 16px;border-radius:4px;font-size:14px}.direct-accept strong,.direct-reject strong{font-size:14px;line-height:22px}.direct-accept em,.direct-reject em{font-size:12px;line-height:20px}
@media(max-width:960px){.tri-grid{grid-template-columns:1fr}}
</style>
