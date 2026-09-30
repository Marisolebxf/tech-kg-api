<script setup lang="ts">
import DeleteConfirmDialog from '../../components/DeleteConfirmDialog.vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { IconInfoCircle, IconRefresh, IconSearch } from '@arco-design/web-vue/es/icon'
import {
  countJobUnifiedStatuses,
  deleteJob,
  deriveJobUnifiedStatus,
  getExecution,
  getTask,
  JOB_STATUS_TONE,
  listJobs,
  triggerJob,
  updateJobState,
  type WorkflowJob,
} from '../../api/workflowOperations'
import { schemaErrorMessage } from '../../api/schemaManagement'
import { subscribeJobEvents } from '../../api/jobEvents'
import { useGraphSpaceStore } from '../../stores/graphSpace'
import JobLaunchDialog from '../../components/JobLaunchDialog.vue'
import ListPagination from '../../components/list-pagination.vue'
import { useClientPagination } from '../../composables/use-client-pagination'
import { useToast } from '../../composables/use-toast'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import { describeCron } from '../../utils/cronSchedule'

const { showToast } = useToast()
const router = useRouter()
const graphSpaceStore = useGraphSpaceStore()

const jobs = ref<WorkflowJob[]>([])
const loading = ref(false)
/** 暂停确认中：点击暂停 → 后端信号送达且执行真正挂起（workflow paused=true）→ 才变已暂停 */
const pausingJobIds = ref<Record<string, boolean>>({})
/** 恢复确认中：点击恢复 → 信号送达且执行离开挂起点（paused=false）→ 才翻运行中 */
const resumingJobIds = ref<Record<string, boolean>>({})
const createOpen = ref(false)
const triggeringJobId = ref('')

const filterName = ref('')
const submittedName = ref('')
const filterStatus = ref('')
const filterTaskType = ref('')

/** 状态/类型筛选带「未选择」伪选项（用例 00843/00847）：value 为空串，选中即清空筛选。
 *  空串映射回 undefined 让框体恢复 placeholder 空态；× 号清空（undefined）同样归一为空串。 */
const filterStatusSelect = computed({
  get: () => filterStatus.value || undefined,
  set: (value: string | undefined) => {
    filterStatus.value = value ?? ''
  },
})
const filterTaskTypeSelect = computed({
  get: () => filterTaskType.value || undefined,
  set: (value: string | undefined) => {
    filterTaskType.value = value ?? ''
  },
})

/** 图空间筛选持久化：'__all__'=全部空间；具体空间名=钉住该空间；空=跟随总览页全局选择器。
 *  由旧版「全部空间」开关迁移：开着的一律视为选了全部空间。 */
const SPACE_SCOPE_KEY = 'tech-kg-graph-build-space-scope'
const OLD_ALL_SPACES_KEY = 'tech-kg-graph-build-all-spaces'
const ALL_SPACES = '__all__'

function readStoredSpaceScope(): string {
  try {
    const stored = localStorage.getItem(SPACE_SCOPE_KEY)
    if (stored === ALL_SPACES) return ALL_SPACES
    if (stored) return stored
    if (localStorage.getItem(OLD_ALL_SPACES_KEY) === '1') return ALL_SPACES
  } catch {
    // localStorage 不可用（隐私模式等）：仅内存态生效
  }
  return ''
}

const spaceScope = ref(readStoredSpaceScope())
const spaceScopeSelect = computed({
  get: () => spaceScope.value || graphSpaceStore.current || graphSpaceStore.spaces[0],
  set: (value: string | undefined) => {
    spaceScope.value = value ?? ''
  },
})
watch(spaceScope, (value) => {
  try {
    localStorage.setItem(SPACE_SCOPE_KEY, value)
  } catch {
    // localStorage 不可用（隐私模式等）：仅内存态生效
  }
})

/** 任务归属空间：payload 未带 graphSpace 的历史任务落当时的默认业务空间（空间列表首位恒为默认）。 */
function jobSpace(job: WorkflowJob): string {
  return job.graphSpace || graphSpaceStore.spaces[0] || graphSpaceStore.current
}

/** extract/chain 可新建；single/upload 为历史键（D2 停止新建），存量行仍需中文展示 */
const TASK_TYPE_LABELS: Record<string, string> = {
  extract: '数据抽取',
  single: '单脚本抽取',
  chain: '多脚本串行',
  upload: '上传脚本',
}

const filteredJobs = computed(() => {
  const name = submittedName.value.toLowerCase()
  const space = spaceScope.value || graphSpaceStore.current
  return jobs.value.filter((job) => {
    if (space !== ALL_SPACES && jobSpace(job) !== space) return false
    if (name && !job.name.toLowerCase().includes(name)) return false
    if (filterStatus.value && deriveJobUnifiedStatus(job) !== filterStatus.value) return false
    if (filterTaskType.value && job.taskType !== filterTaskType.value) return false
    return true
  })
})

// 状态卡片与表格同口径：跟随当前筛选范围（含当前空间过滤）
const summaryItems = computed(() => {
  const counts = countJobUnifiedStatuses(filteredJobs.value)
  return [
    { label: '运行中', value: counts['运行中'], hint: '正在执行的任务' },
    { label: '已完成', value: counts['已完成'], hint: '最近一次执行成功' },
    { label: '运行异常', value: counts['运行异常'], hint: '完成但含失败记录（已转人工审核）' },
    { label: '运行失败', value: counts['运行失败'], hint: '最近一次执行出错' },
    { label: '已暂停', value: counts['已暂停'], hint: '已暂停触发' },
  ]
})

// 任务列表客户端分页（后端按 created_at desc，最新任务总在第 1 页——e2e 按名称找行依赖这一点）
const {
  page: jobPage,
  pageSize: jobPageSize,
  total: jobTotal,
  pagedItems: pagedJobs,
  resetPage: resetJobPage,
  changePage: changeJobPage,
  changePageSize: changeJobPageSize,
} = useClientPagination(filteredJobs, 10)
watch([submittedName, filterStatus, filterTaskType, spaceScope, () => graphSpaceStore.current], resetJobPage)

function submitJobSearch() {
  submittedName.value = filterName.value.trim()
  resetJobPage()
}

const taskTableRef = ref<HTMLElement | null>(null)
const tableHasMoreToScroll = ref(false)
const tableScrollActive = ref(false)
let scrollIdleTimer: ReturnType<typeof setTimeout> | undefined

function updateTaskTableScrollState() {
  const table = taskTableRef.value
  tableHasMoreToScroll.value = !!table && table.scrollWidth - table.clientWidth - table.scrollLeft > 1
}

function handleTaskTableScroll() {
  updateTaskTableScrollState()
  tableScrollActive.value = true
  clearTimeout(scrollIdleTimer)
  scrollIdleTimer = setTimeout(() => { tableScrollActive.value = false }, 700)
}

watch(pagedJobs, async () => {
  await nextTick()
  updateTaskTableScrollState()
}, { flush: 'post' })

async function loadData(silent = false) {
  // silent：轮询刷新用，不转 loading、失败不弹 toast（避免每几秒闪一次）
  if (!silent) loading.value = true
  try {
    const jobList = await listJobs()
    jobs.value = jobList.items
  } catch (error) {
    if (!silent) showToast(schemaErrorMessage(error), 'error')
  } finally {
    if (!silent) loading.value = false
  }
}

// 状态更新走服务端推送（SSE）：后端监视控制面表，Schedule 到点起跑/执行翻终态/
// 暂停恢复/增删即时下发 jobs-changed，前端不再定时轮询。断线由 EventSource
// 自动重连，重连成功时全量重拉补齐漏掉的事件；运行中任务到达终态时弹 toast
// 告知结果（与报错同款提示形式）
let unsubscribeJobEvents: (() => void) | null = null

function announceFinished(prevJobs: WorkflowJob[]) {
  const prev = new Map(prevJobs.map((job) => [job.id, deriveJobUnifiedStatus(job)]))
  for (const job of jobs.value) {
    const now = deriveJobUnifiedStatus(job)
    if (prev.get(job.id) !== '运行中') continue // 只报「运行中→终态」的翻转，历史终态不弹
    if (now === '已完成') showToast(`任务「${job.name}」执行完成`, 'success')
    else if (now === '运行异常') showToast(`任务「${job.name}」执行完成但含失败记录（已转人工审核），点任务名查看`, 'warning')
    else if (now === '运行失败') showToast(`任务「${job.name}」执行失败，点任务名查看原因`, 'error')
  }
}

async function reloadOnEvent(announce: boolean) {
  const prevJobs = [...jobs.value]
  await loadData(true)
  if (announce) announceFinished(prevJobs)
}

onUnmounted(() => {
  unsubscribeJobEvents?.()
  window.removeEventListener('resize', updateTaskTableScrollState)
  clearTimeout(scrollIdleTimer)
})

function openCreate() {
  createOpen.value = true
}

function jobScriptLabel(job: WorkflowJob): string {
  if (job.taskType === 'chain') {
    // 新链任务带 schemaLabels（首个 + N）；存量旧链任务回退 definitionIds 口径
    if (job.schemaLabels?.length) {
      const first = job.schemaLabels[0]
      return job.schemaLabels.length > 1 ? `${first} +${job.schemaLabels.length - 1}` : first
    }
    const first = job.definitionIds[0] || job.definitionId
    return job.definitionIds.length > 1 ? `${first} +${job.definitionIds.length - 1}` : first
  }
  return job.definitionName || job.definitionId
}

async function onTrigger(job: WorkflowJob) {
  // 未运行首启 + 运行失败重跑；已完成按产品决策不提供重复执行
  if (!['未运行', '运行失败'].includes(deriveJobUnifiedStatus(job)) || triggeringJobId.value) return
  triggeringJobId.value = job.id
  try {
    await triggerJob(job.id)
    showToast(`任务「${job.name}」已触发`, 'success')
    await loadData()
  } catch (error) {
    showToast(schemaErrorMessage(error), 'error')
  } finally {
    triggeringJobId.value = ''
  }
}

/** 轮询执行的工作流查询，确认到达期望的暂停态（paused=true=已挂起 / false=已离开挂起点）。 */
async function confirmPausedState(executionId: string, expected: boolean): Promise<boolean> {
  for (let i = 0; i < 10; i++) {
    await new Promise((resolve) => setTimeout(resolve, 2000))
    try {
      const execution = (await getExecution(executionId)) as { taskId?: string }
      if (!execution.taskId) continue
      const task = await getTask(execution.taskId)
      // 执行已到终态（暂停期间失败/完成）：无需再确认
      if (task.taskStatus && task.taskStatus !== '执行中') return true
      const pipeline = task.pipeline as { paused?: boolean } | undefined
      if (pipeline?.paused != null && pipeline.paused === expected) return true
    } catch {
      // 单次轮询失败忽略（工作流刚结束被淘汰等），下一轮再试
    }
  }
  return false
}

async function onToggleState(job: WorkflowJob) {
  // 方向按 job.status：暂停→恢复；其余（含运行中）→暂停。
  const active = job.status === '暂停'
  try {
    await updateJobState(job.id, active)
    if (active || job.lastExecutionStatus !== 'RUNNING') {
      showToast(active ? '已恢复' : '已暂停', 'success')
      await loadData()
      return
    }
    if (active) {
      // 恢复运行中执行：等 workflow 离开挂起点（paused=false）再翻状态
      resumingJobIds.value = { ...resumingJobIds.value, [job.id]: true }
      await loadData()
      const confirmed = await confirmPausedState(job.lastExecutionId as string, false)
      delete resumingJobIds.value[job.id]
      resumingJobIds.value = { ...resumingJobIds.value }
      showToast(confirmed ? '已恢复：从挂起的断点继续执行' : '已恢复（确认超时，执行状态以详情页为准）', confirmed ? 'success' : 'warning')
      await loadData()
      return
    }
    // 暂停运行中的执行：信号已发，等 workflow 到达挂起点（get_progress.paused）再翻状态
    pausingJobIds.value = { ...pausingJobIds.value, [job.id]: true }
    await loadData()
    const confirmed = await confirmPausedState(job.lastExecutionId as string, true)
    delete pausingJobIds.value[job.id]
    pausingJobIds.value = { ...pausingJobIds.value }
    showToast(
      confirmed ? '已暂停：当前步结束后挂起，恢复后从断点继续' : '已暂停调度（挂起确认超时，执行状态以详情页为准）',
      confirmed ? 'success' : 'warning',
    )
    await loadData()
  } catch (error) {
    delete pausingJobIds.value[job.id]
    showToast(schemaErrorMessage(error), 'error')
  }
}

const deleteTarget = ref<WorkflowJob>()
const deleteVisible = ref(false)
const deleteSubmitting = ref(false)
const deleteError = ref('')
function onDelete(job: WorkflowJob) {
  deleteTarget.value = job
  deleteError.value = ''
  deleteVisible.value = true
}
async function confirmDeleteJob() {
  const job = deleteTarget.value
  if (!job || deleteSubmitting.value) return
  deleteSubmitting.value = true
  deleteError.value = ''

  try {
    await deleteJob(job.id)
    deleteVisible.value = false
    showToast('任务已删除', 'success')
    await loadData()
  } catch (error) {
    deleteError.value = schemaErrorMessage(error)
  } finally {
    deleteSubmitting.value = false
  }
}

function openJobDetail(job: WorkflowJob) {
  void router.push({ name: 'job-detail', params: { jobId: job.id } })
}

/** 任务行操作项（有序）：执行/重新执行、暂停/恢复、查看详情、删除。
 *  运行中不可删：置灰而非隐藏（悬停说明原因），与其余操作列同口径。 */
type JobAction = { key: string; label: string; danger?: boolean; disabled?: boolean; title?: string; run: () => void }

function jobActions(job: WorkflowJob): JobAction[] {
  const status = deriveJobUnifiedStatus(job)
  const actions: JobAction[] = []
  if (['未运行', '运行失败'].includes(status)) {
    actions.push({
      key: 'trigger',
      label: status === '运行失败' ? '重新执行' : '执行',
      disabled: triggeringJobId.value === job.id,
      title: triggeringJobId.value === job.id ? '正在下发执行…' : undefined,
      run: () => void onTrigger(job),
    })
  }
  if (status !== '已暂停' && job.status !== '暂停' && (status === '运行中' || job.schedule.kind === 'cron')) {
    actions.push({
      key: 'pause',
      label: pausingJobIds.value[job.id] ? '暂停中…' : '暂停',
      disabled: Boolean(pausingJobIds.value[job.id]),
      run: () => void onToggleState(job),
    })
  } else if (job.status === '暂停' || status === '已暂停') {
    actions.push({
      key: 'resume',
      label: resumingJobIds.value[job.id] ? '恢复中…' : '恢复',
      disabled: Boolean(resumingJobIds.value[job.id]),
      run: () => void onToggleState(job),
    })
  }
  actions.push({ key: 'detail', label: '查看详情', run: () => openJobDetail(job) })
  actions.push({
    key: 'delete',
    label: '删除',
    danger: true,
    disabled: status === '运行中',
    title: status === '运行中' ? '运行中：等待本次任务完成后再删除' : undefined,
    run: () => void onDelete(job),
  })
  return actions
}

/** 平铺操作（与 Schema 管理表对齐）：≤3 个全部平铺；>3 个时只平铺前两个，第三个位置换成「···」。 */
function flatJobActions(job: WorkflowJob): JobAction[] {
  const actions = jobActions(job)
  return actions.length <= 3 ? actions : actions.slice(0, 2)
}

/** 「···」菜单收纳的剩余操作（>3 个时的第 3 个起）。 */
function overflowJobActions(job: WorkflowJob): JobAction[] {
  const actions = jobActions(job)
  return actions.length > 3 ? actions.slice(2) : []
}

function executionStatusClass(status: string): string {
  const s = status.toUpperCase()
  if (s === 'COMPLETED') return 'ok'
  if (s === 'FAILED' || s === 'CANCELED' || s === 'TERMINATED' || s === 'TIMED_OUT') return 'err'
  if (s === 'ABNORMAL') return 'err'
  if (s === 'QUEUED') return 'idle'
  return 'run'
}

onMounted(() => {
  window.addEventListener('resize', updateTaskTableScrollState)
  void nextTick(updateTaskTableScrollState)
  void loadData()
  unsubscribeJobEvents = subscribeJobEvents(
    () => {
      void reloadOnEvent(!document.hidden) // 页面隐藏时静默刷新，不弹无人看的 toast
    },
    () => {
      void loadData(true) // 连接/重连成功：静默全量重拉，补齐断线期间的变化
    },
  )
})
</script>

<template>
  <main class="graph-build-page">
    <div class="gb-actions">
      <button type="button" class="primary" @click="openCreate">＋ 新建任务</button>
      <button type="button" :disabled="loading" @click="loadData()"><IconRefresh class="refresh-icon" />{{ loading ? '刷新中…' : '刷新' }}</button>
    </div>

    <section class="gb-summary">
      <article v-for="item in summaryItems" :key="item.label">
        <div class="gb-summary__label">
          <span>{{ item.label }}</span>
          <a-tooltip v-if="item.hint" :content="item.hint">
            <button class="gb-summary__hint" type="button" :aria-label="item.hint">
              <IconInfoCircle aria-hidden="true" />
            </button>
          </a-tooltip>
        </div>
        <div class="gb-summary__task-stats">
          <strong>{{ item.value }}</strong>
        </div>
      </article>
    </section>

    <section class="gb-jobs-section">
      <header class="gb-jobs-toolbar">
        <strong class="gb-section-title">任务列表</strong>
        <form class="gb-filters" role="search" @submit.prevent="submitJobSearch">
          <a-select
            v-model="spaceScopeSelect"
            class="gb-filter-select"
            placeholder="图空间"
            allow-clear
            title="按图空间筛选任务（清空即跟随总览页全局选择器的当前空间）"
          >
            <a-option :value="ALL_SPACES">全部空间</a-option>
            <a-option v-for="space in graphSpaceStore.spaces" :key="space" :value="space">{{ space }}</a-option>
          </a-select>
          <a-select id="graph-build-filter-status" v-model="filterStatusSelect" class="gb-filter-select" placeholder="状态" allow-clear>
            <a-option value="">未选择</a-option>
            <a-option value="未运行">未运行</a-option>
            <a-option value="运行中">运行中</a-option>
            <a-option value="已暂停">已暂停</a-option>
            <a-option value="已完成">已完成</a-option>
            <a-option value="运行异常">运行异常</a-option>
            <a-option value="运行失败">运行失败</a-option>
          </a-select>
          <a-select id="graph-build-filter-type" v-model="filterTaskTypeSelect" class="gb-filter-select" placeholder="类型" allow-clear>
            <a-option value="">未选择</a-option>
            <a-option value="extract">数据抽取</a-option>
            <a-option value="single">单脚本抽取</a-option>
            <a-option value="chain">多脚本串行</a-option>
            <a-option value="upload">上传脚本</a-option>
          </a-select>
          <a-input id="graph-build-filter-name" v-model="filterName" class="gb-search-input" :max-length="SEARCH_KEYWORD_MAX_LENGTH" aria-label="按名称搜索" placeholder="按名称搜索"><template #prefix><IconSearch /></template></a-input>
          <button class="gb-search-button" type="submit">查询</button>
        </form>
      </header>
      <div class="gb-jobs-panel">
      <div ref="taskTableRef" class="gb-task-table" :class="{ 'has-scroll-right': tableHasMoreToScroll, 'gb-scroll--active': tableScrollActive }" @scroll.passive="handleTaskTableScroll">
        <table>
          <thead>
            <tr><th>任务名</th><th>类型</th><th>脚本</th><th>图空间</th><th>调度</th><th>状态</th><th>最近任务 ID</th><th>最近执行</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="job in pagedJobs" :key="job.id">
              <td><b>{{ job.name }}</b></td>
              <td>{{ TASK_TYPE_LABELS[job.taskType] || job.taskType }}</td>
              <td><code>{{ jobScriptLabel(job) }}</code></td>
              <td>{{ job.graphSpace || '默认' }}</td>
              <td>
                <span
                  v-if="job.schedule.kind === 'cron'"
                  :title="`cron ${job.schedule.cron}`"
                >{{ describeCron(job.schedule.cron ?? '') }}</span>
                <span v-else>单次</span>
              </td>
              <td>
                <span v-if="pausingJobIds[job.id]" class="run">暂停中…</span>
                <span v-else-if="resumingJobIds[job.id]" class="run">恢复中…</span>
                <span v-else :class="JOB_STATUS_TONE[deriveJobUnifiedStatus(job)]">{{ deriveJobUnifiedStatus(job) }}</span>
              </td>
              <td>
                <span v-if="job.lastExecutionId">{{ job.lastExecutionId }}</span>
                <span v-else class="muted">—</span>
              </td>
              <td>
                <span v-if="job.lastExecutionStatus" :class="executionStatusClass(job.lastExecutionStatus)">{{ job.lastExecutionStatus }}</span>
                <span v-else class="idle">未执行</span>
                <small v-if="job.lastRunAt" class="gb-last-run">{{ job.lastRunAt }}</small>
              </td>
              <td class="gb-job-actions">
                <!-- 与 Schema 管理表对齐：≤3 个操作全部平铺；>3 个时平铺前两个，第三个位置换成「···」 -->
                <div class="gb-job-actions__inner">
                  <button
                    v-for="action in flatJobActions(job)"
                    :key="action.key"
                    type="button"
                    class="gb-action-link"
                    :class="{ 'is-danger': action.danger }"
                    :disabled="action.disabled"
                    :title="action.title"
                    @click="action.run()"
                  >{{ action.label }}</button>
                  <a-dropdown v-if="overflowJobActions(job).length" trigger="click" position="bl">
                    <button type="button" class="gb-action-link gb-action-more" :aria-label="`${job.name}更多操作`" title="更多操作">···</button>
                    <template #content>
                      <a-doption
                        v-for="action in overflowJobActions(job)"
                        :key="action.key"
                        class="gb-action-menu-item"
                        :class="{ 'gb-action-menu-item--danger': action.danger }"
                        :disabled="action.disabled"
                        :title="action.title"
                        @click="action.run()"
                      >{{ action.label }}</a-doption>
                    </template>
                  </a-dropdown>
                </div>
              </td>
            </tr>
            <tr v-if="!filteredJobs.length"><td colspan="9" class="empty">暂无任务，点击「新建任务」创建</td></tr>
          </tbody>
        </table>
      </div>
      <ListPagination
        v-if="jobTotal > 0"
        :total="jobTotal"
        :page="jobPage"
        :page-size="jobPageSize"
        :disabled="loading"
        :show-jumper="false"
        :size-at-end="true"
        @change="changeJobPage"
        @change-size="changeJobPageSize"
      ><template #summary><span class="list-pagination__summary">共 {{ jobTotal }} 条</span></template></ListPagination>
      </div>
    </section>

    <JobLaunchDialog
      :open="createOpen"
      @close="createOpen = false"
      @created="loadData()"
    />
    <DeleteConfirmDialog v-model:visible="deleteVisible" title="删除任务" :name="deleteTarget?.name || ''" :identifier="deleteTarget?.id" identifier-label="任务 ID" description="继续操作将删除该图谱构建任务，执行历史将保留。" :loading="deleteSubmitting" :error="deleteError" @confirm="confirmDeleteJob" />
  </main>
</template>

<style scoped>
.graph-build-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;padding:0;color:#1d2129;font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0;flex-direction:column}
.graph-build-page :deep(*){font-family:inherit;letter-spacing:0}
.gb-actions{display:flex;gap:8px;margin-bottom:12px}
.gb-actions button{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;cursor:pointer}
.gb-actions .primary{border-color:#165dff;background:#165dff;color:#fff}
.gb-summary{display:grid;flex-shrink:0;grid-template-columns:repeat(auto-fit,minmax(min(100%,150px),1fr));gap:16px;margin-bottom:16px}
.gb-summary article{display:flex;flex:1;min-height:80px;gap:8px;padding:12px 16px;border:1px solid #e5e6eb;border-radius:6px;background:#fff;flex-direction:column;justify-content:center}
.gb-summary span{color:#1d2129;font-size:16px;line-height:24px;font-weight:600}
.gb-summary strong{color:#1d2129;font-size:28px;line-height:32px;font-weight:600;letter-spacing:0}
.gb-summary__label,.gb-summary__task-stats{display:flex;align-items:center;min-width:0}.gb-summary__label{gap:8px}.gb-summary__hint{display:inline-flex;align-items:center;justify-content:center;flex:0 0 24px;width:24px;height:24px;padding:0;border:0;border-radius:4px;background:transparent;color:#86909c;cursor:help}.gb-summary__hint:hover,.gb-summary__hint:focus-visible{background:#f2f3f5;color:#165dff}.gb-summary__hint svg{width:16px;height:16px}
.gb-jobs-section{display:flex;flex:1;min-height:0;flex-direction:column;gap:16px}
.gb-jobs-toolbar{display:flex;flex-direction:column;flex:0 0 auto;align-items:stretch;gap:12px;box-sizing:border-box;color:#1d2129}
.gb-section-title{position:relative;padding-left:11px;font-size:16px;line-height:24px;font-weight:600}
.gb-section-title::before{position:absolute;top:5px;left:0;width:3px;height:14px;border-radius:1px;background:#165dff;content:""}
.gb-jobs-panel{display:flex;flex:1;min-height:0;overflow:hidden;border:1px solid #e5e6eb;border-radius:6px;background:#fff;box-shadow:none;flex-direction:column}
.gb-jobs-panel :deep(.list-pagination){justify-content:flex-end}
.gb-jobs-panel :deep(.list-pagination__summary){margin-left:auto}
/* 筛选控件向右排列，窄屏时可换行。 */
.gb-filters{display:flex;flex:0 0 auto;min-width:0;margin-left:auto;flex-wrap:wrap;align-items:center;justify-content:flex-end;gap:16px;font-weight:400}
.gb-search-button{box-sizing:border-box;height:32px;padding:0 16px;border:1px solid #165dff;border-radius:4px;background:#165dff;color:#fff;font-size:14px;line-height:22px;cursor:pointer}
.gb-search-button:hover{border-color:#4080ff;background:#4080ff}
.gb-search-button:focus-visible{outline:2px solid rgba(22,93,255,.3);outline-offset:2px}
/* 图空间下拉：跟随筛选条尺寸合同，不换行不被压缩 */
.gb-task-table{flex:1;min-height:0;overflow:auto;padding:0;scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:transparent transparent}
.gb-task-table:hover,.gb-task-table.gb-scroll--active{scrollbar-color:rgba(78,89,105,.55) transparent}
.gb-task-table::-webkit-scrollbar{width:8px;height:8px}
.gb-task-table::-webkit-scrollbar-track{background:transparent}
.gb-task-table::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background:transparent;background-clip:padding-box}
.gb-task-table:hover::-webkit-scrollbar-thumb,.gb-task-table.gb-scroll--active::-webkit-scrollbar-thumb{background-color:rgba(78,89,105,.55)}
/* 与 Schema 管理表一致：由内容语义自动分配列宽，空间不足时由表格容器承接横向滚动。 */
.gb-task-table table{width:max-content;min-width:100%;margin:0;border-collapse:collapse;font-size:14px;line-height:22px}
.gb-task-table th{position:sticky;z-index:2;top:0;height:40px;padding:0 16px;background:#f7f8fa;color:#1d2129;font-size:14px;line-height:22px;font-weight:500;text-align:left;white-space:nowrap}
.gb-task-table td{height:40px;padding:0 16px;border-bottom:1px solid #e5edf8;color:#344763;font-size:14px;line-height:22px;font-weight:400;vertical-align:middle;white-space:nowrap}
.gb-task-table tbody tr:hover td{background:#f4f8ff}
.gb-task-table code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-family:inherit;font-size:14px;line-height:22px;font-weight:400;white-space:nowrap}
.gb-task-table b{color:#1d2129;font-weight:400}
.gb-last-run{display:block;color:#8191aa;font-size:12px;line-height:20px;font-weight:400}
.gb-job-actions{white-space:nowrap}
.gb-job-actions__inner{display:flex;align-items:center;gap:8px}
/* 操作按钮与 Schema 管理表同款：无边框纯文字链接；删除红、其余蓝、禁用灰 */
.gb-action-link{height:auto;padding:0;border:0;background:transparent;color:#165dff;font-size:14px;line-height:22px;font-weight:400;cursor:pointer;text-decoration:none}
.gb-action-link:hover:not(:disabled){color:#4080ff;text-decoration:none}
.gb-action-link:disabled{color:#a9b4c6;cursor:not-allowed;text-decoration:none}
.gb-action-link.is-danger{color:#e5484d}
.gb-action-link.is-danger:hover:not(:disabled){color:#b42318}
.gb-action-more{min-width:24px;font-size:18px;line-height:22px;text-align:center}
/* 操作列与 Schema 管理表对齐：右侧固定列（表头同时吸顶，z 高于数据行），横向滚动时操作不被遮挡 */
.gb-task-table thead th:last-child{position:sticky;right:0;z-index:4;background:#f7f8fa;box-shadow:-1px 0 #e5e6eb}
.gb-task-table td.gb-job-actions{position:sticky;right:0;z-index:3;background:#fff;box-shadow:-1px 0 #e5e6eb}
.gb-task-table tbody tr:hover td.gb-job-actions{background:#f4f8ff}
/* 固定列左侧向内容区渐隐的阴影（与 Schema 管理表同视觉提示） */
.gb-task-table.has-scroll-right :is(thead th:last-child,td.gb-job-actions)::before{position:absolute;top:0;bottom:-1px;left:0;width:12px;content:"";pointer-events:none;transform:translateX(-100%);box-shadow:inset -10px 0 8px -8px rgba(78,89,105,.28)}
.empty{padding:40px 14px;text-align:center;color:#8290a7;font-size:12px;line-height:20px;font-weight:400}
.muted{color:#8191aa;font-size:12px;line-height:20px;font-weight:400}
span.ok,span.err,span.warn,span.run,span.idle{display:inline-flex;align-items:center;gap:6px;font-size:14px;line-height:22px;border-radius:0;background:transparent;padding:0;white-space:nowrap}
span.ok::before,span.err::before,span.warn::before,span.run::before,span.idle::before{display:block;flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}
span.idle{color:var(--status-neutral)}
span.ok{color:var(--status-success)}
span.err{color:var(--status-danger)}
span.warn{color:var(--status-warning)}
span.run{color:var(--status-info)}

@media (max-width: 1024px) {
  .graph-build-page {
    overflow-y: auto;
  }

  .gb-jobs-section {
    flex: 1 0 auto;
    min-height: 300px;
  }
}

</style>
<style>
.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-wrapper{box-sizing:border-box;width:280px;min-width:0;max-width:100%;height:32px;min-height:32px;padding:0 12px;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:0 1 280px}
.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-wrapper:hover{border-color:#4080ff!important;background:#fff!important}
.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-wrapper:focus-within,.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.app-workspace .gb-filters #graph-build-filter-name .arco-input-prefix{padding-right:8px;color:#4e5969}.app-workspace .gb-filters #graph-build-filter-name.arco-input-focus .arco-input-prefix{color:#165dff}.app-workspace .gb-filters #graph-build-filter-name .arco-input-prefix svg{width:16px;height:16px;font-size:16px}
.app-workspace .gb-filters #graph-build-filter-name input.arco-input{box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
/* 筛选下拉统一按类命中（状态/类型/图空间同一边框与尺寸合同），不再绑死控件 id */
.app-workspace .gb-filters .gb-filter-select.arco-select-view{display:inline-flex;box-sizing:border-box;align-items:center;width:160px;min-width:0;max-width:100%;height:32px;min-height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:0 0 160px}
.app-workspace .gb-filters .gb-filter-select.arco-select-view:hover{border-color:#4080ff!important;background:#fff!important}
.app-workspace .gb-filters .gb-filter-select.arco-select-view:focus-within,.app-workspace .gb-filters .gb-filter-select.arco-select-view-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.app-workspace .gb-filters .gb-filter-select input.arco-select-view-input{box-sizing:border-box;width:100%;height:30px!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .gb-filters .gb-filter-select .arco-select-view-input-hidden{position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important}.app-workspace .gb-filters .gb-filter-select .arco-select-view-value{min-width:0;overflow:hidden;font-size:14px;line-height:22px;font-weight:400;text-overflow:ellipsis;white-space:nowrap}
.app-workspace .gb-filters .gb-filter-select :is(.arco-select-view-input,.arco-select-view-value){background:transparent!important}
/* 筛选下拉右侧的箭头/清除图标：Arco 默认仅 12px 且偏淡，肉眼几乎看不出有下拉符号——放大到 14px 并显式着色（与输入框前缀图标同灰度） */
.app-workspace .gb-filters .gb-filter-select .arco-select-view-suffix svg{width:14px;height:14px;font-size:14px;color:#4e5969}
/* 任务操作列「···」更多菜单（teleport 到 body，需全局控制；菜单项口径对齐 Schema 管理表） */
.gb-action-menu-item.arco-dropdown-option{box-sizing:border-box;min-height:32px;padding:5px 16px;color:#165dff;font-size:14px;line-height:22px;font-weight:400;text-decoration:none}
.gb-action-menu-item.arco-dropdown-option:hover{color:#4080ff;text-decoration:none}
.gb-action-menu-item--danger.arco-dropdown-option:not(.arco-dropdown-option-disabled){color:#f53f3f}
.gb-action-menu-item--danger.arco-dropdown-option:not(.arco-dropdown-option-disabled):hover{color:#b42318}
.gb-action-menu-item.arco-dropdown-option-disabled{color:#a9b4c6}
</style>
