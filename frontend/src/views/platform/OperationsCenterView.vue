<script setup lang="ts">
import DeleteConfirmDialog from '../../components/DeleteConfirmDialog.vue'
import AppAlert from '../../components/AppAlert.vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { IconRefresh, IconSearch } from '@arco-design/web-vue/es/icon'

import { batchDeleteProductionReviews, deleteProductionReview, getExecution, getProductionReview, getProductionReviews, getTask, rerunExtractFailures, TRIGGER_SOURCE_LABEL, type ProcessingInstance, type ProcessStep, type ProductionReviewCase, type WorkflowExecution } from '../../api/workflowOperations'
import { currentGraphSpace } from '../../api/currentGraphSpace'
import { useGraphSpaceStore } from '../../stores/graphSpace'
import { clampSearchKeyword, SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import ListPagination from '../../components/list-pagination.vue'
import { PAGE_SIZE_OPTIONS } from '../../composables/use-client-pagination'
import {
  extractCaseStatusBadge,
  type ReviewRecord,
} from './manual-review-data'

type CenterMode = 'review'

const props = defineProps<{ mode: CenterMode }>()
const route = useRoute()
const graphSpaceStore = useGraphSpaceStore()

/** 队列视图状态快照（sessionStorage）：点「查看记录」跳详情再返回时恢复页码/页大小/分类/筛选/排序，
 *  不再回落第 1 页。每次拉取前落盘（兼覆盖手动刷新场景）；显式深链 query（category/keyword）优先于快照。 */
const QUEUE_SNAPSHOT_KEY = 'techkg.manual-review-queue.v1'
type QueueSnapshot = {
  category: 'A' | 'C'
  page: number
  pageSize: number
  status: '全部' | '待处理' | '已处理' | '重跑中'
  kind: '全部' | '实体' | '关系'
  time: '全部' | '近1小时' | '近24小时' | '近7天' | '近30天'
  sort: 'default' | 'desc' | 'asc'
  keyword: string
}
function readQueueSnapshot(): Partial<QueueSnapshot> | null {
  try {
    const raw = sessionStorage.getItem(QUEUE_SNAPSHOT_KEY)
    return raw ? (JSON.parse(raw) as Partial<QueueSnapshot>) : null
  } catch {
    return null
  }
}
/** 快照值仅在合法枚举内才恢复，否则用默认值（防手改存储/字段演进出脏值）。 */
function pickSnapshotOption<T extends string>(value: unknown, allowed: readonly T[], fallback: T): T {
  return allowed.includes(value as T) ? (value as T) : fallback
}
const queueSnapshot = readQueueSnapshot()

const keyword = ref(clampSearchKeyword(String(route.query.keyword || queueSnapshot?.keyword || '')))
const submittedKeyword = ref(keyword.value)
/** 人工审核筛选：状态分组（待处理/已处理）与对象种类（实体/关系/都看）；C 类额外支持 重跑中 精确过滤。
 *  重跑仍失败的记录会重建为新待处理案（attempt+1），不存在「重跑失败」状态，故不提供该筛选项。
 *  undefined = 未选择（清空），语义等同「全部」。 */
const reviewStatusFilter = ref<'全部' | '待处理' | '已处理' | '重跑中' | undefined>(pickSnapshotOption(queueSnapshot?.status, ['全部', '待处理', '已处理', '重跑中'] as const, '全部'))
const reviewKindFilter = ref<'全部' | '实体' | '关系' | undefined>(pickSnapshotOption(queueSnapshot?.kind, ['全部', '实体', '关系'] as const, '全部'))
/** 时间过滤（按更新时间）：全部/近1小时/近24小时/近7天/近30天 → updatedWithin 查询参数。 */
const reviewTimeFilter = ref<'全部' | '近1小时' | '近24小时' | '近7天' | '近30天' | undefined>(pickSnapshotOption(queueSnapshot?.time, ['全部', '近1小时', '近24小时', '近7天', '近30天'] as const, '全部'))
const reviewTimeOptions = ['全部', '近1小时', '近24小时', '近7天', '近30天']
const REVIEW_TIME_PARAMS: Record<string, string | undefined> = { '全部': undefined, '近1小时': '1h', '近24小时': '24h', '近7天': '7d', '近30天': '30d' }
/** 更新时间排序：default=风险+创建时间（默认）；desc=新→旧；asc=旧→新。 */
const reviewTimeSort = ref<'default' | 'desc' | 'asc'>(pickSnapshotOption(queueSnapshot?.sort, ['default', 'desc', 'asc'] as const, 'default'))
const reviewTotal = ref(0)
/** 队列行 = manual-review-data 的 ReviewRecord + 重跑/删除/跳转所需的原始字段。 */
type ReviewRow = ReviewRecord & { templateId?: string; rawStatus?: string; jobId?: string; canOperate?: boolean }

/** 可重跑/可删除：与后端 rerun 门控同口径（未处理）；查看档只读行（canOperate=false，
 *  如开发维护看共享生产空间）同样不可操作，后端对操作档仍强校验 403。
 *  不可操作时按钮置灰禁用而非隐藏（保持操作列布局稳定）。 */
const isRerunnable = (row: ReviewRow) =>
  (row.rawStatus === 'OPEN' || row.rawStatus === 'RERUN_FAILED') && row.canOperate !== false

/** 置灰按钮的悬停说明：按记录状态给出不可操作的原因。 */
function rerunDisabledReason(row: ReviewRow): string {
  if (row.canOperate === false) return '共享生产空间：仅可查看，操作需管理员或本业务开发维护人员'
  if (row.rawStatus === 'RERUNNING') return '重跑中：等待本次重跑完成后再操作'
  return '已处理：仅「待处理 / 重跑失败」的记录可重跑或删除'
}

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

/** 当前队列整页只读（查看档，如开发维护切到共享生产空间）：顶部提示条。 */
const reviewReadOnly = computed(
  () => reviewRows.value.length > 0 && reviewRows.value.every((row) => row.canOperate === false),
)

/** 分页状态：服务端分页，翻页/改页大小都会重新拉取当前筛选下的数据。
 *  分页条为共享 ListPagination（共 N 条/每页/跳页样式随组件自带），默认每页 20；
 *  页码/页大小从快照恢复（跳详情返回不回第 1 页），恢复页超出总页数时由 loadReviews 收敛。 */
const snapshotPage = Math.trunc(Number(queueSnapshot?.page))
const snapshotPageSize = Number(queueSnapshot?.pageSize)
const reviewPage = ref(snapshotPage >= 1 ? snapshotPage : 1)
const reviewPageSize = ref(PAGE_SIZE_OPTIONS.includes(snapshotPageSize) ? snapshotPageSize : 20)

watch(() => route.query.keyword, (value) => {
  keyword.value = clampSearchKeyword(String(value || ''))
  submittedKeyword.value = keyword.value
  void loadReviews()
})

const reviewTableRef = ref<HTMLElement | null>(null)
const tableHasMoreToScroll = ref(false)
const tableScrollActive = ref(false)
let scrollIdleTimer: ReturnType<typeof setTimeout> | undefined

function updateReviewTableScrollState() {
  const table = reviewTableRef.value
  tableHasMoreToScroll.value = !!table && table.scrollWidth - table.clientWidth - table.scrollLeft > 1
}

function handleReviewTableScroll() {
  updateReviewTableScrollState()
  tableScrollActive.value = true
  clearTimeout(scrollIdleTimer)
  scrollIdleTimer = setTimeout(() => { tableScrollActive.value = false }, 700)
}

function submitReviewSearch() {
  submittedKeyword.value = keyword.value.trim()
  void loadReviews()
}

/** 搜索框清空（×）：连已提交关键词一并复位并重新拉取，避免「框已空、列表仍按旧关键词过滤」的假清空。 */
function clearReviewSearch() {
  if (!keyword.value && !submittedKeyword.value) return
  keyword.value = ''
  submittedKeyword.value = ''
  void loadReviews()
}

/** 审核队列分类：A=入库决策（Tab 只筛 T_LINK 实体对齐，T_DIRECT 详情由工作台总览/实例详情直达）；C=抽取失败重跑（T_EXTRACT_FAIL）。
 *  支持 ?category=A|C 深链初始定位子页（工作台总览的「抽取失败重跑」卡片直达 C 子页），深链优先于快照恢复。 */
const reviewCategory = ref<'A' | 'C'>(
  route.query.category === 'A' || route.query.category === 'C'
    ? route.query.category
    : queueSnapshot?.category === 'C' ? 'C' : 'A',
)
watch([reviewRows, reviewCategory], async () => {
  await nextTick()
  updateReviewTableScrollState()
}, { flush: 'post' })
// A 类没有「重跑中」筛选项：快照恢复后按当前分类收敛，避免 Select 挂着不属于该分类的选项
if (reviewCategory.value === 'A' && reviewStatusFilter.value === '重跑中') reviewStatusFilter.value = '全部'
/** Tab 切换不携带筛选条件：入库决策（A）/抽取失败重跑（C）各自独立记忆
 *  状态/类型/时间/排序/关键词/页码，切走再切回按原样恢复（C 的「重跑中」不会带到 A，
 *  A 的筛选也不会带到 C）。页大小与勾选不拆分：页大小是全局偏好，勾选跨 Tab 无意义（切换即清）。 */
type ReviewTabFilters = {
  status: '全部' | '待处理' | '已处理' | '重跑中'
  kind: '全部' | '实体' | '关系'
  time: '全部' | '近1小时' | '近24小时' | '近7天' | '近30天'
  sort: 'default' | 'desc' | 'asc'
  /** keyword=输入框文本（未提交的草稿也保留）；submitted=已作用于当前列表的关键词。 */
  keyword: string
  submitted: string
  page: number
}
const REVIEW_TAB_FILTERS_DEFAULT: ReviewTabFilters = {
  status: '全部', kind: '全部', time: '全部', sort: 'default', keyword: '', submitted: '', page: 1,
}
const reviewTabFilters: Record<'A' | 'C', ReviewTabFilters> = {
  A: { ...REVIEW_TAB_FILTERS_DEFAULT },
  C: { ...REVIEW_TAB_FILTERS_DEFAULT },
}
/** 切走前把当前分类的筛选状态存回（undefined 与「全部」语义等同，落默认值防脏）。 */
function stashReviewTabFilters(category: 'A' | 'C') {
  reviewTabFilters[category] = {
    status: reviewStatusFilter.value ?? '全部',
    kind: reviewKindFilter.value ?? '全部',
    time: reviewTimeFilter.value ?? '全部',
    sort: reviewTimeSort.value,
    keyword: keyword.value,
    submitted: submittedKeyword.value,
    page: reviewPage.value,
  }
}
/** Tab 切换应用筛选时抑制「筛选变化即重拉」的 watch（switchReviewCategory 末尾统一拉取一次）。 */
let applyingTabFilters = false
/** 切入时按该分类上次离开时的状态恢复（含输入框草稿与已提交关键词）。 */
function applyReviewTabFilters(category: 'A' | 'C') {
  const state = reviewTabFilters[category]
  applyingTabFilters = true
  reviewStatusFilter.value = state.status
  reviewKindFilter.value = state.kind
  reviewTimeFilter.value = state.time
  reviewTimeSort.value = state.sort
  keyword.value = state.keyword
  submittedKeyword.value = state.submitted
  reviewPage.value = state.page
  void nextTick(() => { applyingTabFilters = false })
}
// 初始分类沿用快照/深链初始化出的当前 refs；另一分类保持默认值
stashReviewTabFilters(reviewCategory.value)
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
  // 切走先存回当前分类的筛选状态，切入恢复对方自己的（Tab 互不影响，页码随各自状态恢复）
  stashReviewTabFilters(reviewCategory.value)
  reviewCategory.value = category
  rerunSelection.value = new Set()
  applyReviewTabFilters(category)
  void loadReviews()
}

function toggleRerunPick(id: string, checked: boolean) {
  if (checked) rerunSelection.value.add(id)
  else rerunSelection.value.delete(id)
}

/** 表头全选/取消：只作用于当前页可重跑行（不可重跑行禁用不勾选）；跨页勾选保持，按钮数字展示总数。 */
function toggleRerunPickAll(event: Event) {
  if (!rerunPageEligibleIds.value.length || reviewLoading.value || rerunSubmitting.value || batchDeleteSubmitting.value) return
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

/** 单 Schema 执行（kg.schema.extract）的 output 自带 Schema 中文名（schemaLabel），
 *  与 chain 段名同源同值：阶段名用它对齐「原执行 chain 段 / 任务详情页」口径；
 *  chain 段 id 带 schema: 前缀，不套用（名字本就是中文）。 */
const logSchemaLabel = computed(() => {
  const output = logExecution.value?.output as Record<string, unknown> | null | undefined
  return typeof output?.schemaLabel === 'string' && output.schemaLabel ? output.schemaLabel : ''
})

function stepDisplayName(step: ProcessStep): string {
  return logSchemaLabel.value && !step.id.startsWith('schema:') ? logSchemaLabel.value : step.name
}

/** 口径对齐任务详情页（ProcessInstanceDetailView）：环节跑完但含失败行 = 异常，
 *  非成功也非失败；行级失败数在 step.abnormal（kg.schema.extract 的 failed 计数）。 */
function stepDisplayStatus(step: ProcessStep): string {
  if (step.status === '成功' && step.abnormal !== '0' && step.abnormal !== '-') return '异常'
  return step.status
}

/** 执行概要状态三选一：成功（COMPLETED 零失败行）/ 异常（ABNORMAL 含行级失败）/
 *  失败（FAILED 等跑崩类）；运行中为在途执行的瞬时态。 */
function executionDisplayStatus(status?: string | null): string {
  switch ((status || '').toUpperCase()) {
    case 'COMPLETED': return '成功'
    case 'ABNORMAL': return '异常'
    case 'FAILED': case 'CANCELED': case 'TERMINATED': case 'TIMED_OUT': return '失败'
    default: return '运行中'
  }
}

/** 状态圆点配色 tone（对齐 8093 现网 case-log-exec-status 口径）：成功绿/异常橙/失败红/运行中蓝。 */
function executionStatusTone(status?: string | null): string {
  const label = executionDisplayStatus(status)
  return ({ 成功: 'ok', 异常: 'warn', 失败: 'err' } as Record<string, string>)[label] ?? 'run'
}

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

// ---- C 类批量删除：与批量重跑共用勾选集合，二次确认后逐条物理删除 ----

/** 批量删除确认弹窗与提交态（>N 条与重跑同栏展示，勾选集即删除集）。 */
const batchDeleteVisible = ref(false)
const batchDeleteSubmitting = ref(false)

/** 跳过原因摘要：按原因聚合计数，至多列 3 类防刷屏。 */
function summarizeBatchSkipReasons(skipped: Array<{ id: string; reason: string }>): string {
  const groups = new Map<string, number>()
  for (const item of skipped) groups.set(item.reason, (groups.get(item.reason) ?? 0) + 1)
  const parts = [...groups.entries()].map(([reason, count]) => `${reason}×${count}`)
  return parts.length > 3 ? `${parts.slice(0, 3).join('、')} 等 ${parts.length} 类` : parts.join('、')
}

function askBatchDelete() {
  if (!rerunSelection.value.size || batchDeleteSubmitting.value) return
  batchDeleteVisible.value = true
}

/** 确认批量删除：已处理的/不存在的按条跳过不中断整批，结果经反馈条展示（有跳过转警告态）。 */
async function confirmBatchDelete() {
  const ids = [...rerunSelection.value]
  if (!ids.length || batchDeleteSubmitting.value) return
  batchDeleteSubmitting.value = true
  try {
    const result = await batchDeleteProductionReviews({ caseIds: ids })
    const skipped = result.skipped ?? []
    const skippedText = skipped.length ? `；跳过 ${skipped.length} 条（${summarizeBatchSkipReasons(skipped)}）` : ''
    showRerunFeedback(
      skipped.length ? 'warning' : 'success',
      `已删除失败记录 ${result.deleted} 条${skippedText}`,
      [],
    )
    batchDeleteVisible.value = false
    rerunSelection.value = new Set()
    void loadReviews()
  } catch (error) {
    showRerunFeedback('error', error instanceof Error ? error.message : '批量删除失败', [])
  } finally {
    batchDeleteSubmitting.value = false
  }
}

onUnmounted(() => {
  reviewDisposed = true
  reviewRequestId += 1
  window.removeEventListener('resize', updateReviewTableScrollState)
  clearTimeout(scrollIdleTimer)
  window.clearTimeout(rerunFeedbackTimer)
})

async function loadReviews() {
  if (props.mode !== 'review' || reviewDisposed) return
  // 拉取前把当前视图状态落快照：跳详情返回 / 手动刷新都能回到本页
  try {
    sessionStorage.setItem(QUEUE_SNAPSHOT_KEY, JSON.stringify({
      category: reviewCategory.value,
      page: reviewPage.value,
      pageSize: reviewPageSize.value,
      status: reviewStatusFilter.value ?? '全部',
      kind: reviewKindFilter.value ?? '全部',
      time: reviewTimeFilter.value ?? '全部',
      sort: reviewTimeSort.value,
      keyword: submittedKeyword.value,
    } satisfies QueueSnapshot))
  } catch {
    /* 隐私模式等存储不可用：跳过快照，返回时退回默认第 1 页 */
  }
  const requestId = ++reviewRequestId
  reviewLoading.value = true
  reviewLoadError.value = ''
  reviewRecords.value = []
  reviewTotal.value = 0
  try {
    // A=入库决策：Tab 只筛 T_LINK（实体对齐裁决）——T_DIRECT case 不进队列，
    // 详情由工作台总览/处理实例详情直达；C=抽取失败重跑（T_EXTRACT_FAIL）
    const response = await getProductionReviews({
      graphSpace: currentGraphSpace() || undefined,
      category: reviewCategory.value,
      templateId: reviewCategory.value === 'A' ? 'T_LINK' : undefined,
      keyword: submittedKeyword.value || undefined,
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
      id: row.id, templateId: row.templateId, rawStatus: row.status, jobId: row.jobId || '', canOperate: row.canOperate !== false, batch: row.batchId || '-', module: row.phase, node: row.nodeId, type: row.errorType, category: row.category, domain: row.domain, objectType: row.objectType, objectId: row.objectId, object: row.objectName, ruleId: row.templateId, evidence: `${row.evidence?.length || 0} 项`, score: row.riskLevel, handler: row.assigneeName || '待处理', status: extractCaseStatusBadge(row.status), updatedAt: fmtReviewTime(row.updatedAt), sourceResult: row.diagnosis, suggestion: row.scope, sourceTable: row.sourceTable || '-', sourceRecordId: row.sourceRecordId || '-', confidenceValue: row.riskLevel, confidenceLabel: row.status,
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

/** 筛选条件变化：保留当前页重新加载；总页数收缩、当前页超出时由 loadReviews 收敛到最后有效页（FUNC-00781）。
 *  Tab 切换恢复各自筛选状态时的变更不在此触发（applyingTabFilters 抑制，由切换处统一拉取一次）。 */
watch([reviewStatusFilter, reviewKindFilter, reviewTimeFilter], () => {
  if (props.mode !== 'review' || applyingTabFilters) return
  void loadReviews()
})

/** 图空间切换（总览页全局选择器，本页不设控件）：待审核队列跟随当前空间重新拉取
 *  （换的是整份数据，页码归 1；空间是全局态，不进 sessionStorage 快照，与其他业务页
 *  「切空间即重查」同口径）；同时清掉旧空间的批量操作对象与弹窗/日志抽屉，防止跨空间误操作。 */
watch(() => graphSpaceStore.current, () => {
  if (props.mode !== 'review') return
  reviewPage.value = 1
  rerunSelection.value = new Set()
  rerunConfirmVisible.value = false
  rerunFeedback.value = null
  deleteVisible.value = false
  deleteTarget.value = undefined
  logVisible.value = false
  logCase.value = undefined
  logExecution.value = null
  logTask.value = null
  void loadReviews()
})

onMounted(() => {
  window.addEventListener('resize', updateReviewTableScrollState)
  void nextTick(updateReviewTableScrollState)
  void loadReviews()
})
</script>

<template>
  <div class="ops-page">
    <div v-if="mode === 'review'" class="alert-tabs review-tabs">
      <nav>
        <button type="button" :class="{ active: reviewCategory === 'A' }" @click="switchReviewCategory('A')">入库决策</button>
        <button type="button" :class="{ active: reviewCategory === 'C' }" @click="switchReviewCategory('C')">抽取失败重跑</button>
      </nav>
      <div class="review-toolbar-actions">
        <form class="ops-filter is-review review-filter-row" role="search" @submit.prevent="submitReviewSearch">
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
          <a-input v-model="keyword" class="review-search-input review-filter-search" :max-length="SEARCH_KEYWORD_MAX_LENGTH" aria-label="搜索处理实例 ID、对象或来源记录" placeholder="搜索处理实例 ID、对象或来源记录" allow-clear @clear="clearReviewSearch"><template #prefix><IconSearch /></template></a-input>
          <button class="review-search-button" type="submit">查询</button>
        </form>
      </div>
    </div>

    <!-- 查看档只读提示（开发维护切到共享生产空间）：整页不可操作 -->
    <AppAlert v-if="reviewReadOnly" type="warning" class="review-readonly-bar">
      当前图空间为共享生产空间：人工审核仅可查看，操作需管理员或本业务开发维护人员执行。
    </AppAlert>

    <section class="ops-panel">

      <!-- 批量重跑结果反馈：成功/警告/错误按 Arco Alert 四态规范展示（带提示符，可关闭） -->
      <AppAlert
        v-if="rerunFeedback"
        :type="rerunFeedback.type"
        class="rerun-feedback"
        closable
        @close="rerunFeedback = null"
      >
        <span>{{ rerunFeedback.text }}</span>
        <span
          v-for="item in rerunFeedback.executions"
          :key="item.executionId"
          class="rerun-feedback-exec"
        >{{ item.schemaId }} · {{ item.cases }} 条</span>
      </AppAlert>

      <div ref="reviewTableRef" class="ops-review-table-scroll" :class="{ 'has-scroll-right': tableHasMoreToScroll, 'review-scroll--active': tableScrollActive }" :aria-busy="reviewLoading" @scroll.passive="handleReviewTableScroll"><table class="review-case-table" :class="{ 'review-case-table--selectable': reviewCategory === 'C' }">
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
              title="全选当前页可重跑的失败记录（仅「待处理 / 重跑失败」状态可勾选）"
              :disabled="!rerunPageEligibleIds.length || reviewLoading || rerunSubmitting || batchDeleteSubmitting"
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
              :title="!isRerunnable(row) ? rerunDisabledReason(row) : undefined"
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
                <RouterLink class="review-action-btn" :to="`/manual-review/task/${row.id}`">查看记录</RouterLink>
              </div>
              <div v-else class="alert-actions">
                <button class="review-action-btn" type="button" @click="openLog(row)">日志</button>
                <!-- 不可重跑/删除的行（重跑中、已处理）按钮保留占位但置灰禁用，悬停说明原因 -->
                <button
                  class="review-action-btn"
                  type="button"
                  :disabled="!isRerunnable(row) || rerunSubmitting"
                  :title="!isRerunnable(row) ? rerunDisabledReason(row) : undefined"
                  @click="rerunSelected([row.id])"
                >重跑</button>
                <button
                  class="review-action-btn is-danger"
                  type="button"
                  :disabled="!isRerunnable(row) || deleteSubmitting"
                  :title="!isRerunnable(row) ? rerunDisabledReason(row) : undefined"
                  @click="askDelete(row)"
                >删除</button>
              </div>
            </td>
          </tr>
          <tr v-if="!reviewRows.length">
            <td class="review-empty" :colspan="reviewCategory === 'C' ? 8 : 7">
              <span v-if="reviewLoading" role="status">正在加载人工审核记录…</span>
              <div v-else-if="reviewLoadError" role="alert" class="review-load-error">
                <AppAlert type="error" class="review-load-error__alert">{{ reviewLoadError }}</AppAlert>
                <button type="button" class="link" @click="loadReviews"><IconRefresh class="refresh-icon" />重新加载</button>
              </div>
              <span v-else>{{ reviewStatusFilter === '全部' && reviewKindFilter === '全部' && reviewTimeFilter === '全部' && !submittedKeyword ? '暂无人工处理记录' : '暂无符合条件的记录' }}</span>
            </td>
          </tr>
        </tbody>
      </table></div>

      <ListPagination
        v-if="!reviewLoading && !reviewLoadError"
        class="review-pagination"
        :total="reviewTotal"
        :page="reviewPage"
        :page-size="reviewPageSize"
        :show-jumper="false"
        :size-at-end="true"
        @change="changeReviewPage"
        @change-size="changeReviewPageSize"
      >
        <template #summary>
          <!-- 选中可重跑记录后，在分页条左侧显示批量重跑入口。 -->
          <span v-if="reviewCategory === 'C' && rerunSelection.size" class="rerun-confirm-bar">
            <template v-if="rerunSelection.size">已选 {{ rerunSelection.size }} 条失败记录</template>
            <button
              class="review-action-btn rerun-batch-action"
              type="button"
              :disabled="rerunSubmitting || batchDeleteSubmitting"
              @click="rerunSelected()"
            >{{ rerunSubmitting ? '下发中…' : `批量重跑（${rerunSelection.size}）` }}</button>
            <button
              class="review-action-btn rerun-batch-action is-danger"
              type="button"
              :disabled="rerunSubmitting || batchDeleteSubmitting"
              @click="askBatchDelete"
            >{{ batchDeleteSubmitting ? '删除中…' : `批量删除（${rerunSelection.size}）` }}</button>
          </span>
          <span class="review-page-summary">共 {{ reviewTotal }} 条</span>
        </template>
      </ListPagination>
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
      <AppAlert type="warning" class="rerun-confirm-text">即将对已勾选的 {{ rerunSelection.size }} 条失败记录下发重跑，按 schema 合并为新执行（类别=重新执行）。重跑成功的记录自动关闭，仍失败的会重新进入失败列表。</AppAlert>
    </a-modal>

    <a-modal
      v-model:visible="batchDeleteVisible"
      modal-class="rerun-confirm-modal"
      title="确认批量删除"
      :width="560"
      ok-text="删除"
      cancel-text="取消"
      :ok-loading="batchDeleteSubmitting"
      @ok="confirmBatchDelete"
    >
      <AppAlert type="warning" class="rerun-confirm-text">即将物理删除已勾选的 {{ rerunSelection.size }} 条失败记录，连同草稿、决议、附件与审计记录一并清除，不可恢复。仅未处理记录可删除，已处理或不存在的会自动跳过。</AppAlert>
    </a-modal>

    <a-modal
      v-model:visible="logVisible"
      modal-class="case-log-modal"
      :title="`执行日志 · ${logCase?.id || ''}`"
      :width="760"
      title-align="start"
    >
      <p v-if="logLoading" class="case-log-loading">加载中…</p>
      <AppAlert v-else-if="logError" type="error" class="case-log-error-block">
        <pre class="case-log-error-text">{{ logError }}</pre>
      </AppAlert>
      <template v-else-if="logCase">
        <!-- 原执行/重跑执行切换（两者都有时才显示；默认看重跑执行=最新一次处理） -->
        <div v-if="logRerunExecutionId && logOriginalExecutionId" class="case-log-switch">
          <button type="button" :class="{ active: logExecutionChoice === 'rerun' }" @click="switchLogExecution('rerun')">重跑执行</button>
          <button type="button" :class="{ active: logExecutionChoice === 'original' }" @click="switchLogExecution('original')">原执行</button>
        </div>
        <AppAlert v-if="logExecutionMissing" type="warning" class="case-log-missing">未找到关联的工作流执行记录（{{ logActiveExecutionId || '该记录未关联执行 ID' }}）——执行记录可能已随环境重置被清理。</AppAlert>
        <template v-else-if="logExecution">
          <section class="case-log-sec">
            <h4>执行概要</h4>
            <dl class="case-log-dl">
              <div><dt>执行 ID</dt><dd><code>{{ logExecution.id }}</code></dd></div>
              <div><dt>触发方式</dt><dd>{{ TRIGGER_SOURCE_LABEL[logExecution.triggerSource || 'MANUAL'] || logExecution.triggerSource || '—' }}</dd></div>
              <div><dt>状态</dt><dd><span :class="['case-log-exec-status', executionStatusTone(logExecution.status)]">{{ executionDisplayStatus(logExecution.status) }}</span></dd></div>
              <div><dt>开始时间</dt><dd>{{ logExecution.startedAt || '—' }}</dd></div>
              <div><dt>完成时间</dt><dd>{{ logExecution.completedAt || '—' }}</dd></div>
              <div v-if="logExtractSummary"><dt>抽取结果</dt><dd>写入 {{ logExtractSummary.written }} · 失败 {{ logExtractSummary.failed }}（{{ logExtractSummary.sourceCount }} 个来源）</dd></div>
            </dl>
          </section>
          <section v-if="logTask && logTask.steps.length" class="case-log-sec">
            <h4>阶段状态</h4>
            <ul class="case-log-steps">
              <li v-for="step in logTask.steps" :key="step.id">
                <span class="case-log-step-name">{{ stepDisplayName(step) }}</span>
                <a-tooltip v-if="stepDisplayStatus(step) === '异常'" :content="`处理 ${step.count} · 异常 ${step.abnormal}`" position="top">
                  <span :class="['case-log-step-status', `is-${stepDisplayStatus(step)}`]">{{ stepDisplayStatus(step) }}</span>
                </a-tooltip>
                <span v-else :class="['case-log-step-status', `is-${stepDisplayStatus(step)}`]">{{ stepDisplayStatus(step) }}</span>
              </li>
            </ul>
          </section>
          <section class="case-log-sec">
            <h4>执行日志</h4>
            <pre v-if="logLines.length" class="case-log-console">{{ logLines.join('\n') }}</pre>
            <p v-else class="case-log-empty">该执行暂无任务日志。</p>
          </section>
        </template>
        <AppAlert v-else type="warning" class="case-log-missing">该记录未关联工作流执行（无 executionId），无法展示执行日志。</AppAlert>
      </template>
      <template #footer>
        <button type="button" class="case-log-close" @click="logVisible = false">关闭</button>
      </template>
    </a-modal>

    <DeleteConfirmDialog v-model:visible="deleteVisible" title="删除失败记录" :name="deleteTarget?.object || deleteTarget?.id || ''" :identifier="deleteTarget?.id" identifier-label="处理实例 ID" description="继续操作将物理删除该失败记录，连同其草稿、决议和审计记录一并清除，不可恢复。仅未处理记录可删除。" :loading="deleteSubmitting" :error="deleteError" @confirm="confirmDelete" />
  </div>
</template>

<style scoped>
.ops-page{height:100%;overflow:auto;padding-bottom:2px;color:#16233b}.ops-panel{overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:rgba(255,255,255,.94);box-shadow:0 12px 28px rgba(48,105,194,.1)}.ops-filter{display:grid;grid-template-columns:minmax(260px,1fr) repeat(3,160px) auto;gap:10px;padding:14px;border-bottom:1px solid #dce9ff;background:#f7fbff}.ops-filter input,.ops-filter select{height:34px;padding:0 10px;border:1px solid #bdd7ff;border-radius:6px;background:#fff;color:#273957}table{width:100%;border-collapse:collapse;font-size:13px}th,td{height:52px;padding:10px 14px;border-bottom:1px solid #e5edf8;text-align:left;white-space:nowrap}th{position:sticky;z-index:2;top:0;background:#f4f8fd;color:#5a6c88;font-weight:600}td{color:#273957}td small{display:block;margin-top:4px;color:#7b89a1}.alert-actions{display:grid;gap:5px}.alert-tabs{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 14px;border-bottom:1px solid #dce9ff}.alert-tabs nav{display:flex;overflow:auto}.alert-tabs button{padding:13px 14px;border:0;border-bottom:2px solid transparent;background:transparent;color:#52647f;white-space:nowrap;cursor:pointer}.alert-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.alert-tabs label{color:#5f6f88;font-size:12px;white-space:nowrap}.alert-tabs input{margin-right:6px}td a,.link{border:0;background:transparent;color:#165dff;cursor:pointer;text-decoration:none}@media(max-width:1100px){.ops-filter{grid-template-columns:1fr 1fr}.ops-panel{overflow:hidden}}
.review-context{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;padding:12px 14px;border:1px solid #b2ccff;border-radius:7px;background:#f0f5ff}.review-context div{display:grid;gap:3px}.review-context strong{font-size:13px}.review-context span{color:#65738b;font-size:11px}.review-context a{color:#165dff;font-size:12px;text-decoration:none;white-space:nowrap}
.review-evidence{min-width:260px;max-width:360px;white-space:normal;line-height:19px}.review-status{display:inline-flex;padding:3px 8px;border-radius:10px;background:#edf2f7;color:#52647f}.review-status.is-待处理{background:#fff0e8;color:var(--status-warning)}.review-status.is-已完成{background:#e9f8ef;color:var(--status-success)}
.link-disabled{color:#98a2b3;font-size:12px;cursor:default}
.pick-col{width:36px;text-align:center}.pick-col input{cursor:pointer}
.review-severity{min-width:230px;max-width:300px;white-space:normal}.review-severity small{margin:0 0 6px}.review-severity span{display:block;color:#65738b;font-size:11px;line-height:17px}
.review-mask{position:fixed;z-index:49;inset:0;border:0;background:rgba(16,36,76,.24)}.review-drawer{position:fixed;z-index:50;top:0;right:0;display:grid;grid-template-rows:auto minmax(0,1fr) auto;width:620px;height:100vh;background:#f8fbff;box-shadow:-18px 0 42px rgba(34,74,132,.22)}.review-drawer>header{display:flex;justify-content:space-between;padding:20px;border-bottom:1px solid #dce8f8;background:#fff}.review-drawer header span{color:#165dff;font-size:11px}.review-drawer h2{margin:6px 0 3px;font-size:19px}.review-drawer header p{margin:0;color:#70809a;font-size:12px}.review-drawer header>button{width:30px;height:30px;border:0;border-radius:5px;background:#f0f4fa;font-size:20px;cursor:pointer}.review-body{overflow:auto;padding:16px}.review-body section,.review-compare article{padding:14px;border:1px solid #dce8f8;border-radius:7px;background:#fff}.review-body h3{margin:0 0 8px;font-size:14px}.review-body p,.review-body li{color:#61708a;font-size:12px;line-height:20px}.review-compare{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.review-compare span{display:block;margin-bottom:9px;color:#70809a;font-size:11px}.review-compare strong{font-size:13px}.review-compare em{color:#d92d20;font-size:11px;font-style:normal}.review-compare input,.review-compare textarea{width:100%;padding:8px;border:1px solid #bdd0ea;border-radius:5px;font:inherit}.review-compare textarea{min-height:90px;margin-top:8px;resize:vertical}.review-success{padding:10px 12px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3!important;color:#067647!important}.review-drawer>footer{display:flex;justify-content:flex-end;gap:8px;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.review-drawer>footer button{height:34px;padding:0 13px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;cursor:pointer}.review-drawer>footer .primary{border-color:#165dff;background:#165dff;color:#fff}@media(max-width:720px){.review-drawer{width:94vw}.review-compare{grid-template-columns:1fr}}
.ops-page{display:flex;box-sizing:border-box;min-height:0;overflow:hidden;padding-bottom:2px;flex-direction:column}.review-context{flex:0 0 auto}.ops-panel{display:flex;flex:1;min-height:0;flex-direction:column}.alert-tabs,.ops-filter,.review-pagination{flex:0 0 auto}.ops-review-table-scroll{flex:1;min-height:0;max-height:none;overflow:auto}.ops-filter.is-review{grid-template-columns:minmax(280px,1fr) 170px 170px auto}.ops-review-table-scroll table{min-width:1900px}.review-empty{height:100px!important;color:#8290a7;text-align:center!important}.ops-review-table-scroll td code{color:#175cd3;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.review-type-cell{min-width:170px}.review-type-cell>span{display:inline-flex;padding:3px 9px;border-radius:99px;background:#eaf2ff;color:#175cd3;font-size:11px}.review-type-cell>span.is-low-confidence{background:#fff3d8;color:#b54708}.review-type-cell>span.is-extraction{background:#fef3f2;color:#b42318}.review-type-cell>span.is-schema{background:#edf0ff;color:#444ce7}.review-type-cell>span.is-normalization{background:#ecfdf3;color:#067647}.review-type-cell>span.is-other{background:#f2f4f7;color:#475467}
.ops-review-table-scroll table{min-width:1900px}.review-risk-explain{display:grid;flex:0 0 auto;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}.review-risk-explain>div{display:grid;gap:3px;padding:11px 14px;border:1px solid #b9d2f4;border-radius:7px;background:#f7fbff}.review-risk-explain strong{color:#344861;font-size:11px}.review-risk-explain span{color:#6d7c93;font-size:9px;line-height:16px}.review-confidence-cell{min-width:190px;white-space:normal}.review-confidence-cell>b{display:inline-block;margin-right:7px;font-size:13px}.review-confidence-cell>small{display:inline;color:#718098}.review-confidence-cell>span{display:block;margin-top:4px;color:#78869b;font-size:9px;line-height:15px}@media(max-width:900px){.review-risk-explain{grid-template-columns:1fr}}
.review-risk-explain{grid-template-columns:repeat(2,minmax(0,1fr))}.review-risk-explain>div:first-child{border-color:#f5b8b3;background:#fff5f4}.review-risk-explain>div:first-child strong{color:#d92d20}.review-risk-explain>div:nth-child(2){border-color:#f3d08a;background:#fffaf0}.review-risk-explain>div:nth-child(2) strong{color:#b54708}.review-type{min-width:150px}.review-confidence-cell{min-width:130px}.review-confidence-cell>em{display:block;width:max-content;margin-top:5px;padding:2px 7px;border-radius:9px;background:#fff3d8;color:#b54708;font-size:9px;font-style:normal}
.ops-review-table-scroll table{min-width:1288px}
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
.review-status.is-已撤销{background:#f2f4f7;color:var(--status-neutral)}
.review-status.is-已驳回{background:#f2f4f7;color:var(--status-danger)}
</style>
<style scoped>
/* DESIGN_RULES: manual review list contract. */
.ops-page{padding:0;color:#1d2129}
.ops-panel{border-color:#e5e6eb;border-radius:6px;background:#fff;box-shadow:none}
.ops-filter,.ops-filter.is-review{box-sizing:border-box;width:100%;grid-template-columns:minmax(280px,1fr) minmax(160px,200px) minmax(160px,200px) auto;column-gap:16px!important;row-gap:16px!important;padding:16px!important;background:#fff}
.alert-tabs nav button{height:36px;padding:0 16px;font-size:14px;line-height:22px}.alert-tabs nav button.active{font-weight:500}
.ops-filter input,.ops-filter select,.ops-filter button{height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px}.ops-filter button{padding:0 16px}
.ops-review-table-scroll table{min-width:1288px;font-size:14px;line-height:22px}.ops-review-table-scroll th,.ops-review-table-scroll td{height:40px;padding:0 16px}.ops-review-table-scroll th{background:#f7f8fa;color:#1d2129;font-weight:500}
.ops-review-table-scroll td small,.review-source-cell strong,.review-question-cell strong,.review-confidence-cell>b{font-size:12px;line-height:20px}
.review-status{display:inline-flex;align-items:center;gap:6px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px}.review-status::before{display:block;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}
.review-status.is-待处理,.review-status.is-已完成,.review-status.is-已撤销,.review-status.is-已驳回{background:transparent}
.review-risk-explain{grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;margin-bottom:16px}.review-risk-explain>div{gap:4px;padding:8px 16px;border-radius:6px;background:#f7f8fa}.review-risk-explain strong{font-size:14px;line-height:22px}.review-risk-explain span,.review-confidence-cell>span{font-size:12px;line-height:20px}
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
.review-tabs{display:flex;box-sizing:border-box;width:100%;margin-bottom:16px;padding:0;border:0;background:transparent;flex-direction:column;align-items:flex-start;justify-content:flex-start;gap:12px;flex:0 0 auto}
.review-tabs>nav{display:flex;box-sizing:border-box;height:40px;padding:4px;border-radius:4px;background:#f2f3f5;flex:0 0 auto;overflow:visible}
.review-tabs>nav button{display:inline-flex;box-sizing:border-box;align-items:center;justify-content:center;width:120px;height:32px;padding:5px 16px;border:0;border-radius:4px;background:transparent;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;text-align:center}
.review-tabs>nav button+button{border-left:1px solid #c9cdd4}
.review-tabs>nav button.active{border-left-color:transparent;background:#fff;color:#165dff;font-weight:500}
.review-tabs>nav button.active+button{border-left-color:transparent}
.review-tabs>nav button:hover:not(.active){background:#fff;color:#165dff}
.review-toolbar-actions{display:flex;width:100%;min-width:0;align-items:center;justify-content:flex-end;gap:16px;flex:0 0 auto;flex-wrap:wrap}
.review-tabs .ops-filter.is-review{display:flex;box-sizing:border-box;width:auto;min-width:0;margin-left:auto;align-items:center;justify-content:flex-end;grid-template-columns:none;gap:16px!important;padding:0!important;border:0;background:transparent;flex:0 1 auto;flex-wrap:wrap}
.review-search-button{box-sizing:border-box;height:32px;padding:0 16px;border:1px solid #165dff!important;border-radius:4px;background:#165dff!important;color:#fff!important;font-size:14px;line-height:22px;cursor:pointer}
.review-search-button:hover{border-color:#4080ff!important;background:#4080ff!important}
.review-search-button:focus-visible{outline:2px solid rgba(22,93,255,.3);outline-offset:2px}
.review-filter-row :deep(.review-filter-select.arco-select-view){flex:0 0 160px;width:160px}
.review-filter-row :deep(.review-filter-search.arco-input-wrapper){flex:0 0 280px;width:280px}
.review-tabs .ops-filter.is-review :deep(.arco-select-view-value){font-size:14px;line-height:22px;font-weight:400}
.ops-review-table-scroll td{color:#344763;font-size:14px;line-height:22px;font-weight:400;vertical-align:middle}
.ops-review-table-scroll td>b,.ops-review-table-scroll td>strong{font-weight:400}
/* 抽取失败重跑：批量重跑按钮 / 重跑反馈条 / 状态徽标扩展 */
/* 批量重跑沿用日志的文字链接样式。 */
.rerun-confirm-bar{display:inline-flex;align-items:center;gap:8px;flex:0 0 auto;color:#4e5969;font-size:13px;line-height:22px;white-space:nowrap}
.review-pagination .review-page-summary{margin-left:auto;white-space:nowrap}
/* 批量重跑反馈：四态底色/提示符/关闭按钮由 AppAlert（Arco Alert 规范）提供 */
.rerun-feedback{flex:0 0 auto;margin:0 0 10px}
/* 查看档只读提示条（共享生产空间）：警告态底色与提示符由 AppAlert 提供 */
.review-readonly-bar{flex:0 0 auto;margin:0 0 10px}
/* 队列加载失败态：错误态提示条 + 重新加载入口 */
.review-load-error{display:flex;flex-direction:column;align-items:center;gap:8px}
.review-load-error__alert{max-width:720px;text-align:left}
.rerun-confirm-text{margin:0}
.review-status.is-重跑中,.review-status.is-执行中{color:var(--status-info)}
.review-status.is-重跑失败,.review-status.is-失败{color:var(--status-danger)}
.review-status.is-已完成{color:var(--status-success)}
.review-status.is-排队中{color:var(--status-neutral)}
.review-status.is-已取消{color:var(--status-neutral)}

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
.alert-actions{gap:4px}
.pick-col{box-sizing:border-box;width:52px;min-width:52px;padding-right:16px!important;padding-left:16px!important}
/* 审核分页已迁移到共享 ListPagination 组件（样式随组件自带）；.review-pagination 仅保留 flex 布局占位。 */
.ops-review-table-scroll .pick-col{vertical-align:middle;text-align:center}.ops-review-table-scroll .pick-col input[type="checkbox"]{display:block;width:14px;height:14px;margin:0 auto;vertical-align:middle;cursor:pointer}
.rerun-batch-action:focus-visible{outline:0;box-shadow:0 0 0 2px rgba(22,93,255,.2)}
/* 操作列与 Schema 管理表对齐：右侧固定列（表头同时吸顶，z 高于数据行），横向滚动时操作不被遮挡 */
.ops-review-table-scroll th.review-action-col{position:sticky;top:0;right:0;z-index:4;background:#f7f8fa;box-shadow:-1px 0 #e5e6eb;text-align:left}
.ops-review-table-scroll td.review-action-col{position:sticky;right:0;z-index:3;box-sizing:border-box;background:#fff;box-shadow:-1px 0 #e5e6eb;white-space:nowrap}
/* 固定列左侧向内容区渐隐的阴影（与 Schema 管理表同视觉提示） */
.ops-review-table-scroll.has-scroll-right :is(th,td).review-action-col::before{position:absolute;top:0;bottom:-1px;left:0;width:12px;content:"";pointer-events:none;transform:translateX(-100%);box-shadow:inset -10px 0 8px -8px rgba(78,89,105,.28)}
.review-action-col .alert-actions{display:flex;width:100%;min-width:0;align-items:center;justify-content:flex-start;gap:8px}
.ops-review-table-scroll th,.ops-review-table-scroll td{box-sizing:border-box;padding-right:16px;padding-left:16px}
/* 固定列合计 1076px，最小表宽为对象列保留 268px；勾选列额外占 52px。 */
.ops-review-table-scroll table.review-case-table{width:100%;min-width:1288px;table-layout:fixed}
.ops-review-table-scroll table.review-case-table--selectable{min-width:1340px}
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
.review-case-table col.col-actions{width:144px}
.ops-review-table-scroll .review-id-cell{overflow:hidden;text-overflow:ellipsis}
.ops-review-table-scroll .review-id-cell :is(code,.link){display:inline-block;box-sizing:border-box;max-width:100%;overflow:hidden;text-overflow:ellipsis;vertical-align:bottom}
/* 滚动条出现/消失（数据多少切换）不挤动列宽 */
.ops-review-table-scroll{scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:transparent transparent}
.ops-review-table-scroll:hover,.ops-review-table-scroll.review-scroll--active{scrollbar-color:rgba(78,89,105,.55) transparent}
.ops-review-table-scroll::-webkit-scrollbar{width:8px;height:8px}
.ops-review-table-scroll::-webkit-scrollbar-track{background:transparent}
.ops-review-table-scroll::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background-color:transparent;background-clip:padding-box}
.ops-review-table-scroll:hover::-webkit-scrollbar-thumb,.ops-review-table-scroll.review-scroll--active::-webkit-scrollbar-thumb{background-color:rgba(78,89,105,.55)}
.ops-review-table-scroll::-webkit-scrollbar-thumb:hover{background-color:rgba(78,89,105,.8)}
/* 筛选字段标签 / 类型徽标 / 勾选禁用态 / 删除按钮 */
.review-filter-field{display:flex;flex:0 0 auto;align-items:center;gap:8px}
.review-filter-label{color:#4e5969;font-size:14px;line-height:22px;white-space:nowrap}
/* 处理实例 ID 纯文本：中性色，区别于可点击的链接蓝 */
.review-id-cell .review-id-plain{color:#4e5969}
.review-kind-badge{display:inline-flex;white-space:nowrap;padding:0 8px;border-radius:4px;background:#f2f3f5;color:#4e5969;font-size:12px;line-height:20px}
.review-kind-badge.is-实体{background:#eaf2ff;color:#175cd3}
.review-kind-badge.is-关系{background:#fff3d8;color:#b54708}
/* 操作列按钮化：查看记录（A 类）/ 日志、重跑、删除（C 类）统一为描边按钮，删除红色警示 */
/* 操作按钮与 Schema 管理表同款：无边框纯文字链接；删除红、其余蓝、禁用灰 */
.review-action-btn{height:auto;padding:0;border:0;background:transparent;color:#165dff;font-size:14px;line-height:22px;font-weight:400;white-space:nowrap;text-decoration:none;cursor:pointer}
.review-action-btn:hover:not(:disabled){color:#4080ff;text-decoration:none}
.review-action-btn:disabled{color:#a9b4c6;cursor:not-allowed;text-decoration:none}
.review-action-btn.is-danger{color:#e5484d}
.review-action-btn.is-danger:hover:not(:disabled){color:#b42318}
.ops-review-table-scroll .pick-col input[type="checkbox"]:disabled{opacity:.35;cursor:not-allowed}
/* 日志弹窗内容（弹体外壳样式在全局块） */
.case-log-sec{margin:0 0 16px}
.case-log-sec:last-child{margin-bottom:0}
.case-log-sec h4{margin:0 0 8px;color:#1d2129;font-size:14px;line-height:22px;font-weight:600}
/* dt/dd 两列网格下沉到行 div：dl 直接网格化会把整行 div 当格子，落在 88px 窄格的值被硬折行 */
.case-log-dl{display:grid;gap:6px 0;margin:0}
.case-log-dl>div{display:grid;grid-template-columns:88px 1fr;column-gap:12px}
.case-log-dl dt{color:#86909c;font-size:12px;line-height:20px}
.case-log-dl dd{margin:0;color:#1d2129;font-size:13px;line-height:20px;overflow-wrap:anywhere}
.case-log-error-block{margin:0}
.case-log-error-text{margin:0;font:12px/19px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-all}
.case-log-loading{margin:0;padding:24px;color:#86909c;text-align:center}
/* 执行日志弹窗：原执行/重跑执行切换 + 概要 + 阶段状态 + 日志终端 */
.case-log-switch{display:flex;box-sizing:border-box;width:max-content;height:40px;margin:0 0 16px;padding:4px;border-radius:4px;background:#f2f3f5;overflow:visible}
.case-log-switch button{display:inline-flex;box-sizing:border-box;align-items:center;justify-content:center;width:120px;height:32px;padding:5px 16px;border:0;border-radius:4px;background:transparent;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;cursor:pointer}
.case-log-switch button+button{border-left:1px solid #c9cdd4}
.case-log-switch button.active{border-left-color:transparent;background:#fff;color:#165dff;font-weight:500}
.case-log-switch button.active+button{border-left-color:transparent}
.case-log-switch button:hover:not(.active){background:#fff;color:#165dff}
.case-log-missing{margin:0;word-break:break-all}
.case-log-console{margin:0;max-height:280px;overflow:auto;padding:12px 14px;border:1px solid #e5e6eb;border-radius:4px;background:#f7f8fa;color:#1d2129;font:12px/20px ui-monospace,SFMono-Regular,Menlo,monospace;white-space:pre-wrap;word-break:break-all}
.case-log-steps{display:flex;flex-wrap:wrap;gap:8px;margin:0;padding:0;list-style:none}
.case-log-steps li{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:12px;line-height:20px}
.case-log-step-name{color:#4e5969}
/* 阶段状态与执行概要状态：系统标准「6px 语义色圆点 + 文字」，五类语义色 */
.case-log-step-status{display:inline-flex;align-items:center;gap:6px;color:var(--status-info)}
.case-log-step-status::before{content:"";flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:currentColor}
.case-log-step-status.is-成功{color:var(--status-success)}
.case-log-step-status.is-运行中{color:var(--status-info)}
.case-log-step-status.is-异常{color:var(--status-warning)}
.case-log-step-status.is-需人工处理{color:var(--status-danger)}
.case-log-step-status.is-待执行{color:var(--status-neutral)}
.case-log-exec-status{display:inline-flex;align-items:center;gap:6px}
.case-log-exec-status::before{content:"";flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:currentColor}
.case-log-exec-status.ok{color:var(--status-success)}
.case-log-exec-status.warn{color:var(--status-warning)}
.case-log-exec-status.err{color:var(--status-danger)}
.case-log-exec-status.run{color:var(--status-info)}
.case-log-exec-status.idle{color:var(--status-neutral)}
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
/* 删除确认沿用短确认弹窗尺寸，标题左对齐，危险操作与 Schema 删除按钮同色。 */
.delete-confirm-modal .arco-modal-title{justify-content:flex-start;text-align:left}
.delete-confirm-modal .arco-modal-footer .arco-btn-primary{border-color:#e5484d;background:#e5484d;color:#fff}
.delete-confirm-modal .arco-modal-footer .arco-btn-primary:hover:not(:disabled){border-color:#b42318;background:#b42318}
/* 日志弹窗（teleport 到 body，需全局控制弹体） */
.case-log-modal{border-radius:8px;font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.case-log-modal .arco-modal-header{box-sizing:border-box;height:56px;padding:0 24px}.case-log-modal .arco-modal-title{justify-content:flex-start;text-align:left;font-size:16px;line-height:24px;font-weight:600;letter-spacing:0}.case-log-modal .arco-modal-body{max-height:70vh;overflow:auto;padding:16px 24px}.case-log-modal .arco-modal-footer{box-sizing:border-box;min-height:64px;padding:16px 24px;border-top:1px solid #e5e6eb}.case-log-modal .case-log-close{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:22px;cursor:pointer}
</style>
