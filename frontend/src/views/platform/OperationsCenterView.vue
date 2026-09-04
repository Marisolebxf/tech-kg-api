<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { IconSearch } from '@arco-design/web-vue/es/icon'

import { getExecution, getProductionReviews, listExecutions, rerunExtractFailures, type ProductionReviewCase, type ReviewRecord } from '../../api/workflowOperations'
import { clampSearchKeyword, SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import {
  getImpactScope,
  resolvePipelineStep,
} from './manual-review-data'
import {
  extractCaseStatusBadge,
  isRerunExecutionRunning,
  mapRerunExecutionRow,
  type RerunExecutionRow,
} from './rerun-history'

type CenterMode = 'alerts' | 'review'

const props = defineProps<{ mode: CenterMode }>()
const route = useRoute()
const keyword = ref(clampSearchKeyword(String(route.query.keyword || '')))
const status = ref('全部状态')
const domain = ref('全部业务域')
/** 人工审核筛选：状态分组（待处理/已处理）与对象种类（实体/关系/都看）；C 类额外支持 重跑中/重跑失败 精确过滤。
 *  undefined = 未选择（清空），语义等同「全部」。 */
const reviewStatusFilter = ref<'全部' | '待处理' | '已处理' | '重跑中' | '重跑失败' | undefined>('全部')
const reviewKindFilter = ref<'全部' | '实体' | '关系' | undefined>('全部')
const reviewTotal = ref(0)
const severity = ref('全部风险')
const actionFeedback = ref('')
const alertCategory = ref('全部异常')
const blockingOnly = ref(false)
const reviewRecords = ref<ReviewRecord[]>([])
const reviewLoadError = ref('')

const alertCategories = ['全部异常', '数据质量', 'Schema 校验', '大模型抽取', '实体对齐', '图谱入库', '服务运行']

const alertRows = [
  { id: 'ALT-0714-018', level: '高风险', category: '大模型抽取', module: '图谱构建', node: '大模型抽取', domain: '论文', batch: 'UPD-20260714', reason: '同一模型与 Prompt 版本连续产生不符合 Schema 的批量输出', impact: '流程级 · 326 条受影响', strategy: '当前节点及下游已阻断', owner: '张建图', time: '07-14 10:24', status: '待处理', blocked: true, target: '/graph-build?module=图谱构建&batch=UPD-20260714' },
  { id: 'ALT-0714-014', level: '中风险', category: '数据质量', module: '数据处理', node: '质量检验', domain: '论文', batch: 'UPD-20260714', reason: '385 条记录命中唯一性、必填或枚举规则', impact: '任务级 · 385 条已隔离', strategy: '其他任务继续执行', owner: '李质量', time: '07-14 09:48', status: '待处理', blocked: false, target: '/graph-build?module=数据处理&batch=UPD-20260714' },
  { id: 'ALT-0713-012', level: '中风险', category: '服务运行', module: '服务调用', node: '专家关系 Tool', domain: '人才', batch: 'CALL-20260713-1058', reason: 'P95 响应耗时超过 2 秒阈值', impact: '调用级 · 18 次慢调用', owner: '李运维', time: '07-13 10:58', status: '处理中', blocked: false, target: '/graph-tools' },
  { id: 'ALT-0713-106', level: '中风险', category: '实体对齐', module: '图谱构建', node: '实体消歧', domain: '专利', batch: 'UPD-20260713', reason: '候选实体置信度低于 0.75', impact: '任务级 · 42 个候选已处理', owner: '王审核', time: '07-13 18:06', status: '已关闭', blocked: false, target: '/graph-build?module=图谱构建&batch=UPD-20260713' },
  { id: 'ALT-0712-099', level: '低风险', category: 'Schema 校验', module: '图谱构建', node: '字段映射', domain: '企业', batch: 'KG-INC-20260712-099', reason: '2 个新增字段未匹配当前 Schema', impact: '12 条隔离 · 已恢复', owner: '张建图', time: '07-12 14:08', status: '已关闭', blocked: false, target: '/schema' },
  { id: 'ALT-0712-088', level: '低风险', category: '服务运行', module: '服务调用', node: '子图分析 Tool', domain: '产业链', batch: 'CALL-20260712-1031', reason: '查询结果达到最大节点数量限制', impact: '3 次截断 · 未阻断', owner: '王算法', time: '07-12 10:31', status: '已关闭', blocked: false, target: '/graph-tools' },
  { id: 'ALT-0711-072', level: '中风险', category: '图谱入库', module: '图谱构建', node: '增量写入', domain: '人才', batch: 'KG-FULL-20260711-008', reason: '写入吞吐低于近七日基线 20%', impact: '批次级 · 延迟 26 分钟', owner: '张建图', time: '07-11 23:46', status: '已关闭', blocked: false, target: '/task-detail/construction/KG-FULL-20260711-008?step=persist' },
  { id: 'ALT-0711-061', level: '低风险', category: '数据质量', module: '数据处理', node: '标准表写入', domain: '专利', batch: 'DP-20260711-1800', reason: '任务执行时间接近超时阈值', impact: '1 个批次 · 已恢复', owner: '李质量', time: '07-11 18:22', status: '已关闭', blocked: false, target: '/task-detail/processing/DP-20260711-1800?step=write' },
]


const metrics = [
  { label: '高风险待处理', value: '1', hint: '流程级异常' },
  { label: '已阻断流程', value: '1', hint: '调整后才继续下游' },
  { label: '隔离记录', value: '711', hint: '待人工或规则复核' },
  { label: '处理中', value: '2', hint: '已指派责任人' },
  { label: '已超时', value: '1', hint: '超过处置 SLA' },
  { label: '今日已关闭', value: '12', hint: '平均处置 12.6 分钟' },
]

const primaryActionLabel = '刷新检测结果'

const runPrimaryAction = () => {
  actionFeedback.value = '检测结果已刷新，异常状态与任务阻断状态保持同步。'
}

const resetFilters = () => {
  keyword.value = ''
  status.value = '全部状态'
  domain.value = '全部业务域'
  reviewStatusFilter.value = '全部'
  reviewKindFilter.value = '全部'
  severity.value = '全部风险'
  alertCategory.value = '全部异常'
  blockingOnly.value = false
}

const filteredAlertRows = computed(() => alertRows.filter((row) => {
    const text = Object.values(row).join(' ')
    return (!keyword.value || text.includes(keyword.value))
      && (!alertCategory.value || alertCategory.value === '全部异常' || text.includes(alertCategory.value))
      && (!severity.value || severity.value === '全部风险' || text.includes(severity.value))
      && (!blockingOnly.value || row.blocked)
      && (!status.value || status.value === '全部状态' || text.includes(status.value))
      && (!domain.value || domain.value === '全部业务域' || text.includes(domain.value.replace('域', '')))
      && (!route.query.batch || text.includes(String(route.query.batch)))
}))

const reviewRows = computed(() => reviewRecords.value)

/** 分页状态：服务端分页，翻页/改页大小都会重新拉取当前筛选下的数据。 */
const reviewPage = ref(1)
const reviewPageSize = ref(10)
const reviewPageSizeOptions = [10, 20, 50]
const reviewTotalPages = computed(() => Math.max(1, Math.ceil(reviewTotal.value / reviewPageSize.value)))

watch(() => route.query.keyword, (value) => { keyword.value = clampSearchKeyword(String(value || '')) })

/** 审核队列分类：A=入库决策（T_DIRECT/T_LINK/T_EVIDENCE）；C=抽取失败重跑（T_EXTRACT_FAIL）。 */
const reviewCategory = ref<'A' | 'C'>('A')
/** C 类二级视图：cases=失败列表（默认）；history=重跑记录（按执行维度）。 */
const rerunView = ref<'cases' | 'history'>('cases')
/** C 类勾选的待重跑 case。 */
const rerunSelection = ref<Set<string>>(new Set())
const rerunSubmitting = ref(false)
/** 批量重跑结果反馈（替代 alert）：展示新执行可跳转链接，15s 自动消失。 */
const rerunFeedback = ref<{ type: 'success' | 'error'; text: string; executions: Array<{ executionId: string; schemaId: string; cases: number; records: number }> } | null>(null)
/** 勾选 >20 条时的 a-modal 二次确认。 */
const rerunConfirmVisible = ref(false)
/** 重跑记录（triggerSource=RERUN 执行）行 + 轮询状态。 */
const rerunExecutions = ref<RerunExecutionRow[]>([])
const rerunHistoryLoading = ref(false)
const rerunHistoryError = ref('')
let rerunPollTimer: number | undefined
let rerunFeedbackTimer: number | undefined

/** A 类只有 全部/待处理/已处理；C 类追加 重跑中/重跑失败（后端 status 精确过滤）。 */
const reviewStatusOptions = computed(() => (
  reviewCategory.value === 'C'
    ? ['全部', '待处理', '已处理', '重跑中', '重跑失败']
    : ['全部', '待处理', '已处理']
))

/** 当前页 OPEN 行的全选/半选态（跨页勾选由 rerunSelection 保持，按钮数字展示总数）。 */
const rerunPageOpenIds = computed(() => reviewRows.value.filter((row) => row.rawStatus === 'OPEN').map((row) => row.id))
const rerunAllChecked = computed(() => rerunPageOpenIds.value.length > 0 && rerunPageOpenIds.value.every((id) => rerunSelection.value.has(id)))
const rerunSomeChecked = computed(() => !rerunAllChecked.value && rerunPageOpenIds.value.some((id) => rerunSelection.value.has(id)))

function switchReviewCategory(category: 'A' | 'C') {
  if (reviewCategory.value === category) return
  reviewCategory.value = category
  rerunView.value = 'cases'
  stopRerunPoll()
  rerunSelection.value = new Set()
  reviewPage.value = 1
  void loadReviews()
}

function switchRerunView(view: 'cases' | 'history') {
  if (rerunView.value === view) return
  rerunView.value = view
  if (view === 'history') void loadRerunExecutions()
  else stopRerunPoll()
}

function toggleRerunPick(id: string, checked: boolean) {
  if (checked) rerunSelection.value.add(id)
  else rerunSelection.value.delete(id)
}

function showRerunFeedback(type: 'success' | 'error', text: string, executions: Array<{ executionId: string; schemaId: string; cases: number; records: number }>) {
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
    showRerunFeedback('success', `已下发重跑：${result.cases} 条失败记录 → ${result.executions.length} 个新执行（类别=重新执行）`, result.executions)
    rerunSelection.value = new Set()
    void loadReviews()
    if (rerunView.value === 'history') void loadRerunExecutions()
  } catch (error) {
    showRerunFeedback('error', error instanceof Error ? error.message : '重跑下发失败', [])
  } finally {
    rerunSubmitting.value = false
  }
}

async function loadRerunExecutions() {
  rerunHistoryLoading.value = true
  try {
    const response = await listExecutions(50, { triggerSource: 'RERUN' })
    rerunExecutions.value = response.items.map(mapRerunExecutionRow)
    rerunHistoryError.value = ''
  } catch (error) {
    rerunHistoryError.value = error instanceof Error ? error.message : '重跑记录加载失败'
  } finally {
    rerunHistoryLoading.value = false
  }
  scheduleRerunPoll()
}

/** 列表接口不触发 Temporal refresh，RUNNING 行需逐条 getExecution 单刷（会刷新并落库）。 */
async function refreshRunningRerunExecutions() {
  const running = rerunExecutions.value.filter(isRerunExecutionRunning)
  if (!running.length) return
  const results = await Promise.all(running.map((row) => getExecution(row.executionId).catch(() => null)))
  const byId = new Map(rerunExecutions.value.map((row) => [row.executionId, row]))
  for (const execution of results) {
    if (execution) byId.set(execution.id, mapRerunExecutionRow(execution))
  }
  rerunExecutions.value = [...byId.values()]
}

/** 子视图可见且存在 RUNNING 行时每 8s 轮询单刷；切视图/切 tab/卸载都会停。 */
function scheduleRerunPoll() {
  window.clearTimeout(rerunPollTimer)
  if (props.mode !== 'review' || reviewCategory.value !== 'C' || rerunView.value !== 'history') return
  if (!rerunExecutions.value.some(isRerunExecutionRunning)) return
  rerunPollTimer = window.setTimeout(async () => {
    await refreshRunningRerunExecutions()
    scheduleRerunPoll()
  }, 8000)
}

function stopRerunPoll() {
  window.clearTimeout(rerunPollTimer)
  rerunPollTimer = undefined
}

onUnmounted(() => {
  stopRerunPoll()
  window.clearTimeout(rerunFeedbackTimer)
})

async function loadReviews() {
  if (props.mode !== 'review') return
  try {
    // A=入库决策（T_DIRECT/T_LINK/T_EVIDENCE）；C=抽取失败重跑（T_EXTRACT_FAIL）；
    // B 类数据修正在 TODO，先不混入
    const response = await getProductionReviews({
      category: reviewCategory.value,
      keyword: keyword.value || undefined,
      statusGroup: reviewStatusFilter.value === '待处理' ? 'pending' : reviewStatusFilter.value === '已处理' ? 'processed' : undefined,
      status: reviewStatusFilter.value === '重跑中' ? 'RERUNNING' : reviewStatusFilter.value === '重跑失败' ? 'RERUN_FAILED' : undefined,
      kind: !reviewKindFilter.value || reviewKindFilter.value === '全部' ? undefined : reviewKindFilter.value === '实体' ? 'entity' : 'relation',
      page: reviewPage.value,
      pageSize: reviewPageSize.value,
    })
    reviewTotal.value = response.total
    // 筛选后总页数变小时收敛当前页（如翻到第 3 页后把筛选改成只有 1 页数据）
    if (reviewPage.value > Math.max(1, Math.ceil(response.total / reviewPageSize.value))) {
      reviewPage.value = Math.max(1, Math.ceil(response.total / reviewPageSize.value))
      return loadReviews()
    }
    reviewRecords.value = response.items.map((row: ProductionReviewCase) => ({
      id: row.id, templateId: row.templateId, rawStatus: row.status, batch: row.batchId || '-', module: row.phase, node: row.nodeId, type: row.errorType, category: row.category, domain: row.domain, objectType: row.objectType, objectId: row.objectId, object: row.objectName, ruleId: row.templateId, evidence: `${row.evidence?.length || 0} 项`, score: row.riskLevel, handler: row.assigneeName || '待领取', status: extractCaseStatusBadge(row.status), updatedAt: row.updatedAt, sourceResult: row.diagnosis, suggestion: row.scope, sourceTable: row.sourceTable || '-', sourceRecordId: row.sourceRecordId || '-', confidenceValue: row.riskLevel, confidenceLabel: row.status,
    }))
    reviewLoadError.value = ''
  } catch (error) { reviewLoadError.value = error instanceof Error ? error.message : '人工处理队列加载失败' }
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

/** 筛选条件变化：回到第 1 页重新加载（重跑记录子视图不消费这些筛选）。 */
watch([reviewStatusFilter, reviewKindFilter], () => {
  if (props.mode !== 'review' || (reviewCategory.value === 'C' && rerunView.value === 'history')) return
  reviewPage.value = 1
  void loadReviews()
})

/** 关键字输入防抖后走服务端检索（与分页/筛选同口径，避免页内客户端过滤与总数不一致）。 */
let reviewKeywordTimer: number | undefined
watch(keyword, () => {
  if (props.mode !== 'review' || (reviewCategory.value === 'C' && rerunView.value === 'history')) return
  window.clearTimeout(reviewKeywordTimer)
  reviewKeywordTimer = window.setTimeout(() => {
    reviewPage.value = 1
    void loadReviews()
  }, 300)
})
onMounted(loadReviews)
</script>

<template>
  <div class="ops-page">
    <template v-if="mode === 'alerts'">
      <header class="ops-head">
        <div><h1>异常治理</h1></div>
        <button class="primary" type="button" @click="runPrimaryAction">{{ primaryActionLabel }}</button>
      </header>

      <section class="ops-metrics is-alerts">
        <article v-for="item in metrics" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><em v-if="item.hint">{{ item.hint }}</em></article>
      </section>

      <p v-if="actionFeedback" class="ops-feedback">{{ actionFeedback }}</p>
    </template>
    <div v-if="mode === 'review'" class="alert-tabs review-tabs">
      <nav>
        <button type="button" :class="{ active: reviewCategory === 'A' }" @click="switchReviewCategory('A')">入库决策</button>
        <button type="button" :class="{ active: reviewCategory === 'C' }" @click="switchReviewCategory('C')">抽取失败重跑</button>
      </nav>
      <div class="review-toolbar-actions">
        <div
          v-if="reviewCategory === 'A' || rerunView === 'cases'"
          class="ops-filter is-review review-filter-row"
        >
          <a-select v-model="reviewStatusFilter" class="review-filter-select" :options="reviewStatusOptions" />
          <a-select v-model="reviewKindFilter" class="review-filter-select" :options="['全部', '实体', '关系']" />
          <a-input v-model="keyword" class="review-search-input review-filter-search" :max-length="SEARCH_KEYWORD_MAX_LENGTH" aria-label="搜索处理实例 ID、对象或来源记录" placeholder="搜索处理实例 ID、对象或来源记录"><template #prefix><IconSearch /></template></a-input>
        </div>
      </div>
    </div>

    <section class="ops-panel">
      <div v-if="mode === 'review' && reviewCategory === 'C'" class="rerun-subtabs">
        <nav>
          <button type="button" :class="{ active: rerunView === 'cases' }" @click="switchRerunView('cases')">失败列表</button>
          <button type="button" :class="{ active: rerunView === 'history' }" @click="switchRerunView('history')">重跑记录</button>
        </nav>
        <button
          v-if="rerunView === 'cases'"
          class="rerun-batch-action"
          type="button"
          :disabled="!rerunSelection.size || rerunSubmitting"
          @click="rerunSelected()"
        >{{ rerunSubmitting ? '下发中…' : `批量重跑（${rerunSelection.size}）` }}</button>
        <button
          v-else
          class="rerun-refresh"
          type="button"
          :disabled="rerunHistoryLoading"
          @click="loadRerunExecutions"
        >{{ rerunHistoryLoading ? '加载中…' : '刷新' }}</button>
      </div>

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

      <div v-if="mode === 'alerts'" class="alert-tabs"><nav><button v-for="item in alertCategories" :key="item" type="button" :class="{ active:alertCategory===item }" @click="alertCategory=item">{{ item }}</button></nav><a-checkbox v-model="blockingOnly">仅看已阻断</a-checkbox></div>
      <a-form v-if="mode === 'alerts'" :model="{ keyword, severity, domain, status }" class="ops-filter" layout="vertical">
        <a-form-item field="keyword"><input v-model="keyword" :maxlength="SEARCH_KEYWORD_MAX_LENGTH" aria-label="搜索批次、对象、异常原因" placeholder="搜索批次、对象、异常原因" /></a-form-item>
        <a-form-item field="severity"><a-select v-model="severity" allow-clear placeholder="全部风险" :options="['全部风险', '高风险', '中风险', '低风险']" /></a-form-item>
        <a-form-item field="domain"><a-select v-model="domain" allow-clear placeholder="全部业务域" :options="['全部业务域', '人才域', '论文域', '企业域']" /></a-form-item>
        <a-form-item field="status"><a-select v-model="status" allow-clear placeholder="全部状态" :options="['全部状态', '待处理', '处理中', '已关闭']" /></a-form-item>
        <a-form-item><button type="button" @click="resetFilters">清空筛选</button></a-form-item>
      </a-form>

      <div v-if="mode === 'alerts'" class="ops-table-scroll"><table>
        <thead><tr><th>异常编号 / 风险</th><th>异常类型</th><th>模块 / 节点</th><th>业务域</th><th>任务批次</th><th>异常说明</th><th>影响范围 / 阻断策略</th><th>责任人</th><th>发生时间</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in filteredAlertRows" :key="row.id"><td><strong>{{ row.id }}</strong><small :class="`level-${row.level}`">{{ row.level }}</small></td><td><b>{{ row.category }}</b></td><td><b>{{ row.module }}</b><small>{{ row.node }}</small></td><td>{{ row.domain }}</td><td><code>{{ row.batch }}</code></td><td class="alert-reason">{{ row.reason }}</td><td class="alert-impact"><strong>{{ row.impact }}</strong><small>{{ row.strategy || (row.blocked ? '阻断当前节点及下游' : '不阻断流程，按告警策略处理') }}</small></td><td>{{ row.owner }}</td><td>{{ row.time }}</td><td><span :class="['alert-status', `is-${row.status}`]">{{ row.status }}</span></td><td><div class="alert-actions"><RouterLink :to="row.target">查看诊断</RouterLink><RouterLink v-if="row.status !== '已关闭' && row.module !== '服务调用'" :to="`/manual-review?batch=${row.batch}`">人工审核</RouterLink></div></td></tr></tbody>
      </table></div>

      <div v-else-if="rerunView === 'history'" class="ops-review-table-scroll rerun-history-scroll"><table>
        <thead>
          <tr>
            <th>执行 ID</th>
            <th>Schema</th>
            <th>状态</th>
            <th>触发时间</th>
            <th>重跑记录</th>
            <th>失败记录</th>
            <th>来源执行</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rerunExecutions" :key="row.executionId">
            <td class="review-id-cell"><RouterLink class="link" :to="`/processing-instance/${row.executionId}`">{{ row.executionId }}</RouterLink></td>
            <td><code>{{ row.schemaId }}</code></td>
            <td><span :class="['review-status', `is-${row.statusLabel}`]">{{ row.statusLabel }}</span></td>
            <td>{{ row.startedAt }}</td>
            <td>{{ row.caseCount ?? '—' }} 条 / {{ row.recordCount ?? '—' }} 行</td>
            <td><span :class="{ 'rerun-fail-count': (row.failureCount ?? 0) > 0 }">{{ row.failureCount ?? '—' }}</span></td>
            <td>
              <RouterLink v-if="row.rerunOfExecutionId" class="link" :to="`/processing-instance/${row.rerunOfExecutionId}`">{{ row.rerunOfExecutionId }}</RouterLink>
              <template v-else>—</template>
            </td>
            <td><RouterLink class="link" :to="`/processing-instance/${row.executionId}`">查看详情 →</RouterLink></td>
          </tr>
          <tr v-if="!rerunExecutions.length">
            <td class="review-empty" :colspan="8">{{ rerunHistoryError || '暂无重跑记录' }}</td>
          </tr>
        </tbody>
      </table></div>

      <div v-else class="ops-review-table-scroll"><table>
        <thead>
          <tr>
            <th v-if="reviewCategory === 'C'" class="pick-col"><input
              type="checkbox"
              :checked="rerunAllChecked"
              :indeterminate="rerunSomeChecked"
              @change="((event?: Event) => {
                const checked = ((event?.target as HTMLInputElement) || {} as HTMLInputElement).checked
                reviewRows.forEach((row) => toggleRerunPick(row.id, checked && row.rawStatus === 'OPEN'))
              })()"
            /></th>
            <th>处理实例 ID</th>
            <th>待处理对象</th>
            <th>阻断节点</th>
            <th>来源记录</th>
            <th>更新批次</th>
            <th>处理人</th>
            <th>状态</th>
            <th>更新时间</th>
            <th>操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in reviewRows" :key="row.id">
            <td v-if="reviewCategory === 'C'" class="pick-col"><input
              v-if="row.rawStatus === 'OPEN'"
              type="checkbox"
              :checked="rerunSelection.has(row.id)"
              @change="((event?: Event) => toggleRerunPick(row.id, Boolean((event?.target as HTMLInputElement)?.checked)))"
            /></td>
            <td class="review-id-cell">
              <RouterLink class="link" :to="`/manual-review/task/${row.id}`">{{ row.id }}</RouterLink>
            </td>
            <td>
              <strong>{{ row.object }}</strong>
              <small>{{ row.objectType }} · {{ row.type }}</small>
            </td>
            <td>
              <b>{{ resolvePipelineStep(row).name }}</b>
              <small>{{ resolvePipelineStep(row).phase }} · {{ row.node }}</small>
              <small :class="getImpactScope(row) === '批次级' ? 'scope-batch' : 'scope-task'">{{ getImpactScope(row) }}{{ getImpactScope(row) === '批次级' ? ' · 已阻断' : '' }}</small>
            </td>
            <td class="review-source-cell">
              <strong>{{ row.sourceTable || '—' }}</strong>
              <small><code>{{ row.sourceRecordId || '—' }}</code></small>
            </td>
            <td><code>{{ row.batch }}</code></td>
            <td>{{ row.handler }}</td>
            <td><span :class="['review-status', `is-${row.status}`]">{{ row.status }}</span></td>
            <td>{{ row.completedAt || row.updatedAt }}</td>
            <td>
              <div class="alert-actions">
                <RouterLink class="link" :to="`/manual-review/task/${row.id}`">
                  {{ row.status === '待处理' ? '进入处理' : '查看记录' }} →
                </RouterLink>
                <button
                  v-if="reviewCategory === 'C' && row.rawStatus === 'OPEN'"
                  class="link rerun-link"
                  type="button"
                  :disabled="rerunSubmitting"
                  @click="rerunSelected([row.id])"
                >重跑该记录</button>
              </div>
            </td>
          </tr>
          <tr v-if="!reviewRows.length">
            <td class="review-empty" :colspan="reviewCategory === 'C' ? 10 : 9">{{ reviewLoadError || (reviewStatusFilter === '全部' && reviewKindFilter === '全部' && !keyword ? '暂无人工处理记录' : '暂无符合条件的记录') }}</td>
          </tr>
        </tbody>
      </table></div>

      <footer v-if="mode === 'alerts'" class="alert-pagination"><span>每页显示　<a-select :default-value="20" :options="[20, 50, 100]" />　共 158 条异常</span><nav><button type="button" disabled>上一页</button><button class="active" type="button">1</button><button type="button">2</button><button type="button">3</button><button type="button">…</button><button type="button">8</button><button type="button">下一页</button></nav></footer>
      <footer v-else-if="reviewCategory === 'A' || rerunView === 'cases'" class="review-pagination">
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
  </div>
</template>

<style scoped>
.ops-page{height:100%;overflow:auto;padding-bottom:2px;color:#16233b}.ops-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.ops-head h1{margin:0;font-size:20px}.ops-head p{margin:3px 0 0;color:#61708a;font-size:13px}.primary,.ops-filter button{height:34px;padding:0 16px;border:0;border-radius:6px;background:#165dff;color:#fff;cursor:pointer}.ops-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:14px}.ops-metrics.is-alerts{grid-template-columns:repeat(6,minmax(0,1fr))}.ops-metrics article{display:grid;gap:7px;padding:18px;border:1px solid #bdd7ff;border-radius:9px;background:linear-gradient(145deg,#fff,#f2f8ff);box-shadow:0 8px 20px rgba(48,105,194,.09)}.ops-metrics span{color:#61708a;font-size:14px}.ops-metrics strong{font-size:27px}.ops-metrics em{color:#7890b5;font-size:12px;font-style:normal}.ops-feedback{margin:-3px 0 12px;padding:9px 12px;border:1px solid #b2ccff;border-radius:6px;background:#f0f5ff;color:#344f7a;font-size:12px}.ops-panel{overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:rgba(255,255,255,.94);box-shadow:0 12px 28px rgba(48,105,194,.1)}.ops-filter{display:grid;grid-template-columns:minmax(260px,1fr) repeat(3,160px) auto;gap:10px;padding:14px;border-bottom:1px solid #dce9ff;background:#f7fbff}.ops-filter input,.ops-filter select{height:34px;padding:0 10px;border:1px solid #bdd7ff;border-radius:6px;background:#fff;color:#273957}.ops-table-scroll{max-height:430px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{height:52px;padding:10px 14px;border-bottom:1px solid #e5edf8;text-align:left;white-space:nowrap}th{position:sticky;z-index:2;top:0;background:#f4f8fd;color:#5a6c88;font-weight:600}td{color:#273957}td small{display:block;margin-top:4px;color:#7b89a1}.alert-reason{min-width:240px;white-space:normal;line-height:19px}.alert-actions{display:grid;gap:5px}.alert-tabs{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 14px;border-bottom:1px solid #dce9ff}.alert-tabs nav{display:flex;overflow:auto}.alert-tabs button{padding:13px 14px;border:0;border-bottom:2px solid transparent;background:transparent;color:#52647f;white-space:nowrap;cursor:pointer}.alert-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.alert-tabs label{color:#5f6f88;font-size:12px;white-space:nowrap}.alert-tabs input{margin-right:6px}.level-严重,.level-警告,.level-提示{width:max-content;padding:2px 7px;border-radius:10px}.level-严重{background:#fee4e2!important;color:#d92d20!important}.level-警告{background:#fff3d8!important;color:#dc6803!important}.level-提示{background:#eaf2ff!important;color:#175cd3!important}.alert-status{padding:3px 8px;border-radius:10px;background:#edf2f7;color:#52647f}.alert-status.is-待处理{background:#fff0e8;color:#c4320a}.alert-status.is-处理中{background:#eaf2ff;color:#175cd3}.alert-status.is-已关闭{background:#e9f8ef;color:#067647}.alert-pagination{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;background:#fff;color:#687892;font-size:12px}.alert-pagination nav{display:flex;gap:5px}.alert-pagination button,.alert-pagination select{height:29px;padding:0 10px;border:1px solid #d3deee;border-radius:4px;background:#fff;color:#52647f}.alert-pagination button.active{border-color:#165dff;color:#165dff}.alert-pagination button:disabled{opacity:.45}td a,.link{border:0;background:transparent;color:#165dff;cursor:pointer;text-decoration:none}.danger{color:#d92d20}.success{color:#079455}@media(max-width:1280px){.ops-metrics.is-alerts{grid-template-columns:repeat(3,1fr)}}@media(max-width:1100px){.ops-metrics{grid-template-columns:repeat(2,1fr)}.ops-filter{grid-template-columns:1fr 1fr}.ops-panel{overflow:hidden}}
.review-context{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;padding:12px 14px;border:1px solid #b2ccff;border-radius:7px;background:#f0f5ff}.review-context div{display:grid;gap:3px}.review-context strong{font-size:13px}.review-context span{color:#65738b;font-size:11px}.review-context a{color:#165dff;font-size:12px;text-decoration:none;white-space:nowrap}
.review-evidence{min-width:260px;max-width:360px;white-space:normal;line-height:19px}.review-status{display:inline-flex;padding:3px 8px;border-radius:10px;background:#edf2f7;color:#52647f}.review-status.is-待处理{background:#fff0e8;color:#c4320a}.review-status.is-已完成{background:#e9f8ef;color:#067647}
.link-disabled{color:#98a2b3;font-size:12px;cursor:default}
.pick-col{width:36px;text-align:center}.pick-col input{cursor:pointer}
.rerun-link{padding:0;font-size:12px;border:0;background:transparent}
.review-severity{min-width:230px;max-width:300px;white-space:normal}.review-severity small{margin:0 0 6px}.review-severity span{display:block;color:#65738b;font-size:11px;line-height:17px}
.review-mask{position:fixed;z-index:49;inset:0;border:0;background:rgba(16,36,76,.24)}.review-drawer{position:fixed;z-index:50;top:0;right:0;display:grid;grid-template-rows:auto minmax(0,1fr) auto;width:620px;height:100vh;background:#f8fbff;box-shadow:-18px 0 42px rgba(34,74,132,.22)}.review-drawer>header{display:flex;justify-content:space-between;padding:20px;border-bottom:1px solid #dce8f8;background:#fff}.review-drawer header span{color:#165dff;font-size:11px}.review-drawer h2{margin:6px 0 3px;font-size:19px}.review-drawer header p{margin:0;color:#70809a;font-size:12px}.review-drawer header>button{width:30px;height:30px;border:0;border-radius:5px;background:#f0f4fa;font-size:20px;cursor:pointer}.review-body{overflow:auto;padding:16px}.review-body section,.review-compare article{padding:14px;border:1px solid #dce8f8;border-radius:7px;background:#fff}.review-body h3{margin:0 0 8px;font-size:14px}.review-body p,.review-body li{color:#61708a;font-size:12px;line-height:20px}.review-compare{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.review-compare span{display:block;margin-bottom:9px;color:#70809a;font-size:11px}.review-compare strong{font-size:13px}.review-compare em{color:#d92d20;font-size:11px;font-style:normal}.review-compare input,.review-compare textarea{width:100%;padding:8px;border:1px solid #bdd0ea;border-radius:5px;font:inherit}.review-compare textarea{min-height:90px;margin-top:8px;resize:vertical}.review-success{padding:10px 12px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3!important;color:#067647!important}.review-drawer>footer{display:flex;justify-content:flex-end;gap:8px;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.review-drawer>footer button{height:34px;padding:0 13px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;cursor:pointer}.review-drawer>footer .primary{border-color:#165dff;background:#165dff;color:#fff}@media(max-width:720px){.review-drawer{width:94vw}.review-compare{grid-template-columns:1fr}}
.ops-page{display:flex;box-sizing:border-box;min-height:0;overflow:hidden;padding-bottom:2px;flex-direction:column}.ops-head,.ops-metrics,.ops-feedback,.review-context{flex:0 0 auto}.ops-panel{display:flex;flex:1;min-height:0;flex-direction:column}.alert-tabs,.ops-filter,.alert-pagination,.review-pagination{flex:0 0 auto}.ops-table-scroll,.ops-review-table-scroll{flex:1;min-height:0;max-height:none;overflow:auto}.ops-filter.is-review{grid-template-columns:minmax(280px,1fr) 170px 170px auto}.ops-review-table-scroll table{min-width:1900px}.review-pagination{display:flex;align-items:center;gap:14px;padding:11px 14px;border-top:1px solid #e4ecf6;background:#fff;color:#71809a;font-size:11px}.review-pagination>span{white-space:nowrap}.review-pagination .review-page-size{display:flex;align-items:center;gap:6px;margin-left:auto;white-space:nowrap}.review-pagination :deep(.arco-select){width:76px}.review-pagination :deep(.arco-select-view){box-sizing:border-box;width:76px;height:28px;border:1px solid #d3deee;border-radius:4px;background:#fff}.review-empty{height:100px!important;color:#8290a7;text-align:center!important}.ops-review-table-scroll td code{color:#175cd3;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.review-type-cell{min-width:170px}.review-type-cell>span{display:inline-flex;padding:3px 9px;border-radius:99px;background:#eaf2ff;color:#175cd3;font-size:11px}.review-type-cell>span.is-low-confidence{background:#fff3d8;color:#b54708}.review-type-cell>span.is-extraction{background:#fef3f2;color:#b42318}.review-type-cell>span.is-schema{background:#edf0ff;color:#444ce7}.review-type-cell>span.is-normalization{background:#ecfdf3;color:#067647}.review-type-cell>span.is-other{background:#f2f4f7;color:#475467}
.ops-review-table-scroll table{min-width:1900px}.review-risk-explain{display:grid;flex:0 0 auto;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}.review-risk-explain>div{display:grid;gap:3px;padding:11px 14px;border:1px solid #b9d2f4;border-radius:7px;background:#f7fbff}.review-risk-explain strong{color:#344861;font-size:11px}.review-risk-explain span{color:#6d7c93;font-size:9px;line-height:16px}.review-confidence-cell{min-width:190px;white-space:normal}.review-confidence-cell>b{display:inline-block;margin-right:7px;font-size:13px}.review-confidence-cell>small{display:inline;color:#718098}.review-confidence-cell>span{display:block;margin-top:4px;color:#78869b;font-size:9px;line-height:15px}@media(max-width:900px){.review-risk-explain{grid-template-columns:1fr}}
.alert-impact{min-width:260px;max-width:340px;white-space:normal}.alert-impact strong,.alert-impact small{display:block;line-height:18px}.alert-impact small{color:#718099}.review-risk-explain{grid-template-columns:repeat(2,minmax(0,1fr))}.review-risk-explain>div:first-child{border-color:#f5b8b3;background:#fff5f4}.review-risk-explain>div:first-child strong{color:#d92d20}.review-risk-explain>div:nth-child(2){border-color:#f3d08a;background:#fffaf0}.review-risk-explain>div:nth-child(2) strong{color:#b54708}.review-type{min-width:150px}.review-confidence-cell{min-width:130px}.review-confidence-cell>em{display:block;width:max-content;margin-top:5px;padding:2px 7px;border-radius:9px;background:#fff3d8;color:#b54708;font-size:9px;font-style:normal}
.level-高风险{width:max-content;padding:2px 7px;border-radius:10px;background:#fee4e2;color:#d92d20}.level-中风险{width:max-content;padding:2px 7px;border-radius:10px;background:#fff3d8;color:#b54708}.level-低风险{width:max-content;padding:2px 7px;border-radius:10px;background:#eaf2ff;color:#175cd3}
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
.ops-page{padding:0;color:#1d2129}.ops-head{margin-bottom:16px}.ops-head h1,.ops-head p{display:none}
.ops-metrics{display:flex;gap:16px;margin-bottom:16px;border:0}.ops-metrics article{flex:1;gap:4px;padding:8px 16px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;box-shadow:none}
.ops-metrics span,.ops-metrics em{font-size:12px;line-height:20px}.ops-metrics strong{font-size:20px;line-height:28px;font-weight:600}
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
@media(max-width:900px){.ops-filter,.ops-filter.is-review{grid-template-columns:1fr}.review-risk-explain{grid-template-columns:1fr}.ops-metrics{display:grid;grid-template-columns:repeat(2,1fr)}}
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
/* 抽取失败重跑：二级子视图 / 重跑反馈条 / 状态徽标扩展 */
.rerun-subtabs{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;padding:0 16px;border-bottom:1px solid #e5e6eb;background:#fff}
.rerun-subtabs nav{display:flex;gap:4px}
.rerun-subtabs nav button{padding:9px 12px;border:0;border-bottom:2px solid transparent;background:transparent;color:#4e5969;font-size:13px;line-height:20px;cursor:pointer}
.rerun-subtabs nav button.active{border-color:#165dff;color:#165dff;font-weight:600}
.rerun-batch-action{height:32px;padding:0 16px;border:1px solid #165dff;border-radius:4px;background:#165dff;color:#fff;font-size:14px;line-height:22px;font-weight:400;cursor:pointer}
.rerun-batch-action:hover:not(:disabled){border-color:#4080ff;background:#4080ff}
.rerun-batch-action:active:not(:disabled){border-color:#0e42d2;background:#0e42d2}
.rerun-batch-action:disabled{border-color:#94bfff;background:#94bfff;color:#fff;cursor:not-allowed}
.rerun-refresh{height:28px;padding:0 12px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;color:#4e5969;font-size:12px;cursor:pointer}
.rerun-refresh:disabled{opacity:.5;cursor:not-allowed}
.rerun-feedback{flex:0 0 auto;display:flex;flex-wrap:wrap;align-items:center;gap:10px;padding:9px 16px;border-bottom:1px solid #a6f4c5;background:#ecfdf3;color:#067647;font-size:12px;line-height:20px}
.rerun-feedback.is-error{border-color:#f5b8b3;background:#fef3f2;color:#b42318}
.rerun-feedback-close{margin-left:auto;width:22px;height:22px;border:0;border-radius:4px;background:transparent;color:inherit;font-size:14px;cursor:pointer}
.rerun-confirm-text{margin:0;color:#4e5969;font-size:13px;line-height:22px}
.rerun-history-scroll table{min-width:1100px}
.rerun-fail-count{color:#b42318;font-weight:600}
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
.review-pagination{gap:16px;padding:8px 16px}
.review-pagination :deep(.arco-select-view),.review-pagination :deep(.arco-pagination-item){height:32px;min-height:32px}
.review-pagination :deep(.arco-pagination-item){min-width:32px;font-size:14px;line-height:22px}
.review-pagination :deep(.review-page-size-select.arco-select-view){display:inline-flex;box-sizing:border-box;align-items:center;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important}
.review-pagination :deep(.review-page-size-select.arco-select-view:hover){border-color:#4080ff!important}.review-pagination :deep(.review-page-size-select.arco-select-view:focus-within),.review-pagination :deep(.review-page-size-select.arco-select-view-focus){border-color:#165dff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.review-pagination :deep(.review-page-size-select .arco-select-view-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.review-pagination :deep(.review-page-size-select .arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important;pointer-events:none!important}
.review-pagination :deep(.review-page-size-select .arco-select-view-value){min-width:0;font-size:14px;line-height:22px;font-weight:400}
.ops-review-table-scroll .pick-col{vertical-align:middle;text-align:center}.ops-review-table-scroll .pick-col input[type="checkbox"]{display:block;width:14px;height:14px;margin:0 auto;vertical-align:middle;cursor:pointer}
.rerun-subtabs{min-height:48px;padding:8px 16px}
.rerun-subtabs nav{gap:0}.rerun-subtabs nav button{height:32px;padding:0 16px;font-size:14px;line-height:22px;font-weight:400}.rerun-subtabs nav button.active{font-weight:500}
.rerun-batch-action:focus-visible{outline:0;box-shadow:0 0 0 2px rgba(22,93,255,.2)}
.rerun-refresh{height:32px;padding:0 16px;font-size:14px;line-height:22px;font-weight:400}
.rerun-feedback{gap:8px;padding:8px 16px}.rerun-feedback-close{width:24px;height:24px}
.rerun-confirm-text{font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
</style>
<style>
/* Keep the Arco input's native field transparent; the wrapper is the only visible input shell. */
.app-workspace .ops-page .ops-filter.is-review .review-search-input.arco-input-wrapper input.arco-input{box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .ops-page .ops-filter.is-review .review-search-input.arco-input-wrapper input.arco-input:focus{border:0!important;background:transparent!important;box-shadow:none!important;outline:0!important}
.rerun-confirm-modal{border-radius:8px;font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}
.rerun-confirm-modal .arco-modal-header{box-sizing:border-box;height:56px;padding:0 24px}.rerun-confirm-modal .arco-modal-title{font-size:16px;line-height:24px;font-weight:600;letter-spacing:0}.rerun-confirm-modal .arco-modal-body{padding:24px}.rerun-confirm-modal .arco-modal-footer{box-sizing:border-box;min-height:64px;padding:16px 24px}.rerun-confirm-modal .arco-btn{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0}.rerun-confirm-modal .arco-btn+.arco-btn{margin-left:16px}
</style>
