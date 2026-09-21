<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { IconSearch } from '@arco-design/web-vue/es/icon'

import { deleteProductionReview, getExecution, getProductionReview, getProductionReviews, getTask, rerunExtractFailures, TRIGGER_SOURCE_LABEL, type ProcessingInstance, type ProductionReviewCase, type WorkflowExecution } from '../../api/workflowOperations'
import { clampSearchKeyword, SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import {
  extractCaseStatusBadge,
  type ReviewRecord,
} from './manual-review-data'

type CenterMode = 'review'

const props = defineProps<{ mode: CenterMode }>()
const route = useRoute()
const keyword = ref(clampSearchKeyword(String(route.query.keyword || '')))
/** 人工审核筛选：状态分组（待处理/已处理）与对象种类（实体/关系/都看）；C 类额外支持 重跑中 精确过滤。
 *  重跑仍失败的记录会重建为新待处理案（attempt+1），不存在「重跑失败」状态，故不提供该筛选项。
 *  undefined = 未选择（清空），语义等同「全部」。 */
const reviewStatusFilter = ref<'全部' | '待处理' | '已处理' | '重跑中' | undefined>('全部')
const reviewKindFilter = ref<'全部' | '实体' | '关系' | undefined>('全部')
/** 时间过滤（按更新时间）：全部/近1小时/近24小时/近7天/近30天 → updatedWithin 查询参数。 */
const reviewTimeFilter = ref<'全部' | '近1小时' | '近24小时' | '近7天' | '近30天' | undefined>('全部')
const reviewTimeOptions = ['全部', '近1小时', '近24小时', '近7天', '近30天']
const REVIEW_TIME_PARAMS: Record<string, string | undefined> = { '全部': undefined, '近1小时': '1h', '近24小时': '24h', '近7天': '7d', '近30天': '30d' }
/** 更新时间排序：default=风险+创建时间（默认）；desc=新→旧；asc=旧→新。 */
const reviewTimeSort = ref<'default' | 'desc' | 'asc'>('default')
const reviewTotal = ref(0)
/** 队列行 = manual-review-data 的 ReviewRecord + 重跑/删除/跳转所需的原始字段。 */
type ReviewRow = ReviewRecord & { templateId?: string; rawStatus?: string; jobId?: string }

/** 可重跑/可删除：与后端 rerun 门控同口径（未处理）。 */
const isRerunnable = (row: ReviewRow) => row.rawStatus === 'OPEN' || row.rawStatus === 'RERUN_FAILED'

/** 类型列：objectType（entity/relation）→ 实体/关系；T_LINK 是实体对齐，恒实体。 */
function rowKindLabel(row: ReviewRow): string {
  if (row.templateId === 'T_LINK' || row.objectType === 'entity') return '实体'
  if (row.objectType === 'relation') return '关系'
  return '—'
}
const reviewRecords = ref<ReviewRow[]>([])
const reviewLoadError = ref('')
const reviewLoading = ref(true)
let reviewRequestId = 0
let reviewDisposed = false

const reviewRows = computed(() => reviewRecords.value)

/** 分页状态：服务端分页，翻页/改页大小都会重新拉取当前筛选下的数据。
 *  默认每页 20：表格区可视高度约 13~14 行，10 行填不满会在面板内留大片空白。 */
const reviewPage = ref(1)
const reviewPageSize = ref(20)
const reviewPageSizeOptions = [10, 20, 50]
const reviewTotalPages = computed(() => Math.max(1, Math.ceil(reviewTotal.value / reviewPageSize.value)))

watch(() => route.query.keyword, (value) => { keyword.value = clampSearchKeyword(String(value || '')) })

/** 审核队列分类：A=入库决策（Tab 只筛 T_LINK 实体对齐，T_DIRECT 详情由工作台总览/实例详情直达）；C=抽取失败重跑（T_EXTRACT_FAIL）。
 *  支持 ?category=A|C 深链初始定位子页（工作台总览的「抽取失败重跑」卡片直达 C 子页）。 */
const reviewCategory = ref<'A' | 'C'>(route.query.category === 'C' ? 'C' : 'A')
/** C 类勾选的待重跑 case。 */
const rerunSelection = ref<Set<string>>(new Set())
const rerunSubmitting = ref(false)
/** 批量重跑结果反馈（替代 alert）：展示新执行可跳转链接，15s 自动消失；warning=部分 schema 被跳过。 */
const rerunFeedback = ref<{ type: 'success' | 'warning' | 'error'; text: string; executions: Array<{ executionId: string; schemaId: string; cases: number; records: number }> } | null>(null)
/** 勾选 >20 条时的 a-modal 二次确认。 */
const rerunConfirmVisible = ref(false)
let rerunFeedbackTimer: number | undefined

/** A 类只有 全部/待处理/已处理；C 类追加 重跑中（后端 status 精确过滤）。 */
const reviewStatusOptions = computed(() => (
  reviewCategory.value === 'C'
    ? ['全部', '待处理', '已处理', '重跑中']
    : ['全部', '待处理', '已处理']
))

/** 当前页可重跑行的全选/半选态（跨页勾选由 rerunSelection 保持，按钮数字展示总数）。 */
const rerunPageEligibleIds = computed(() => reviewRows.value.filter(isRerunnable).map((row) => row.id))
const rerunAllChecked = computed(() => rerunPageEligibleIds.value.length > 0 && rerunPageEligibleIds.value.every((id) => rerunSelection.value.has(id)))
const rerunSomeChecked = computed(() => !rerunAllChecked.value && rerunPageEligibleIds.value.some((id) => rerunSelection.value.has(id)))

function switchReviewCategory(category: 'A' | 'C') {
  if (reviewCategory.value === category) return
  reviewCategory.value = category
  rerunSelection.value = new Set()
  reviewPage.value = 1
  void loadReviews()
}

function toggleRerunPick(id: string, checked: boolean) {
  if (checked) rerunSelection.value.add(id)
  else rerunSelection.value.delete(id)
}

/** 表头全选/取消：只作用于当前页可重跑行（不可重跑行禁用不勾选）；跨页勾选保持，按钮数字展示总数。 */
function toggleRerunPickAll(event: Event) {
  const checked = (event.target as HTMLInputElement).checked
  for (const id of rerunPageEligibleIds.value) toggleRerunPick(id, checked)
}

function showRerunFeedback(type: 'success' | 'warning' | 'error', text: string, executions: Array<{ executionId: string; schemaId: string; cases: number; records: number }>) {
  rerunFeedback.value = { type, text, executions }
  window.clearTimeout(rerunFeedbackTimer)
  rerunFeedbackTimer = window.setTimeout(() => { rerunFeedback.value = null }, 15000)
}

async function rerunSelected(caseIds: string[] | undefined = undefined, skipConfirm = false) {
  const ids = caseIds ?? [...rerunSelection.value]
  if (!ids.length || rerunSubmitting.value) return
  if (!skipConfirm && ids.length > 20) {
    rerunConfirmVisible.value = true
    return
  }
  rerunSubmitting.value = true
  try {
    const result = await rerunExtractFailures({ caseIds: ids })
    // 部分 schema 校验失败被跳过（已删/不在当前控制面）：黄条提示，其余已正常下发
    const skipped = result.skipped ?? []
    const skippedText = skipped.length
      ? `；跳过 ${skipped.reduce((n, s) => n + s.cases, 0)} 条（${skipped.map((s) => `${s.schemaKey || s.schemaId}×${s.cases}`).join('、')}：Schema 不在当前控制面或已删除）`
      : ''
    showRerunFeedback(
      skipped.length ? 'warning' : 'success',
      `已下发重跑：${result.cases} 条失败记录 → ${result.executions.length} 个新执行（类别=重新执行）${skippedText}`,
      result.executions,
    )
    rerunSelection.value = new Set()
    void loadReviews()
  } catch (error) {
    showRerunFeedback('error', error instanceof Error ? error.message : '重跑下发失败', [])
  } finally {
    rerunSubmitting.value = false
  }
}

// ---- C 类操作列：日志弹窗（工作流执行日志）/ 删除 ----

/** 日志弹窗：按 case 关联的抽取工作流执行（重跑执行优先）拉 getExecution + 任务(PI-) logs，
 *  展示执行概要/阶段状态/任务执行日志；旧的 case 审计时间线等内容不再展示。 */
const logVisible = ref(false)
const logLoading = ref(false)
const logError = ref('')
const logCase = ref<ProductionReviewCase>()
const logExecution = ref<WorkflowExecution | null>(null)
const logTask = ref<ProcessingInstance | null>(null)
const logExecutionMissing = ref(false)
/** 当前展示哪个执行：rerun=重跑执行（最新一次处理）；original=原执行。 */
const logExecutionChoice = ref<'rerun' | 'original'>('rerun')

const logInput = computed<Record<string, unknown>>(() =>
  ((logCase.value?.data?.input || logCase.value?.input || {}) as Record<string, unknown>))
const logOriginalExecutionId = computed(() => String(logInput.value.executionId ?? ''))
const logRerunExecutionId = computed(() => String(logInput.value.rerunExecutionId ?? ''))
const logActiveExecutionId = computed(() =>
  logExecutionChoice.value === 'rerun' && logRerunExecutionId.value ? logRerunExecutionId.value : logOriginalExecutionId.value)

/** 抽取执行 output 汇总（kg.schema.extract）：写入/失败计数（多来源求和）。 */
const logExtractSummary = computed(() => {
  const output = logExecution.value?.output as Record<string, unknown> | null | undefined
  if (!output || typeof output !== 'object') return null
  const sources = Array.isArray(output.sources) ? (output.sources as Array<Record<string, unknown>>) : []
  const written = sources.reduce((sum, item) => sum + Number(item.written || 0), 0)
  const failed = Number((output.failures as Record<string, unknown> | undefined)?.count ?? 0)
  if (!sources.length && !failed) return null
  return { written, failed, sourceCount: sources.length }
})

/** 执行日志行：任务 logs 数组优先；无任务记录时退回执行 message 单行。 */
const logLines = computed<string[]>(() => {
  const lines = logTask.value?.logs
  if (Array.isArray(lines) && lines.length) return lines.map(String)
  const message = logExecution.value?.message
  return message ? [message] : []
})

async function loadExecutionLog(executionId: string) {
  logExecution.value = null
  logTask.value = null
  logExecutionMissing.value = false
  if (!executionId) {
    logExecutionMissing.value = true
    return
  }
  try {
    const execution = await getExecution(executionId)
    logExecution.value = execution ?? null
    if (!execution) logExecutionMissing.value = true
    else if (execution.taskId) {
      // 任务（PI-）记录携带工作流执行日志数组与阶段回写 steps
      try { logTask.value = await getTask(execution.taskId) } catch { logTask.value = null }
    }
  } catch {
    logExecution.value = null
    logExecutionMissing.value = true
  }
}

async function openLog(row: ReviewRow) {
  logVisible.value = true
  logLoading.value = true
  logError.value = ''
  logCase.value = undefined
  logExecution.value = null
  logTask.value = null
  try {
    logCase.value = await getProductionReview(row.id)
    // 重跑执行优先展示（最新一次对该记录的处理）；无重跑则展示原执行
    logExecutionChoice.value = logRerunExecutionId.value ? 'rerun' : 'original'
    await loadExecutionLog(logActiveExecutionId.value)
  } catch (error) {
    logError.value = error instanceof Error ? error.message : '日志加载失败'
  } finally {
    logLoading.value = false
  }
}

/** 切换 原执行/重跑执行 视图。 */
function switchLogExecution(choice: 'rerun' | 'original') {
  if (choice === logExecutionChoice.value) return
  logExecutionChoice.value = choice
  void loadExecutionLog(logActiveExecutionId.value)
}

/** 删除：二次确认后物理删除（仅未处理可删，与重跑同门控）。 */
const deleteTarget = ref<ReviewRow>()
const deleteVisible = ref(false)
const deleteSubmitting = ref(false)
const deleteError = ref('')

function askDelete(row: ReviewRow) {
  deleteTarget.value = row
  deleteError.value = ''
  deleteVisible.value = true
}

async function confirmDelete() {
  const target = deleteTarget.value
  if (!target || deleteSubmitting.value) return
  deleteSubmitting.value = true
  try {
    await deleteProductionReview(target.id)
    deleteVisible.value = false
    rerunSelection.value.delete(target.id)
    showRerunFeedback('success', `已删除失败记录 ${target.id}`, [])
    void loadReviews()
  } catch (error) {
    deleteError.value = error instanceof Error ? error.message : '删除失败'
  } finally {
    deleteSubmitting.value = false
  }
}

onUnmounted(() => {
  reviewDisposed = true
  reviewRequestId += 1
  window.clearTimeout(reviewKeywordTimer)
  window.clearTimeout(rerunFeedbackTimer)
})

async function loadReviews() {
  if (props.mode !== 'review' || reviewDisposed) return
  const requestId = ++reviewRequestId
  reviewLoading.value = true
  reviewLoadError.value = ''
  reviewRecords.value = []
  reviewTotal.value = 0
  try {
    // A=入库决策：Tab 只筛 T_LINK（实体对齐裁决）——T_DIRECT case 不进队列，
    // 详情由工作台总览/处理实例详情直达；C=抽取失败重跑（T_EXTRACT_FAIL）
    const response = await getProductionReviews({
      category: reviewCategory.value,
      templateId: reviewCategory.value === 'A' ? 'T_LINK' : undefined,
      keyword: keyword.value || undefined,
      statusGroup: reviewStatusFilter.value === '待处理' ? 'pending' : reviewStatusFilter.value === '已处理' ? 'processed' : undefined,
      status: reviewStatusFilter.value === '重跑中' ? 'RERUNNING' : undefined,
      kind: !reviewKindFilter.value || reviewKindFilter.value === '全部' ? undefined : reviewKindFilter.value === '实体' ? 'entity' : 'relation',
      updatedWithin: REVIEW_TIME_PARAMS[reviewTimeFilter.value || '全部'],
      sort: reviewTimeSort.value === 'default' ? undefined : `updated_${reviewTimeSort.value}`,
      page: reviewPage.value,
      pageSize: reviewPageSize.value,
    })
    if (reviewDisposed || requestId !== reviewRequestId) return
    reviewTotal.value = response.total
    // 筛选后总页数变小时收敛当前页（如翻到第 3 页后把筛选改成只有 1 页数据）
    if (reviewPage.value > Math.max(1, Math.ceil(response.total / reviewPageSize.value))) {
      reviewPage.value = Math.max(1, Math.ceil(response.total / reviewPageSize.value))
      return loadReviews()
    }
    reviewRecords.value = response.items.map((row: ProductionReviewCase) => ({
      id: row.id, templateId: row.templateId, rawStatus: row.status, jobId: row.jobId || '', batch: row.batchId || '-', module: row.phase, node: row.nodeId, type: row.errorType, category: row.category, domain: row.domain, objectType: row.objectType, objectId: row.objectId, object: row.objectName, ruleId: row.templateId, evidence: `${row.evidence?.length || 0} 项`, score: row.riskLevel, handler: row.assigneeName || '待处理', status: extractCaseStatusBadge(row.status), updatedAt: fmtReviewTime(row.updatedAt), sourceResult: row.diagnosis, suggestion: row.scope, sourceTable: row.sourceTable || '-', sourceRecordId: row.sourceRecordId || '-', confidenceValue: row.riskLevel, confidenceLabel: row.status,
    }))
    reviewLoadError.value = ''
  } catch (error) {
    if (reviewDisposed || requestId !== reviewRequestId) return
    reviewLoadError.value = error instanceof Error ? error.message : '人工处理队列加载失败'
  } finally {
    if (!reviewDisposed && requestId === reviewRequestId) reviewLoading.value = false
  }
}

/** 后端 ISO 时间（2026-09-17T09:30:00）转界面习惯的 2026-09-17 09:30:00。 */
function fmtReviewTime(value?: string): string {
  if (!value) return ''
  return value.replace('T', ' ').slice(0, 19)
}

function changeReviewPage(page: number) {
  if (page === reviewPage.value) return
  reviewPage.value = page
  void loadReviews()
}

function changeReviewPageSize(size: unknown) {
  const value = Number(size)
  if (!Number.isFinite(value) || value <= 0 || value === reviewPageSize.value) return
  reviewPageSize.value = value
  reviewPage.value = 1
  void loadReviews()
}

/** 更新时间表头排序：三态循环 默认 → 新→旧 → 旧→新 → 默认。 */
function toggleReviewTimeSort() {
  reviewTimeSort.value = reviewTimeSort.value === 'default' ? 'desc' : reviewTimeSort.value === 'desc' ? 'asc' : 'default'
  reviewPage.value = 1
  void loadReviews()
}

/** 筛选条件变化：保留当前页重新加载；总页数收缩、当前页超出时由 loadReviews 收敛到最后有效页（FUNC-00781）。 */
watch([reviewStatusFilter, reviewKindFilter, reviewTimeFilter], () => {
  if (props.mode !== 'review') return
  void loadReviews()
})

/** 关键字输入防抖后走服务端检索（与分页/筛选同口径，避免页内客户端过滤与总数不一致）；页码同样保留+收敛。 */
let reviewKeywordTimer: number | undefined
watch(keyword, () => {
  if (props.mode !== 'review') return
  window.clearTimeout(reviewKeywordTimer)
  reviewKeywordTimer = window.setTimeout(() => {
    void loadReviews()
  }, 300)
})
onMounted(loadReviews)
</script>

<template>
  <div class="ops-page">
    <div v-if="mode === 'review'" class="alert-tabs review-tabs">
      <nav>
        <button type="button" :class="{ active: reviewCategory === 'A' }" @click="switchReviewCategory('A')">入库决策</button>
        <button type="button" :class="{ active: reviewCategory === 'C' }" @click="switchReviewCategory('C')">抽取失败重跑</button>
      </nav>
      <div class="review-toolbar-actions">
        <div class="ops-filter is-review review-filter-row">
          <div class="review-filter-field">
            <span class="review-filter-label">状态</span>
            <a-select v-model="reviewStatusFilter" class="review-filter-select" :options="reviewStatusOptions" />
          </div>
          <div class="review-filter-field">
            <span class="review-filter-label">类型</span>
            <a-select v-model="reviewKindFilter" class="review-filter-select" :options="['全部', '实体', '关系']" />
          </div>
          <div class="review-filter-field">
            <span class="review-filter-label">时间</span>
            <a-select v-model="reviewTimeFilter" class="review-filter-select" :options="reviewTimeOptions" />
          </div>
          <a-input v-model="keyword" class="review-search-input review-filter-search" :max-length="SEARCH_KEYWORD_MAX_LENGTH" aria-label="搜索处理实例 ID、对象或来源记录" placeholder="搜索处理实例 ID、对象或来源记录"><template #prefix><IconSearch /></template></a-input>
        </div>
      </div>
    </div>

    <!-- 批量重跑：单独一行右对齐（不挤在筛选栏里） -->
    <div v-if="reviewCategory === 'C'" class="rerun-batch-row">
      <button
        class="rerun-batch-action"
        type="button"
        :disabled="!rerunSelection.size || rerunSubmitting"
        @click="rerunSelected()"
      >{{ rerunSubmitting ? '下发中…' : `批量重跑（${rerunSelection.size}）` }}</button>
    </div>

    <section class="ops-panel">

      <div v-if="rerunFeedback" :class="['rerun-feedback', `is-${rerunFeedback.type}`]">
        <span>{{ rerunFeedback.text }}</span>
        <RouterLink
          v-for="item in rerunFeedback.executions"
          :key="item.executionId"
          class="link"
          :to="`/processing-instance/${item.executionId}`"
        >{{ item.schemaId }} · {{ item.cases }} 条</RouterLink>
        <button class="rerun-feedback-close" type="button" @click="rerunFeedback = null">×</button>
      </div>

      <div class="ops-review-table-scroll" :aria-busy="reviewLoading"><table class="review-case-table" :class="{ 'review-case-table--selectable': reviewCategory === 'C' }">
        <!-- 固定列宽：有数据/无数据切换时表头列位不漂移（待处理对象列吃剩余宽度） -->
        <colgroup>
          <col v-if="reviewCategory === 'C'" class="col-pick" />
          <col class="col-id" />
          <col class="col-object" />
          <col class="col-kind" />
          <col class="col-source" />
          <col class="col-status" />
          <col class="col-time" />
          <col class="col-actions" />
        </colgroup>
        <thead>
          <tr>
            <th v-if="reviewCategory === 'C'" class="pick-col"><input aria-label="checkbox-input"
              type="checkbox"
              :checked="rerunAllChecked"
              :indeterminate="rerunSomeChecked"
              @change="toggleRerunPickAll"
            /></th>
            <th>处理实例 ID</th>
            <th>待处理对象</th>
            <th>类型</th>
            <th>来源记录</th>
            <th>状态</th>
            <th class="th-time-sort" :class="{ 'is-active': reviewTimeSort !== 'default' }" title="按更新时间排序" @click="toggleReviewTimeSort">更新时间<span class="sort-arrow">{{ reviewTimeSort === 'desc' ? '↓' : reviewTimeSort === 'asc' ? '↑' : '↕' }}</span></th>
            <th class="review-action-col">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in reviewRows" :key="row.id">
            <td v-if="reviewCategory === 'C'" class="pick-col"><input aria-label="checkbox-input"
              type="checkbox"
              :disabled="!isRerunnable(row)"
              :checked="rerunSelection.has(row.id)"
              @change="((event?: Event) => toggleRerunPick(row.id, Boolean((event?.target as HTMLInputElement)?.checked)))"
            /></td>
            <td class="review-id-cell"><code class="review-id-plain" :title="row.id">{{ row.id }}</code></td>
            <td class="review-object-cell">
              <strong>{{ row.object || '—' }}</strong>
            </td>
            <td><span :class="['review-kind-badge', `is-${rowKindLabel(row)}`]">{{ rowKindLabel(row) }}</span></td>
            <td class="review-id-cell">
              <!-- 来源记录：统一 job 维度，跳图谱构建任务详情（含执行历史）；
                   无 jobId 的存量 case 不再回落 EXEC 执行链接（后端已按执行兜底解析 job） -->
              <RouterLink v-if="row.jobId" class="link" :to="`/graph-build/jobs/${row.jobId}`">{{ row.jobId }}</RouterLink>
              <template v-else>—</template>
            </td>
            <td><span :class="['review-status', `is-${row.status}`]">{{ row.status }}</span></td>
            <td>{{ row.completedAt || row.updatedAt }}</td>
            <td class="review-action-col">
              <div v-if="reviewCategory === 'A'" class="alert-actions">
                <RouterLink class="link" :to="`/manual-review/task/${row.id}`">查看记录 →</RouterLink>
              </div>
              <div v-else class="alert-actions">
                <button class="link rerun-link" type="button" @click="openLog(row)">日志</button>
                <button
                  v-if="isRerunnable(row)"
                  class="link rerun-link"
                  type="button"
                  :disabled="rerunSubmitting"
                  @click="rerunSelected([row.id])"
                >重跑</button>
                <button
                  v-if="isRerunnable(row)"
                  class="link rerun-link is-danger"
                  type="button"
                  :disabled="deleteSubmitting"
                  @click="askDelete(row)"
                >删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="!reviewRows.length">
            <td class="review-empty" :colspan="reviewCategory === 'C' ? 8 : 7">
              <span v-if="reviewLoading" role="status">正在加载人工审核记录…</span>
              <div v-else-if="reviewLoadError" role="alert">
                <p>{{ reviewLoadError }}</p>
                <button type="button" class="link" @click="loadReviews">重新加载</button>
              </div>
              <span v-else>{{ reviewStatusFilter === '全部' && reviewKindFilter === '全部' && reviewTimeFilter === '全部' && !keyword ? '暂无人工处理记录' : '暂无符合条件的记录' }}</span>
            </td>
          </tr>
        </tbody>
      </table></div>

      <footer v-if="!reviewLoading && !reviewLoadError" class="review-pagination">
        <span>共 {{ reviewTotal }} 条 · 第 {{ reviewPage }} / {{ reviewTotalPages }} 页</span>
        <span class="review-page-size">每页
          <a-select class="review-page-size-select" :model-value="reviewPageSize" :options="reviewPageSizeOptions" :scrollbar="false" @change="changeReviewPageSize" />
        </span>
        <a-pagination
          :current="reviewPage"
          :page-size="reviewPageSize"
          :total="reviewTotal"
          :show-jumper="reviewTotalPages > 7"
          @change="changeReviewPage"
        />
      </footer>
    </section>

    <a-modal
      v-model:visible="rerunConfirmVisible"
      modal-class="rerun-confirm-modal"
      title="确认批量重跑"
      :width="560"
      ok-text="下发重跑"
      cancel-text="取消"
      :ok-loading="rerunSubmitting"
      @ok="rerunSelected(undefined, true)"
    >
      <p class="rerun-confirm-text">即将对已勾选的 {{ rerunSelection.size }} 条失败记录下发重跑，按 schema 合并为新执行（类别=重新执行）。重跑成功的记录自动关闭，仍失败的会重新进入失败列表。</p>
    </a-modal>

    <a-modal
      v-model:visible="logVisible"
      modal-class="case-log-modal"
      :title="`执行日志 · ${logCase?.id || ''}`"
      :width="760"
      :footer="false"
    >
      <p v-if="logLoading" class="case-log-loading">加载中…</p>
      <p v-else-if="logError" class="case-log-error-text">{{ logError }}</p>
      <template v-else-if="logCase">
        <!-- 原执行/重跑执行切换（两者都有时才显示；默认看重跑执行=最新一次处理） -->
        <div v-if="logRerunExecutionId && logOriginalExecutionId" class="case-log-switch">
          <button type="button" :class="{ active: logExecutionChoice === 'rerun' }" @click="switchLogExecution('rerun')">重跑执行</button>
          <button type="button" :class="{ active: logExecutionChoice === 'original' }" @click="switchLogExecution('original')">原执行</button>
        </div>
        <p v-if="logExecutionMissing" class="case-log-missing">未找到关联的工作流执行记录（{{ logActiveExecutionId || '该记录未关联执行 ID' }}）——执行记录可能已随环境重置被清理。</p>
        <template v-else-if="logExecution">
          <section class="case-log-sec">
            <h4>执行概要</h4>
            <dl class="case-log-dl">
              <div><dt>执行 ID</dt><dd><RouterLink class="link" :to="`/processing-instance/${logExecution.id}`"><code>{{ logExecution.id }}</code></RouterLink></dd></div>
              <div><dt>触发方式</dt><dd>{{ TRIGGER_SOURCE_LABEL[logExecution.triggerSource || 'MANUAL'] || logExecution.triggerSource || '—' }}</dd></div>
              <div><dt>状态</dt><dd>{{ logExecution.status }}</dd></div>
              <div><dt>开始时间</dt><dd>{{ logExecution.startedAt || '—' }}</dd></div>
              <div><dt>完成时间</dt><dd>{{ logExecution.completedAt || '—' }}</dd></div>
              <div v-if="logExtractSummary"><dt>抽取结果</dt><dd>写入 {{ logExtractSummary.written }} · 失败 {{ logExtractSummary.failed }}（{{ logExtractSummary.sourceCount }} 个来源）</dd></div>
            </dl>
          </section>
          <section v-if="logTask && logTask.steps.length" class="case-log-sec">
            <h4>阶段状态</h4>
            <ul class="case-log-steps">
              <li v-for="step in logTask.steps" :key="step.id">
                <span class="case-log-step-name">{{ step.name }}</span>
                <span :class="['case-log-step-status', `is-${step.status}`]">{{ step.status }}</span>
              </li>
            </ul>
          </section>
          <section class="case-log-sec">
            <h4>执行日志</h4>
            <pre v-if="logLines.length" class="case-log-console">{{ logLines.join('\n') }}</pre>
            <p v-else class="case-log-empty">该执行暂无任务日志。</p>
          </section>
        </template>
        <p v-else class="case-log-missing">该记录未关联工作流执行（无 executionId），无法展示执行日志。</p>
      </template>
    </a-modal>

    <a-modal
      v-model:visible="deleteVisible"
      modal-class="rerun-confirm-modal"
      title="确认删除"
      :width="560"
      ok-text="删除"
      cancel-text="取消"
      :ok-loading="deleteSubmitting"
      @ok="confirmDelete"
    >
      <p class="rerun-confirm-text">即将物理删除失败记录 <code>{{ deleteTarget?.id }}</code>（{{ deleteTarget?.object }}），连同其草稿/决议/审计一并清除，不可恢复。仅未处理记录可删除。</p>
      <p v-if="deleteError" class="case-log-error-text">{{ deleteError }}</p>
    </a-modal>
  </div>
</template>

<style scoped>
.ops-page{height:100%;overflow:auto;padding-bottom:2px;color:#16233b}.ops-panel{overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:rgba(255,255,255,.94);box-shadow:0 12px 28px rgba(48,105,194,.1)}.ops-filter{display:grid;grid-template-columns:minmax(260px,1fr) repeat(3,160px) auto;gap:10px;padding:14px;border-bottom:1px solid #dce9ff;background:#f7fbff}.ops-filter input,.ops-filter select{height:34px;padding:0 10px;border:1px solid #bdd7ff;border-radius:6px;background:#fff;color:#273957}table{width:100%;border-collapse:collapse;font-size:13px}th,td{height:52px;padding:10px 14px;border-bottom:1px solid #e5edf8;text-align:left;white-space:nowrap}th{position:sticky;z-index:2;top:0;background:#f4f8fd;color:#5a6c88;font-weight:600}td{color:#273957}td small{display:block;margin-top:4px;color:#7b89a1}.alert-actions{display:grid;gap:5px}.alert-tabs{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 14px;border-bottom:1px solid #dce9ff}.alert-tabs nav{display:flex;overflow:auto}.alert-tabs button{padding:13px 14px;border:0;border-bottom:2px solid transparent;background:transparent;color:#52647f;white-space:nowrap;cursor:pointer}.alert-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.alert-tabs label{color:#5f6f88;font-size:12px;white-space:nowrap}.alert-tabs input{margin-right:6px}td a,.link{border:0;background:transparent;color:#165dff;cursor:pointer;text-decoration:none}@media(max-width:1100px){.ops-filter{grid-template-columns:1fr 1fr}.ops-panel{overflow:hidden}}
.review-context{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;padding:12px 14px;border:1px solid #b2ccff;border-radius:7px;background:#f0f5ff}.review-context div{display:grid;gap:3px}.review-context strong{font-size:13px}.review-context span{color:#65738b;font-size:11px}.review-context a{color:#165dff;font-size:12px;text-decoration:none;white-space:nowrap}
.review-evidence{min-width:260px;max-width:360px;white-space:normal;line-height:19px}.review-status{display:inline-flex;padding:3px 8px;border-radius:10px;background:#edf2f7;color:#52647f}.review-status.is-待处理{background:#fff0e8;color:#c4320a}.review-status.is-已完成{background:#e9f8ef;color:#067647}
.link-disabled{color:#98a2b3;font-size:12px;cursor:default}
.pick-col{width:36px;text-align:center}.pick-col input{cursor:pointer}
.rerun-link{padding:0;font-size:12px;border:0;background:transparent}
.review-severity{min-width:230px;max-width:300px;white-space:normal}.review-severity small{margin:0 0 6px}.review-severity span{display:block;color:#65738b;font-size:11px;line-height:17px}
.review-mask{position:fixed;z-index:49;inset:0;border:0;background:rgba(16,36,76,.24)}.review-drawer{position:fixed;z-index:50;top:0;right:0;display:grid;grid-template-rows:auto minmax(0,1fr) auto;width:620px;height:100vh;background:#f8fbff;box-shadow:-18px 0 42px rgba(34,74,132,.22)}.review-drawer>header{display:flex;justify-content:space-between;padding:20px;border-bottom:1px solid #dce8f8;background:#fff}.review-drawer header span{color:#165dff;font-size:11px}.review-drawer h2{margin:6px 0 3px;font-size:19px}.review-drawer header p{margin:0;color:#70809a;font-size:12px}.review-drawer header>button{width:30px;height:30px;border:0;border-radius:5px;background:#f0f4fa;font-size:20px;cursor:pointer}.review-body{overflow:auto;padding:16px}.review-body section,.review-compare article{padding:14px;border:1px solid #dce8f8;border-radius:7px;background:#fff}.review-body h3{margin:0 0 8px;font-size:14px}.review-body p,.review-body li{color:#61708a;font-size:12px;line-height:20px}.review-compare{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.review-compare span{display:block;margin-bottom:9px;color:#70809a;font-size:11px}.review-compare strong{font-size:13px}.review-compare em{color:#d92d20;font-size:11px;font-style:normal}.review-compare input,.review-compare textarea{width:100%;padding:8px;border:1px solid #bdd0ea;border-radius:5px;font:inherit}.review-compare textarea{min-height:90px;margin-top:8px;resize:vertical}.review-success{padding:10px 12px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3!important;color:#067647!important}.review-drawer>footer{display:flex;justify-content:flex-end;gap:8px;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.review-drawer>footer button{height:34px;padding:0 13px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;cursor:pointer}.review-drawer>footer .primary{border-color:#165dff;background:#165dff;color:#fff}@media(max-width:720px){.review-drawer{width:94vw}.review-compare{grid-template-columns:1fr}}
.ops-page{display:flex;box-sizing:border-box;min-height:0;overflow:hidden;padding-bottom:2px;flex-direction:column}.review-context{flex:0 0 auto}.ops-panel{display:flex;flex:1;min-height:0;flex-direction:column}.alert-tabs,.ops-filter,.review-pagination{flex:0 0 auto}.ops-review-table-scroll{flex:1;min-height:0;max-height:none;overflow:auto}.ops-filter.is-review{grid-template-columns:minmax(280px,1fr) 170px 170px auto}.ops-review-table-scroll table{min-width:1900px}.review-pagination{display:flex;align-items:center;gap:14px;padding:11px 14px;border-top:1px solid #e4ecf6;background:#fff;color:#71809a;font-size:11px}.review-pagination>span{white-space:nowrap}.review-pagination .review-page-size{display:flex;align-items:center;gap:6px;margin-left:auto;white-space:nowrap}.review-pagination :deep(.arco-select){width:76px}.review-pagination :deep(.arco-select-view){box-sizing:border-box;width:76px;height:28px;border:1px solid #d3deee;border-radius:4px;background:#fff}.review-empty{height:100px!important;color:#8290a7;text-align:center!important}.ops-review-table-scroll td code{color:#175cd3;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.review-type-cell{min-width:170px}.review-type-cell>span{display:inline-flex;padding:3px 9px;border-radius:99px;background:#eaf2ff;color:#175cd3;font-size:11px}.review-type-cell>span.is-low-confidence{background:#fff3d8;color:#b54708}.review-type-cell>span.is-extraction{background:#fef3f2;color:#b42318}.review-type-cell>span.is-schema{background:#edf0ff;color:#444ce7}.review-type-cell>span.is-normalization{background:#ecfdf3;color:#067647}.review-type-cell>span.is-other{background:#f2f4f7;color:#475467}
.ops-review-table-scroll table{min-width:1900px}.review-risk-explain{display:grid;flex:0 0 auto;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}.review-risk-explain>div{display:grid;gap:3px;padding:11px 14px;border:1px solid #b9d2f4;border-radius:7px;background:#f7fbff}.review-risk-explain strong{color:#344861;font-size:11px}.review-risk-explain span{color:#6d7c93;font-size:9px;line-height:16px}.review-confidence-cell{min-width:190px;white-space:normal}.review-confidence-cell>b{display:inline-block;margin-right:7px;font-size:13px}.review-confidence-cell>small{display:inline;color:#718098}.review-confidence-cell>span{display:block;margin-top:4px;color:#78869b;font-size:9px;line-height:15px}@media(max-width:900px){.review-risk-explain{grid-template-columns:1fr}}
.review-risk-explain{grid-template-columns:repeat(2,minmax(0,1fr))}.review-risk-explain>div:first-child{border-color:#f5b8b3;background:#fff5f4}.review-risk-explain>div:first-child strong{color:#d92d20}.review-risk-explain>div:nth-child(2){border-color:#f3d08a;background:#fffaf0}.review-risk-explain>div:nth-child(2) strong{color:#b54708}.review-type{min-width:150px}.review-confidence-cell{min-width:130px}.review-confidence-cell>em{display:block;width:max-content;margin-top:5px;padding:2px 7px;border-radius:9px;background:#fff3d8;color:#b54708;font-size:9px;font-style:normal}
.ops-review-table-scroll table{min-width:1280px}
.review-id-cell{min-width:150px;white-space:nowrap}
.review-id-cell .link{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
.review-source-cell{min-width:160px}
.review-source-cell strong{display:block;font-size:12px;font-weight:600}
.review-source-cell small{margin-top:4px}
.ops-filter.is-review{grid-template-columns:minmax(240px,1fr) 160px 160px auto}
.review-type-cell>span.is-align{background:#f0ebff;color:#6938ef}
.review-type-cell>span.is-relation{background:#fff3d8;color:#b54708}
.review-subtype{display:block!important;margin-top:5px!important;color:#7b89a1;font-size:10px;white-space:nowrap}
.review-question-cell{min-width:220px;max-width:320px;white-space:normal}
.review-question-cell strong{display:block;font-size:12px;font-weight:600;line-height:18px}
.review-question-cell small{margin-top:4px;color:#165dff}
.scope-batch{color:#b42318!important}
.scope-task{color:#175cd3!important}
.review-status.is-已撤销{background:#f2f4f7;color:#475467}
.review-status.is-已驳回{background:#f2f4f7;color:#b42318}
</style>
<style scoped>
/* DESIGN_RULES: manual review list contract. */
.ops-page{padding:0;color:#1d2129}
.ops-panel{border-color:#e5e6eb;border-radius:6px;background:#fff;box-shadow:none}
.ops-filter,.ops-filter.is-review{box-sizing:border-box;width:100%;grid-template-columns:minmax(280px,1fr) minmax(160px,200px) minmax(160px,200px) auto;column-gap:16px!important;row-gap:16px!important;padding:16px!important;background:#fff}
.alert-tabs nav button{height:36px;padding:0 16px;font-size:14px;line-height:22px}.alert-tabs nav button.active{font-weight:500}
.ops-filter input,.ops-filter select,.ops-filter button{height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px}.ops-filter button{padding:0 16px}
.ops-review-table-scroll table{min-width:1280px;font-size:14px;line-height:22px}.ops-review-table-scroll th,.ops-review-table-scroll td{height:40px;padding:0 16px}.ops-review-table-scroll th{background:#f7f8fa;color:#1d2129;font-weight:500}
.ops-review-table-scroll td small,.review-source-cell strong,.review-question-cell strong,.review-confidence-cell>b{font-size:12px;line-height:20px}
.review-status{display:inline-flex;align-items:center;gap:6px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}.review-status::before{display:block;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}
.review-status.is-待处理,.review-status.is-已完成,.review-status.is-已撤销,.review-status.is-已驳回{background:transparent}
.review-risk-explain{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:16px}.review-risk-explain>div{gap:4px;padding:8px 16px;border-radius:6px;background:#f7f8fa}.review-risk-explain strong{font-size:14px;line-height:22px}.review-risk-explain span,.review-confidence-cell>span{font-size:12px;line-height:20px}
.review-pagination{height:56px;box-sizing:border-box;padding:12px 16px;font-size:12px;line-height:20px}.review-pagination :deep(.arco-pagination-item){min-width:28px;height:28px;border-radius:4px;font-size:12px;line-height:20px}.review-pagination :deep(.arco-pagination-item-active){background:#165dff;color:#fff}
.review-drawer{width:min(640px,calc(100vw - 48px));background:#fff}.review-drawer>header{height:56px;box-sizing:border-box;padding:8px 24px}.review-body{padding:24px}.review-body section,.review-compare article{padding:16px;border-radius:6px}.review-compare{gap:16px;margin:16px 0}
.review-drawer>footer{height:64px;box-sizing:border-box;gap:16px;padding:0 24px}.review-drawer>footer button{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px}
.ops-filter :deep(.arco-form-item){box-sizing:border-box;width:100%;min-width:0;margin:0!important}
.ops-filter :deep(.arco-form-item-layout-inline){margin-right:0!important}
.ops-filter :deep(.arco-form-item-wrapper-col),.ops-filter :deep(.arco-form-item-content-wrapper),.ops-filter :deep(.arco-form-item-content){box-sizing:border-box;width:100%;min-width:0}
/* Prevent page-level native input rules from styling Arco Select's internal input. */
.ops-filter :deep(.arco-select){width:100%;min-width:0}
.review-search-input.arco-input-wrapper{box-sizing:border-box;width:100%;height:32px;min-height:32px;padding:0 12px;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important}
.review-search-input.arco-input-wrapper:hover{border-color:#4080ff!important;background:#fff!important}
.review-search-input.arco-input-wrapper:focus-within,.review-search-input.arco-input-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.review-search-input.arco-input-wrapper :deep(.arco-input-prefix){padding-right:8px;color:#4e5969}.review-search-input.arco-input-focus :deep(.arco-input-prefix){color:#165dff}
.review-search-input.arco-input-wrapper :deep(.arco-input-prefix svg){width:16px;height:16px;font-size:16px}
.review-search-input.arco-input-wrapper :deep(.arco-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:none!important}
.ops-filter :deep(.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff}
.ops-filter :deep(.arco-select-view-input){height:100%!important;min-height:0!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important}
.ops-filter :deep(.arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;pointer-events:none!important}
.ops-filter :deep(.arco-select-view-value){min-width:0;line-height:30px}
@media(max-width:900px){.ops-filter,.ops-filter.is-review{grid-template-columns:1fr}.review-risk-explain{grid-template-columns:1fr}}
/* 人工审核一级切换与筛选工具栏沿用 Schema 管理页的二级分段按钮。 */
.review-tabs{display:flex;box-sizing:border-box;width:100%;min-height:40px;margin-bottom:16px;padding:0;border:0;background:transparent;align-items:center;justify-content:space-between;gap:16px;flex:0 0 auto;flex-wrap:nowrap;overflow-x:auto;overflow-y:hidden;white-space:nowrap}
.review-tabs>nav{display:flex;box-sizing:border-box;height:40px;padding:4px;border-radius:4px;background:#f2f3f5;flex:0 0 auto;overflow:visible}
.review-tabs>nav button{display:inline-flex;box-sizing:border-box;align-items:center;justify-content:center;width:120px;height:32px;padding:5px 16px;border:0;border-radius:4px;background:transparent;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;text-align:center}
.review-tabs>nav button+button{border-left:1px solid #c9cdd4}
.review-tabs>nav button.active{border-left-color:transparent;background:#fff;color:#165dff;font-weight:500}
.review-tabs>nav button.active+button{border-left-color:transparent}
.review-tabs>nav button:hover:not(.active){background:#fff;color:#165dff}
.review-toolbar-actions{display:flex;min-width:0;align-items:center;justify-content:flex-end;gap:16px;margin-left:auto;flex:0 0 auto;flex-wrap:nowrap}
.review-tabs .ops-filter.is-review{display:flex;box-sizing:border-box;width:auto;min-width:0;align-items:center;grid-template-columns:none;gap:16px!important;padding:0!important;border:0;background:transparent;flex:0 0 auto;flex-wrap:nowrap}
.review-filter-row :deep(.review-filter-select.arco-select-view){flex:0 0 160px;width:160px}
.review-filter-row :deep(.review-filter-search.arco-input-wrapper){flex:0 0 280px;width:280px}
.review-tabs .ops-filter.is-review :deep(.arco-select-view-value){font-size:14px;line-height:22px;font-weight:400}
.ops-review-table-scroll td{color:#344763;font-size:14px;line-height:22px;font-weight:400;vertical-align:middle}
.ops-review-table-scroll td>b,.ops-review-table-scroll td>strong{font-weight:400}
/* 抽取失败重跑：批量重跑按钮 / 重跑反馈条 / 状态徽标扩展 */
/* 批量重跑单独一行右对齐（贴合分段切换行下方，负 margin 收紧与上行的间距） */
.rerun-batch-row{display:flex;box-sizing:border-box;width:100%;min-height:32px;margin:-8px 0 12px;align-items:center;justify-content:flex-end;flex:0 0 auto}
.rerun-batch-action{height:32px;padding:0 16px;border:1px solid #165dff;border-radius:4px;background:#165dff;color:#fff;font-size:14px;line-height:22px;font-weight:400;cursor:pointer}
.rerun-batch-action:hover:not(:disabled){border-color:#4080ff;background:#4080ff}
.rerun-batch-action:active:not(:disabled){border-color:#0e42d2;background:#0e42d2}
.rerun-batch-action:disabled{border-color:#94bfff;background:#94bfff;color:#fff;cursor:not-allowed}
.rerun-feedback{flex:0 0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:9px 16px;border-bottom:1px solid #a6f4c5;background:#ecfdf3;color:#067647;font-size:12px;line-height:20px}
.rerun-feedback.is-error{border-color:#f5b8b3;background:#fef3f2;color:#b42318}
.rerun-feedback.is-warning{border-color:#fec84b;background:#fffaeb;color:#b54708}
.rerun-feedback-close{margin-left:auto;width:22px;height:22px;border:0;border-radius:4px;background:transparent;color:inherit;font-size:14px;cursor:pointer}
.rerun-confirm-text{margin:0;color:#4e5969;font-size:13px;line-height:22px}
.review-status.is-重跑中,.review-status.is-执行中{color:#175cd3}
.review-status.is-重跑失败,.review-status.is-失败{color:#b42318}
.review-status.is-已完成{color:#067647}
.review-status.is-排队中{color:#b54708}
.review-status.is-已取消{color:#86909c}

/* 人工审核页排版、间距与控件合同。 */
.ops-page,.ops-page :deep(*){font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;letter-spacing:0}
.ops-page{font-size:14px;line-height:22px;font-weight:400}
.review-tabs>nav button{padding:0 16px}
.review-filter-row :deep(.arco-select-view:hover){border-color:#4080ff}
.review-filter-row :deep(.arco-select-view-focus),.review-filter-row :deep(.arco-select-view:focus-within){border-color:#165dff;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.ops-review-table-scroll table,.ops-review-table-scroll td{font-size:14px;line-height:22px;font-weight:400}
.ops-review-table-scroll th{font-size:14px;line-height:22px;font-weight:500}
.ops-review-table-scroll td code,.review-id-cell .link{font-family:inherit;font-size:14px;line-height:22px;font-weight:400}
.ops-review-table-scroll td small,.ops-review-table-scroll td small code{font-size:12px;line-height:20px;font-weight:400}
.review-source-cell strong{font-size:14px;line-height:22px;font-weight:400}
.alert-actions{gap:4px}.alert-actions .link,.rerun-link{font-size:14px;line-height:22px;font-weight:400}
.pick-col{box-sizing:border-box;width:52px;min-width:52px;padding-right:16px!important;padding-left:16px!important}
/* 分页留在表格滚动区之外，窄屏换行后仍能访问翻页和跳页控件。 */
.review-pagination{height:auto;min-height:56px;flex-wrap:wrap;gap:8px 16px;padding:8px 16px}
.review-pagination :deep(.arco-pagination){max-width:100%;flex-wrap:wrap;row-gap:8px}
.review-pagination :deep(.arco-pagination-list){display:flex;max-width:100%;flex-wrap:wrap;row-gap:8px;white-space:normal}
.review-pagination :deep(.arco-pagination-list>.arco-pagination-item){flex-shrink:0}
.review-pagination :deep(.arco-select-view),.review-pagination :deep(.arco-pagination-item){height:32px;min-height:32px}
.review-pagination :deep(.arco-pagination-item){min-width:32px;font-size:14px;line-height:22px}
.review-pagination :deep(.review-page-size-select.arco-select-view){display:inline-flex;box-sizing:border-box;align-items:center;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important}
.review-pagination :deep(.review-page-size-select.arco-select-view:hover){border-color:#4080ff!important}.review-pagination :deep(.review-page-size-select.arco-select-view:focus-within),.review-pagination :deep(.review-page-size-select.arco-select-view-focus){border-color:#165dff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.review-pagination :deep(.review-page-size-select .arco-select-view-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.review-pagination :deep(.review-page-size-select .arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important;pointer-events:none!important}
.review-pagination :deep(.review-page-size-select .arco-select-view-value){min-width:0;font-size:14px;line-height:22px;font-weight:400}
.ops-review-table-scroll .pick-col{vertical-align:middle;text-align:center}.ops-review-table-scroll .pick-col input[type="checkbox"]{display:block;width:14px;height:14px;margin:0 auto;vertical-align:middle;cursor:pointer}
.rerun-batch-action:focus-visible{outline:0;box-shadow:0 0 0 2px rgba(22,93,255,.2)}
.rerun-feedback{gap:8px;padding:8px 16px}.rerun-feedback-close{width:24px;height:24px}
.rerun-confirm-text{font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
/* 操作列撤销旧的右侧固定列实现；static 只作用 td——表头单元格要保留全局 th 的吸顶 */
.ops-review-table-scroll td.review-action-col{position:static;box-sizing:border-box;width:auto;min-width:0;box-shadow:none;white-space:nowrap}
.review-action-col .alert-actions{display:flex;width:max-content;min-width:0;align-items:center;gap:8px}
.ops-review-table-scroll th,.ops-review-table-scroll td{box-sizing:border-box;padding-right:16px;padding-left:16px}
/* 固定列合计 1012px，最小表宽为对象列保留 268px；勾选列额外占 52px。 */
.ops-review-table-scroll table.review-case-table{width:100%;min-width:1280px;table-layout:fixed}
.ops-review-table-scroll table.review-case-table--selectable{min-width:1332px}
.ops-review-table-scroll .review-object-cell{padding-top:8px;padding-bottom:8px;overflow-wrap:anywhere;word-break:normal}
.ops-review-table-scroll td{white-space:normal}
.ops-review-table-scroll :is(code,.review-id-cell,.review-status){white-space:nowrap}
.ops-review-table-scroll :is(th,td):last-child{white-space:nowrap}
.ops-review-table-scroll .review-id-cell,.ops-review-table-scroll .review-source-cell{min-width:0}
/* 固定布局下的列宽合同：col.col-object 不设宽吃剩余空间；宽内容列超长省略号截断 */
.review-case-table col.col-pick{width:52px}
.review-case-table col.col-id{width:264px}
.review-case-table col.col-kind{width:88px}
.review-case-table col.col-source{width:220px}
.review-case-table col.col-status{width:104px}
.review-case-table col.col-time{width:200px}
.review-case-table col.col-actions{width:136px}
.ops-review-table-scroll .review-id-cell{overflow:hidden;text-overflow:ellipsis}
.ops-review-table-scroll .review-id-cell :is(code,.link){display:inline-block;box-sizing:border-box;max-width:100%;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
/* 滚动条出现/消失（数据多少切换）不挤动列宽 */
.ops-review-table-scroll{scrollbar-gutter:stable}
/* 筛选字段标签 / 类型徽标 / 勾选禁用态 / 删除按钮 */
.review-filter-field{display:flex;flex:0 0 auto;align-items:center;gap:8px}
.review-filter-label{color:#4e5969;font-size:14px;line-height:22px;white-space:nowrap}
/* 处理实例 ID 纯文本：中性色，区别于可点击的链接蓝 */
.review-id-cell .review-id-plain{color:#4e5969}
.review-kind-badge{display:inline-flex;white-space:nowrap;padding:0 8px;border-radius:4px;background:#f2f3f5;color:#4e5969;font-size:12px;line-height:20px}
.review-kind-badge.is-实体{background:#eaf2ff;color:#175cd3}
.review-kind-badge.is-关系{background:#fff3d8;color:#b54708}
.rerun-link.is-danger{color:#b42318}
.ops-review-table-scroll .pick-col input[type="checkbox"]:disabled{opacity:.35;cursor:not-allowed}
/* 日志弹窗内容（弹体外壳样式在全局块） */
.case-log-sec{margin:0 0 16px}
.case-log-sec h4{margin:0 0 8px;color:#1d2129;font-size:14px;line-height:22px;font-weight:600}
/* dt/dd 两列网格下沉到行 div：dl 直接网格化会把整行 div 当格子，落在 88px 窄格的值被硬折行 */
.case-log-dl{display:grid;gap:6px 0;margin:0}
.case-log-dl>div{display:grid;grid-template-columns:88px 1fr;column-gap:12px}
.case-log-dl dt{color:#86909c;font-size:12px;line-height:20px}
.case-log-dl dd{margin:0;color:#1d2129;font-size:13px;line-height:20px;overflow-wrap:anywhere}
.case-log-error-text{margin:0;padding:10px 12px;border:1px solid #f6c6b4;border-radius:4px;background:#fff8f5;color:#b42318;font:12px/19px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-all}
.case-log-loading{margin:0;padding:24px;color:#86909c;text-align:center}
/* 执行日志弹窗：原执行/重跑执行切换 + 概要 + 阶段状态 + 日志终端 */
.case-log-switch{display:flex;gap:8px;margin:0 0 12px}
.case-log-switch button{height:28px;padding:0 14px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;color:#4e5969;font-size:13px;line-height:20px;cursor:pointer}
.case-log-switch button.active{border-color:#165dff;background:#165dff;color:#fff}
.case-log-missing{margin:0;padding:14px;border:1px dashed #e5e6eb;border-radius:4px;background:#f7f8fa;color:#86909c;font-size:13px;line-height:20px;word-break:break-all}
.case-log-console{margin:0;max-height:280px;overflow:auto;padding:12px 14px;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa;color:#1d2129;font:12px/20px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-all}
.case-log-steps{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}
.case-log-steps li{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:12px;line-height:20px}
.case-log-step-name{color:#4e5969}
.case-log-step-status{color:#165dff}
.case-log-step-status.is-成功{color:#067647}
.case-log-step-status.is-运行中{color:#175cd3}
.case-log-step-status.is-需人工处理{color:#b54708}
.case-log-step-status.is-待执行{color:#86909c}
.case-log-empty{color:#86909c}
/* 更新时间表头三态排序 */
.th-time-sort{cursor:pointer;user-select:none}
.th-time-sort:hover{color:#165dff}
.th-time-sort.is-active{color:#165dff}
.th-time-sort .sort-arrow{margin-left:4px;color:#86909c;font-size:12px}
.th-time-sort.is-active .sort-arrow{color:#165dff}
/* 横屏高度不足时允许整页上下滚动，避免分页把表格挤到只剩表头。 */
@media(max-height:600px){
  .ops-page{overflow:auto}
  .ops-panel{flex:none}
  .ops-review-table-scroll{flex:none;min-height:160px;max-height:50vh}
}
</style>
<style>
/* Keep the Arco input's native field transparent; the wrapper is the only visible input shell. */
.app-workspace .ops-page .ops-filter.is-review .review-search-input.arco-input-wrapper input.arco-input{box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .ops-page .ops-filter.is-review .review-search-input.arco-input-wrapper input.arco-input:focus{border:0!important;background:transparent!important;box-shadow:none!important;outline:0!important}
.rerun-confirm-modal{border-radius:8px;font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.rerun-confirm-modal .arco-modal-header{box-sizing:border-box;height:56px;padding:0 24px}.rerun-confirm-modal .arco-modal-title{font-size:16px;line-height:24px;font-weight:600;letter-spacing:0}.rerun-confirm-modal .arco-modal-body{padding:24px}.rerun-confirm-modal .arco-modal-footer{box-sizing:border-box;min-height:64px;padding:16px 24px}.rerun-confirm-modal .arco-btn{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}.rerun-confirm-modal .arco-btn+.arco-btn{margin-left:16px}
/* 日志弹窗（teleport 到 body，需全局控制弹体） */
.case-log-modal{border-radius:8px;font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.case-log-modal .arco-modal-header{box-sizing:border-box;height:56px;padding:0 24px}.case-log-modal .arco-modal-title{font-size:16px;line-height:24px;font-weight:600;letter-spacing:0}.case-log-modal .arco-modal-body{max-height:70vh;overflow:auto;padding:16px 24px}
</style>
