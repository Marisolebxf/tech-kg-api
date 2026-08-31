<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  deleteJob,
  getTaskOverview,
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
const summary = ref<{ label: string; value: string; hint: string }[]>([])
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

const filteredJobs = computed(() => {
  const name = filterName.value.trim().toLowerCase()
  return jobs.value.filter((job) => {
    if (name && !job.name.toLowerCase().includes(name)) return false
    if (filterStatus.value && job.status !== filterStatus.value) return false
    if (filterTaskType.value && job.taskType !== filterTaskType.value) return false
    return true
  })
})

async function loadData() {
  loading.value = true
  try {
    const [jobList, overview] = await Promise.all([listJobs(), getTaskOverview()])
    jobs.value = jobList.items
    summary.value = overview.summary
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

function jobRunning(job: WorkflowJob): boolean {
  return job.lastExecutionStatus === 'RUNNING'
}

async function onTrigger(job: WorkflowJob) {
  if (jobRunning(job) || triggeringJobId.value) return
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
  const active = job.status !== '启用'
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
    <header class="gb-header">
      <div>
        <h1>任务中心</h1>
        <p>创建一次性 / 周期性任务 → 触发执行 → 查看执行历史与每步输入输出</p>
      </div>
      <div class="gb-actions">
        <button type="button" :disabled="loading" @click="loadData">{{ loading ? '刷新中…' : '刷新' }}</button>
        <button type="button" class="primary" @click="openCreate">新建任务</button>
      </div>
    </header>

    <section class="gb-summary">
      <article v-for="item in summary" :key="item.label">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <em v-if="item.hint">{{ item.hint }}</em>
      </article>
    </section>

    <section class="gb-jobs-panel">
      <header>
        <strong>任务列表（{{ filteredJobs.length }}）</strong>
        <div class="gb-filters">
          <input v-model="filterName" :maxlength="SEARCH_KEYWORD_MAX_LENGTH" placeholder="按名称搜索" />
          <a-select v-model="filterStatus" placeholder="状态" allow-clear style="width: 110px">
            <a-option value="启用">启用</a-option>
            <a-option value="暂停">暂停</a-option>
          </a-select>
          <a-select v-model="filterTaskType" placeholder="类型" allow-clear style="width: 130px">
            <a-option value="single">单脚本抽取</a-option>
            <a-option value="chain">多脚本串行</a-option>
            <a-option value="upload">上传脚本</a-option>
          </a-select>
        </div>
      </header>
      <div class="gb-task-table">
        <table>
          <thead>
            <tr><th>任务名</th><th>类型</th><th>脚本</th><th>图空间</th><th>调度</th><th>状态</th><th>最近执行</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="job in filteredJobs" :key="job.id">
              <td><b>{{ job.name }}</b></td>
              <td>{{ TASK_TYPE_LABELS[job.taskType] || job.taskType }}</td>
              <td><code>{{ jobScriptLabel(job) }}</code></td>
              <td>{{ job.graphSpace || '默认' }}</td>
              <td>{{ job.schedule.kind === 'cron' ? `cron ${job.schedule.cron}` : '单次' }}</td>
              <td><span :class="job.status === '启用' ? 'ok' : 'warn'">{{ job.status }}</span></td>
              <td>
                <span v-if="job.lastExecutionStatus" :class="executionStatusClass(job.lastExecutionStatus)">{{ job.lastExecutionStatus }}</span>
                <span v-else class="muted">未执行</span>
                <small v-if="job.lastRunAt" class="gb-last-run">{{ job.lastRunAt }}</small>
              </td>
              <td class="gb-job-actions">
                <button type="button" class="primary" :disabled="jobRunning(job) || triggeringJobId === job.id" @click="onTrigger(job)">执行</button>
                <button v-if="job.schedule.kind === 'cron'" type="button" @click="onToggleState(job)">{{ job.status === '启用' ? '暂停' : '恢复' }}</button>
                <button type="button" @click="openJobDetail(job)">查看详情</button>
                <button type="button" class="danger" @click="onDelete(job)">删除</button>
              </td>
            </tr>
            <tr v-if="!filteredJobs.length"><td colspan="8" class="empty">暂无任务，点击「新建任务」创建</td></tr>
          </tbody>
        </table>
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
.graph-build-page{display:flex;height:100%;min-height:0;overflow:hidden;padding:2px 2px 18px;color:#142443;flex-direction:column;box-sizing:border-box}
.gb-header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}
.gb-header h1{margin:0;font-size:18px;color:#1d2129}
.gb-header p{margin:4px 0 0;color:#66758f;font-size:12px}
.gb-actions{display:flex;gap:8px}
.gb-actions button{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;cursor:pointer}
.gb-actions .primary{border-color:#165dff;background:#165dff;color:#fff}
.gb-summary{display:flex;gap:16px;margin-bottom:16px}
.gb-summary article{flex:1;display:grid;gap:4px;padding:8px 16px;border:1px solid #e5e6eb;border-radius:4px;background:#fff}
.gb-summary span,.gb-summary em{font-size:12px;line-height:20px;color:#687996;font-style:normal}
.gb-summary strong{font-size:20px;line-height:28px;font-weight:600}
.gb-jobs-panel{display:flex;flex:1;min-height:0;overflow:hidden;border:1px solid #bcd4f7;border-radius:9px;background:#fff;box-shadow:0 10px 24px rgba(48,105,194,.08);flex-direction:column}
.gb-jobs-panel>header{display:flex;flex:0 0 auto;align-items:center;justify-content:space-between;gap:14px;min-height:40px;box-sizing:border-box;padding:8px 16px;border-bottom:1px solid #e3ebf6;background:#f7f8fa;font-size:14px;line-height:22px;font-weight:600;color:#1d2129}
.gb-filters{display:flex;align-items:center;gap:8px;font-weight:400}
.gb-filters input{height:30px;width:200px;padding:0 10px;border:1px solid #c9cdd4;border-radius:4px;font-size:12px}
.gb-task-table{flex:1;min-height:0;overflow:auto}
.gb-task-table table{width:100%;border-collapse:collapse;font-size:13px;line-height:22px}
.gb-task-table th{position:sticky;z-index:2;top:0;padding:0 16px;height:40px;background:#f7f8fa;color:#1d2129;font-weight:500;text-align:left;white-space:nowrap}
.gb-task-table td{height:40px;padding:0 16px;border-bottom:1px solid #e5edf8;color:#344763;vertical-align:middle}
.gb-task-table tbody tr:hover td{background:#f4f8ff}
.gb-task-table code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:12px}
.gb-task-table b{font-weight:600;color:#1d2129}
.gb-last-run{display:block;color:#8191aa;font-size:11px;line-height:16px}
.gb-job-actions{display:flex;gap:6px;white-space:nowrap}
.gb-job-actions button{height:26px;padding:0 10px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:12px;cursor:pointer}
.gb-job-actions button.primary{border-color:#165dff;background:#165dff;color:#fff}
.gb-job-actions button.danger{border-color:#f6b9b4;color:#b42318}
.gb-job-actions button:disabled{opacity:.45;cursor:not-allowed}
.empty{padding:40px 14px;text-align:center;color:#8290a7;font-size:12px}
.muted{color:#8191aa;font-size:12px}
span.ok,span.err,span.warn,span.run{display:inline-flex;align-items:center;gap:6px;font-size:14px;line-height:22px;border-radius:0;background:transparent;padding:0}
span.ok::before,span.err::before,span.warn::before,span.run::before{display:block;flex:0 0 6px;width:6px;height:6px;border-radius:50%;background:currentColor;content:""}
span.ok{color:#067647}
span.err{color:#b42318}
span.warn{color:#b54708}
span.run{color:#175cd3}
</style>
