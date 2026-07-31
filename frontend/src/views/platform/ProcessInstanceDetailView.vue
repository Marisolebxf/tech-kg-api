<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getProcessingInstance, getUpdateBatch, updateBatches } from './update-batch-data'

type StepStatus = '成功' | '运行中' | '需人工处理' | '待执行'
type RiskLevel = '低风险' | '中风险' | '高风险'
type DetailTab = 'overview' | 'io' | 'logs' | 'lineage'
type Step = {
  id: string
  phase: '数据处理' | '图谱构建'
  name: string
  status: StepStatus
  risk: RiskLevel
  count: string
  abnormal: string
  duration: string
  description: string
  engine: string
}

const route = useRoute()
const router = useRouter()
const taskId = computed(() => String(route.params.taskId || route.params.instanceId || 'UPD-20260714'))
const processingInstance = computed(() => getProcessingInstance(taskId.value))
const batch = computed(() => getUpdateBatch(processingInstance.value?.batchId ?? taskId.value) ?? updateBatches[0])
const isConstructionTask = computed(() => processingInstance.value?.stage === '图谱构建' || String(route.params.area) === 'construction')
const needsTaskReview = computed(() => processingInstance.value
  ? processingInstance.value.status === '待人工处理'
  : batch.value.status === '待审核')
const activeTab = ref<DetailTab>('overview')

const baseSteps: Omit<Step, 'status' | 'count' | 'abnormal' | 'duration'>[] = [
  { id: 'source', phase: '数据处理', name: '数据接入', risk: '低风险', description: '读取科技要素库增量数据并校验连接。', engine: 'Data Connector 3.1' },
  { id: 'incremental', phase: '数据处理', name: '增量识别', risk: '低风险', description: '按更新时间水位识别新增、修改和删除记录。', engine: 'CDC Engine 2.8' },
  { id: 'normalize', phase: '数据处理', name: '清洗标准化', risk: '低风险', description: '完成字段清洗、字典映射与格式统一。', engine: 'Data Pipeline 3.1' },
  { id: 'quality', phase: '数据处理', name: '数据质量校验', risk: '高风险', description: '检查完整性、唯一性和枚举一致性，异常数据自动隔离。', engine: 'Quality Rules 2.6' },
  { id: 'write', phase: '数据处理', name: '标准数据写入', risk: '低风险', description: '将通过检验的结果写入标准表，异常记录保留在隔离区。', engine: 'Data Writer 3.1' },
  { id: 'schema', phase: '图谱构建', name: 'Schema 映射', risk: '低风险', description: '将标准数据映射到当前图谱 Schema。', engine: 'Schema Mapper 1.8' },
  { id: 'llm', phase: '图谱构建', name: '大模型抽取', risk: '高风险', description: '抽取实体、关系与属性候选，按置信度分流。', engine: 'Qwen3-32B-Instruct' },
  { id: 'align', phase: '图谱构建', name: '实体对齐消歧', risk: '高风险', description: '判断候选实体与存量实体是否指向同一对象。', engine: 'Entity Resolver 2.4' },
  { id: 'validate', phase: '图谱构建', name: '规则与证据校验', risk: '中风险', description: '通过 Schema 约束、来源证据和存量图谱校验候选结果。', engine: 'Evidence Validator 2.1' },
  { id: 'persist', phase: '图谱构建', name: '图谱入库', risk: '中风险', description: '将通过校验的实体、关系和属性写入图数据库。', engine: 'Graph Writer 2.4' },
  { id: 'publish', phase: '图谱构建', name: '版本发布', risk: '低风险', description: '生成新图谱版本并切换查询与能力服务。', engine: 'Version Publisher 1.6' },
]

const steps = computed<Step[]>(() => {
  const resolved = baseSteps.map<Step>((step, index) => {
  if (!needsTaskReview.value) {
    return { ...step, status: '成功', count: index < 4 ? `${batch.value.input.toLocaleString()} 条` : step.id === 'llm' ? `${batch.value.entities.toLocaleString()} 实体 / ${batch.value.relations.toLocaleString()} 关系` : '已完成', abnormal: '0', duration: step.risk === '高风险' ? '8分24秒' : '1分08秒' }
  }
  const attention: Record<string, Pick<Step, 'status' | 'count' | 'abnormal' | 'duration'>> = {
    source: { status: '成功', count: '25,140 条', abnormal: '0', duration: '2分18秒' },
    incremental: { status: '成功', count: '25,140 条', abnormal: '0', duration: '48秒' },
    normalize: { status: processingInstance.value?.reviewType === '公共字典配置异常' ? '需人工处理' : '成功', count: processingInstance.value?.reviewType === '公共字典配置异常' ? '1 个异常批次' : '24,755 条', abnormal: processingInstance.value?.reviewType === '公共字典配置异常' ? '批量' : '0', duration: processingInstance.value?.reviewType === '公共字典配置异常' ? '未完成' : '4分06秒' },
    quality: processingInstance.value?.reviewType === '公共字典配置异常'
      ? { status: '待执行', count: '前置节点阻断', abnormal: '-', duration: '-' }
      : { status: '成功', count: processingInstance.value ? '1 条已检验' : '24,755 通过', abnormal: processingInstance.value?.stage === '数据处理' ? '1' : '385', duration: '1分42秒' },
    write: { status: processingInstance.value?.stage === '数据处理' ? '待执行' : '成功', count: processingInstance.value?.reviewType === '公共字典配置异常' ? '前置节点阻断' : '-', abnormal: '-', duration: '-' },
    schema: { status: processingInstance.value?.reviewType === 'Schema 批量映射失败' ? '需人工处理' : '成功', count: processingInstance.value?.reviewType === 'Schema 批量映射失败' ? '1,284 条受影响' : '7 类实体', abnormal: processingInstance.value?.reviewType === 'Schema 批量映射失败' ? '批量' : '0', duration: processingInstance.value?.reviewType === 'Schema 批量映射失败' ? '未完成' : '36秒' },
    llm: processingInstance.value?.reviewType === 'Schema 批量映射失败'
      ? { status: '待执行', count: '前置节点阻断', abnormal: '-', duration: '-' }
      : { status: processingInstance.value?.reviewType === '模型批量输出异常' ? '需人工处理' : '成功', count: processingInstance.value?.reviewType === '模型批量输出异常' ? '未产生有效结果' : processingInstance.value ? '1 个候选结果' : '3,261 实体 / 8,942 关系', abnormal: processingInstance.value?.reviewType === '模型批量输出异常' ? '批量' : '0', duration: processingInstance.value?.reviewType === '模型批量输出异常' ? '未完成' : '8分24秒' },
    align: ['单任务执行失败', '实体冲突'].includes(processingInstance.value?.reviewType ?? '')
      ? { status: '需人工处理', count: processingInstance.value?.reviewType === '单任务执行失败' ? '未产生结果' : '1 个候选冲突', abnormal: '1', duration: processingInstance.value?.reviewType === '单任务执行失败' ? '超时' : '6秒' }
      : ['关系证据不足', '属性冲突', '低置信度'].includes(processingInstance.value?.reviewType ?? '')
        ? { status: '成功', count: '1 个候选已对齐', abnormal: '0', duration: '6秒' }
        : { status: '待执行', count: '-', abnormal: '-', duration: '-' },
    validate: { status: ['关系证据不足', '属性冲突', '低置信度'].includes(processingInstance.value?.reviewType ?? '') ? '需人工处理' : '待执行', count: ['关系证据不足', '属性冲突', '低置信度'].includes(processingInstance.value?.reviewType ?? '') ? '1 个候选结果' : '-', abnormal: ['关系证据不足', '属性冲突', '低置信度'].includes(processingInstance.value?.reviewType ?? '') ? '1' : '-', duration: ['关系证据不足', '属性冲突', '低置信度'].includes(processingInstance.value?.reviewType ?? '') ? '12秒' : '-' },
    persist: { status: '待执行', count: '-', abnormal: '-', duration: '-' },
    publish: { status: '待执行', count: '-', abnormal: '-', duration: '-' },
  }
  return { ...step, ...attention[step.id] }
  })
  return resolved.map((step, index) => {
    const blockerIndex = resolved.findIndex((item) => item.phase === step.phase && item.status === '需人工处理')
    if (blockerIndex >= 0 && index > blockerIndex && resolved[blockerIndex].phase === step.phase) {
      return { ...step, status: '待执行', count: '前置节点阻断', abnormal: '-', duration: '-' }
    }
    return step
  })
})

function initialStepId() {
  if (processingInstance.value?.reviewType === 'Schema 批量映射失败') return 'schema'
  if (processingInstance.value?.reviewType === '公共字典配置异常') return 'normalize'
  if (processingInstance.value?.reviewType === '模型批量输出异常') return 'llm'
  if (processingInstance.value?.reviewType === '单任务执行失败') return 'align'
  if (processingInstance.value?.stage === '数据处理') return 'quality'
  if (processingInstance.value?.reviewType === '实体冲突') return 'align'
  if (['关系证据不足', '属性冲突', '低置信度'].includes(processingInstance.value?.reviewType ?? '')) return 'validate'
  if (processingInstance.value) return 'llm'
  return steps.value.find((step) => step.status === '需人工处理')?.id ?? 'source'
}

const selectedStepId = ref(String(route.query.step || initialStepId()))
const selectedStep = computed(() => steps.value.find((step) => step.id === selectedStepId.value) ?? steps.value[0])
const visiblePhase = computed(() => isConstructionTask.value ? '图谱构建' as const : '数据处理' as const)
const visibleSteps = computed(() => steps.value.filter((step) => step.phase === visiblePhase.value))
const needsReview = computed(() => needsTaskReview.value && selectedStep.value.abnormal !== '0' && selectedStep.value.abnormal !== '-')
const isAiStep = computed(() => selectedStep.value.id === 'llm')
const isQualityStep = computed(() => selectedStep.value.id === 'quality')
const attentionLabel = computed(() => selectedStep.value.risk === '高风险' ? '重点关注' : selectedStep.value.risk === '中风险' ? '一般关注' : '常规节点')
const isProcessLevelIncident = computed(() => ['模型批量输出异常', 'Schema 批量映射失败', '公共字典配置异常'].includes(processingInstance.value?.reviewType ?? ''))
const isTaskExecutionFailure = computed(() => processingInstance.value?.reviewType === '单任务执行失败')
const isExecutionInterrupted = computed(() => isProcessLevelIncident.value || isTaskExecutionFailure.value)
const taskStatus = computed(() => isExecutionInterrupted.value ? '执行中断' : '执行成功')
const resultStatus = computed(() => isProcessLevelIncident.value ? '流程已阻断' : isTaskExecutionFailure.value ? '未产生结果' : processingInstance.value?.status === '人工处理完成' ? '人工确认通过' : needsTaskReview.value ? '结果待确认' : '结果已通过')
const resultConfidence = computed(() => isExecutionInterrupted.value || visiblePhase.value === '数据处理' || !processingInstance.value?.confidence ? '—' : processingInstance.value.confidence)
const incidentScope = computed(() => isProcessLevelIncident.value ? '流程级·高风险（P0）' : needsTaskReview.value ? '任务级·中风险（P1）' : '无异常')
const blockingStrategy = computed(() => isProcessLevelIncident.value ? '阻断当前节点及下游，调整后恢复' : needsTaskReview.value ? '只隔离当前任务，其他任务继续执行' : '无需阻断')

const modelMetrics = computed(() => [
  ['模型', 'Qwen3-32B-Instruct'], ['Prompt 模板', 'kg-extract-v2.6.1'], ['Schema', 'tech-kg-schema-v1.8'],
  ['自动通过阈值', '≥ 0.90'], ['人工审核区间', '0.70 ～ 0.90'], ['调用成功率', '97.42%'],
  ['当前任务置信度', isExecutionInterrupted.value ? '—（未产生结果）' : processingInstance.value?.confidence || '0.82'],
  ['分流结果', isExecutionInterrupted.value ? '未分流' : Number(processingInstance.value?.confidence ?? 0.82) >= 0.9 ? '自动通过' : '转人工审核'],
  ['规则校验', processingInstance.value?.result ?? '候选结果已生成'],
])

const llmPrompt = `系统角色：你是科技知识图谱的实体与关系抽取引擎。
任务：仅依据输入文本和 tech-kg-schema-v1.8 输出候选实体、关系、属性及证据片段。
约束：
1. 不得生成 Schema 未定义的类型和关系；
2. 结果必须引用原文证据，禁止补全未出现的事实；
3. 同名实体不直接合并，输出待消歧标识；
4. 按 JSON Schema 输出 confidence 和 evidence。`

const qualityPrompt = `仅判断记录的语义是否存在明显矛盾、主体与属性是否错配。
不允许根据常识补全缺失值；不允许直接删除记录。
输出：issue_type、evidence、confidence。置信度低于 0.85 只生成告警，最终判定仍由确定性规则或人工完成。`

const qualityChecks = computed(() => {
  const checks = [
    { name: '必填完整性', method: '规则引擎', strategy: '标题、主键、来源标识不得为空', result: processingInstance.value?.reviewType === '必填缺失' ? '本任务命中' : '通过' },
    { name: '唯一性校验', method: '规则 + 向量相似度', strategy: 'DOI 精确匹配；标题+作者相似度 ≥ 0.92 转人工', result: processingInstance.value?.reviewType === '唯一性冲突' ? '本任务命中' : '通过' },
    { name: '枚举一致性', method: '字典规则', strategy: '未命中标准字典的值进入隔离区', result: processingInstance.value?.reviewType === '枚举异常' ? '本任务命中' : '通过' },
    { name: '语义合理性', method: '大模型辅助', strategy: 'Qwen3-32B + quality-semantic-v1.3，置信度 < 0.85 仅告警不自动删除', result: Number(processingInstance.value?.confidence ?? 1) < 0.85 ? '生成辅助告警' : '通过' },
  ]
  return selectedStep.value.status === '待执行' ? checks.map((item) => ({ ...item, result: '未执行' })) : checks
})

const genericMetrics = computed(() => [
  ['运行状态', selectedStep.value.status], ['处理数量', selectedStep.value.count], ['异常数量', selectedStep.value.abnormal],
  ['执行耗时', selectedStep.value.duration], ['执行引擎', selectedStep.value.engine], ['技术关注度', attentionLabel.value],
  ['异常影响', incidentScope.value], ['阻断策略', blockingStrategy.value],
])

const lineageEvidenceRows = computed(() => {
  const type = processingInstance.value?.reviewType ?? ''
  const sourceId = processingInstance.value?.sourceRecordId ?? '-'
  if (type === '唯一性冲突') return [
    { table: 'dwd_zh_paper_detail', record: `${sourceId}-01`, field: 'title / doi', raw: '知识图谱增量构建方法 / 10.2026.kg.089', basis: '标题与 DOI' },
    { table: 'dwd_paper_author', record: `${sourceId}-02`, field: 'author_name / affiliation', raw: '张明远 / 中国科学院自动化研究所', basis: '作者及单位' },
    { table: 'dwd_paper_source', record: `${sourceId}-03`, field: 'source_url / updated_at', raw: 'https://source.example/paper/89 / 2026-07-13 01:42', basis: '来源时间' },
  ]
  if (type === '必填缺失') return [
    { table: 'dwd_zh_paper_detail', record: sourceId, field: 'title', raw: 'null', basis: '异常字段' },
    { table: 'dwd_zh_paper_detail', record: sourceId, field: 'doi', raw: '10.2026/kg.104', basis: '外部核对键' },
    { table: 'dwd_paper_abstract', record: sourceId, field: 'abstract_zh', raw: '本文研究知识图谱增量构建与质量校验…', basis: '标题补全辅助' },
  ]
  if (type === '枚举异常' || type === '公共字典配置异常') return [
    { table: 'dwd_patent', record: sourceId, field: 'legal_status / source_type', raw: 'substantive-review / conference-online', basis: '原始枚举值' },
    { table: 'dim_quality_dictionary', record: 'quality-dict-v2.6', field: 'standard_value', raw: '实质审查 / conference', basis: '标准字典' },
  ]
  if (type === '实体冲突' || type === '单任务执行失败') return [
    { table: 'dwd_scholar', record: sourceId, field: 'name_zh / organization_name', raw: `${processingInstance.value?.objectName ?? '张明远'} / 中国科学院自动化研究所`, basis: '候选实体主记录' },
    { table: 'dwd_paper_author', record: 'AUTHOR-10291', field: 'author_id / affiliation', raw: '10291 / 中国科学院自动化研究所', basis: '论文作者证据' },
    { table: 'dwd_expert_employment', record: 'EMP-18426', field: 'organization / start_date', raw: '华南智能芯片 / 2022-03', basis: '任职冲突证据' },
  ]
  if (type === '关系证据不足' || type === '低置信度') return [
    { table: 'dwd_org_cooperation', record: sourceId, field: 'source_org / target_org / relation_type', raw: `${processingInstance.value?.objectName ?? '候选两端'} / COOPERATE_WITH`, basis: '关系两端与类型' },
    { table: 'dwd_org_important_news_info', record: 'NEWS-89321', field: 'title / source_url', raw: '联合研发合作公告 / https://source.example/news/89321', basis: '已命中来源' },
    { table: 'kg_relation_evidence', record: processingInstance.value?.objectId ?? '-', field: 'independent_source_count', raw: '1', basis: '入图要求 ≥ 2' },
  ]
  if (type === '属性冲突') return [
    { table: 'dwd_expert_employment', record: sourceId, field: 'organization / start_date / end_date', raw: '自动化研究所 / 2023-01 / null', basis: '来源记录 A' },
    { table: 'dwd_expert_employment', record: `${sourceId}-B`, field: 'organization / start_date / end_date', raw: '华南智能芯片 / 2022-06 / null', basis: '来源记录 B' },
  ]
  if (type === 'Schema 批量映射失败') return [
    { table: 'dwd_org_reg_info', record: sourceId, field: 'org_name / credit_code / org_type', raw: '华南智能芯片 / 9144XXXX / technology_company', basis: '批量映射输入' },
    { table: 'dim_schema_field_mapping', record: 'tech-kg-schema-v1.8', field: 'org_type → org_category', raw: 'mapping_not_found', basis: '失败映射项' },
  ]
  return [
    { table: visiblePhase.value === '数据处理' ? 'dwd_source_record' : 'kg_stage_standard_record', record: sourceId, field: 'raw_payload', raw: processingInstance.value?.objectName ?? '当前批次原始数据', basis: '当前任务输入' },
    { table: 'dim_schema_definition', record: 'tech-kg-schema-v1.8', field: 'object_type / constraints', raw: `${processingInstance.value?.kind ?? '记录'} / ${processingInstance.value?.rule ?? selectedStep.value.engine}`, basis: '结果校验依据' },
  ]
})

const selectStep = (id: string) => {
  selectedStepId.value = id
  activeTab.value = 'overview'
  void router.replace({ query: { ...route.query, step: id } })
}

watch(() => route.query.step, (step) => {
  if (step && steps.value.some((item) => item.id === String(step))) selectedStepId.value = String(step)
})
watch(taskId, () => {
  selectedStepId.value = String(route.query.step || initialStepId())
})
</script>

<template>
  <div class="task-detail-page">
    <header class="detail-head">
      <div><RouterLink :to="`/tasks?module=${encodeURIComponent(visiblePhase)}&batch=${batch.id}`">← 返回{{ visiblePhase }}任务</RouterLink><h1>{{ processingInstance?.objectName || `${visiblePhase}任务详情` }}</h1><p>{{ processingInstance?.action || batch.trigger }} · {{ processingInstance?.sourceTable || batch.source }}</p></div>
    </header>

    <section class="summary-grid">
      <article><span>执行状态</span><strong :class="isExecutionInterrupted ? 'danger' : 'success-text'">{{ taskStatus }}</strong><em>{{ isExecutionInterrupted ? '任务未完成' : '程序无异常退出' }}</em></article>
      <article><span>结果验收</span><strong :class="{ warning: needsTaskReview }">{{ resultStatus }}</strong><em>{{ processingInstance?.reviewType || '自动质量校验' }}</em></article>
      <article><span>模型结果置信度</span><strong :class="{ warning: resultConfidence !== '—' && Number(processingInstance?.confidence || 1) < 0.9 }">{{ resultConfidence }}</strong><em>{{ isExecutionInterrupted ? '未产生结果' : resultConfidence === '—' ? '确定性规则，不适用' : '自动通过阈值 0.90' }}</em></article>
      <article><span>任务 ID</span><strong class="version">{{ taskId }}</strong><em>{{ batch.id }}</em></article>
    </section>

    <section class="detail-workspace">
      <aside class="process-sidebar">
        <header><div><h2>{{ visiblePhase }}流程</h2></div><span>{{ visibleSteps.filter(step => step.status === '成功').length }}/{{ visibleSteps.length }}</span></header>
        <section class="phase-group">
          <div class="phase-title"><strong>{{ visiblePhase }}</strong></div>
          <button v-for="step in visibleSteps" :key="step.id" type="button" :class="['process-step', `is-${step.status}`, `is-${step.risk}`, { active: selectedStep.id === step.id, 'has-review': step.abnormal !== '0' && step.abnormal !== '-' }]" @click="selectStep(step.id)">
            <i>{{ step.status === '成功' ? '✓' : step.status === '需人工处理' ? '!' : '·' }}</i>
            <span><strong>{{ step.name }}<b v-if="step.id === 'llm'">AI</b><b v-if="step.risk === '高风险'" class="risk">重点</b></strong><em>{{ step.count }}<template v-if="step.abnormal !== '0' && step.abnormal !== '-'"> · {{ step.abnormal }} 异常</template></em></span>
            <small>{{ step.status }}</small>
          </button>
        </section>
      </aside>

      <main class="step-detail">
        <header class="step-head"><div><span>{{ selectedStep.phase }} · {{ attentionLabel }}</span><h2>{{ selectedStep.name }} <b v-if="isAiStep">AI 重点关注节点</b><b v-else-if="isQualityStep">含 AI 辅助检验</b></h2><p>{{ selectedStep.description }}</p></div><RouterLink v-if="needsReview" :to="`/manual-review/task/${taskId}`">进入人工处理 →</RouterLink></header>
        <nav class="detail-tabs"><button v-for="tab in ([['overview','概况与结果'],['io','输入输出'],['logs','异常与日志'],['lineage','数据溯源']] as const)" :key="tab[0]" type="button" :class="{ active: activeTab === tab[0] }" @click="activeTab = tab[0]">{{ tab[1] }}</button></nav>

        <div v-if="activeTab === 'overview'" class="overview-content">
          <section class="metric-card"><h3>节点结果</h3><dl><div v-for="row in genericMetrics" :key="row[0]"><dt>{{ row[0] }}</dt><dd>{{ row[1] }}</dd></div></dl></section>
          <section v-if="isAiStep" class="ai-card"><header><div><b>AI</b><span><strong>大模型运行透明度</strong><em>展示版本、阈值、分流与质量，不展示模型内部思维过程</em></span></div><i>需关注</i></header><dl><div v-for="row in modelMetrics" :key="row[0]"><dt>{{ row[0] }}</dt><dd>{{ row[1] }}</dd></div></dl></section>
          <section v-if="isAiStep" class="prompt-card"><h3>实际提示词模板 <span>kg-extract-v2.6.1</span></h3><pre>{{ llmPrompt }}</pre></section>
          <section v-if="isQualityStep" class="quality-strategy"><h3>质量检验项与判定策略</h3><table><thead><tr><th>检验项</th><th>方法</th><th>具体判定策略</th><th>结果</th></tr></thead><tbody><tr v-for="item in qualityChecks" :key="item.name"><td>{{ item.name }}</td><td><span :class="{ ai: item.method.includes('大模型') }">{{ item.method }}</span></td><td>{{ item.strategy }}</td><td>{{ item.result }}</td></tr></tbody></table><div class="quality-ai-note"><b>AI</b><span><strong>语义合理性检验使用大模型辅助</strong><em>模型 Qwen3-32B-Instruct · Prompt quality-semantic-v1.3 · AI 只告警，不直接删改数据</em></span></div><pre>{{ qualityPrompt }}</pre></section>
          <section v-if="needsReview" class="result-card alert"><h3>执行结果与业务验收</h3><template v-if="isExecutionInterrupted"><p><strong>执行结果：</strong>任务未运行完成，尚未产生可验收结果。</p><p><strong>置信度：</strong>无，因为没有模型结果。</p></template><template v-else><p><strong>执行结果：</strong>程序已正常运行完成并生成输出。</p><p><strong>验收结果：</strong>{{ processingInstance?.result }}，当前不能视为正确结果。</p></template><p><strong>后续处理：</strong>{{ blockingStrategy }}。</p></section>
          <section v-else class="result-card success"><h3>执行结果与业务验收</h3><p><strong>执行成功：</strong>程序正常结束。 <strong>结果已通过：</strong>{{ processingInstance?.result || '输出通过当前质量规则' }}。两项状态分别记录，不相互替代。</p></section>
        </div>

        <div v-else-if="activeTab === 'io'" class="io-content">
          <section><h3>输入数据</h3><template v-if="isAiStep"><div class="sample-text"><span>实际任务输入 · {{ processingInstance?.sourceTable }} / {{ processingInstance?.sourceRecordId }}</span><p>“{{ processingInstance?.objectName }}，来源记录包含主体、机构、成果与关系证据，要求按当前 Schema 抽取候选结果……”</p></div></template><template v-else><pre>{
  "task_id": "{{ taskId }}",
  "source_table": "{{ processingInstance?.sourceTable || batch.source }}",
  "source_record_id": "{{ processingInstance?.sourceRecordId || '-' }}",
  "object_id": "{{ processingInstance?.objectId || '-' }}",
  "action": "{{ processingInstance?.action || selectedStep.name }}"
}</pre></template></section>
          <section><h3>输出结果</h3><template v-if="isExecutionInterrupted"><div class="candidate-result"><span>未产生输出</span><strong>{{ resultStatus }}</strong><p>{{ processingInstance?.result }} · 置信度 —</p></div></template><template v-else-if="isAiStep"><div class="candidate-result"><span>{{ processingInstance?.kind || '实体' }}候选结果 · {{ processingInstance?.rule }}</span><strong>{{ processingInstance?.objectName }}</strong><p>置信度 <b>{{ processingInstance?.confidence }}</b> · {{ resultStatus }} · {{ processingInstance?.result }}</p></div></template><template v-else><pre>{
  "task_id": "{{ taskId }}",
  "execution_status": "{{ taskStatus }}",
  "result_status": "{{ resultStatus }}",
  "confidence": "{{ resultConfidence }}",
  "rule": "{{ processingInstance?.rule || selectedStep.engine }}",
  "result": "{{ processingInstance?.result || '已生成节点输出' }}"
}</pre></template></section>
        </div>

        <div v-else-if="activeTab === 'logs'" class="log-content"><section class="issue-list"><h3>{{ isExecutionInterrupted ? '执行异常' : '结果验收' }}</h3><article><span>{{ processingInstance?.reviewType || '自动质量判定' }}</span><strong :class="{ safe: !needsTaskReview }">{{ isExecutionInterrupted ? '已中断' : needsTaskReview ? '待确认' : '已通过' }}</strong><em>执行状态：{{ taskStatus }} · 结果状态：{{ resultStatus }}</em></article></section><pre>{{ processingInstance?.processedAt || '02:00:00' }} INFO  具体任务 {{ taskId }} 启动
{{ processingInstance?.processedAt || '02:00:02' }} INFO  加载处理规则 {{ processingInstance?.rule || selectedStep.engine }}
{{ isExecutionInterrupted ? `${processingInstance?.processedAt || '02:00:04'} ERROR 节点执行中断：${processingInstance?.result}\n${processingInstance?.processedAt || '02:00:05'} WARN  未产生结果，置信度不可用\n${processingInstance?.processedAt || '02:00:06'} INFO  ${blockingStrategy}` : `${processingInstance?.processedAt || '02:00:04'} INFO  节点程序执行成功，已生成输出快照\n${needsTaskReview ? `${processingInstance?.processedAt || '02:00:05'} WARN  输出未通过业务验收：${processingInstance?.result}\n${processingInstance?.processedAt || '02:00:06'} INFO  结果已隔离，等待人工确认` : `${processingInstance?.processedAt || '02:00:05'} INFO  输出通过质量验收，可供下游使用`}` }}</pre></div>

        <div v-else class="trace-content">
          <section class="lineage-compare">
            <header><div><h3>原表数据依据</h3><p>英文物理表名与任务执行时的原始字段值</p></div><span>{{ lineageEvidenceRows.length }} 条依据</span></header>
            <table><thead><tr><th>来源表</th><th>记录 ID</th><th>原始字段</th><th>原始值</th><th>判定用途</th></tr></thead><tbody><tr v-for="row in lineageEvidenceRows" :key="`${row.table}-${row.record}-${row.field}`"><td><code>{{ row.table }}</code></td><td>{{ row.record }}</td><td><code>{{ row.field }}</code></td><td class="raw-value">{{ row.raw }}</td><td>{{ row.basis }}</td></tr></tbody></table>
          </section>
          <section><h3>处理链路</h3><div class="lineage"><span>{{ lineageEvidenceRows[0]?.table }}<small>{{ processingInstance?.sourceRecordId }}</small></span><b>→</b><span>{{ selectedStep.name }}<small>{{ processingInstance?.rule || selectedStep.engine }}</small></span><template v-if="isExecutionInterrupted"><b>→</b><span>下游未执行<small>未写入</small></span></template><template v-else><b>→</b><span>{{ visiblePhase === '数据处理' ? 'kg_stage_standard_record' : 'kg_candidate_object' }}<small>{{ batch.id }}</small></span><b>→</b><span>{{ processingInstance?.objectId || '任务结果' }}</span></template></div></section>
        </div>
      </main>
    </section>
  </div>
</template>

<style scoped>
.task-detail-page{height:100%;overflow:auto;padding:0 0 18px;color:#17233b}.detail-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:12px}.detail-head a{color:#165dff;font-size:12px;text-decoration:none}.detail-head>div>span{margin-left:10px;color:#8793a8;font-size:10px}.detail-head h1{margin:7px 0 3px;font-size:22px}.detail-head p{margin:0;color:#66758f;font-size:11px}.detail-actions{display:flex;gap:8px}.detail-actions button{height:34px;padding:0 14px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;cursor:pointer}.detail-actions .primary{border-color:#d92d20;background:#d92d20;color:#fff}.action-message{margin:0 0 12px;padding:9px 12px;border:1px solid #b2ccff;border-radius:6px;background:#f0f5ff;color:#344f7a;font-size:11px}.attention-banner{display:flex;align-items:center;gap:12px;margin-bottom:12px;padding:11px 14px;border:1px solid #f6c7c2;border-radius:8px;background:#fff7f6}.attention-banner>i{display:grid;place-items:center;flex:0 0 28px;width:28px;height:28px;border-radius:50%;background:#d92d20;color:#fff;font-style:normal;font-weight:700}.attention-banner>div{flex:1}.attention-banner strong{color:#912018;font-size:12px}.attention-banner p{margin:3px 0 0;color:#77504c;font-size:10px}.attention-banner a{padding:8px 11px;border-radius:5px;background:#d92d20;color:#fff;font-size:10px;text-decoration:none}.summary-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}.summary-grid article{display:grid;gap:5px;padding:13px 14px;border:1px solid #c9dcf7;border-radius:8px;background:#fff}.summary-grid span{color:#6b7890;font-size:10px}.summary-grid strong{font-size:19px}.summary-grid strong.version{font-size:13px}.summary-grid em{overflow:hidden;color:#8793a8;font-size:9px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}.danger{color:#d92d20}.warning{color:#b54708}.detail-workspace{display:grid;grid-template-columns:340px minmax(0,1fr);min-height:560px;overflow:hidden;border:1px solid #bed4f3;border-radius:9px;background:#fff}.process-sidebar{border-right:1px solid #dce8f8;background:#f8fbff}.process-sidebar>header{display:flex;align-items:center;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #dce8f8;background:#fff}.process-sidebar h2{margin:0;font-size:14px}.process-sidebar header p{margin:3px 0 0;color:#7b899e;font-size:9px}.process-sidebar header>span{padding:4px 8px;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:10px}.phase-group{padding:10px}.phase-title{display:flex;align-items:center;justify-content:space-between;padding:4px 3px 8px}.phase-title strong{font-size:11px}.phase-title em{color:#8290a7;font-size:9px;font-style:normal}.process-step{display:grid;grid-template-columns:22px minmax(0,1fr) auto;align-items:center;gap:8px;width:100%;min-height:48px;margin-bottom:5px;padding:7px 8px;border:1px solid transparent;border-radius:6px;background:transparent;color:#34435c;text-align:left;cursor:pointer}.process-step:hover,.process-step.active{border-color:#8eb8f7;background:#fff;box-shadow:0 3px 10px rgba(39,89,164,.08)}.process-step>i{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#12b76a;color:#fff;font-size:10px;font-style:normal}.process-step>span{display:grid;gap:3px}.process-step span strong{display:flex;align-items:center;gap:5px;font-size:11px}.process-step span em{color:#7c899d;font-size:9px;font-style:normal}.process-step span b{padding:1px 5px;border-radius:3px;background:#7f56d9;color:#fff;font-size:8px}.process-step span b.risk{background:#f79009}.process-step>small{color:#667085;font-size:8px}.process-step.is-高风险{min-height:58px;border-left:3px solid #f79009;background:#fffaf0}.process-step.is-需人工处理{border-color:#f7c6c2;background:#fff7f6}.process-step.is-需人工处理>i{background:#d92d20}.process-step.is-需人工处理>small{color:#b42318}.process-step.is-待执行{opacity:.62}.process-step.is-待执行>i{background:#98a2b3}.step-detail{min-width:0}.step-head{display:flex;align-items:flex-start;justify-content:space-between;gap:15px;padding:14px 16px;border-bottom:1px solid #dce8f8;background:#fbfdff}.step-head span{color:#165dff;font-size:9px}.step-head h2{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:18px}.step-head h2 b{padding:3px 7px;border-radius:4px;background:#7f56d9;color:#fff;font-size:9px}.step-head p{margin:0;color:#718099;font-size:10px}.step-head>a{padding:8px 11px;border-radius:5px;background:#d92d20;color:#fff;font-size:10px;text-decoration:none}.detail-tabs{display:flex;padding:0 14px;border-bottom:1px solid #dce8f8}.detail-tabs button{height:40px;padding:0 14px;border:0;border-bottom:2px solid transparent;background:transparent;color:#66758f;font-size:10px;cursor:pointer}.detail-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.overview-content{display:grid;grid-template-columns:minmax(220px,.75fr) minmax(320px,1.25fr);gap:12px;padding:14px}.overview-content>section{border:1px solid #dce8f8;border-radius:7px;background:#fff}.overview-content h3,.io-content h3,.trace-content h3,.issue-list h3{margin:0;padding:11px 13px;border-bottom:1px solid #e4ecf6;font-size:12px}.metric-card dl,.ai-card dl{display:grid;grid-template-columns:1fr 1fr;margin:0;padding:7px 12px}.metric-card dl{grid-template-columns:1fr}.metric-card dl div,.ai-card dl div{display:flex;justify-content:space-between;gap:10px;padding:7px 3px;border-bottom:1px solid #eef2f7;font-size:10px}.metric-card dt,.ai-card dt{color:#718099}.metric-card dd,.ai-card dd{margin:0;text-align:right}.ai-card{border-color:#cbbaf7!important;background:#fcfaff!important}.ai-card>header{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid #e4dcfa}.ai-card header>div{display:flex;align-items:center;gap:8px}.ai-card header b{display:grid;place-items:center;width:27px;height:27px;border-radius:6px;background:#7f56d9;color:#fff;font-size:10px}.ai-card header span{display:grid}.ai-card header strong{font-size:11px}.ai-card header em{color:#766b91;font-size:8px;font-style:normal}.ai-card header>i{padding:3px 7px;border-radius:999px;background:#fff0d5;color:#b54708;font-size:8px;font-style:normal}.result-card{grid-column:1/-1;padding-bottom:10px}.result-card.alert{border-color:#f7c6c2;background:#fff8f7}.result-card.success{border-color:#abefc6;background:#f6fef9}.result-card p,.result-card li{color:#596981;font-size:10px;line-height:18px}.result-card p{margin:10px 13px}.io-content{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:14px}.io-content>section,.trace-content>section{overflow:hidden;border:1px solid #dce8f8;border-radius:7px}.io-content pre,.log-content>pre{min-height:250px;margin:0;padding:15px;overflow:auto;background:#17233b;color:#d9e7ff;font:10px/18px Consolas,monospace;white-space:pre-wrap}.sample-text,.candidate-result{margin:13px;padding:14px;border-radius:6px;background:#f5f8fc}.sample-text span,.candidate-result span{color:#728099;font-size:9px}.sample-text p{font-size:11px;line-height:20px}.candidate-result strong{display:block;margin:10px 0;font-size:12px}.candidate-result p{color:#68778e;font-size:10px}.candidate-result p b{color:#b54708}.log-content{display:grid;grid-template-columns:230px minmax(0,1fr);gap:12px;padding:14px}.issue-list{overflow:hidden;border:1px solid #f4c7c3;border-radius:7px;background:#fff8f7}.issue-list article{display:grid;gap:7px;padding:14px}.issue-list span,.issue-list em{color:#77504c;font-size:9px;font-style:normal}.issue-list strong{color:#b42318;font-size:24px}.trace-content{display:grid;gap:12px;padding:14px}.lineage{display:flex;align-items:center;justify-content:center;gap:9px;padding:22px;overflow:auto}.lineage span{min-width:115px;padding:12px;border:1px solid #bdd7ff;border-radius:6px;background:#f6faff;font-size:9px;text-align:center}.lineage b{color:#165dff}.trace-content table{width:100%;border-collapse:collapse;font-size:10px}.trace-content th,.trace-content td{padding:10px 13px;border-bottom:1px solid #e4ecf6;text-align:left}.trace-content th{width:140px;color:#65738b}@media(max-width:1200px){.summary-grid{grid-template-columns:repeat(3,1fr)}.detail-workspace{grid-template-columns:300px minmax(0,1fr)}.overview-content{grid-template-columns:1fr}.result-card{grid-column:auto}}@media(max-width:900px){.summary-grid{grid-template-columns:repeat(2,1fr)}.detail-workspace{grid-template-columns:1fr}.process-sidebar{border-right:0;border-bottom:1px solid #dce8f8}.io-content,.log-content{grid-template-columns:1fr}}
.process-step.has-review:not(.is-需人工处理){border-color:#f4d39b;background:#fffbf2}.process-step.has-review:not(.is-需人工处理)>small{color:#b54708}
.success-text{color:#067647}.prompt-card,.quality-strategy{grid-column:1/-1;overflow:hidden}.prompt-card h3,.quality-strategy h3{display:flex;align-items:center;justify-content:space-between}.prompt-card h3 span{padding:2px 6px;border-radius:4px;background:#eee8ff;color:#6941c6;font-size:8px;font-weight:500}.prompt-card pre,.quality-strategy>pre{margin:0;padding:13px 15px;background:#201a32;color:#eee9ff;font:10px/18px Consolas,monospace;white-space:pre-wrap}.quality-strategy table{width:100%;border-collapse:collapse;font-size:9px}.quality-strategy th,.quality-strategy td{padding:9px 11px;border-bottom:1px solid #e5ecf5;text-align:left;vertical-align:top}.quality-strategy th{background:#f5f8fc;color:#66758f}.quality-strategy td span.ai{display:inline-flex;padding:2px 5px;border-radius:4px;background:#eee8ff;color:#6941c6}.quality-ai-note{display:flex;align-items:center;gap:9px;margin:10px;padding:10px;border:1px solid #d9ccfa;border-radius:6px;background:#fbfaff}.quality-ai-note>b{display:grid;place-items:center;width:26px;height:26px;border-radius:5px;background:#7f56d9;color:#fff;font-size:9px}.quality-ai-note span{display:grid;gap:2px}.quality-ai-note strong{font-size:10px}.quality-ai-note em{color:#766b91;font-size:8px;font-style:normal}.issue-list strong.safe{color:#067647}.lineage span small{display:block;margin-top:4px;color:#7d899b;font-size:8px}
.lineage-compare>header{display:flex;align-items:center;justify-content:space-between;padding:11px 13px;border-bottom:1px solid #e4ecf6;background:#fbfdff}.lineage-compare>header h3{padding:0;border:0}.lineage-compare>header p{margin:3px 0 0;color:#7a879a;font-size:9px}.lineage-compare>header>span{padding:3px 7px;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:9px}.lineage-compare code{padding:2px 5px;border-radius:4px;background:#f1f5fa;color:#344f73;font:9px Consolas,monospace}.lineage-compare .raw-value{max-width:360px;color:#354760;line-height:17px;white-space:normal}
</style>
