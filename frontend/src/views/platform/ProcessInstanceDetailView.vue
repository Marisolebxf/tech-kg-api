<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { deriveJobUnifiedStatus, getExecution, getJob, getTask, listExecutions, retryTask, TRIGGER_SOURCE_LABEL, type AccessReport, type PipelineActivityInfo, type PipelineStepInfo, type ProcessingInstance, type UpdateBatch, type WorkflowExecution, type WorkflowJob } from '../../api/workflowOperations'
import { getSchemaDetail, type SchemaDefinition } from '../../api/schemaManagement'
import { currentUserId } from '../../api/currentUser'
import { accessChips } from '../../utils/accessReport'
import ListPagination from '../../components/list-pagination.vue'
import { useClientPagination } from '../../composables/use-client-pagination'

const triggerLabel = (e: WorkflowExecution) => TRIGGER_SOURCE_LABEL[e.triggerSource ?? 'MANUAL'] ?? '手动触发'
const failureCount = (e: WorkflowExecution) =>
  ((e as { output?: { failures?: { count?: number } } }).output?.failures?.count) ?? '—'

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
  input?: unknown
  output?: unknown
  access?: AccessReport
  /** chain 任务：脚本 step 内含的 activity step 数（抽屉可展开）。 */
  activityCount?: number
  /** 执行序（内部排序用） */
  position?: number
}

function stepDuration(startedAt?: string, finishedAt?: string): string {
  if (!startedAt || !finishedAt) return '-'
  const start = new Date(startedAt.replace(' ', 'T')).getTime()
  const end = new Date(finishedAt.replace(' ', 'T')).getTime()
  if (!Number.isFinite(start) || !Number.isFinite(end)) return '-'
  const seconds = Math.max(Math.round((end - start) / 1000), 0)
  return seconds < 60 ? `${seconds}s` : `${Math.floor(seconds / 60)}m${String(seconds % 60).padStart(2, '0')}s`
}

const route = useRoute()
const router = useRouter()
const jobId = computed(() => String(route.params.jobId || ''))
const job = ref<WorkflowJob | null>(null)
const taskId = computed(() => String(route.params.taskId || route.params.instanceId || 'UPD-20260714'))
const processingInstance = ref<ProcessingInstance>()
const fallbackBatch: UpdateBatch = { id: '-', name: '任务详情', updateDate: '-', dataWindow: '-', source: '-', trigger: '-', input: 0, entities: 0, relations: 0, completed: 0, abnormal: 0, progress: 0, status: '处理中', startedAt: '-', completedAt: '-' }
const batch = computed(() => processingInstance.value?.batch ?? fallbackBatch)
const isConstructionTask = computed(() => processingInstance.value?.stage === '图谱构建' || String(route.params.area) === 'construction')
const needsTaskReview = computed(() => ['执行出错', '等待人工审核'].includes(processingInstance.value?.taskStatus ?? ''))
const activeTab = ref<DetailTab>('overview')
const isPipelineTask = computed(() => ['kg.custom.steps', 'kg.custom.chain', 'kg.schema.extract.chain'].includes(processingInstance.value?.workflowType ?? ''))
/** 多脚本串行任务：流程里每个 step 是一个 Schema 抽取（旧版为一个脚本），点击在按钮下方展开其 activity steps。 */
const isChainTask = computed(() => ['kg.custom.chain', 'kg.schema.extract.chain'].includes(processingInstance.value?.workflowType ?? ''))
/** chain 内联展开：当前展开的脚本 step 与选中的 activity step。 */
const selectedActivityId = ref(String(route.query.activity || ''))
const expandedScriptId = ref(selectedActivityId.value ? String(route.query.step || '') : '')

const steps = computed<Step[]>(() => {
  if (processingInstance.value?.workflowType === 'kg.custom.python') {
    // 单脚本任务：脚本整体就是一个 activity step（execute_python_script），直接展示任务级输入输出
    const instance = processingInstance.value
    const failed = instance.taskStatus === '执行出错'
    return [{
      id: 'script',
      phase: '图谱构建',
      name: instance.objectName || '脚本执行',
      status: instance.taskStatus === '执行中' ? '运行中' : failed ? '需人工处理' : '成功',
      risk: (failed ? '高风险' : '低风险') as RiskLevel,
      count: '-',
      abnormal: failed ? '1' : '0',
      duration: '-',
      description: 'activity: execute_python_script · 脚本入口 workflow(payload) 整体执行',
      engine: 'Temporal Script Worker',
      input: instance.input,
      output: instance.output,
    }]
  }
  if (processingInstance.value?.workflowType === 'kg.schema.extract') {
    // 平台喂数抽取：workflow 不上报 pipeline step（任务 steps 恒空），用任务
    // 回写的真实统计合成步骤——否则概况卡全落占位符（运行状态=待执行、处理数量=-）
    return [buildExtractStep(processingInstance.value)]
  }
  if (isPipelineTask.value) {
    const built = buildPipelineSteps()
    // kg.custom.steps 单脚本：流程 step 与脚本内 activity step 一一对应
    if (built.length) return built
    // pipeline 实时查询失败（如历史过期）时，退回落库的 task.steps（含真实 input/output）
  }
  if (processingInstance.value?.steps?.length) {
    return processingInstance.value.steps.map((step) => ({
      ...step,
      risk: step.risk ?? (step.status === '需人工处理' ? '高风险' : step.phase === '图谱构建' ? '中风险' : '低风险'),
      engine: step.engine ?? (step.phase === '图谱构建' ? 'Temporal KG Worker' : 'Temporal Data Worker'),
    }))
  }
  // 无真实流程数据时不展示假步骤
  return []
})

function initialStepId() {
  // 统一展示全部步骤；失败步骤优先选中，否则选当前/第一个
  const failed = steps.value.find((step) => step.status === '需人工处理')
  if (failed) return failed.id
  const state = processingInstance.value?.pipeline
  if (state?.current) return state.current
  return steps.value[0]?.id ?? ''
}

function mapPipelineStatus(s: PipelineStepInfo['status']): StepStatus {
  switch (s) {
    case 'COMPLETED': return '成功'
    case 'RUNNING': return '运行中'
    case 'FAILED': return '需人工处理'
    default: return '待执行'
  }
}

function buildPipelineSteps(): Step[] {
  const state = processingInstance.value?.pipeline
  if (!state?.steps) return [] as Step[]
  const engine = processingInstance.value?.workflowType ?? 'kg.custom.steps'
  const built = Object.entries(state.steps).map(([id, info]) => ({
    id,
    phase: '图谱构建' as const,
    name: info.name || id,
    status: mapPipelineStatus(info.status),
    risk: (info.status === 'FAILED' ? '高风险' : '低风险') as RiskLevel,
    count: typeof info.records === 'number'
      ? `${info.records} 行 / 写图 ${info.written ?? 0} 条`
      : info.activities
        ? `${Object.keys(info.activities).length} 个 activity`
        : info.attempt
          ? `attempt=${info.attempt}`
          : '-',
    abnormal: typeof info.failed === 'number' ? String(info.failed) : info.error ? '1' : '0',
    duration: stepDuration(info.startedAt, info.finishedAt),
    description: info.error || info.description || `${engine} · ${info.status}`,
    engine,
    position: info.position,
    input: info.input,
    output: info.output,
    access: info.access,
    activityCount: info.activities ? Object.keys(info.activities).length : undefined,
  }))
  // Temporal JSON 编码按 key 排序：按 position 还原执行序（无 position 保持原序）
  if (built.some((step) => step.position != null)) {
    built.sort((a, b) =>
      (a.position ?? Number.MAX_SAFE_INTEGER) - (b.position ?? Number.MAX_SAFE_INTEGER))
  }
  // 正在执行的 step 尚未写入 state：用 current 补一个「运行中」节点，避免流程断档
  const currentKey = state.current
  const currentKnown =
    currentKey != null && Boolean(state.steps[currentKey] || state.steps[`schema:${currentKey}`])
  if (currentKey && !currentKnown) {
    built.push({
      id: currentKey,
      phase: '图谱构建',
      name: currentKey,
      status: '运行中',
      risk: '低风险',
      count: '-',
      abnormal: '0',
      duration: '-',
      description: `${engine} · 执行中`,
      engine,
      position: undefined,
      input: undefined,
      output: undefined,
      access: undefined,
      activityCount: undefined,
    })
  }
  return built
}

/** chain 任务：某脚本/Schema step 的 activity steps（实时 query 优先，落库 steps 回退）。 */
function chainActivities(scriptId: string): Array<{ id: string; info: PipelineActivityInfo }> {
  const activities = processingInstance.value?.pipeline?.steps?.[scriptId]?.activities
    // 实时 query 失败（workflow 已结束被历史淘汰）时，回退落库 task.steps（pipeline_steps 透传 activities）
    ?? processingInstance.value?.steps?.find((s) => s.id === scriptId)?.activities
  if (!activities) return []
  // Temporal JSON 编码按 key 排序：dict 序 ≠ 脚本步序，按 position 还原（旧数据无 position 保持原序）
  const entries = Object.entries(activities).map(([id, info]) => ({ id, info }))
  if (entries.some((e) => (e.info as { position?: number }).position != null)) {
    entries.sort((a, b) =>
      ((a.info as { position?: number }).position ?? Number.MAX_SAFE_INTEGER)
      - ((b.info as { position?: number }).position ?? Number.MAX_SAFE_INTEGER))
  }
  return entries
}

/** 把选中的 activity step 合成为右侧详情面板用的 Step。 */
function buildActivityStep(scriptId: string, activityId: string): Step | null {
  const entry = chainActivities(scriptId).find((item) => item.id === activityId)
  if (!entry) return null
  const scriptName = processingInstance.value?.pipeline?.steps?.[scriptId]?.name
    || processingInstance.value?.steps?.find((s) => s.id === scriptId)?.name
    || scriptId
  return {
    id: `${scriptId}::${activityId}`,
    phase: '图谱构建',
    name: `${scriptName} · ${entry.info.name || activityId}`,
    status: mapPipelineStatus(entry.info.status),
    risk: (entry.info.status === 'FAILED' ? '高风险' : '低风险') as RiskLevel,
    count: typeof entry.info.records === 'number'
      ? `${entry.info.records} 行 / 写图 ${entry.info.written ?? 0} 条`
      : entry.info.attempt ? `attempt=${entry.info.attempt}` : '-',
    abnormal: entry.info.error ? '1' : '0',
    duration: '-',
    description: entry.info.error || `脚本 activity step（${activityId}）· 输入输出为该 activity 真实上报 JSON`,
    engine: 'Temporal Activity',
    input: entry.info.input,
    output: entry.info.output,
    access: entry.info.access,
  }
}

/** kg.schema.extract 任务：用任务回写的真实统计（output.sources/failures）合成流程步骤。
 *
 * 只读 instance 自身字段——setup 期 initialStepId 就会触发 steps 求值，
 * 不能引用声明在其后的 extractOutput/selectedExecution（TDZ）。 */
function buildExtractStep(instance: ProcessingInstance): Step {
  const output = (instance.output ?? {}) as {
    sources?: Array<{ source?: string; table?: string; rows?: number; written?: number; failed?: number; watermark?: string | null; pkCursor?: string | null }>
    failures?: { count?: number }
  }
  const sources = output.sources ?? []
  const rows = sources.reduce((sum, item) => sum + Number(item.rows ?? 0), 0)
  const written = sources.reduce((sum, item) => sum + Number(item.written ?? 0), 0)
  const failed = Number(output.failures?.count ?? sources.reduce((sum, item) => sum + Number(item.failed ?? 0), 0))
  const errored = instance.taskStatus === '执行出错'
  const pending = instance.taskStatus === '等待人工审核'
  const lastCursor = [...sources].reverse().find((item) => item.watermark || item.pkCursor)
  const cursorText = lastCursor?.watermark || (lastCursor?.pkCursor ? `pk > ${lastCursor.pkCursor}` : '')
  return {
    id: 'extract',
    phase: '图谱构建',
    name: instance.objectName || '平台喂数抽取',
    status: instance.taskStatus === '执行中' ? '运行中' : errored || pending ? '需人工处理' : '成功',
    risk: (errored ? '高风险' : failed > 0 ? '中风险' : '低风险') as RiskLevel,
    count: rows ? `${rows} 行 · 写入 ${written}` : '-',
    abnormal: errored ? '1' : String(failed || 0),
    duration: '-',
    description: sources.length
      ? `kg.schema.extract · ${sources.map((item) => item.table ?? item.source ?? '来源').join('、')}${cursorText ? ` · 水位 ${cursorText}` : ''}`
      : 'kg.schema.extract · 未产出批次结果（启动失败或仍在执行）',
    engine: 'Temporal KG Worker',
    input: instance.input,
    output: instance.output,
  }
}

const selectedStepId = ref(String(route.query.step || initialStepId()))
const EMPTY_STEP: Step = { id: 'none', phase: '图谱构建', name: '暂无步骤数据', status: '待执行', risk: '低风险', count: '-', abnormal: '-', duration: '-', description: '未获取到步骤数据（workflow 可能仍在启动或状态查询失败）', engine: '-' }
const selectedStep = computed<Step>(() => {
  if (isChainTask.value && selectedActivityId.value) {
    const activityStep = buildActivityStep(selectedStepId.value, selectedActivityId.value)
    if (activityStep) return activityStep
  }
  return steps.value.find((step) => step.id === selectedStepId.value) ?? steps.value[0] ?? EMPTY_STEP
})
const visiblePhase = computed<'数据处理' | '图谱构建'>(() => steps.value[0]?.phase ?? (isConstructionTask.value ? '图谱构建' : '数据处理'))
const visibleSteps = computed(() => steps.value)
const needsReview = computed(() => needsTaskReview.value && selectedStep.value.abnormal !== '0' && selectedStep.value.abnormal !== '-')
const attentionLabel = computed(() => selectedStep.value.risk === '高风险' ? '重点关注' : selectedStep.value.risk === '中风险' ? '一般关注' : '常规节点')
const isProcessLevelIncident = computed(() => ['模型批量输出异常', 'Schema 批量映射失败', '公共字典配置异常'].includes(processingInstance.value?.reviewType ?? ''))
const isTaskExecutionFailure = computed(() => processingInstance.value?.reviewType === '单任务执行失败')
const isExecutionInterrupted = computed(() => isProcessLevelIncident.value || isTaskExecutionFailure.value)
const taskStatus = computed(() => processingInstance.value?.taskStatus ?? (isExecutionInterrupted.value ? '执行出错' : '执行完成'))
const resultStatus = computed(() => isProcessLevelIncident.value ? '流程已阻断' : isTaskExecutionFailure.value ? '未产生结果' : processingInstance.value?.status === '人工处理完成' ? '人工确认通过' : needsTaskReview.value ? '结果待确认' : '结果已通过')
const incidentScope = computed(() => isProcessLevelIncident.value ? '流程级·高风险（P0）' : needsTaskReview.value ? '任务级·中风险（P1）' : '无异常')
const blockingStrategy = computed(() => isProcessLevelIncident.value ? '阻断当前节点及下游，调整后恢复' : needsTaskReview.value ? '只隔离当前任务，其他任务继续执行' : '无需阻断')

const genericMetrics = computed(() => [
  ['运行状态', selectedStep.value.status], ['处理数量', selectedStep.value.count], ['异常数量', selectedStep.value.abnormal],
  ['执行耗时', selectedStep.value.duration], ['执行引擎', selectedStep.value.engine], ['技术关注度', attentionLabel.value],
  ['异常影响', incidentScope.value], ['阻断策略', blockingStrategy.value],
])

const selectStep = (id: string) => {
  selectedStepId.value = id
  selectedActivityId.value = ''
  activeTab.value = 'overview'
  // 多脚本任务：点击脚本 step 在按钮下方展开/收起该脚本的 activity steps
  if (isChainTask.value) {
    expandedScriptId.value = expandedScriptId.value === id ? '' : id
  }
  void router.replace({ query: { ...route.query, step: id, activity: undefined } })
}

const selectActivity = (scriptId: string, activityId: string) => {
  selectedStepId.value = scriptId
  selectedActivityId.value = activityId
  activeTab.value = 'overview'
  void router.replace({ query: { ...route.query, step: scriptId, activity: activityId } })
}

const clearActivitySelection = () => {
  selectedActivityId.value = ''
  activeTab.value = 'overview'
  void router.replace({ query: { ...route.query, activity: undefined } })
}

// === kg.custom.steps 流水线状态 ===
const pipelineSteps = computed(() => {
  const state = processingInstance.value?.pipeline
  if (!state?.steps) return [] as { id: string; info: PipelineStepInfo; isCurrent: boolean }[]
  return Object.entries(state.steps).map(([id, info]) => ({
    id,
    info,
    isCurrent: state.current === id,
  }))
})
const isPipelineFailed = computed(() => processingInstance.value?.taskStatus === '执行出错' && pipelineSteps.value.some((s) => s.info.status === 'FAILED'))
const retrySubmitting = ref(false)
const pipelineMessage = ref('')

async function handlePipelineRetry() {
  retrySubmitting.value = true
  try {
    const result = await retryTask(taskId.value)
    pipelineMessage.value = `重试已下发，新 run_id=${result.newRunId}`
    await loadTaskDetail()
  } catch (e) {
    pipelineMessage.value = `重试失败：${(e as Error).message}`
  } finally {
    retrySubmitting.value = false
  }
}

function formatIo(value: unknown): string {
  if (typeof value === 'string') return value
  try {
    return JSON.stringify(value, null, 2)
  } catch {
    return String(value)
  }
}

const hasRealIo = computed(() => !!(selectedStep.value?.input || selectedStep.value?.output))
const stepAccessChips = computed(() => accessChips(selectedStep.value?.access))

async function loadTaskDetail() {
  try {
    processingInstance.value = await getTask(taskId.value)
    if (!route.query.step) {
      selectedStepId.value = initialStepId()
    }
    if (!route.query.activity) selectedActivityId.value = ''
  } catch {
    processingInstance.value = undefined
  }
}

// === 执行加载（列表页不再展示执行记录表；这里只取最新一次执行填充流程详情） ===
const scheduleId = computed(() => String(route.query.scheduleId || ''))
/** 最新一次执行的状态/备注：执行没落任务记录（如脚本启动即崩）时，这是唯一的失败原因出处。 */
const latestExecutionMessage = ref('')
/** job 执行历史（含触发方式：手动/定期/重新执行），点击行切换展示的执行。 */
const jobExecutions = ref<WorkflowExecution[]>([])
// 执行历史客户端分页：翻页不影响 selectedExecutionId（选中态独立于当前页）
const {
  page: execPage,
  pageSize: execPageSize,
  total: execTotal,
  pagedItems: pagedExecutions,
  resetPage: resetExecPage,
  changePage: changeExecPage,
  changePageSize: changeExecPageSize,
} = useClientPagination(jobExecutions, 10)
const selectedExecutionId = ref('')
const selectedExecution = ref<WorkflowExecution | null>(null)
/** F6：embedding/Milvus 等外部服务故障导致索引构建降级时，执行详情必须显式提醒（不能只埋在输出 JSON 里）。 */
const indexDegrade = computed(() => {
  const output = (selectedExecution.value as { output?: { index?: { degraded?: boolean; error?: string } } } | null)?.output
  const index = output?.index
  return index && typeof index === 'object' && (index.degraded || index.error) ? index : null
})

// === 数据溯源：只展示真实可查证的对象（Schema 来源绑定 / 抽取脚本 / 任务参数 /
// 工作流回写的分批统计与水位）。行级原始字段值不落库，不做不可回放的编造。 ===
const schemaDetail = ref<SchemaDefinition | null>(null)
/** kg.schema.extract 的真实终态输出（优先任务回写，其次执行详情）。 */
type ExtractOutput = {
  schemaId?: string
  sources?: Array<{ source?: string; table?: string; batches?: number; rows?: number; written?: number; failed?: number; watermark?: string | null; pkCursor?: string | null }>
  failures?: { count?: number }
}
const extractOutput = computed<ExtractOutput | null>(() => {
  const output = (processingInstance.value?.output ?? (selectedExecution.value as { output?: ExtractOutput } | null)?.output ?? null) as (ExtractOutput & { chain?: boolean; steps?: Record<string, { output?: ExtractOutput }> }) | null
  if (!output) return null
  // chain：顶层没有 sources/failures 汇总（分散在各环 output 里），聚合后
  // 验收摘要/执行输出统计才能显示真实写入行数，而不是回退「工作流已下发」
  if (output.chain && output.steps) {
    const sources: ExtractOutput['sources'] = []
    let failed = 0
    for (const step of Object.values(output.steps)) {
      const inner = step?.output ?? {}
      if (inner.sources?.length) sources.push(...inner.sources)
      failed += Number(inner.failures?.count ?? 0)
    }
    return { ...output, sources, failures: { count: failed } }
  }
  return output
})
const schemaId = computed(() => String(
  job.value?.schemaId
  || (processingInstance.value?.input as { schemaId?: unknown } | undefined)?.schemaId
  || extractOutput.value?.schemaId
  || '',
))
watch(schemaId, async (id) => {
  if (!id || schemaDetail.value?.id === id) return
  schemaDetail.value = null
  try {
    schemaDetail.value = await getSchemaDetail(id, currentUserId())
  } catch {
    schemaDetail.value = null // Schema 已删除或无权限：溯源仅退化为任务级依据
  }
}, { immediate: true })

const lineageGraphSpace = computed(() => job.value?.graphSpace || schemaDetail.value?.graphSpace || '默认图空间')
const lineageChainSource = computed(() => {
  const sources = schemaDetail.value?.sources ?? []
  if (sources.length) {
    const first = sources[0]
    const label = first.querySql ? `${first.databaseName}（自定义 SQL）` : `${first.databaseName}.${first.tableName}`
    return sources.length > 1 ? `${label} 等 ${sources.length} 张` : label
  }
  return processingInstance.value?.sourceTable || '来源绑定'
})

/** 来源与任务级依据行（全部真实字段）。 */
const lineageSourceRows = computed(() => {
  const rows: Array<{ table: string; field: string; raw: string; basis: string }> = []
  for (const source of schemaDetail.value?.sources ?? []) {
    rows.push({
      table: source.querySql ? `${source.databaseName} · 自定义 SQL` : `${source.databaseName}.${source.tableName}`,
      field: [source.pkColumn, source.timeColumn].filter(Boolean).join(' / ') || '—',
      raw: source.querySql || '按绑定整表分批读取',
      basis: `来源绑定 #${source.position + 1}`,
    })
  }
  const script = schemaDetail.value?.script
  if (script) {
    rows.push({
      table: '抽取脚本（S3）',
      field: script.filename,
      raw: `sha256 ${script.sha256.slice(0, 12)}${script.stale ? ' · 落后属性修订' : ''}`,
      basis: '转换逻辑',
    })
  }
  if (processingInstance.value) {
    const cursor = processingInstance.value.sourceRecordId
    rows.push({
      table: '本次读取起点',
      field: 'payload.since',
      raw: !cursor || cursor === 'latest-cursor' ? 'latest-cursor（按来源当前水位增量）' : cursor,
      basis: '任务参数',
    })
  }
  rows.push({ table: '目标图空间', field: 'graphSpace', raw: lineageGraphSpace.value, basis: '写图去向' })
  return rows
})

/** 工作流回写的每个来源的真实分批结果与水位推进。 */
const lineageResultRows = computed(() => (extractOutput.value?.sources ?? []).map((source) => ({
  table: source.table ?? source.source ?? '来源',
  batches: source.batches ?? '—',
  rows: source.rows ?? '—',
  written: source.written ?? '—',
  failed: source.failed ?? 0,
  cursor: source.watermark || (source.pkCursor ? `pk > ${source.pkCursor}` : '未推进'),
})))
const lineageResultSummary = computed(() => {
  const output = extractOutput.value
  if (!output) return processingInstance.value?.rule || ''
  const written = (output.sources ?? []).reduce((sum, source) => sum + Number(source.written ?? 0), 0)
  const failed = output.failures?.count ?? 0
  return `写入 ${written} 行${failed ? ` · 失败 ${failed} 转人工审核` : ''}`
})
/** 验收摘要：抽取任务用回写统计（task.result 只是「工作流已下发」回执，不是结果）。 */
const resultVerdict = computed(() => (extractOutput.value?.sources?.length
  ? lineageResultSummary.value
  : processingInstance.value?.result || '输出通过当前质量规则'))
const taskLogLines = computed(() => (processingInstance.value?.logs ?? []).map(String))
const executionOutput = computed(() => processingInstance.value?.output ?? (selectedExecution.value as { output?: unknown } | null)?.output ?? null)

async function loadLatestExecution() {
  let executions: WorkflowExecution[] = []
  try {
    if (jobId.value) {
      // job 详情：由 getJob 直接带回执行历史（最新在前）
      const detail = await getJob(jobId.value)
      job.value = detail.job
      executions = detail.executions
    } else if (scheduleId.value) {
      executions = (await listExecutions(200, { scheduleId: scheduleId.value })).items
    } else if (processingInstance.value?.rule) {
      executions = (await listExecutions(200, { definitionId: String(processingInstance.value.rule) })).items
    } else if (String(route.params.instanceId || '').startsWith('EXEC-')) {
      // /processing-instance/{执行ID} 直达：路由参数是执行 ID 本身（重跑记录
      // 视图/审核 case 跳转入口），直接加载该执行——否则 selectedExecution
      // 恒空，F6 索引降级告警等执行级信息不展示
      const execution = await getExecution(String(route.params.instanceId))
      selectedExecution.value = execution ?? null
      jobExecutions.value = execution ? [execution] : []
      selectedExecutionId.value = execution?.id ?? ''
      latestExecutionMessage.value = [execution?.status, execution?.message].filter(Boolean).join(' · ')
      return
    }
  } catch {
    executions = []
  }
  jobExecutions.value = executions
  resetExecPage()
  if (!executions.length) return
  await selectExecution(executions[0].id)
}

/** 选中一条执行（含重新执行类）：拉详情并填充下方流程面板。 */
async function selectExecution(executionId: string) {
  selectedExecutionId.value = executionId
  try {
    const execution = await getExecution(executionId)
    selectedExecution.value = execution ?? null
    latestExecutionMessage.value = [execution?.status, execution?.message].filter(Boolean).join(' · ')
    // job / 周期任务视图：用最新 execution 的任务填充流程详情
    if ((jobId.value || scheduleId.value) && execution?.taskId) {
      try {
        processingInstance.value = await getTask(execution.taskId)
        if (!route.query.step) selectedStepId.value = initialStepId()
        if (!route.query.activity) selectedActivityId.value = ''
      } catch {
        // 保留当前任务详情
      }
    } else if (jobId.value && !processingInstance.value && latestExecutionMessage.value) {
      // 执行未产生任务记录（启动即失败/Temporal 不可用）：至少把状态与备注亮出来
      pipelineMessage.value = `最近一次执行：${latestExecutionMessage.value}`
    }
  } catch (error) {
    pipelineMessage.value = `执行详情加载失败：${(error as Error).message}`
  }
}

// 选中的执行仍在运行时轮询刷新（重拉执行 + 任务详情），终态即停；
// 页面切到后台时跳过本轮，避免不可见时白白打接口
let execPollTimer: ReturnType<typeof setInterval> | null = null
watch(
  () => selectedExecution.value?.status === 'RUNNING',
  (running) => {
    if (running && execPollTimer === null) {
      execPollTimer = setInterval(() => {
        if (!document.hidden && selectedExecutionId.value) void selectExecution(selectedExecutionId.value)
      }, 5000)
    } else if (!running && execPollTimer !== null) {
      clearInterval(execPollTimer)
      execPollTimer = null
    }
  },
  { immediate: true },
)
onUnmounted(() => {
  if (execPollTimer !== null) clearInterval(execPollTimer)
})

watch(() => route.query.step, (step) => {
  if (step && steps.value.some((item) => item.id === String(step))) selectedStepId.value = String(step)
})
watch(() => route.query.activity, (value) => {
  selectedActivityId.value = String(value || '')
  // 深链带 activity 时确保对应脚本 step 处于展开状态
  if (value && isChainTask.value) expandedScriptId.value = String(route.query.step || expandedScriptId.value)
})
watch(taskId, () => {
  void loadTaskDetail()
})
onMounted(async () => {
  if (jobId.value) {
    await loadLatestExecution()
    return
  }
  if (scheduleId.value) {
    // 周期任务详情：先取最新执行，再由其补任务详情
    await loadLatestExecution()
    if (!processingInstance.value) await loadTaskDetail()
    return
  }
  await loadTaskDetail()
  await loadLatestExecution()
})
</script>

<template>
  <div class="task-detail-page">
    <header class="detail-head">
      <div><RouterLink to="/graph-build">← 返回图谱构建</RouterLink><h1>{{ job?.name || processingInstance?.objectName || `${visiblePhase}任务详情` }}</h1><p>{{ processingInstance?.action || batch.trigger }} · {{ processingInstance?.sourceTable || batch.source }}</p></div>
    </header>

    <section v-if="job" class="job-config-panel">
      <div class="job-config-grid job-config-grid-3">
        <div><span>图空间</span><strong>{{ job.graphSpace || '默认' }}</strong></div>
        <div><span>数据源</span><strong>{{ job.mysqlDatasourceId || '默认' }}{{ job.mysqlDatabase ? ` / ${job.mysqlDatabase}` : '' }}</strong></div>
        <div><span>执行状态</span><strong>{{ deriveJobUnifiedStatus(job) }}</strong></div>
      </div>
    </section>

    <section v-if="job && jobExecutions.length" class="job-executions-panel">
      <h2>执行历史</h2>
      <div class="exec-table-wrap">
        <table class="exec-table">
          <thead>
            <tr><th>执行 ID</th><th>触发方式</th><th>状态</th><th>开始时间</th><th>失败记录</th></tr>
          </thead>
          <tbody>
            <tr
              v-for="e in pagedExecutions"
              :key="e.id"
              :class="{ active: e.id === selectedExecutionId }"
              @click="selectExecution(e.id)"
            >
              <td><code>{{ e.id }}</code></td>
              <td><span class="trigger-chip" :data-kind="e.triggerSource || 'MANUAL'">{{ triggerLabel(e) }}</span></td>
              <td>{{ e.status }}</td>
              <td>{{ e.startedAt }}</td>
              <td>{{ failureCount(e) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <ListPagination
        v-if="execTotal > 0"
        :total="execTotal"
        :page="execPage"
        :page-size="execPageSize"
        @change="changeExecPage"
        @change-size="changeExecPageSize"
      />
    </section>

    <section v-if="!job && processingInstance" class="summary-grid">
      <article><span>执行状态</span><strong :class="isExecutionInterrupted ? 'danger' : 'success-text'">{{ taskStatus }}</strong><em>{{ isExecutionInterrupted ? '任务未完成' : '程序无异常退出' }}</em></article>
    </section>

    <p v-if="pipelineMessage" class="pipeline-message">{{ pipelineMessage }}</p>

    <div v-if="indexDegrade" class="index-degrade-alert" role="alert" aria-label="索引构建降级告警">
      <strong>⚠ 实体索引构建失败（已降级）</strong>
      <span>图数据写入正常，但实体检索索引未重建——关键词 / 语义检索将缺失本次新增实体。</span>
      <code v-if="indexDegrade.error">{{ indexDegrade.error }}</code>
      <em>该告警针对选中的执行 {{ selectedExecutionId || '最新一次' }}（后续成功执行可能已重建索引）；请检查 embedding 服务可用性后，重新执行该任务——执行末尾会全量重建该图空间的实体索引。</em>
    </div>

    <section class="detail-workspace">
      <aside class="process-sidebar">
        <header><div><h2>{{ visiblePhase }}流程</h2></div><span>{{ visibleSteps.filter(step => step.status === '成功').length }}/{{ visibleSteps.length }}</span></header>
        <section class="phase-group">
          <p v-if="!visibleSteps.length" class="process-empty">暂无流程步骤数据：任务尚未执行，或为无 pipeline 记录的旧执行。</p>
          <div v-else class="phase-title"><strong>{{ visiblePhase }}</strong></div>
          <template v-for="step in visibleSteps" :key="step.id">
            <button type="button" :class="['process-step', `is-${step.status}`, `is-${step.risk}`, { active: selectedStepId === step.id, 'has-review': step.abnormal !== '0' && step.abnormal !== '-', 'is-script': isChainTask, 'is-expanded': isChainTask && expandedScriptId === step.id }]" @click="selectStep(step.id)">
              <i>{{ step.status === '成功' ? '✓' : step.status === '需人工处理' ? '!' : '·' }}</i>
              <span><strong>{{ step.name }}<b v-if="step.id === 'llm'">AI</b><b v-if="step.risk === '高风险'" class="risk">重点</b></strong><em>{{ step.count }}<template v-if="step.abnormal !== '0' && step.abnormal !== '-'"> · {{ step.abnormal }} 异常</template></em></span>
              <small>{{ step.status }}</small>
            </button>
            <template v-if="isChainTask && expandedScriptId === step.id">
              <button v-for="act in chainActivities(step.id)" :key="`${step.id}::${act.id}`" type="button" :class="['process-substep', `is-${mapPipelineStatus(act.info.status)}`, { active: selectedActivityId === act.id && selectedStepId === step.id }]" @click="selectActivity(step.id, act.id)">
                <i>{{ mapPipelineStatus(act.info.status) === '成功' ? '✓' : mapPipelineStatus(act.info.status) === '需人工处理' ? '!' : '·' }}</i>
                <span><strong>{{ act.info.name || act.id }}</strong><em>{{ act.info.error ? '执行失败' : typeof act.info.records === 'number' ? `${act.info.records} 行 · 写图 ${act.info.written ?? 0} 条` : act.info.output !== undefined && act.info.output !== null ? '已上报输出 JSON' : '无输出记录' }}<template v-if="act.info.attempt"> · attempt={{ act.info.attempt }}</template></em></span>
                <small>{{ mapPipelineStatus(act.info.status) }}</small>
              </button>
              <p v-if="!chainActivities(step.id).length" class="process-substep-empty">暂无 activity step 记录：脚本可能仍在执行，或为旧版本执行的链（重新执行可记录逐步状态）。</p>
            </template>
          </template>
        </section>
      </aside>

      <main class="step-detail">
        <header class="step-head"><div><span>{{ selectedStep.phase }} · {{ attentionLabel }}</span><h2>{{ selectedStep.name }}</h2><p>{{ selectedStep.description }}</p></div><div class="step-head-actions"><button v-if="isChainTask && selectedActivityId" type="button" class="step-head-back" @click="clearActivitySelection()">← 返回脚本级信息</button><button v-if="isPipelineTask && isPipelineFailed" type="button" class="step-head-retry" :disabled="retrySubmitting" @click="handlePipelineRetry">{{ retrySubmitting ? '提交中…' : '重试（reset 回放）' }}</button><RouterLink v-else-if="!isPipelineTask && needsReview" :to="`/manual-review/task/${taskId}`">进入人工处理 →</RouterLink></div></header>
        <nav class="detail-tabs"><button v-for="tab in ([['overview','概况与结果'],['io','输入输出'],['logs','异常与日志'],['lineage','数据溯源']] as const)" :key="tab[0]" type="button" :class="{ active: activeTab === tab[0] }" @click="activeTab = tab[0]">{{ tab[1] }}</button></nav>

        <div v-if="activeTab === 'overview'" class="overview-content">
          <section class="metric-card"><h3>节点结果</h3><dl><div v-for="row in genericMetrics" :key="row[0]"><dt>{{ row[0] }}</dt><dd>{{ row[1] }}</dd></div></dl></section>
          <section v-if="needsReview" class="result-card alert"><h3>执行结果与业务验收</h3><template v-if="isExecutionInterrupted"><p><strong>执行结果：</strong>任务未运行完成，尚未产生可验收结果。</p><p><strong>置信度：</strong>无，因为没有模型结果。</p></template><template v-else><p><strong>执行结果：</strong>程序已正常运行完成并生成输出。</p><p><strong>验收结果：</strong>{{ processingInstance?.result }}，当前不能视为正确结果。</p></template><p><strong>后续处理：</strong>{{ blockingStrategy }}。</p></section>
          <section v-else class="result-card success"><h3>执行结果与业务验收</h3><p><strong>执行成功：</strong>程序正常结束。 <strong>结果已通过：</strong>{{ resultVerdict }}。两项状态分别记录，不相互替代。</p></section>
        </div>

        <div v-else-if="activeTab === 'io'" class="io-content">
          <section v-if="stepAccessChips.length" class="access-card">
            <h3>实际访问资源 <span>观测式溯源</span></h3>
            <div class="access-chips">
              <span v-for="chip in stepAccessChips" :key="`${chip.group}:${chip.name}`" class="access-chip">
                <em>{{ chip.group }}</em>
                <code>{{ chip.name }}</code>
                <b v-if="chip.read" class="op-read">R</b>
                <b v-if="chip.write" class="op-write">W</b>
                <small>{{ chip.detail }}</small>
              </span>
            </div>
          </section>
          <section v-if="hasRealIo" class="real-io-card"><h3>阶段真实输入输出 <span>脚本上报</span></h3><div v-if="selectedStep.input" class="real-io-block"><strong>输入</strong><pre>{{ formatIo(selectedStep.input) }}</pre></div><div v-if="selectedStep.output" class="real-io-block"><strong>输出</strong><pre>{{ formatIo(selectedStep.output) }}</pre></div></section>
          <template v-if="!hasRealIo">
          <section><h3>任务输入 <span>Temporal 下发 payload</span></h3><pre v-if="processingInstance?.input">{{ formatIo(processingInstance.input) }}</pre><p v-else class="io-empty">无输入记录：旧任务未落 payload，或为 Temporal 不可用时的本地降级（QUEUED）执行。</p></section>
          <section><h3>执行输出 <span>工作流回写</span></h3><template v-if="isExecutionInterrupted"><div class="candidate-result"><span>未产生输出</span><strong>{{ resultStatus }}</strong><p>{{ processingInstance?.result }} · 置信度 —</p></div></template><template v-else-if="executionOutput"><pre>{{ formatIo(executionOutput) }}</pre></template><p v-else class="io-empty">暂无输出：执行仍在进行，或本次执行未回写输出。</p></section>
          </template>
        </div>

        <div v-else-if="activeTab === 'logs'" class="log-content">
          <template v-if="processingInstance">
            <section class="issue-list"><h3>{{ isExecutionInterrupted ? '执行异常' : '结果验收' }}</h3><article><span>{{ processingInstance.reviewType || '未关联人工审核' }}</span><strong :class="{ safe: !needsTaskReview }">{{ isExecutionInterrupted ? '已中断' : needsTaskReview ? '待确认' : '已通过' }}</strong><em>执行状态：{{ taskStatus }} · 结果状态：{{ resultStatus }}</em></article></section>
            <div class="log-block">
              <p v-if="processingInstance.workflowId" class="log-meta">workflow <code>{{ processingInstance.workflowId }}</code><template v-if="processingInstance.runId"> · run <code>{{ processingInstance.runId }}</code></template></p>
              <pre v-if="taskLogLines.length">{{ taskLogLines.join('\n') }}</pre>
              <p v-else class="io-empty">暂无日志行：日志仅在任务创建与执行终态回写时追加，本任务尚未经历状态回写。</p>
            </div>
          </template>
          <p v-else class="process-empty" style="grid-column:1/-1;margin:0">暂无日志：任务尚未执行，或本次执行未产生任务记录。</p>
        </div>

        <div v-else class="trace-content">
          <template v-if="processingInstance">
            <section class="lineage-compare">
              <header><div><h3>来源与执行依据</h3><p>Schema 来源绑定、抽取脚本与任务真实参数；行级原始值不落库，不做编造展示</p></div><span>{{ lineageSourceRows.length }} 条依据</span></header>
              <table><thead><tr><th>对象</th><th>关键字段</th><th>当前值</th><th>用途</th></tr></thead><tbody><tr v-for="row in lineageSourceRows" :key="`${row.table}-${row.field}`"><td><code>{{ row.table }}</code></td><td><code>{{ row.field }}</code></td><td class="raw-value">{{ row.raw }}</td><td>{{ row.basis }}</td></tr></tbody></table>
            </section>
            <section v-if="lineageResultRows.length" class="lineage-compare">
              <header><div><h3>本次执行来源结果</h3><p>工作流回写的真实分批统计与水位推进（游标在来源全部批次成功后一次性推进）</p></div><span>{{ lineageResultRows.length }} 个来源</span></header>
              <table><thead><tr><th>来源表</th><th>批次</th><th>读取行</th><th>写入行</th><th>失败行</th><th>推进水位 / 游标</th></tr></thead><tbody><tr v-for="row in lineageResultRows" :key="row.table"><td><code>{{ row.table }}</code></td><td>{{ row.batches }}</td><td>{{ row.rows }}</td><td>{{ row.written }}</td><td :class="{ danger: Number(row.failed) > 0 }">{{ row.failed }}</td><td class="raw-value">{{ row.cursor }}</td></tr></tbody></table>
            </section>
            <section><h3>处理链路</h3><div class="lineage"><span>{{ lineageChainSource }}<small>{{ schemaDetail?.label || schemaDetail?.key || 'Schema 未关联或已删除' }}</small></span><b>→</b><span>{{ schemaDetail?.script?.filename || processingInstance.objectName || '转换脚本' }}<small>脚本转换（只输出 JSON）</small></span><b>→</b><span>写入图空间<small>{{ lineageGraphSpace }} · nGQL INSERT</small></span><template v-if="isExecutionInterrupted"><b>→</b><span>下游未执行<small>游标停在上一轮</small></span></template><template v-else><b>→</b><span>{{ selectedExecution?.status || taskStatus }}<small>{{ lineageResultSummary }}</small></span></template></div></section>
          </template>
          <p v-else class="process-empty" style="margin:0">暂无溯源数据：任务尚未执行，或本次执行未产生任务记录{{ latestExecutionMessage ? `（最近执行：${latestExecutionMessage}）` : '' }}。</p>
        </div>
      </main>
    </section>
  </div>
</template>

<style scoped>
.task-detail-page{height:100%;overflow:auto;padding:0 0 18px;color:#17233b}.detail-head{display:flex;align-items:flex-end;justify-content:space-between;gap:20px;margin-bottom:12px}.detail-head a{color:#165dff;font-size:12px;text-decoration:none}.detail-head>div>span{margin-left:10px;color:#8793a8;font-size:10px}.detail-head h1{margin:7px 0 3px;font-size:22px}.detail-head p{margin:0;color:#66758f;font-size:11px}.detail-actions{display:flex;gap:8px}.detail-actions button{height:34px;padding:0 14px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;cursor:pointer}.detail-actions .primary{border-color:#d92d20;background:#d92d20;color:#fff}.action-message{margin:0 0 12px;padding:9px 12px;border:1px solid #b2ccff;border-radius:6px;background:#f0f5ff;color:#344f7a;font-size:11px}.attention-banner{display:flex;align-items:center;gap:12px;margin-bottom:12px;padding:11px 14px;border:1px solid #f6c7c2;border-radius:8px;background:#fff7f6}.attention-banner>i{display:grid;place-items:center;flex:0 0 28px;width:28px;height:28px;border-radius:50%;background:#d92d20;color:#fff;font-style:normal;font-weight:700}.attention-banner>div{flex:1}.attention-banner strong{color:#912018;font-size:12px}.attention-banner p{margin:3px 0 0;color:#77504c;font-size:10px}.attention-banner a{padding:8px 11px;border-radius:5px;background:#d92d20;color:#fff;font-size:10px;text-decoration:none}.summary-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:10px;margin-bottom:12px}.summary-grid article{display:grid;gap:5px;padding:13px 14px;border:1px solid #c9dcf7;border-radius:8px;background:#fff}.summary-grid span{color:#6b7890;font-size:10px}.summary-grid strong{font-size:19px}.summary-grid strong.version{font-size:13px}.summary-grid em{overflow:hidden;color:#8793a8;font-size:9px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}.danger{color:#d92d20}.warning{color:#b54708}.detail-workspace{display:grid;grid-template-columns:340px minmax(0,1fr);min-height:560px;overflow:hidden;border:1px solid #bed4f3;border-radius:9px;background:#fff}.process-sidebar{border-right:1px solid #dce8f8;background:#f8fbff}.process-sidebar>header{display:flex;align-items:center;justify-content:space-between;padding:13px 14px;border-bottom:1px solid #dce8f8;background:#fff}.process-sidebar h2{margin:0;font-size:14px}.process-sidebar header p{margin:3px 0 0;color:#7b899e;font-size:9px}.process-sidebar header>span{padding:4px 8px;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:10px}.phase-group{padding:10px}.phase-title{display:flex;align-items:center;justify-content:space-between;padding:4px 3px 8px}.phase-title strong{font-size:11px}.phase-title em{color:#8290a7;font-size:9px;font-style:normal}.process-step{display:grid;grid-template-columns:22px minmax(0,1fr) auto;align-items:center;gap:8px;width:100%;min-height:48px;margin-bottom:5px;padding:7px 8px;border:1px solid transparent;border-radius:6px;background:transparent;color:#34435c;text-align:left;cursor:pointer}.process-step:hover,.process-step.active{border-color:#8eb8f7;background:#fff;box-shadow:0 3px 10px rgba(39,89,164,.08)}.process-step>i{display:grid;place-items:center;width:20px;height:20px;border-radius:50%;background:#12b76a;color:#fff;font-size:10px;font-style:normal}.process-step>span{display:grid;gap:3px}.process-step span strong{display:flex;align-items:center;gap:5px;font-size:11px}.process-step span em{color:#7c899d;font-size:9px;font-style:normal}.process-step span b{padding:1px 5px;border-radius:3px;background:#7f56d9;color:#fff;font-size:8px}.process-step span b.risk{background:#f79009}.process-step>small{color:#667085;font-size:8px}.process-step.is-高风险{min-height:58px;border-left:3px solid #f79009;background:#fffaf0}.process-step.is-需人工处理{border-color:#f7c6c2;background:#fff7f6}.process-step.is-需人工处理>i{background:#d92d20}.process-step.is-需人工处理>small{color:#b42318}.process-step.is-待执行{opacity:.62}.process-step.is-待执行>i{background:#98a2b3}.step-detail{min-width:0}.step-head{display:flex;align-items:flex-start;justify-content:space-between;gap:15px;padding:14px 16px;border-bottom:1px solid #dce8f8;background:#fbfdff}.step-head span{color:#165dff;font-size:9px}.step-head h2{display:flex;align-items:center;gap:8px;margin:4px 0;font-size:18px}.step-head h2 b{padding:3px 7px;border-radius:4px;background:#7f56d9;color:#fff;font-size:9px}.step-head p{margin:0;color:#718099;font-size:10px}.step-head>a{padding:8px 11px;border-radius:5px;background:#d92d20;color:#fff;font-size:10px;text-decoration:none}.detail-tabs{display:flex;padding:0 14px;border-bottom:1px solid #dce8f8}.detail-tabs button{height:40px;padding:0 14px;border:0;border-bottom:2px solid transparent;background:transparent;color:#66758f;font-size:10px;cursor:pointer}.detail-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.overview-content{display:grid;grid-template-columns:minmax(220px,.75fr) minmax(320px,1.25fr);gap:12px;padding:14px}.overview-content>section{border:1px solid #dce8f8;border-radius:7px;background:#fff}.overview-content h3,.io-content h3,.trace-content h3,.issue-list h3{margin:0;padding:11px 13px;border-bottom:1px solid #e4ecf6;font-size:12px}.metric-card dl,.ai-card dl{display:grid;grid-template-columns:1fr 1fr;margin:0;padding:7px 12px}.metric-card dl{grid-template-columns:1fr}.metric-card dl div,.ai-card dl div{display:flex;justify-content:space-between;gap:10px;padding:7px 3px;border-bottom:1px solid #eef2f7;font-size:10px}.metric-card dt,.ai-card dt{color:#718099}.metric-card dd,.ai-card dd{margin:0;text-align:right}.ai-card{border-color:#cbbaf7!important;background:#fcfaff!important}.ai-card>header{display:flex;align-items:center;justify-content:space-between;padding:10px 12px;border-bottom:1px solid #e4dcfa}.ai-card header>div{display:flex;align-items:center;gap:8px}.ai-card header b{display:grid;place-items:center;width:27px;height:27px;border-radius:6px;background:#7f56d9;color:#fff;font-size:10px}.ai-card header span{display:grid}.ai-card header strong{font-size:11px}.ai-card header em{color:#766b91;font-size:8px;font-style:normal}.ai-card header>i{padding:3px 7px;border-radius:999px;background:#fff0d5;color:#b54708;font-size:8px;font-style:normal}.result-card{grid-column:1/-1;padding-bottom:10px}.result-card.alert{border-color:#f7c6c2;background:#fff8f7}.result-card.success{border-color:#abefc6;background:#f6fef9}.result-card p,.result-card li{color:#596981;font-size:10px;line-height:18px}.result-card p{margin:10px 13px}.io-content{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:14px}.io-content>section,.trace-content>section{overflow:hidden;border:1px solid #dce8f8;border-radius:7px}.io-content pre,.log-content>pre,.log-block pre{min-height:250px;margin:0;padding:15px;overflow:auto;background:#17233b;color:#d9e7ff;font:10px/18px Consolas,monospace;white-space:pre-wrap}.sample-text,.candidate-result{margin:13px;padding:14px;border-radius:6px;background:#f5f8fc}.sample-text span,.candidate-result span{color:#728099;font-size:9px}.sample-text p{font-size:11px;line-height:20px}.candidate-result strong{display:block;margin:10px 0;font-size:12px}.candidate-result p{color:#68778e;font-size:10px}.candidate-result p b{color:#b54708}.log-content{display:grid;grid-template-columns:230px minmax(0,1fr);gap:12px;padding:14px}.issue-list{overflow:hidden;border:1px solid #f4c7c3;border-radius:7px;background:#fff8f7}.issue-list article{display:grid;gap:7px;padding:14px}.issue-list span,.issue-list em{color:#77504c;font-size:9px;font-style:normal}.issue-list strong{color:#b42318;font-size:24px}.trace-content{display:grid;gap:12px;padding:14px}.lineage{display:flex;align-items:center;justify-content:center;gap:9px;padding:22px;overflow:auto}.lineage span{min-width:115px;padding:12px;border:1px solid #bdd7ff;border-radius:6px;background:#f6faff;font-size:9px;text-align:center}.lineage b{color:#165dff}.trace-content table{width:100%;border-collapse:collapse;font-size:10px}.trace-content th,.trace-content td{padding:10px 13px;border-bottom:1px solid #e4ecf6;text-align:left}.trace-content th{width:140px;color:#65738b}@media(max-width:1200px){.summary-grid{grid-template-columns:repeat(3,1fr)}.detail-workspace{grid-template-columns:300px minmax(0,1fr)}.overview-content{grid-template-columns:1fr}.result-card{grid-column:auto}}@media(max-width:900px){.summary-grid{grid-template-columns:repeat(2,1fr)}.detail-workspace{grid-template-columns:1fr}.process-sidebar{border-right:0;border-bottom:1px solid #dce8f8}.io-content,.log-content{grid-template-columns:1fr}}
.process-step.has-review:not(.is-需人工处理){border-color:#f4d39b;background:#fffbf2}.process-step.has-review:not(.is-需人工处理)>small{color:#b54708}
.success-text{color:#067647}.prompt-card,.quality-strategy{grid-column:1/-1;overflow:hidden}.prompt-card h3,.quality-strategy h3{display:flex;align-items:center;justify-content:space-between}.prompt-card h3 span{padding:2px 6px;border-radius:4px;background:#eee8ff;color:#6941c6;font-size:8px;font-weight:500}.prompt-card pre,.quality-strategy>pre{margin:0;padding:13px 15px;background:#201a32;color:#eee9ff;font:10px/18px Consolas,monospace;white-space:pre-wrap}.quality-strategy table{width:100%;border-collapse:collapse;font-size:9px}.quality-strategy th,.quality-strategy td{padding:9px 11px;border-bottom:1px solid #e5ecf5;text-align:left;vertical-align:top}.quality-strategy th{background:#f5f8fc;color:#66758f}.quality-strategy td span.ai{display:inline-flex;padding:2px 5px;border-radius:4px;background:#eee8ff;color:#6941c6}.quality-ai-note{display:flex;align-items:center;gap:9px;margin:10px;padding:10px;border:1px solid #d9ccfa;border-radius:6px;background:#fbfaff}.quality-ai-note>b{display:grid;place-items:center;width:26px;height:26px;border-radius:5px;background:#7f56d9;color:#fff;font-size:9px}.quality-ai-note span{display:grid;gap:2px}.quality-ai-note strong{font-size:10px}.quality-ai-note em{color:#766b91;font-size:8px;font-style:normal}.issue-list strong.safe{color:#067647}.lineage span small{display:block;margin-top:4px;color:#7d899b;font-size:8px}
.lineage-compare>header{display:flex;align-items:center;justify-content:space-between;padding:11px 13px;border-bottom:1px solid #e4ecf6;background:#fbfdff}.lineage-compare>header h3{padding:0;border:0}.lineage-compare>header p{margin:3px 0 0;color:#7a879a;font-size:9px}.lineage-compare>header>span{padding:3px 7px;border-radius:999px;background:#eaf2ff;color:#165dff;font-size:9px}.lineage-compare code{padding:2px 5px;border-radius:4px;background:#f1f5fa;color:#344f73;font:9px Consolas,monospace}.lineage-compare .raw-value{max-width:360px;color:#354760;line-height:17px;white-space:normal}

.access-card{grid-column:1/-1;overflow:hidden;border:1px solid #cfe0d8;border-radius:7px;background:#f7fdf9}
.access-card h3{display:flex;align-items:center;justify-content:space-between}
.access-card h3 span{padding:2px 6px;border-radius:4px;background:#e5f6ee;color:#067647;font-size:8px;font-weight:500}
.access-chips{display:flex;flex-wrap:wrap;gap:7px;padding:13px}
.access-chip{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border:1px solid #cfe0d8;border-radius:6px;background:#fff;font-size:10px;color:#344763}
.access-chip em{color:#067647;font-size:9px;font-style:normal;white-space:nowrap}
.access-chip code{padding:1px 5px;border-radius:3px;background:#edf4ff;color:#165dff;font-size:10px}
.access-chip b{display:grid;place-items:center;min-width:15px;height:15px;border-radius:4px;color:#fff;font-size:9px;font-style:normal}
.access-chip b.op-read{background:#175cd3}
.access-chip b.op-write{background:#f79009}
.access-chip small{color:#8191aa;font-size:9px;white-space:nowrap}

.pipeline-panel{margin-bottom:12px;padding:14px 16px;border:1px solid #c9dcf7;border-radius:9px;background:#fff}
.pipeline-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px}
.pipeline-head h2{margin:0;font-size:15px}
.pipeline-message{margin:0 0 10px;padding:8px 12px;border:1px solid #b2ccff;border-radius:6px;background:#f0f5ff;color:#344f7a;font-size:11px}
.index-degrade-alert{display:flex;flex-direction:column;gap:4px;margin:0 0 12px;padding:10px 14px;border:1px solid #f0a6a6;border-left:4px solid #d92d20;border-radius:6px;background:#fef3f2;color:#912018;font-size:12px}
.index-degrade-alert strong{font-size:13px}
.index-degrade-alert code{padding:2px 6px;border-radius:4px;background:#fde8e8;word-break:break-all}
.index-degrade-alert em{color:#a8655c;font-style:normal;font-size:11px}
/* 真实输入输出（脚本上报 JSON）：跨两列，输入/输出分块，超长 JSON 内部滚动 */
.io-content h3 span{padding:2px 6px;border-radius:4px;background:#eef4ff;color:#165dff;font-size:8px;font-weight:500}
.io-empty{margin:0;padding:15px;border-top:1px solid #eef2f7;color:#8290a7;font-size:10px;line-height:18px}
.io-content pre{min-height:0}
.log-block{display:grid;align-content:start;gap:0;min-width:0}
.log-meta{margin:0;padding:9px 15px;border-bottom:1px solid #253554;background:#17233b;color:#8fa5c9;font-size:9px}
.log-meta code{color:#9fd0ff}
.log-block .io-empty{border:1px dashed #35476d;background:#101a30}
.log-block pre{min-height:0}
.real-io-card{grid-column:1/-1}
.real-io-card h3 span{padding:2px 6px;border-radius:4px;background:#e5f6ee;color:#067647;font-size:8px;font-weight:500}
.real-io-block{padding:12px 14px;border-bottom:1px solid #eef2f7}
.real-io-block:last-child{border-bottom:0}
.real-io-block strong{display:block;margin-bottom:7px;color:#34405e;font-size:10px}
.real-io-block pre{min-height:0;max-height:340px}
.step-head-retry{height:34px;padding:0 14px;border:1px solid #d92d20;border-radius:6px;background:#d92d20;color:#fff;cursor:pointer;font-size:11px}
.step-head-retry:disabled{opacity:.6;cursor:not-allowed}
.step-head-actions{display:flex;align-items:center;gap:8px}
.step-head-actions a{color:#165dff;font-size:11px;text-decoration:none}
.step-head-back{height:32px;padding:0 12px;border:1px solid #bfd4f0;border-radius:6px;background:#f4f8ff;color:#175cd3;cursor:pointer;font-size:11px}
.step-head-back:hover{background:#e8f1ff}
/* chain 任务：脚本 step 可展开 activity steps 的视觉提示（chevron 展开时旋转） */
.process-step.is-script::after{color:#9db1cc;content:"›";font-size:16px;font-weight:700;transition:transform .15s ease}
.process-step.is-script.is-expanded::after{color:#165dff;transform:rotate(90deg)}
/* chain 任务：脚本 step 下方内联展开的 activity steps */
.process-substep{display:grid;grid-template-columns:18px minmax(0,1fr) auto;align-items:center;gap:7px;width:calc(100% - 6px);min-height:38px;margin:0 0 4px 14px;padding:5px 8px;border:1px solid transparent;border-left:2px solid #cfe0f8;border-radius:6px;background:#f4f8fd;color:#4a5a74;text-align:left;cursor:pointer}
.process-substep:hover{border-color:#a9c8f5;background:#eef5ff}
.process-substep.active{border-color:#165dff;background:#edf4ff;box-shadow:0 0 0 1px #165dff inset}
.process-substep>i{display:grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#12b76a;color:#fff;font-size:9px;font-style:normal}
.process-substep.is-需人工处理{border-left-color:#f4a9a2;background:#fff6f5}
.process-substep.is-需人工处理>i{background:#d92d20}
.process-substep.is-待执行{opacity:.62}
.process-substep.is-待执行>i{background:#98a2b3}
.process-substep>span{display:grid;gap:2px;min-width:0}
.process-substep span strong{overflow:hidden;color:#2b3a55;font-size:10px;text-overflow:ellipsis;white-space:nowrap}
.process-substep span em{overflow:hidden;color:#7c899d;font-size:8px;font-style:normal;text-overflow:ellipsis;white-space:nowrap}
.process-substep>small{color:#667085;font-size:8px}
.process-substep-empty{margin:0 0 6px 16px;padding:8px 10px;border:1px dashed #d5e2f2;border-radius:6px;background:#f8fbff;color:#8290a7;font-size:9px;line-height:15px}
/* job 配置摘要 */
.job-config-panel{overflow:hidden;margin-bottom:12px;border:1px solid #c9dcf7;border-radius:9px;background:#fff}
.job-config-grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:0}
.job-config-grid-3{grid-template-columns:repeat(3,minmax(0,1fr))}
.process-empty{margin:0;padding:18px 14px;border:1px dashed #d5e2f2;border-radius:6px;background:#f8fbff;color:#8290a7;font-size:11px;line-height:18px}
.job-config-grid>div{display:grid;gap:4px;padding:11px 15px;border-right:1px solid #e8eef7;border-bottom:1px solid #e8eef7}
.job-config-grid span{color:#6b7890;font-size:10px}
.job-config-grid strong{overflow:hidden;color:#1d2129;font-size:12px;text-overflow:ellipsis;white-space:nowrap}
.job-executions-panel{margin-bottom:16px;padding:14px 18px;border:1px solid #e5e6eb;border-radius:8px;background:#fff}
.job-executions-panel h2{margin:0 0 10px;font-size:14px;color:#1d2129}
.exec-table-wrap{max-height:240px;overflow:auto}
.exec-table{width:100%;border-collapse:collapse;font-size:12px}
.exec-table th{position:sticky;top:0;padding:8px 10px;background:#f7f8fa;color:#4e5969;text-align:left;font-weight:600}
.exec-table td{padding:8px 10px;border-top:1px solid #f2f3f5;color:#1d2129}
.exec-table tbody tr{cursor:pointer}
.exec-table tbody tr:hover{background:#f7f9ff}
.exec-table tbody tr.active{background:#eef4ff}
.exec-table code{font-size:11px;color:#165dff}
.trigger-chip{display:inline-block;padding:1px 8px;border-radius:10px;font-size:11px;background:#f2f3f5;color:#4e5969}
.trigger-chip[data-kind='SCHEDULE']{background:#e8ffea;color:#00b42a}
.trigger-chip[data-kind='RERUN']{background:#fff3e8;color:#f77234}
</style>
