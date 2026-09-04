<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { IconInfoCircle, IconSearch } from '@arco-design/web-vue/es/icon'
import {
  countJobUnifiedStatuses,
  deleteJob,
  deriveJobUnifiedStatus,
  JOB_STATUS_TONE,
  listDefinitions,
  listJobs,
  triggerJob,
  updateJobState,
  type WorkflowDefinition,
  type WorkflowJob,
} from '../../api/workflowOperations'
import { schemaErrorMessage } from '../../api/schemaManagement'
import { listLlmConfigs, type LlmConfig } from '../../api/llmConfig'
import { listEmbeddingConfigs, type EmbeddingConfig } from '../../api/embeddingConfig'
import { listMilvusConfigs, type MilvusConfig } from '../../api/milvusConfig'
import { listMysqlDatasources, type MysqlDatasource } from '../../api/mysqlDatasource'
import { listGraphSpaces } from '../../api/graphSpace'
import { currentUserId as getCurrentUserId } from '../../api/currentUser'
import JobLaunchDialog from '../../components/JobLaunchDialog.vue'
import { useToast } from '../../composables/use-toast'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'

const { showToast } = useToast()
const router = useRouter()
const currentUserId = getCurrentUserId()

const jobs = ref<WorkflowJob[]>([])
const definitions = ref<WorkflowDefinition[]>([])
const llmConfigs = ref<LlmConfig[]>([])
const embeddingConfigs = ref<EmbeddingConfig[]>([])
const milvusConfigs = ref<MilvusConfig[]>([])
const mysqlDatasources = ref<MysqlDatasource[]>([])
const graphSpaces = ref<string[]>([])
const loading = ref(false)
const createOpen = ref(false)
const triggeringJobId = ref('')

const filterName = ref('')
const filterStatus = ref('')
const filterTaskType = ref('')

const TASK_TYPE_LABELS: Record<string, string> = {
  single: '单脚本抽取',
  chain: '多脚本串行',
  upload: '上传脚本',
}

const summaryItems = computed(() => {
  const counts = countJobUnifiedStatuses(jobs.value)
  return [
    { label: '运行中', value: counts['运行中'], hint: '正在执行的任务' },
    { label: '已完成', value: counts['已完成'], hint: '最近一次执行成功' },
    { label: '运行失败', value: counts['运行失败'], hint: '最近一次执行出错' },
    { label: '已暂停', value: counts['已暂停'], hint: '已暂停触发' },
  ]
})

const filteredJobs = computed(() => {
  const name = filterName.value.trim().toLowerCase()
  return jobs.value.filter((job) => {
    if (name && !job.name.toLowerCase().includes(name)) return false
    if (filterStatus.value && deriveJobUnifiedStatus(job) !== filterStatus.value) return false
    if (filterTaskType.value && job.taskType !== filterTaskType.value) return false
    return true
  })
})

async function loadData() {
  loading.value = true
  try {
    const jobList = await listJobs()
    jobs.value = jobList.items
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    loading.value = false
  }
}

async function loadDialogResources() {
  try {
    const [defs, llm, embedding, milvus, mysql, spaces] = await Promise.all([
      listDefinitions(),
      listLlmConfigs(currentUserId),
      listEmbeddingConfigs(currentUserId),
      listMilvusConfigs(currentUserId),
      listMysqlDatasources(currentUserId),
      listGraphSpaces(currentUserId),
    ])
    definitions.value = defs.items
    llmConfigs.value = llm
    embeddingConfigs.value = embedding
    milvusConfigs.value = milvus
    mysqlDatasources.value = mysql
    graphSpaces.value = spaces
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
}

function openCreate() {
  void loadDialogResources()
  createOpen.value = true
}

function jobScriptLabel(job: WorkflowJob): string {
  if (job.taskType === 'chain') {
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
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    triggeringJobId.value = ''
  }
}

async function onToggleState(job: WorkflowJob) {
  // 方向必须按统一状态推导：运行中(含已暂停但仍在跑)→暂停；已暂停→恢复。
  // 用原始 job.status 推导会在「运行中点暂停」后再点变成反向操作。
  const active = deriveJobUnifiedStatus(job) === '已暂停'
  try {
    await updateJobState(job.id, active)
    showToast(active ? '已恢复' : '已暂停', 'success')
    await loadData()
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
}

async function onDelete(job: WorkflowJob) {
  if (!window.confirm(`确认删除任务「${job.name}」？执行历史将保留。`)) return
  try {
    await deleteJob(job.id)
    showToast('任务已删除', 'success')
    await loadData()
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  }
}

function openJobDetail(job: WorkflowJob) {
  void router.push({ name: 'job-detail', params: { jobId: job.id } })
}

function executionStatusClass(status: string): string {
  const s = status.toUpperCase()
  if (s === 'COMPLETED') return 'ok'
  if (s === 'FAILED' || s === 'CANCELED' || s === 'TERMINATED' || s === 'TIMED_OUT') return 'err'
  if (s === 'QUEUED') return 'warn'
  return 'run'
}

onMounted(loadData)
</script>

<template>
  <main class="graph-build-page">
    <div class="gb-actions">
      <button type="button" class="primary" @click="openCreate">＋ 新建任务</button>
      <button type="button" :disabled="loading" @click="loadData">{{ loading ? '刷新中…' : '刷新' }}</button>
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
        <div class="gb-filters">
          <a-select id="graph-build-filter-status" v-model="filterStatus" class="gb-filter-select" placeholder="状态" allow-clear>
            <a-option value="未运行">未运行</a-option>
            <a-option value="运行中">运行中</a-option>
            <a-option value="已暂停">已暂停</a-option>
            <a-option value="已完成">已完成</a-option>
            <a-option value="运行失败">运行失败</a-option>
          </a-select>
          <a-select id="graph-build-filter-type" v-model="filterTaskType" class="gb-filter-select" placeholder="类型" allow-clear>
            <a-option value="single">单脚本抽取</a-option>
            <a-option value="chain">多脚本串行</a-option>
            <a-option value="upload">上传脚本</a-option>
          </a-select>
          <a-input id="graph-build-filter-name" v-model="filterName" class="gb-search-input" :max-length="SEARCH_KEYWORD_MAX_LENGTH" aria-label="按名称搜索" placeholder="按名称搜索"><template #prefix><IconSearch /></template></a-input>
        </div>
      </header>
      <div class="gb-jobs-panel">
      <div class="gb-task-table">
        <table>
          <thead>
            <tr><th>任务名</th><th>类型</th><th>脚本</th><th>图空间</th><th>调度</th><th>状态</th><th>最近任务 ID</th><th>最近执行</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="job in filteredJobs" :key="job.id">
              <td><b>{{ job.name }}</b></td>
              <td>{{ TASK_TYPE_LABELS[job.taskType] || job.taskType }}</td>
              <td><code>{{ jobScriptLabel(job) }}</code></td>
              <td>{{ job.graphSpace || '默认' }}</td>
              <td>{{ job.schedule.kind === 'cron' ? `cron ${job.schedule.cron}` : '单次' }}</td>
              <td><span :class="JOB_STATUS_TONE[deriveJobUnifiedStatus(job)]">{{ deriveJobUnifiedStatus(job) }}</span></td>
              <td>
                <code v-if="job.lastExecutionId">{{ job.lastExecutionId }}</code>
                <span v-else class="muted">—</span>
              </td>
              <td>
                <span v-if="job.lastExecutionStatus" :class="executionStatusClass(job.lastExecutionStatus)">{{ job.lastExecutionStatus }}</span>
                <span v-else class="muted">未执行</span>
                <small v-if="job.lastRunAt" class="gb-last-run">{{ job.lastRunAt }}</small>
              </td>
              <td class="gb-job-actions">
                <button v-if="['未运行', '运行失败'].includes(deriveJobUnifiedStatus(job))" type="button" class="primary" :disabled="triggeringJobId === job.id" @click="onTrigger(job)">{{ deriveJobUnifiedStatus(job) === '运行失败' ? '重新执行' : '执行' }}</button>
                <button v-if="deriveJobUnifiedStatus(job) === '运行中'" type="button" @click="onToggleState(job)">暂停</button>
                <button v-if="deriveJobUnifiedStatus(job) === '已暂停'" type="button" class="primary" @click="onToggleState(job)">恢复</button>
                <button type="button" @click="openJobDetail(job)">查看详情</button>
                <button v-if="deriveJobUnifiedStatus(job) === '已完成' && job.schedule.kind === 'cron'" type="button" @click="onToggleState(job)">暂停调度</button>
                <button v-if="deriveJobUnifiedStatus(job) !== '运行中'" type="button" class="danger" @click="onDelete(job)">删除</button>
              </td>
            </tr>
            <tr v-if="!filteredJobs.length"><td colspan="9" class="empty">暂无任务，点击「新建任务」创建</td></tr>
          </tbody>
        </table>
      </div>
      </div>
    </section>

    <JobLaunchDialog
      :open="createOpen"
      :definitions="definitions"
      :llm-configs="llmConfigs"
      :embedding-configs="embeddingConfigs"
      :milvus-configs="milvusConfigs"
      :mysql-datasources="mysqlDatasources"
      :graph-spaces="graphSpaces"
      @close="createOpen = false"
      @created="loadData"
    />
  </main>
</template>

<style scoped>
.graph-build-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;padding:0;color:#1d2129;font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0;flex-direction:column}
.graph-build-page :deep(*){font-family:inherit;letter-spacing:0}
.gb-actions{display:flex;gap:8px;margin-bottom:12px}
.gb-actions button{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;cursor:pointer}
.gb-actions .primary{border-color:#165dff;background:#165dff;color:#fff}
.gb-summary{display:flex;gap:16px;margin-bottom:16px}
.gb-summary article{display:flex;flex:1;min-height:80px;gap:8px;padding:12px 16px;border:1px solid #e5e6eb;border-radius:6px;background:#fff;flex-direction:column;justify-content:center}
.gb-summary span{color:#1d2129;font-size:16px;line-height:24px;font-weight:600}
.gb-summary strong{color:#1d2129;font-size:28px;line-height:32px;font-weight:600;letter-spacing:0}
.gb-summary__label,.gb-summary__task-stats{display:flex;align-items:center;min-width:0}.gb-summary__label{gap:8px}.gb-summary__hint{display:inline-flex;align-items:center;justify-content:center;flex:0 0 24px;width:24px;height:24px;padding:0;border:0;border-radius:4px;background:transparent;color:#86909c;cursor:help}.gb-summary__hint:hover,.gb-summary__hint:focus-visible{background:#f2f3f5;color:#165dff}.gb-summary__hint svg{width:16px;height:16px}
.gb-jobs-section{display:flex;flex:1;min-height:0;flex-direction:column;gap:16px}
.gb-jobs-toolbar{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:16px;min-height:32px;box-sizing:border-box;color:#1d2129}
.gb-section-title{position:relative;padding-left:11px;font-size:16px;line-height:24px;font-weight:600}
.gb-section-title::before{position:absolute;top:5px;left:0;width:3px;height:14px;border-radius:1px;background:#165dff;content:""}
.gb-jobs-panel{display:flex;flex:1;min-height:0;overflow:hidden;border:1px solid #e5e6eb;border-radius:6px;background:#fff;box-shadow:none;flex-direction:column}
.gb-filters{display:flex;align-items:center;gap:8px;font-weight:400}
.gb-task-table{flex:1;min-height:0;overflow:auto;padding:0}
/* 9 列任务表在窄视口下禁止压扁列（否则中文逐字换行"竖排"）：列内容不足时横向滚动 */
.gb-task-table table{width:100%;min-width:1200px;margin:0;border-collapse:collapse;font-size:14px;line-height:22px}
.gb-task-table th{position:sticky;z-index:2;top:0;height:40px;padding:0 16px;background:#f7f8fa;color:#1d2129;font-size:14px;line-height:22px;font-weight:500;text-align:left;white-space:nowrap}
.gb-task-table td{height:40px;padding:0 16px;border-bottom:1px solid #e5edf8;color:#344763;font-size:14px;line-height:22px;font-weight:400;vertical-align:middle}
.gb-task-table tbody tr:hover td{background:#f4f8ff}
.gb-task-table code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-family:inherit;font-size:14px;line-height:22px;font-weight:400}
.gb-task-table b{color:#1d2129;font-weight:400}
.gb-last-run{display:block;color:#8191aa;font-size:12px;line-height:20px;font-weight:400}
.gb-job-actions{display:flex;gap:6px;white-space:nowrap}
.gb-job-actions button{height:26px;padding:0 10px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;cursor:pointer}
.gb-job-actions button.primary{border-color:#165dff;background:#165dff;color:#fff}
.gb-job-actions button.danger{border-color:#f6b9b4;color:#b42318}
.gb-job-actions button:disabled{opacity:.45;cursor:not-allowed}
.empty{padding:40px 14px;text-align:center;color:#8290a7;font-size:12px;line-height:20px;font-weight:400}
.muted{color:#8191aa;font-size:12px;line-height:20px;font-weight:400}
span.ok,span.err,span.warn,span.run{display:inline-flex;align-items:center;gap:6px;font-size:14px;line-height:22px;border-radius:0;background:transparent;padding:0;white-space:nowrap}
span.ok::before,span.err::before,span.warn::before,span.run::before{display:block;flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}
span.ok{color:#067647}
span.err{color:#b42318}
span.warn{color:#b54708}
span.run{color:#175cd3}
</style>
<style>
.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-wrapper{box-sizing:border-box;width:280px;min-width:280px;max-width:280px;height:32px;min-height:32px;padding:0 12px;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:0 0 280px}
.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-wrapper:hover{border-color:#4080ff!important;background:#fff!important}
.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-wrapper:focus-within,.app-workspace .gb-filters #graph-build-filter-name.gb-search-input.arco-input-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.app-workspace .gb-filters #graph-build-filter-name .arco-input-prefix{padding-right:8px;color:#4e5969}.app-workspace .gb-filters #graph-build-filter-name.arco-input-focus .arco-input-prefix{color:#165dff}.app-workspace .gb-filters #graph-build-filter-name .arco-input-prefix svg{width:16px;height:16px;font-size:16px}
.app-workspace .gb-filters #graph-build-filter-name input.arco-input{box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type).gb-filter-select.arco-select-view{display:inline-flex;box-sizing:border-box;align-items:center;width:160px;min-width:160px;max-width:160px;height:32px;min-height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:0 0 160px}
.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type).gb-filter-select.arco-select-view:hover{border-color:#4080ff!important;background:#fff!important}
.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type).gb-filter-select.arco-select-view:focus-within,.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type).gb-filter-select.arco-select-view-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type) input.arco-select-view-input{box-sizing:border-box;width:100%;height:30px!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type) .arco-select-view-input-hidden{position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important}.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type) .arco-select-view-value{min-width:0;overflow:hidden;font-size:14px;line-height:22px;font-weight:400;text-overflow:ellipsis;white-space:nowrap}
.app-workspace .gb-filters :is(#graph-build-filter-status,#graph-build-filter-type) :is(.arco-select-view-input,.arco-select-view-value){background:transparent!important}
</style>
