<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  getImpactScope,
  getReviewRecord,
  getReviewTemplate,
  type ReviewAction,
  type ReviewRecord,
} from './manual-review-data'

const route = useRoute()
const sourceRecord = getReviewRecord(String(route.params.instanceId || ''))
const record = ref<ReviewRecord | undefined>(sourceRecord ? { ...sourceRecord } : undefined)
const isSupported = computed(() => Boolean(record.value))
const isHistory = computed(() => record.value?.status === '已完成')
const isEditable = computed(() => record.value?.status === '待处理')

const template = computed(() => (record.value ? getReviewTemplate(record.value) : null))
const impactScope = computed(() => (record.value ? getImpactScope(record.value) : '任务级'))
const templateId = computed(() => template.value?.id ?? 'T_GENERIC')

const note = ref(record.value?.decisionNote ?? '')
const feedback = ref('')

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
const genericClass = ref('T_ENTITY')

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

  if (id === 'T_ENTITY') {
    entityVerdict.value = item.type.includes('实体类型判断错误')
      ? 'retype'
      : item.type === '单任务执行失败'
        ? 'create'
        : 'merge'
    entityTypeFix.value = 'Expert'
  }

  if (id === 'T_RELATION') {
    const parts = item.object.split('→').map((s) => s.trim())
    evidenceItems.value = item.type.includes('合作关系')
      ? [
          { id: '1', label: '华南智能芯片官网新闻', table: item.sourceTable, recordId: item.sourceRecordId, excerpt: '双方将围绕智能芯片设计与云端算力平台展开联合技术研发。', trust: '企业官网 · 可信度 0.82', checked: true },
          { id: '2', label: '第二独立来源', table: '—', recordId: '—', excerpt: '尚未获取，需补充合作公告、合同编号或权威媒体报道。', trust: '待补充', checked: false },
        ]
      : [
          { id: '1', label: '参考文献原文片段', table: item.sourceTable, recordId: item.sourceRecordId, excerpt: '文末参考文献中出现《矩阵分析基础》，但未解析到完整 DOI。', trust: '论文原文 · 可信度 0.78', checked: true },
          { id: '2', label: 'DOI / 标题交叉验证', table: '—', recordId: '—', excerpt: '尚未完成被引论文 DOI 与标题一致性校验。', trust: '待补充', checked: false },
        ]
    if (parts.length >= 2) {
      // keep for display via record.object
    }
  }

  if (id === 'T_DQ_FILL') {
    fillTitleZh.value = item.id === 'PI-20260714-0008' ? '' : ''
    fillTitleEn.value = ''
  }
}

initWorkspace(record.value)

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

const primaryActionLabel = computed(() => {
  if (templateId.value === 'T_ENTITY') {
    if (entityVerdict.value === 'merge') return '确认合并并重跑'
    if (entityVerdict.value === 'create') return '确认新建并重跑'
    if (entityVerdict.value === 'retype') return '改类型并重跑'
    return '驳回候选'
  }
  if (templateId.value === 'T_RELATION') {
    if (relationVerdict.value === 'reject') return '驳回该合作关系'
    if (relationVerdict.value === 'hold') return '保持隔离，继续补证'
    return '确认关系并重跑入图'
  }
  return template.value?.actions.find((a) => a.kind === 'primary')?.label ?? '确认并重跑'
})

const isCooperationRelation = computed(() => record.value?.type.includes('合作关系') ?? false)
const relationSchemaLabel = computed(() => isCooperationRelation.value ? 'COOPERATE_WITH\n企业合作' : 'CITES\n论文引用')
const relationRuleSummary = computed(() => isCooperationRelation.value
  ? '系统识别双方存在联合技术研发合作，但当前只有 1 个独立来源。'
  : '系统识别两篇论文存在引用关系，但 DOI 与标题交叉验证不完整。')

const relationEvidenceCount = computed(() => (
  evidenceItems.value.filter((item) => item.checked && item.recordId !== '—').length
  + (extraEvidence.value.trim() ? 1 : 0)
))

const isPrimaryDisabled = computed(() => {
  if (!isEditable.value) return true
  if (templateId.value === 'T_DQ_FILL') return !fillTitleZh.value.trim()
  if (templateId.value === 'T_RELATION' && relationVerdict.value === 'approve') return relationEvidenceCount.value < 2
  return false
})

const footerHint = computed(() => {
  if (isHistory.value) return '处理已完成'
  if (templateId.value === 'T_DQ_FILL' && !fillTitleZh.value.trim()) return '请先补全论文中文标题，再保存并重跑校验'
  if (templateId.value === 'T_RELATION' && relationVerdict.value === 'approve' && relationEvidenceCount.value < 2) return '确认入图前需补充第二个独立可信来源'
  if (impactScope.value === '批次级') return `批次级异常 · 确认后将从「${record.value?.node}」恢复公共流程`
  return `任务级异常 · 确认后将从「${record.value?.node}」重跑本对象`
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

const handleAction = (action: ReviewAction | { id: string; label: string; kind: string; rerun?: boolean }) => {
  if (!record.value || !isEditable.value) return
  let label = action.label
  if (action.id === 'entity-confirm' || (templateId.value === 'T_ENTITY' && action.kind === 'primary')) {
    label = primaryActionLabel.value
    if (entityVerdict.value === 'reject') {
      label = '驳回候选'
    }
  }
  record.value.status = '已完成'
  record.value.decision = label
  record.value.decisionNote = note.value
  record.value.completedAt = '2026-07-15 11:08:26'
  record.value.updatedAt = '刚刚'
  if (templateId.value === 'T_MAP') {
    record.value.sourceResult = mappingRows.value.map((row) => `${row.source} → ${row.target}`).join('；')
  }
  const rerun = 'rerun' in action ? action.rerun : label.includes('重跑') || label.includes('重试')
  feedback.value = label.includes('驳回') || label.includes('退回')
    ? '处理结果已回写，该对象将返回上游节点重新处理。'
    : label.includes('升级')
      ? '已提交升级，治理员将接手本异常。'
      : label.includes('隔离') || label.includes('废弃') || label.includes('跳过')
        ? '处理结果已回写，对象保持隔离或结束，未进入下游。'
        : rerun
          ? `修正结果已回写，系统已从「${record.value.node}」创建重跑实例。请到图谱构建查看进度。`
          : '处理结果已回写。'
}

const runPrimary = () => {
  if (templateId.value === 'T_ENTITY' && entityVerdict.value === 'reject') {
    handleAction({ id: 'reject-candidate', label: '驳回候选', kind: 'secondary' })
    return
  }
  if (templateId.value === 'T_RELATION' && relationVerdict.value !== 'approve') {
    handleAction({
      id: relationVerdict.value === 'reject' ? 'reject-extract' : 'keep-isolated',
      label: primaryActionLabel.value,
      kind: 'secondary',
      rerun: relationVerdict.value === 'reject',
    })
    return
  }
  const primary = template.value?.actions.find((a) => a.kind === 'primary')
  if (primary) handleAction({ ...primary, label: primaryActionLabel.value })
}

const secondaryActions = computed(() => (
  templateId.value === 'T_RELATION'
    ? []
    : template.value?.actions.filter((a) => a.kind !== 'primary') ?? []
))
</script>

<template>
  <div v-if="record && isSupported" class="rw">
    <header class="rw-head">
      <div class="rw-head__main">
        <RouterLink :to="backPath">← 返回处理队列</RouterLink>
        <h1>{{ isHistory ? '处理记录' : '人工处理详情' }}</h1>
        <p>
          <code>{{ record.id }}</code>
          <span>{{ record.handler }}</span>
          <em>{{ record.node }} · {{ record.type }} · {{ record.ruleId }}</em>
        </p>
      </div>
      <div class="rw-head__badges">
        <span :class="['scope', impactScope === '批次级' ? 'is-batch' : 'is-task']">{{ impactScope }}{{ impactScope === '批次级' ? ' · 已阻断' : '' }}</span>
        <span :class="['status', `is-${record.status}`]">{{ record.status }}</span>
      </div>
    </header>

    <section class="rw-diag" aria-label="异常诊断">
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
    </section>

    <main class="rw-body">
      <header class="rw-zone-head">
        <div>
          <h2>{{ template?.title }}</h2>
          <p>{{ template?.question }} · {{ record.suggestion }}</p>
        </div>
      </header>

      <!-- T_MAP -->
      <section v-if="templateId === 'T_MAP'" class="zone zone-map">
        <p class="zone-banner">{{ impactScope === '批次级' ? '本映射影响公共流程，当前节点及下游已阻断。' : '修正后仅重跑本对象相关任务。' }}</p>
        <div class="map-head"><span>来源字段</span><span>样例值</span><span>Schema / 字典目标</span></div>
        <div v-for="row in mappingRows" :key="row.source" class="map-row">
          <code>{{ row.source }}</code>
          <span>{{ row.sample }}</span>
          <select v-model="row.target" :disabled="!isEditable">
            <option v-for="opt in row.options" :key="opt.value" :value="opt.value">{{ opt.label }}</option>
          </select>
        </div>
        <label v-if="record.type.includes('标准化失败')" class="check-line">
          <input v-model="keepRawEnum" type="checkbox" :disabled="!isEditable" /> 保留原始值用于追溯
        </label>
        <label v-if="record.type === '专利状态标准化失败'" class="inline-select">
          <span>字典版本</span>
          <select v-model="dictVersion" :disabled="!isEditable">
            <option value="v1.2">回滚到 dict-patent-v1.2</option>
            <option value="v1.3-fix">在 v1.3 新增枚举条目</option>
          </select>
        </label>
      </section>

      <!-- T_ENTITY -->
      <section v-else-if="templateId === 'T_ENTITY'" class="zone zone-entity">
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
        <div class="verdict" role="radiogroup" aria-label="实体裁决">
          <label :class="{ active: entityVerdict === 'merge' }"><input v-model="entityVerdict" type="radio" value="merge" :disabled="!isEditable" /> 合并到右侧存量实体</label>
          <label :class="{ active: entityVerdict === 'create' }"><input v-model="entityVerdict" type="radio" value="create" :disabled="!isEditable" /> 保留为新建实体</label>
          <label :class="{ active: entityVerdict === 'retype' }">
            <input v-model="entityVerdict" type="radio" value="retype" :disabled="!isEditable" />
            仅修正类型为
            <select v-model="entityTypeFix" :disabled="!isEditable || entityVerdict !== 'retype'">
              <option v-for="t in entityTypes" :key="t.value" :value="t.value">{{ t.label }}</option>
            </select>
            后重跑
          </label>
          <label :class="{ active: entityVerdict === 'reject' }"><input v-model="entityVerdict" type="radio" value="reject" :disabled="!isEditable" /> 不是同一实体，驳回候选</label>
        </div>
      </section>

      <!-- T_RELATION -->
      <section v-else-if="templateId === 'T_RELATION'" class="zone zone-relation">
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
        <div class="evidence-list">
          <label v-for="item in evidenceItems" :key="item.id" class="evidence-item">
            <input v-model="item.checked" type="checkbox" :disabled="!isEditable || item.recordId === '—'" />
            <div>
              <strong>{{ item.label }} <em>{{ item.trust }}</em></strong>
              <p>{{ item.excerpt }}</p>
              <span>{{ item.table }} / {{ item.recordId }}</span>
            </div>
          </label>
        </div>
        <label v-if="isEditable" class="wide-field">
          <span>补充证据（链接或记录 ID）</span>
          <input v-model="extraEvidence" placeholder="例如：COOP-89321-B 或公告 URL" />
        </label>
        <h3 class="zone-subtitle">处理结论</h3>
        <div class="verdict relation-verdict">
          <label :class="{ active: relationVerdict === 'approve' }"><input v-model="relationVerdict" type="radio" value="approve" :disabled="!isEditable" /><span><strong>确认合作关系</strong><small>证据充分，允许该关系进入图谱</small></span></label>
          <label :class="{ active: relationVerdict === 'hold' }"><input v-model="relationVerdict" type="radio" value="hold" :disabled="!isEditable" /><span><strong>保持隔离</strong><small>暂不入图，等待补充第二独立来源</small></span></label>
          <label :class="{ active: relationVerdict === 'reject' }"><input v-model="relationVerdict" type="radio" value="reject" :disabled="!isEditable" /><span><strong>驳回关系</strong><small>认定当前证据不支持合作关系，退回抽取节点</small></span></label>
        </div>
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
        <div class="verdict">
          <label :class="{ active: attrVerdict === 'A' }"><input v-model="attrVerdict" type="radio" value="A" :disabled="!isEditable" /> 采用来源 A</label>
          <label :class="{ active: attrVerdict === 'B' }"><input v-model="attrVerdict" type="radio" value="B" :disabled="!isEditable" /> 采用来源 B</label>
          <label :class="{ active: attrVerdict === 'manual' }">
            <input v-model="attrVerdict" type="radio" value="manual" :disabled="!isEditable" /> 手工改写
            <input v-model="attrManualOrg" class="mini" placeholder="机构" :disabled="!isEditable || attrVerdict !== 'manual'" />
            <input v-model="attrManualRange" class="mini" placeholder="起止时间" :disabled="!isEditable || attrVerdict !== 'manual'" />
          </label>
          <label :class="{ active: attrVerdict === 'split' }"><input v-model="attrVerdict" type="radio" value="split" :disabled="!isEditable" /> 时间切分（两段都保留）</label>
        </div>
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
          <label class="wide-field"><span>title_zh <b>必填</b></span><input v-model="fillTitleZh" :disabled="!isEditable" placeholder="论文中文标题" /></label>
          <label class="wide-field"><span>title_en</span><input v-model="fillTitleEn" :disabled="!isEditable" placeholder="论文英文标题（可选）" /></label>
          <p class="fill-rerun-note">保存后将仅从“必填校验”节点重跑当前论文记录，不影响同批次其他数据。</p>
        </div>
      </section>

      <!-- T_DQ_MERGE -->
      <section v-else-if="templateId === 'T_DQ_MERGE'" class="zone zone-merge">
        <p class="zone-banner">同一 paper_id 命中 {{ dupRecords.length }} 条源记录</p>
        <div class="verdict">
          <label v-for="(row, index) in dupRecords" :key="row.id" :class="{ active: mergeMaster === index }">
            <input v-model="mergeMaster" type="radio" :value="index" :disabled="!isEditable" />
            主记录 {{ row.id }} · {{ row.hint }}
            <small>{{ row.detail }}</small>
          </label>
        </div>
        <div class="merge-fields">
          <span>从非主记录并入字段</span>
          <label><input v-model="mergeFields.authors" type="checkbox" :disabled="!isEditable" /> authors</label>
          <label><input v-model="mergeFields.affiliation" type="checkbox" :disabled="!isEditable" /> affiliation</label>
          <label><input v-model="mergeFields.source_channel" type="checkbox" :disabled="!isEditable" /> source_channel</label>
        </div>
      </section>

      <!-- T_RUNTIME -->
      <section v-else-if="templateId === 'T_RUNTIME'" class="zone zone-runtime">
        <dl class="runtime-dl">
          <div><dt>影响范围</dt><dd>{{ impactScope }}{{ impactScope === '批次级' ? ' · 已阻断下游' : ' · 仅本任务' }}</dd></div>
          <div><dt>失败摘要</dt><dd>{{ record.evidence }}</dd></div>
          <div><dt>版本信息</dt><dd>模型 Qwen3-32B-Instruct · Prompt kg-extract-v2.6.1 · Schema v1.8</dd></div>
          <div><dt>系统结论</dt><dd>{{ record.sourceResult }}</dd></div>
        </dl>
        <div class="runtime-links">
          <RouterLink :to="`/processing-instance/${record.id}`">打开任务详情日志 →</RouterLink>
        </div>
        <label v-if="isEditable && impactScope === '批次级'" class="inline-select">
          <span>重跑使用 Prompt</span>
          <select v-model="runtimeConfig">
            <option value="kg-extract-v2.6.1">kg-extract-v2.6.1（当前）</option>
            <option value="kg-extract-v2.5.0">kg-extract-v2.5.0（回退）</option>
            <option value="kg-extract-v2.6.2-rc">kg-extract-v2.6.2-rc（试验）</option>
          </select>
        </label>
      </section>

      <!-- T_GENERIC -->
      <section v-else class="zone zone-generic">
        <p class="zone-banner">未匹配专用模板，请选择建议归类后处置。</p>
        <p>{{ record.evidence }}</p>
        <label class="inline-select">
          <span>建议归类</span>
          <select v-model="genericClass" :disabled="!isEditable">
            <option value="T_MAP">映射修复</option>
            <option value="T_ENTITY">实体裁决</option>
            <option value="T_RELATION">关系证据</option>
            <option value="T_ATTR">属性对照</option>
            <option value="T_DQ_FILL">源数据补全</option>
            <option value="T_DQ_MERGE">重复定主</option>
            <option value="T_RUNTIME">运行处置</option>
          </select>
        </label>
      </section>

      <div v-if="!isEditable" class="rw-readonly">
        <strong>{{ record.decision }}</strong>
        <p>{{ record.decisionNote }}</p>
        <em>{{ record.completedAt }}</em>
      </div>

      <p v-if="feedback" class="rw-feedback">{{ feedback }}</p>
    </main>

    <footer class="rw-foot">
      <span>{{ footerHint }}</span>
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
  flex: 1;
  min-height: 0;
  overflow: auto;
  padding: 14px 16px 18px;
  border: 1px solid #bdd7ff;
  border-radius: 9px;
  background: #fff;
}

.rw-zone-head {
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
</style>
