<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import {
  getTaskOverview,
  listExecutions,
  type AccessReport,
  type WorkflowExecution,
} from '../../api/workflowOperations'
import { accessChips, mergeAccessReports } from '../../utils/accessReport'
import {
  listAllSchemas,
  schemaErrorMessage,
  type SchemaDefinition,
} from '../../api/schemaManagement'
import { listLlmConfigs, type LlmConfig } from '../../api/llmConfig'
import JobLaunchDialog from '../../components/JobLaunchDialog.vue'
import { useToast } from '../../composables/use-toast'

const { showToast } = useToast()
const router = useRouter()
const currentUserId = localStorage.getItem('tech-kg-schema-user-id') || 'platform-admin'

const schemas = ref<SchemaDefinition[]>([])
const llmConfigs = ref<LlmConfig[]>([])
const executions = ref<WorkflowExecution[]>([])
const summary = ref<{ label: string; value: string; hint: string }[]>([])
const loading = ref(false)
const launchOpen = ref(false)
const selectedExecution = ref<WorkflowExecution | null>(null)

const jobSchemas = computed(() => schemas.value.filter((s) => s.script?.workflowDefinitionId))

/** execution 级聚合：单脚本直接读 output.access；多步 pipeline 合并各 step 的 access。 */
const executionAccess = computed<AccessReport | undefined>(() => {
  const output = selectedExecution.value?.output
  if (!output || typeof output !== 'object') return undefined
  const record = output as Record<string, unknown>
  if (record.access && typeof record.access === 'object') {
    return record.access as AccessReport
  }
  const steps = record.steps
  if (steps && typeof steps === 'object') {
    return mergeAccessReports(
      Object.values(steps as Record<string, { access?: AccessReport }>).map(
        (step) => step?.access,
      ),
    )
  }
  return undefined
})
const executionAccessChips = computed(() => accessChips(executionAccess.value))

async function loadData() {
  loading.value = true
  try {
    const [schemaList, configs, overview, execList] = await Promise.all([
      listAllSchemas(currentUserId),
      listLlmConfigs(currentUserId),
      getTaskOverview(),
      listExecutions(200),
    ])
    schemas.value = schemaList
    llmConfigs.value = configs
    summary.value = overview.summary
    executions.value = execList.items
  } catch (error) {
    showToast(schemaErrorMessage(error), 'warning')
  } finally {
    loading.value = false
  }
}

function selectExecution(execution: WorkflowExecution) {
  selectedExecution.value = execution
}

function onLaunched() {
  showToast('作业已下发，可在列表查看执行状态', 'success')
  void loadData()
}

function openFlowDetail(taskId: string | undefined) {
  if (!taskId) {
    showToast('该记录无关联任务详情（旧记录）', 'warning')
    return
  }
  void router.push({ name: 'processing-instance-detail', params: { instanceId: taskId } })
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
        <h1>图谱构建 · 作业运行监控</h1>
        <p>选择作业 → 配置运行时参数（大模型 / 执行模式 / 增量游标）→ 执行一次或定期调度</p>
      </div>
      <div class="gb-actions">
        <button type="button" :disabled="loading" @click="loadData">{{ loading ? '刷新中…' : '刷新' }}</button>
        <button type="button" class="primary" @click="launchOpen = true">启动作业</button>
      </div>
    </header>

    <section class="gb-summary">
      <article v-for="item in summary" :key="item.label">
        <span>{{ item.label }}</span>
        <strong>{{ item.value }}</strong>
        <em v-if="item.hint">{{ item.hint }}</em>
      </article>
    </section>

    <section class="gb-body">
      <div class="gb-task-panel">
        <header><strong>作业执行记录（{{ executions.length }}）</strong></header>
        <div class="gb-task-table">
          <table>
            <thead>
              <tr><th>执行 ID</th><th>工作流定义</th><th>状态</th><th>下发模式</th><th>启动时间</th></tr>
            </thead>
            <tbody>
              <tr v-for="e in executions" :key="e.id" :class="{ active: selectedExecution?.id === e.id }" @click="selectExecution(e)">
                <td><code>{{ e.id }}</code></td>
                <td><code>{{ e.definitionId }}</code></td>
                <td><span :class="executionStatusClass(e.status)">{{ e.status }}</span></td>
                <td>{{ e.dispatchMode || '—' }}</td>
                <td>{{ e.startedAt }}</td>
              </tr>
              <tr v-if="!executions.length"><td colspan="5" class="empty">暂无执行记录，点击「启动作业」下发一次</td></tr>
            </tbody>
          </table>
        </div>
      </div>

      <aside class="gb-detail-panel">
        <header><strong>执行详情</strong></header>
        <div v-if="!selectedExecution" class="empty">选择左侧记录查看详情</div>
        <div v-else class="gb-detail-body">
          <div class="gb-detail-meta">
            <div><span>执行 ID</span><code>{{ selectedExecution.id }}</code></div>
            <div><span>工作流定义</span><code>{{ selectedExecution.definitionId }}</code></div>
            <div><span>状态</span><strong :class="executionStatusClass(selectedExecution.status)">{{ selectedExecution.status }}</strong></div>
            <div><span>启动时间</span><code>{{ selectedExecution.startedAt }}</code></div>
            <div v-if="selectedExecution.runId"><span>Run ID</span><code>{{ selectedExecution.runId }}</code></div>
            <div v-if="selectedExecution.completedAt"><span>完成时间</span><code>{{ selectedExecution.completedAt }}</code></div>
          </div>
          <div v-if="selectedExecution.message" class="gb-message">
            <strong>消息</strong>
            <p>{{ selectedExecution.message }}</p>
          </div>
          <div v-if="selectedExecution.payload && Object.keys(selectedExecution.payload).length" class="gb-logs">
            <strong>入参 payload</strong>
            <pre>{{ JSON.stringify(selectedExecution.payload, null, 2) }}</pre>
          </div>
          <div v-if="selectedExecution.output" class="gb-logs">
            <strong>输出</strong>
            <pre>{{ typeof selectedExecution.output === 'string' ? selectedExecution.output : JSON.stringify(selectedExecution.output, null, 2) }}</pre>
          </div>
          <div v-if="executionAccessChips.length" class="gb-access">
            <strong>实际访问资源 <span>观测式溯源</span></strong>
            <div class="access-chips">
              <span v-for="chip in executionAccessChips" :key="`${chip.group}:${chip.name}`" class="access-chip">
                <em>{{ chip.group }}</em>
                <code>{{ chip.name }}</code>
                <b v-if="chip.read" class="op-read">R</b>
                <b v-if="chip.write" class="op-write">W</b>
                <small>{{ chip.detail }}</small>
              </span>
            </div>
          </div>
          <div class="gb-detail-actions">
            <button type="button" class="primary" @click="openFlowDetail(selectedExecution.taskId)">查看流程详情 →</button>
          </div>
        </div>
      </aside>
    </section>

    <JobLaunchDialog
      :open="launchOpen"
      :schemas="jobSchemas"
      :llm-configs="llmConfigs"
      @close="launchOpen = false"
      @launched="onLaunched"
    />
  </main>
</template>

<style scoped>
.graph-build-page{display:flex;height:100%;min-height:0;overflow:hidden;padding:2px 2px 18px;color:#142443;flex-direction:column;box-sizing:border-box}
.gb-header{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px}
.gb-header h1{margin:0;font-size:18px;color:#1d2129}
.gb-header p{margin:4px 0 0;color:#66758f;font-size:12px}
.gb-actions{display:flex;gap:8px}
.gb-actions button{height:34px;padding:0 14px;border:1px solid #c9cdd4;border-radius:6px;background:#fff;color:#4e5969;font-size:13px;cursor:pointer}
.gb-actions .primary{border-color:#165dff;background:#165dff;color:#fff}
.gb-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:12px}
.gb-summary article{display:grid;gap:3px;padding:12px 14px;border:1px solid #bfd6fa;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}
.gb-summary span{color:#687996;font-size:11px}
.gb-summary strong{font-size:22px}
.gb-summary em{color:#8191aa;font-size:10px;font-style:normal}
.gb-body{display:grid;flex:1;min-height:0;grid-template-columns:minmax(0,1.4fr) minmax(0,1fr);gap:12px}
.gb-task-panel,.gb-detail-panel{display:flex;min-height:0;overflow:hidden;border:1px solid #bcd4f7;border-radius:9px;background:#fff;box-shadow:0 10px 24px rgba(48,105,194,.08);flex-direction:column}
.gb-task-panel>header,.gb-detail-panel>header{flex:0 0 auto;padding:11px 14px;border-bottom:1px solid #e3ebf6;background:#f8fbff;font-size:13px;color:#243b5d}
.gb-task-table{flex:1;min-height:0;overflow:auto}
.gb-task-table table{width:100%;border-collapse:collapse;font-size:12px}
.gb-task-table th{position:sticky;z-index:2;top:0;padding:10px 12px;background:#eef5ff;color:#5a6c88;text-align:left;white-space:nowrap}
.gb-task-table td{padding:10px 12px;border-bottom:1px solid #e5edf8;color:#344763;vertical-align:middle}
.gb-task-table tbody tr{cursor:pointer}
.gb-task-table tbody tr:hover td{background:#f4f8ff}
.gb-task-table tbody tr.active td{background:#eaf2ff}
.gb-task-table code{padding:2px 6px;border-radius:4px;background:#edf4ff;color:#165dff;font-size:11px}
.empty{padding:40px 14px;text-align:center;color:#8290a7;font-size:12px}
.gb-detail-body{flex:1;min-height:0;overflow:auto;padding:14px;display:flex;flex-direction:column;gap:14px}
.gb-detail-meta{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.gb-detail-meta>div{display:flex;flex-direction:column;gap:3px;padding:9px 11px;border:1px solid #e3ebf6;border-radius:6px;background:#fafcff}
.gb-detail-meta span{color:#687996;font-size:10px}
.gb-detail-meta code,.gb-detail-meta strong{font-size:12px;color:#1d2129}
.gb-detail-meta code{padding:1px 5px;border-radius:3px;background:#edf4ff;color:#165dff;font-size:11px}
.gb-steps{display:flex;flex-direction:column;gap:4px}
.gb-steps-head{font-size:12px;color:#4e5969;font-weight:600;margin-bottom:4px}
.gb-step{display:flex;align-items:center;gap:8px;padding:7px 9px;border:1px solid #e3ebf6;border-radius:5px;background:#fff}
.gb-step-index{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#eaf2ff;color:#165dff;font-size:10px;font-weight:600}
.gb-step-name{flex:1;font-size:12px;color:#344763}
.gb-step-status{padding:2px 7px;border-radius:999px;font-size:10px}
.gb-step-status.ok{background:#dcfae6;color:#067647}
.gb-step-status.run{background:#eaf2ff;color:#175cd3}
.gb-step-status.warn{background:#fff3d8;color:#b54708}
.gb-step-status.pending{background:#f0f2f5;color:#5e6b7e}
.gb-step-duration{color:#8191aa;font-size:10px}
.gb-logs{display:flex;flex-direction:column;gap:5px}
.gb-logs strong{font-size:12px;color:#4e5969}
.gb-logs pre{margin:0;max-height:200px;overflow:auto;padding:10px;background:#0d1117;border-radius:6px;color:#c9d1d9;font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:11px;line-height:17px;white-space:pre-wrap}
.gb-access{display:flex;flex-direction:column;gap:7px}
.gb-access strong{display:flex;align-items:center;gap:7px;font-size:12px;color:#4e5969}
.gb-access strong span{padding:2px 6px;border-radius:4px;background:#e5f6ee;color:#067647;font-size:9px;font-weight:500}
.access-chips{display:flex;flex-wrap:wrap;gap:7px}
.access-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid #cfe0d8;border-radius:6px;background:#fff;font-size:11px;color:#344763}
.access-chip em{color:#067647;font-size:10px;font-style:normal;white-space:nowrap}
.access-chip code{padding:1px 5px;border-radius:3px;background:#edf4ff;color:#165dff;font-size:10px}
.access-chip b{display:grid;place-items:center;min-width:16px;height:16px;border-radius:4px;color:#fff;font-size:10px;font-style:normal}
.access-chip b.op-read{background:#175cd3}
.access-chip b.op-write{background:#f79009}
.access-chip small{color:#8191aa;font-size:10px;white-space:nowrap}
.gb-detail-actions{display:flex;justify-content:flex-end}
.gb-detail-actions button{height:32px;padding:0 14px;border:0;border-radius:6px;background:#165dff;color:#fff;font-size:12px;cursor:pointer}
.muted{color:#8191aa;font-size:11px}
span.ok{display:inline-flex;padding:2px 8px;border-radius:999px;background:#dcfae6;color:#067647;font-size:11px}
span.err{display:inline-flex;padding:2px 8px;border-radius:999px;background:#fee4e2;color:#b42318;font-size:11px}
span.warn{display:inline-flex;padding:2px 8px;border-radius:999px;background:#fff3d8;color:#b54708;font-size:11px}
span.run{display:inline-flex;padding:2px 8px;border-radius:999px;background:#eaf2ff;color:#175cd3;font-size:11px}
@media(max-width:1200px){.gb-summary{grid-template-columns:repeat(2,1fr)}.gb-body{grid-template-columns:1fr}}
</style>
