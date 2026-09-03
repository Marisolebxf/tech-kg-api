<script setup lang="ts">
import { Message } from '@arco-design/web-vue'
import { computed, onMounted, ref, watch } from 'vue'

import {
  cancelCorrection, createCorrection, getCorrection, listCorrections, retryCorrection,
  reviewCorrection, updateCorrection, type CorrectionOperation, type CorrectionRecord,
  type CorrectionTargetType,
} from '../../api/corrections'
import { getErrorMessage } from '../../api/http'
import { getExampleCorrections } from '../../data/adminGovernanceExamples'
import { useAuthStore } from '../../stores/auth'

const props = withDefaults(defineProps<{ scope?: 'mine' | 'admin'; initialStatus?: string; mode?: 'records' | 'review' }>(), {
  scope: 'mine', initialStatus: '', mode: 'records',
})
const authStore = useAuthStore()
const loading = ref(true)
const saving = ref(false)
const rows = ref<CorrectionRecord[]>([])
const total = ref(0)
const counts = ref<Record<string, number>>({})
const page = ref(1)
const pageSize = 20
const dataMode = ref<'live' | 'example'>('live')
const exampleRows = ref(getExampleCorrections())
const exampleFallbackEnabled = import.meta.env.VITE_ADMIN_EXAMPLE_FALLBACK !== 'false'
const formVisible = ref(false)
const queryVisible = ref(false)
const reviewVisible = ref(false)
const detailVisible = ref(false)
const editing = ref<CorrectionRecord | null>(null)
const reviewing = ref<CorrectionRecord | null>(null)
const selected = ref<CorrectionRecord | null>(null)
const decision = ref<'approve' | 'reject'>('approve')
const decisionNote = ref('')
const beforeText = ref('{}')
const afterText = ref('{}')
const form = ref({ targetType: 'expert' as CorrectionTargetType, operation: 'update' as CorrectionOperation, targetId: '', title: '', reason: '' })
const queryForm = ref({ keyword: '', targetType: '', status: '' })
const activeQuery = ref({ keyword: '', targetType: '', status: '' })
let loadSequence = 0

const isAdmin = computed(() => props.scope === 'admin' && authStore.isAdmin)
const isReviewPage = computed(() => isAdmin.value && props.mode === 'review')
const reviewQueueStatuses = new Set(['PENDING_REVIEW', 'PENDING_SYNC', 'SYNC_FAILED'])
const reviewQueueTotal = computed(() => (
  (counts.value.PENDING_REVIEW || 0)
  + (counts.value.PENDING_SYNC || 0)
  + (counts.value.SYNC_FAILED || 0)
))
const detailFlowNote = computed(() => {
  if (isReviewPage.value) return '本页负责审核、驳回与失败重试；申请内容的维护请在修正记录中完成。'
  if (isAdmin.value) return '本页负责查询全部记录，并维护尚未审核的申请；审核与同步操作请前往审核与同步。'
  return '待审核期间可以修改或撤销自己的申请；管理员审核通过后由后台自动同步。'
})
const targetLabels: Record<CorrectionTargetType, string> = { expert: '专家', organization: '机构/企业', relation: '专家任职关系' }
const operationLabels: Record<CorrectionOperation, string> = { create: '新增', update: '修改', delete: '删除' }
const statusLabels: Record<string, string> = { PENDING_REVIEW: '待审核', PENDING_SYNC: '同步中', SYNC_FAILED: '同步失败', COMPLETED: '已完成', REJECTED: '已驳回', CANCELLED: '已撤销' }

function syncStatusLabel(row: CorrectionRecord) {
  if (row.status === 'PENDING_SYNC') return '同步中'
  if (row.status === 'SYNC_FAILED') return '同步失败'
  if (row.status === 'COMPLETED') return '同步完成'
  if (row.status === 'REJECTED' || row.status === 'CANCELLED') return '无需同步'
  return '未开始'
}
function canEdit(row: CorrectionRecord) { return row.status === 'PENDING_REVIEW' }
function canCancel(row: CorrectionRecord) { return row.status === 'PENDING_REVIEW' }
function canReview(row: CorrectionRecord) { return isReviewPage.value && row.status === 'PENDING_REVIEW' }
function canRetry(row: CorrectionRecord) { return isReviewPage.value && row.status === 'SYNC_FAILED' }

function errorMessage(error: unknown) {
  return getErrorMessage(error, '操作失败')
}
function pretty(value: Record<string, unknown>) { return JSON.stringify(value || {}, null, 2) }
function parseJson(value: string, label: string) {
  try {
    const parsed = JSON.parse(value || '{}')
    if (!parsed || Array.isArray(parsed) || typeof parsed !== 'object') {
      throw new TypeError(`${label}必须是 JSON 对象`)
    }
    return parsed as Record<string, unknown>
  } catch { throw new Error(`${label}必须是合法的 JSON 对象`) }
}
function filterExampleRows(source: CorrectionRecord[]) {
  const keyword = activeQuery.value.keyword.trim().toLowerCase()
  return source.filter((item) => {
    if (isReviewPage.value && !reviewQueueStatuses.has(item.status)) return false
    if (props.initialStatus && item.status !== props.initialStatus) return false
    if (activeQuery.value.status && item.status !== activeQuery.value.status) return false
    if (activeQuery.value.targetType && item.targetType !== activeQuery.value.targetType) return false
    if (!keyword) return true
    return [item.title, item.reason, item.targetId, item.submitterName]
      .some((value) => String(value || '').toLowerCase().includes(keyword))
  })
}
function applyExampleData() {
  const filtered = filterExampleRows(exampleRows.value)
  const start = (page.value - 1) * pageSize
  rows.value = filtered.slice(start, start + pageSize)
  total.value = filtered.length
  counts.value = filtered.reduce<Record<string, number>>((result, item) => {
    result[item.status] = (result[item.status] || 0) + 1
    return result
  }, {})
  dataMode.value = 'example'
}
async function load() {
  const sequence = ++loadSequence
  loading.value = true
  rows.value = []
  try {
    const keyword = activeQuery.value.keyword.trim()
    const requestedStatus = activeQuery.value.status || props.initialStatus
    const params: Record<string, unknown> = {
      scope: isAdmin.value ? 'all' : 'mine',
      page: page.value,
      pageSize,
    }
    if (keyword) params.keyword = keyword
    if (activeQuery.value.targetType) params.targetType = activeQuery.value.targetType
    if (requestedStatus) params.status = requestedStatus
    else if (isReviewPage.value) params.statuses = [...reviewQueueStatuses].join(',')
    const result = await listCorrections(params)
    if (sequence !== loadSequence) return
    if (result.items.length || result.total > 0) {
      rows.value = result.items
      total.value = result.total
      counts.value = result.statusCounts || {}
      dataMode.value = 'live'
    } else if (exampleFallbackEnabled) applyExampleData()
    else { rows.value = []; total.value = 0; counts.value = {}; dataMode.value = 'live' }
  } catch (error) {
    if (sequence !== loadSequence) return
    if (exampleFallbackEnabled) applyExampleData()
    else Message.error(errorMessage(error))
  } finally { if (sequence === loadSequence) loading.value = false }
}
function resetPayloadExample(type: CorrectionTargetType) {
  if (type === 'expert') afterText.value = '{\n  "name_zh": "",\n  "scholar_org_name_zh": ""\n}'
  else if (type === 'organization') afterText.value = '{\n  "name_cn": "",\n  "province": ""\n}'
  else afterText.value = '{\n  "sourceId": "专家ID",\n  "targetId": "机构ID",\n  "edgeType": "EMPLOYED_BY",\n  "properties": {\n    "role": ""\n  }\n}'
}
function openCreate() {
  editing.value = null
  form.value = { targetType: 'expert', operation: 'update', targetId: '', title: '', reason: '' }
  beforeText.value = '{}'; resetPayloadExample('expert'); formVisible.value = true
}
function submitQuery() {
  activeQuery.value = { ...queryForm.value }
  page.value = 1
  if (dataMode.value === 'live') void load()
  else applyExampleData()
  queryVisible.value = false
}
function resetQuery() {
  queryForm.value = { keyword: '', targetType: '', status: '' }
  activeQuery.value = { keyword: '', targetType: '', status: '' }
  page.value = 1
  if (dataMode.value === 'live') void load()
  else applyExampleData()
}
function changePage(value: number) {
  page.value = value
  if (dataMode.value === 'live') void load()
  else applyExampleData()
}
function openEdit(row: CorrectionRecord) {
  editing.value = row
  form.value = { targetType: row.targetType, operation: row.operation, targetId: row.targetId, title: row.title, reason: row.reason }
  beforeText.value = pretty(row.beforeData); afterText.value = pretty(row.afterData); formVisible.value = true
}
async function save() {
  if (!form.value.targetId.trim() || !form.value.title.trim() || !form.value.reason.trim()) { Message.warning('请填写对象 ID、标题和修正原因'); return }
  saving.value = true
  try {
    const beforeData = parseJson(beforeText.value, '修正前数据')
    const afterData = parseJson(afterText.value, '修正后数据')
    if (dataMode.value === 'example') {
      const now = new Date().toISOString()
      if (editing.value) {
        const target = exampleRows.value.find((item) => item.id === editing.value?.id)
        if (target) Object.assign(target, { title: form.value.title, reason: form.value.reason, beforeData, afterData, updatedAt: now })
        Message.success('示例修正记录已更新')
      } else {
        exampleRows.value.unshift({
          id: `example-correction-${Date.now()}`, targetType: form.value.targetType, operation: form.value.operation,
          targetId: form.value.targetId, title: form.value.title, reason: form.value.reason, beforeData, afterData,
          status: 'PENDING_REVIEW', submitterId: String(authStore.profile?.user.id || 'current-user'),
          submitterName: authStore.displayName, reviewerId: null, reviewerName: null, decisionNote: '', version: 1,
          submittedAt: now, reviewedAt: null, completedAt: null, updatedAt: now, sync: null,
          history: [{ id: `example-history-${Date.now()}`, action: 'SUBMIT', actorId: String(authStore.profile?.user.id || 'current-user'), actorName: authStore.displayName, note: '新增示例修正申请', createdAt: now }],
        })
        Message.success('示例修正申请已添加')
      }
      formVisible.value = false; applyExampleData(); return
    }
    if (editing.value) {
      await updateCorrection(editing.value.id, { title: form.value.title, reason: form.value.reason, before_data: beforeData, after_data: afterData })
      Message.success('修正记录已更新')
    } else {
      await createCorrection({ target_type: form.value.targetType, operation: form.value.operation, target_id: form.value.targetId, title: form.value.title, reason: form.value.reason, before_data: beforeData, after_data: afterData })
      Message.success('修正申请已提交')
    }
    formVisible.value = false; await load()
  } catch (error) { Message.error(errorMessage(error)) } finally { saving.value = false }
}
async function showDetail(row: CorrectionRecord) {
  if (dataMode.value === 'example') { selected.value = row; detailVisible.value = true; return }
  try { selected.value = await getCorrection(row.id); detailVisible.value = true } catch (error) { Message.error(errorMessage(error)) }
}
async function cancel(row: CorrectionRecord) {
  if (!window.confirm(`确认撤销“${row.title}”？撤销后保留操作记录，且不能继续修改。`)) return
  try {
    if (dataMode.value === 'example') {
      const target = exampleRows.value.find((item) => item.id === row.id)
      if (target) {
        const now = new Date().toISOString()
        target.status = 'CANCELLED'
        target.updatedAt = now
        target.history = [
          ...(target.history || []),
          {
            id: `example-history-${Date.now()}`,
            action: 'CANCEL',
            actorId: String(authStore.profile?.user.id || 'current-user'),
            actorName: authStore.displayName,
            note: '撤销人工修正申请',
            createdAt: now,
          },
        ]
      }
      applyExampleData()
      Message.success('示例修正申请已撤销')
      return
    }
    await cancelCorrection(row.id)
    Message.success('人工修正申请已撤销')
    await load()
  } catch (error) { Message.error(errorMessage(error)) }
}
function openReview(row: CorrectionRecord, value: 'approve' | 'reject') { reviewing.value = row; decision.value = value; decisionNote.value = ''; reviewVisible.value = true }
async function submitReview() {
  if (!reviewing.value) return
  if (decision.value === 'reject' && !decisionNote.value.trim()) { Message.warning('驳回时必须填写原因'); return }
  saving.value = true
  try {
    if (dataMode.value === 'example') {
      const target = exampleRows.value.find((item) => item.id === reviewing.value?.id)
      if (target) {
        const now = new Date().toISOString()
        target.status = decision.value === 'approve' ? 'PENDING_SYNC' : 'REJECTED'
        target.reviewerId = String(authStore.profile?.user.id || 'current-admin')
        target.reviewerName = authStore.displayName
        target.decisionNote = decisionNote.value
        target.reviewedAt = now; target.updatedAt = now
        if (decision.value === 'approve') target.sync = { id: `example-sync-${Date.now()}`, status: 'PENDING', mysqlStatus: 'PENDING', graphStatus: 'PENDING', attempts: 0, maxAttempts: 8, nextRetryAt: null, lastError: '' }
      }
      Message.success(decision.value === 'approve' ? '示例申请已批准并进入同步' : '示例申请已驳回')
      reviewVisible.value = false; applyExampleData(); return
    }
    const result = await reviewCorrection(reviewing.value.id, decision.value, decisionNote.value)
    Message.success(result.status === 'COMPLETED' ? '审核通过，已同步完成' : '审核结果已保存')
    reviewVisible.value = false; await load()
  } catch (error) { Message.error(errorMessage(error)) } finally { saving.value = false }
}
async function retry(row: CorrectionRecord) {
  if (dataMode.value === 'example') {
    row.status = 'PENDING_SYNC'; row.updatedAt = new Date().toISOString()
    if (row.sync) { row.sync.status = 'PENDING'; row.sync.graphStatus = 'PENDING'; row.sync.lastError = '' }
    applyExampleData(); Message.success('示例记录已加入同步重试队列'); return
  }
  try { await retryCorrection(row.id, '管理员从管理端手动重试'); Message.success('已加入同步重试队列'); await load() } catch (error) { Message.error(errorMessage(error)) }
}
watch([() => props.initialStatus, () => props.mode], () => {
  queryForm.value = { keyword: '', targetType: '', status: '' }
  activeQuery.value = { keyword: '', targetType: '', status: '' }
  page.value = 1
  rows.value = []
  total.value = 0
  counts.value = {}
  detailVisible.value = false
  reviewVisible.value = false
  formVisible.value = false
  dataMode.value = 'live'
  void load()
}, { flush: 'sync' })
watch(() => form.value.targetType, (value, oldValue) => { if (!editing.value && value !== oldValue) resetPayloadExample(value) })
watch(() => form.value.operation, (value, oldValue) => {
  if (editing.value || value === oldValue) return
  if (value === 'delete') afterText.value = '{}'
  else if (oldValue === 'delete') resetPayloadExample(form.value.targetType)
})
onMounted(() => { void load() })
</script>

<template>
  <div class="correction-page">
    <header class="page-heading"><div class="page-actions"><a-button type="primary" @click="queryVisible=true">查询</a-button><button v-if="!isReviewPage" class="page-action" type="button" @click="openCreate">新增修正申请</button></div></header>
    <section class="summary-row">
      <template v-if="isReviewPage"><article><span>队列记录</span><strong>{{ reviewQueueTotal }}</strong></article><article><span>待审核</span><strong>{{ counts.PENDING_REVIEW || 0 }}</strong></article><article><span>同步中</span><strong>{{ counts.PENDING_SYNC || 0 }}</strong></article><article><span>同步失败</span><strong>{{ counts.SYNC_FAILED || 0 }}</strong></article></template>
      <template v-else><article><span>记录总数</span><strong>{{ total }}</strong></article><article><span>待审核</span><strong>{{ counts.PENDING_REVIEW || 0 }}</strong></article><article><span>同步失败</span><strong>{{ counts.SYNC_FAILED || 0 }}</strong></article><article><span>已完成</span><strong>{{ counts.COMPLETED || 0 }}</strong></article></template>
    </section>
    <section class="table-panel">
      <div class="table-scroll"><table aria-label="数据表"><colgroup><col class="col-content"><col class="col-target"><col class="col-operation"><col class="col-applicant"><col class="col-status"><col class="col-sync"><col class="col-time"><col class="col-actions"></colgroup><thead><tr><th>修正内容</th><th>对象</th><th>申请人对图谱的操作</th><th>申请人</th><th>状态</th><th>同步状态</th><th>更新时间</th><th><span class="action-column-label">操作</span></th></tr></thead><tbody>
        <tr v-for="row in rows" :key="row.id"><td><span class="record-title">{{ row.title }}</span></td><td class="target-cell">{{ targetLabels[row.targetType] }}</td><td class="operation-cell">{{ operationLabels[row.operation] }}</td><td>{{ row.submitterName }}</td><td class="status-cell"><span class="status" :class="`is-${row.status.toLowerCase()}`">{{ statusLabels[row.status] || row.status }}</span></td><td class="sync-cell"><span class="status" :class="`is-${row.status.toLowerCase()}`">{{ syncStatusLabel(row) }}</span></td><td class="time-cell">{{ row.updatedAt?.replace('T', ' ').slice(0, 16) }}</td><td class="action-cell"><div v-if="isAdmin" class="actions"><template v-if="isReviewPage"><button type="button" title="查看申请说明、修正前后数据和操作轨迹" @click="showDetail(row)">详情</button><button type="button" :disabled="!canReview(row)" title="审核通过后进入自动同步流程" @click="openReview(row, 'approve')">通过</button><button type="button" :disabled="!canReview(row)" title="驳回后不再同步本次修正" @click="openReview(row, 'reject')">驳回</button><button type="button" :disabled="!canRetry(row)" title="仅同步失败记录可以重新同步" @click="retry(row)">重试</button></template><template v-else><button type="button" title="查看申请说明、修正前后数据和操作轨迹" @click="showDetail(row)">详情</button><button type="button" :disabled="!canEdit(row)" title="仅待审核申请可以修改" @click="openEdit(row)">修改</button><button type="button" :disabled="!canCancel(row)" title="撤销后保留操作记录且不能继续修改" @click="cancel(row)">撤销</button></template></div><div v-else class="actions user-actions"><button type="button" title="查看申请说明、修正前后数据和操作轨迹" @click="showDetail(row)">详情</button><button type="button" :disabled="!canEdit(row)" title="仅待审核申请可以修改" @click="openEdit(row)">修改</button><button type="button" :disabled="!canCancel(row)" title="撤销后保留操作记录且不能继续修改" @click="cancel(row)">撤销</button></div></td></tr>
        <tr v-if="!rows.length"><td colspan="8" class="empty">{{ loading ? '正在加载…' : '暂无修正记录' }}</td></tr>
      </tbody></table></div>
      <footer v-if="dataMode === 'live' && total > pageSize" class="table-pagination"><a-pagination :current="page" :page-size="pageSize" :total="total" @change="changePage" /></footer>
    </section>
    <a-modal v-model:visible="queryVisible" :footer="false" :width="520" title="查询修正记录">
      <div class="query-form">
        <label class="wide query-keyword" for="correction-query-keyword"><span>关键词</span><a-input id="correction-query-keyword" v-model="queryForm.keyword" placeholder="修正内容、对象 ID、申请人" @press-enter="submitQuery" /></label>
        <div class="form-field"><span>修正对象</span><a-select v-model="queryForm.targetType" aria-label="修正对象" class="correction-select" :scrollbar="true"><a-option value="">全部</a-option><a-option value="expert">专家</a-option><a-option value="organization">机构/企业</a-option><a-option value="relation">专家任职关系</a-option></a-select></div>
        <div class="form-field"><span>状态</span><a-select v-model="queryForm.status" aria-label="状态" class="correction-select" :scrollbar="true"><a-option value="">全部</a-option><a-option value="PENDING_REVIEW">待审核</a-option><a-option value="PENDING_SYNC">同步中</a-option><a-option value="SYNC_FAILED">同步失败</a-option><a-option v-if="!isReviewPage" value="COMPLETED">已完成</a-option><a-option v-if="!isReviewPage" value="REJECTED">已驳回</a-option><a-option v-if="!isReviewPage" value="CANCELLED">已撤销</a-option></a-select></div>
      </div>
      <footer class="modal-actions"><a-button @click="resetQuery">重置</a-button><a-button type="primary" @click="submitQuery">查询</a-button></footer>
    </a-modal>
    <a-modal v-model:visible="formVisible" :footer="false" :width="720" :title="editing ? '修改修正申请' : '新增人工修正'">
      <div class="correction-dialog-shell">
        <div class="correction-dialog-body">
          <div class="form-grid"><div class="form-field"><span>修正对象</span><a-select v-model="form.targetType" aria-label="修正对象" class="correction-select" :disabled="Boolean(editing)" :scrollbar="true"><a-option value="expert">专家</a-option><a-option value="organization">机构/企业</a-option><a-option value="relation">专家任职关系</a-option></a-select></div><div class="form-field"><span>操作类型</span><a-select v-model="form.operation" aria-label="操作类型" class="correction-select" :disabled="Boolean(editing)" :scrollbar="true"><a-option value="create">新增</a-option><a-option value="update">修改</a-option><a-option value="delete">删除（软删除）</a-option></a-select></div><label class="wide" for="correction-target-id"><span>对象 ID</span><a-input id="correction-target-id" v-model="form.targetId" :disabled="Boolean(editing)" placeholder="专家 ID、机构 ID 或 source->target@0" /></label><label class="wide" for="correction-title"><span>标题</span><a-input id="correction-title" v-model="form.title" /></label><label class="wide" for="correction-reason"><span>修正原因</span><a-textarea id="correction-reason" v-model="form.reason" :auto-size="{ minRows: 2, maxRows: 4 }" /></label><label for="correction-before-json"><span>修正前数据（JSON）</span><a-textarea id="correction-before-json" v-model="beforeText" :auto-size="{ minRows: 8, maxRows: 14 }" /></label><label for="correction-after-json"><span>修正后数据（JSON）</span><a-textarea id="correction-after-json" v-model="afterText" :disabled="form.operation === 'delete'" :auto-size="{ minRows: 8, maxRows: 14 }" /></label></div>
        </div>
        <footer class="modal-actions"><a-button @click="formVisible=false">取消</a-button><a-button type="primary" :loading="saving" @click="save">{{ editing ? '保存修改' : '提交审核' }}</a-button></footer>
      </div>
    </a-modal>
    <a-modal v-model:visible="reviewVisible" :footer="false" :width="520" title="审核人工修正"><div class="review-form"><p><strong>{{ reviewing?.title }}</strong><span>{{ reviewing?.targetId }}</span></p><a-radio-group v-model="decision"><a-radio value="approve">批准并同步</a-radio><a-radio value="reject">驳回申请</a-radio></a-radio-group><a-textarea v-model="decisionNote" :placeholder="decision === 'reject' ? '请填写驳回原因' : '可填写审核说明'" :auto-size="{ minRows: 3, maxRows: 6 }" /></div><footer class="modal-actions"><a-button @click="reviewVisible=false">取消</a-button><a-button :status="decision === 'reject' ? 'danger' : 'normal'" type="primary" :loading="saving" @click="submitReview">确认审核</a-button></footer></a-modal>
    <a-modal v-model:visible="detailVisible" :footer="false" :width="720" title="修正记录详情">
      <div class="correction-dialog-shell">
        <div class="correction-dialog-body">
          <div v-if="selected" class="detail-content"><h3>{{ selected.title }}</h3><p class="flow-note">{{ detailFlowNote }}</p><dl><dt>对象</dt><dd>{{ targetLabels[selected.targetType] }} / {{ selected.targetId }}</dd><dt>操作类型</dt><dd>{{ operationLabels[selected.operation] }}<span v-if="selected.operation === 'delete'">（软删除）</span></dd><dt>当前状态</dt><dd>{{ statusLabels[selected.status] || selected.status }}</dd><dt>修正说明</dt><dd>{{ selected.reason }}</dd><dt>修正前</dt><dd><pre>{{ pretty(selected.beforeData) }}</pre></dd><dt>修正后</dt><dd><pre>{{ pretty(selected.afterData) }}</pre></dd><dt>同步状态</dt><dd>{{ syncStatusLabel(selected) }}</dd><template v-if="selected.sync?.lastError"><dt>同步说明</dt><dd>{{ selected.sync.lastError }}</dd></template></dl><button v-if="selected.status === 'SYNC_FAILED' && isReviewPage" class="detail-retry" type="button" @click="retry(selected)">重新同步</button><h4>操作说明</h4><ul class="operation-help"><template v-if="isReviewPage"><li><strong>详情</strong>查看完整申请和处理轨迹</li><li><strong>通过</strong>批准申请并进入自动同步</li><li><strong>驳回</strong>拒绝申请且不执行同步</li><li><strong>重试</strong>重新处理同步失败记录</li></template><template v-else><li><strong>详情</strong>查看完整申请和处理轨迹</li><li><strong>修改</strong>修改尚未审核的申请</li><li><strong>撤销</strong>撤销待审核申请并保留记录</li></template></ul><h4>操作轨迹</h4><ol><li v-for="item in selected.history" :key="item.id"><strong>{{ item.actorName }}</strong><span>{{ item.action }} · {{ item.createdAt?.replace('T', ' ').slice(0, 19) }}</span><p>{{ item.note }}</p></li></ol></div>
        </div>
      </div>
    </a-modal>
  </div>
</template>

<style scoped>
.correction-page{display:flex;height:100%;min-height:0;flex-direction:column;color:var(--gkx-text-primary)}.page-heading{display:flex;align-items:flex-end;justify-content:flex-end;margin-bottom:16px}.page-heading span{color:var(--gkx-primary);font-size:10px;letter-spacing:.12em}.page-heading em{margin-left:8px;padding:2px 6px;border-radius:3px;background:#e8f3ff;color:#004ecc;font-size:9px;font-style:normal;letter-spacing:0}.page-heading h1{margin:4px 0;font-size:22px}.page-heading p{margin:0;color:var(--gkx-text-secondary);font-size:12px}.page-actions{display:flex;align-items:center;gap:18px}.page-action{padding:2px 0;border:0;background:transparent;color:#004ecc;font-size:12px;white-space:nowrap;cursor:pointer}.summary-row{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:14px}.summary-row article{display:flex;align-items:center;justify-content:space-between;padding:16px;border:1px solid var(--gkx-border);border-radius:6px;background:#fff}.summary-row span{color:var(--gkx-text-secondary);font-size:12px}.summary-row strong{color:var(--gkx-text-primary);font-size:22px}.table-panel{display:flex;flex:1;min-height:0;border:1px solid var(--gkx-border);border-radius:6px;background:#fff;flex-direction:column}.table-scroll{min-height:0;overflow:auto}.table-scroll table{width:100%;border-collapse:collapse;font-size:12px}.table-scroll th,.table-scroll td{padding:11px 12px;border-bottom:1px solid var(--gkx-border);text-align:left;vertical-align:middle}.table-scroll th{position:sticky;z-index:1;top:0;background:var(--gkx-bg-subtle);white-space:nowrap}.table-scroll td:first-child{min-width:210px}.table-scroll strong,.table-scroll small,.table-scroll code{display:block}.table-scroll small,.table-scroll code{max-width:260px;margin-top:4px;overflow:hidden;color:var(--gkx-text-tertiary);font-size:10px;text-overflow:ellipsis;white-space:nowrap}.table-pagination{display:flex;justify-content:flex-end;padding:12px 16px;border-top:1px solid var(--gkx-border)}.table-scroll td.action-cell{padding-right:16px!important}.status{display:inline-flex;align-items:center;padding:2px 10px;border-radius:999px;font-size:11px;font-weight:500;white-space:nowrap}.status.is-pending_review{background:#e8f3ff;color:#004ecc}.status.is-pending_sync{background:#fff7e8;color:#b54708}.status.is-sync_failed{background:#fee4e2;color:#b42318}.status.is-completed{background:#dcfae6;color:#067647}.status.is-rejected,.status.is-cancelled{background:#f0f2f5;color:#5e6b7e}.actions{display:flex;flex-wrap:wrap;gap:7px;min-width:140px}.actions button{padding:0;border:0;background:transparent;color:var(--gkx-primary);font-size:11px;cursor:pointer}.actions button:disabled{color:var(--gkx-primary);cursor:not-allowed;opacity:.42}.empty{height:120px;text-align:center!important;color:var(--gkx-text-tertiary)}.form-grid,.query-form{display:grid;grid-template-columns:1fr 1fr;gap:14px}.form-grid label,.query-form label{display:grid;gap:6px}.form-grid label>span,.query-form label>span{color:var(--gkx-text-secondary);font-size:12px}.form-grid .wide,.query-form .wide{grid-column:1/-1}.modal-actions{display:flex;justify-content:flex-end;gap:8px;margin:20px -24px -24px;padding:16px 24px;border-top:1px solid var(--gkx-border)}.review-form{display:grid;gap:18px}.review-form p{display:grid;gap:4px;margin:0;padding:12px;background:var(--gkx-bg-subtle)}.review-form p span{color:var(--gkx-text-secondary);font-size:11px}.detail-content h3{margin-top:0}.flow-note{margin:0 0 18px;padding:10px 12px;background:var(--gkx-bg-subtle);color:var(--gkx-text-secondary);font-size:11px;line-height:1.6}.detail-content dl{display:grid;grid-template-columns:90px 1fr;gap:12px;margin:0}.detail-content dt{color:var(--gkx-text-secondary)}.detail-content dd{margin:0;min-width:0}.detail-content pre{max-height:240px;margin:0;padding:12px;overflow:auto;border-radius:4px;background:#f7f8fa;font:11px/1.6 Consolas,monospace}.detail-retry{margin-top:14px;padding:0;border:0;background:transparent;color:var(--gkx-primary);cursor:pointer}.operation-help{display:grid;gap:8px;margin:0;padding:0;list-style:none}.operation-help li{color:var(--gkx-text-secondary);font-size:11px}.operation-help strong{display:inline-block;width:48px;color:var(--gkx-text-primary);font-weight:500}.detail-content ol{display:grid;gap:10px;padding-left:20px}.detail-content li span{margin-left:8px;color:var(--gkx-text-tertiary);font-size:10px}.detail-content li p{margin:3px 0 0;color:var(--gkx-text-secondary);font-size:11px}@media(max-width:1000px){.summary-row{grid-template-columns:repeat(2,1fr)}}
.form-grid .form-field,.query-form .form-field{display:grid;gap:6px}.form-grid .form-field>span,.query-form .form-field>span{color:var(--gkx-text-secondary);font-size:12px}
</style>

<style scoped>
.table-scroll {
  background: var(--gkx-bg-subtle);
}
.table-scroll table {
  table-layout: fixed;
  min-width: 1200px;
  font-size: 14px !important;
}
.table-scroll tbody {
  background: #fff;
}
.table-scroll .col-content,
.table-scroll .col-target,
.table-scroll .col-sync,
.table-scroll .col-time { width: 12.5%; }
.table-scroll .col-operation,
.table-scroll .col-applicant,
.table-scroll .col-status { width: 11.3333%; }
.table-scroll .col-actions { width: 16%; }
.table-scroll th,
.table-scroll td {
  padding-right: 4px !important;
  padding-left: 4px !important;
  font-size: 14px !important;
  text-align: left !important;
}
.table-scroll td:first-child {
  min-width: 0;
}
.table-scroll th:first-child,
.table-scroll td:first-child {
  padding-left: 6px !important;
}
.record-title {
  display: block;
  overflow: hidden;
  font-weight: 400;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-cell {
  text-align: left;
}
.operation-cell {
  white-space: nowrap;
}
.target-cell,
.sync-cell {
  white-space: nowrap;
}
.time-cell {
  overflow: hidden;
  font-size: 14px !important;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.action-cell {
  overflow: visible;
}
.action-column-label,
.action-cell > .actions {
  display: inline-flex;
  transform: translateX(80px);
}
.actions {
  min-width: 0;
  flex-wrap: nowrap;
  gap: 1em;
  white-space: nowrap;
}
.actions button,
.actions .approve,
.actions .reject {
  color: var(--gkx-primary);
  font-size: 14px !important;
}
.correction-dialog-shell {
  display: flex;
  box-sizing: border-box;
  height: 560px;
  min-height: 0;
  flex-direction: column;
}
.correction-dialog-body {
  min-height: 0;
  padding-right: 2px;
  overflow-y: auto;
  flex: 1;
}
.form-grid :deep(.arco-input-wrapper),
.form-grid :deep(.arco-textarea-wrapper) {
  box-sizing: border-box;
  padding-inline: 0;
}
.form-grid :deep(.arco-input),
.form-grid :deep(.arco-textarea) {
  padding-inline: 12px;
}
.detail-content {
  padding: 0 1px;
}
:deep(.correction-select.arco-select-view) {
  box-sizing: border-box;
  width: 100%;
  height: 32px;
  min-height: 32px;
  padding: 0 12px;
  color: var(--gkx-text-primary);
  font: inherit;
  background: #fff !important;
  border: 1px solid #e5e6eb !important;
  border-radius: 4px;
  outline: none;
  cursor: pointer;
}
:deep(.correction-select.arco-select-view:hover),
:deep(.correction-select.arco-select-view-focus) {
  border-color: var(--gkx-primary) !important;
}
:deep(.correction-select.arco-select-view-disabled) {
  color: var(--gkx-text-tertiary);
  background: #fff !important;
  cursor: not-allowed;
  opacity: 1;
  -webkit-text-fill-color: var(--gkx-text-tertiary);
}
.query-keyword :deep(.arco-input-wrapper) {
  min-height: 32px;
  padding-inline: 0;
  border: 0 !important;
  border-bottom: 1px solid #e5e6eb !important;
  border-radius: 0;
  background: transparent !important;
  box-shadow: none !important;
}
.query-keyword :deep(.arco-input) {
  padding-inline: 2px 12px;
}
.query-keyword :deep(.arco-input-wrapper:hover),
.query-keyword :deep(.arco-input-wrapper-focus) {
  border-bottom-color: var(--gkx-primary) !important;
}
</style>
