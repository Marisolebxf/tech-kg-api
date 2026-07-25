<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
// import GraphVersionView from './GraphVersionView.vue'
import { getUpdateBatch, processingInstances, updateBatches } from './update-batch-data'

const route = useRoute()
const router = useRouter()
const initialModule = ['数据处理', '图谱构建'].includes(String(route.query.module)) ? String(route.query.module) : '数据处理'
const moduleFilter = ref(initialModule)
const statusFilter = ref(String(route.query.status || '全部执行状态'))
const batchFilter = ref(String(route.query.batch || '全部更新批次'))
const scopeFilter = ref(initialModule === '数据处理' ? '全部数据域' : '全部图谱对象')
const keyword = ref('')
const changeDrawerOpen = ref(false)
const scheduleDialogOpen = ref(false)
const scheduleFrequency = ref('每天')
const scheduleTime = ref('02:00')
const updateNotice = ref('')
const canManageUpdates = true
const selectedChange = ref<null | {
  change: string
  type: string
  id: string
  content: string
  time: string
  source: string
  field: string
  before: string
  after: string
  result: string
}>(null)

const changeRows = [
  { change: '新增', type: '论文', id: 'P202607140018', content: '《多模态大模型知识推理方法研究》', time: '02:00:13', source: 'dwd_zh_paper_detail', field: '整条记录', before: '不存在', after: '新增论文标题、作者、机构、关键词和 DOI 信息', result: '已进入数据清洗与论文实体对齐' },
  { change: '新增', type: '专家', id: 'EXPERT_20418', content: '周启航 · 中国科学院自动化研究所', time: '02:00:18', source: 'dwd_scholar', field: '整条记录', before: '不存在', after: '新增专家姓名、任职机构与研究方向', result: '已进入专家候选实体对齐' },
  { change: '修改', type: '专利', id: 'CN2026102841', content: '法律状态：公开 → 实质审查', time: '02:00:22', source: 'dwd_patent', field: 'legal_status', before: '公开', after: '实质审查', result: '已更新专利属性，等待增量图谱入库' },
  { change: '删除', type: '项目', id: 'PROJ_2024_0892', content: '来源记录已标记删除，图谱对象待下线', time: '02:00:31', source: 'dwd_zh_project', field: 'is_deleted', before: '0', after: '1', result: '已进入删除影响分析，确认关系依赖后下线' },
]

const activeStage = computed<'数据处理' | '图谱构建'>(() => moduleFilter.value === '图谱构建' ? '图谱构建' : '数据处理')
const processFailureTypes = ['模型批量输出异常', 'Schema 批量映射失败', '公共字典配置异常']
const taskFailureTypes = ['单任务执行失败']
const getDataDomain = (item: { objectType: string; sourceTable: string }) => {
  const text = `${item.objectType} ${item.sourceTable}`
  if (text.includes('论文')) return '论文域'
  if (text.includes('专家') || text.includes('人才')) return '人才域'
  if (text.includes('机构')) return '机构域'
  if (text.includes('企业')) return '企业域'
  return '综合数据域'
}
const taskRows = computed(() => processingInstances.filter((item) => item.stage === activeStage.value).map((item) => {
  const batch = getUpdateBatch(item.batchId)
  const confidence = Number(item.confidence)
  const isProcessFailure = processFailureTypes.includes(item.reviewType ?? '')
  const isTaskFailure = taskFailureTypes.includes(item.reviewType ?? '')
  const executionInterrupted = isProcessFailure || isTaskFailure
  return {
    ...item,
    batchName: batch?.name ?? item.batchId,
    dataWindow: batch?.dataWindow ?? '-',
    updateDate: batch?.updateDate ?? '-',
    dataDomain: getDataDomain(item),
    executionStatus: executionInterrupted ? '执行中断' : '执行成功',
    executionHint: isProcessFailure ? '公共流程已阻断' : isTaskFailure ? '当前任务未完成' : '程序正常结束',
    confidenceDisplay: executionInterrupted || item.stage === '数据处理' || !item.confidence ? '—' : item.confidence,
    confidenceHint: executionInterrupted ? '未产生结果' : item.stage === '数据处理' ? '确定性规则，不适用' : confidence < 0.9 ? '低于自动通过阈值' : '达到阈值',
    currentStep: item.reviewType === '公共字典配置异常' ? '清洗标准化' : item.reviewType === 'Schema 批量映射失败' ? 'Schema 映射' : item.reviewType === '模型批量输出异常' ? '大模型抽取' : item.stage === '数据处理' ? '质量检验' : ['实体冲突', '单任务执行失败'].includes(item.reviewType ?? '') ? '实体对齐消歧' : '大模型抽取与校验',
  }
}))

const summary = computed(() => {
  const today = processingInstances.filter((item) => item.batchId === 'UPD-20260714')
  const interrupted = today.filter((item) => [...processFailureTypes, ...taskFailureTypes].includes(item.reviewType ?? ''))
  const pendingResult = today.filter((item) => !interrupted.includes(item) && item.status === '待人工处理')
  return [
    { label: '今日具体任务', value: String(today.length), hint: `数据处理 ${today.filter(item => item.stage === '数据处理').length} · 图谱构建 ${today.filter(item => item.stage === '图谱构建').length}` },
    { label: '执行成功', value: String(today.length - interrupted.length), hint: '' },
    { label: '执行中断', value: String(interrupted.length), hint: '' },
    { label: '结果待确认', value: String(pendingResult.length), hint: '' },
  ]
})

const filteredRows = computed(() => taskRows.value.filter((row) => (
  (statusFilter.value === '全部执行状态' || row.executionStatus === statusFilter.value)
  && (batchFilter.value === '全部更新批次' || row.batchId === batchFilter.value)
  && (activeStage.value === '数据处理'
    ? (scopeFilter.value === '全部数据域' || row.dataDomain === scopeFilter.value)
    : (scopeFilter.value === '全部图谱对象' || row.kind === scopeFilter.value))
  && (route.query.range !== 'today' || row.updateDate === '2026-07-14')
  && (!keyword.value || Object.values(row).join(' ').includes(keyword.value))
)))

const taskCategories = computed(() => [
  { label: '数据处理', value: '数据处理', count: processingInstances.filter((item) => item.stage === '数据处理').length },
  { label: '图谱构建', value: '图谱构建', count: processingInstances.filter((item) => item.stage === '图谱构建').length },
  // { label: '图谱版本', value: '图谱版本', count: 3 },
])

function selectCategory(value: string) {
  moduleFilter.value = value
  scopeFilter.value = value === '数据处理' ? '全部数据域' : '全部图谱对象'
  const query = { ...route.query }
  query.module = value
  void router.replace({ query })
}

function openTask(row: { id: string }) {
  void router.push({ name: 'processing-instance-detail', params: { instanceId: row.id } })
}

function saveUpdateSchedule() {
  scheduleDialogOpen.value = false
  updateNotice.value = `自动更新策略已保存：${scheduleFrequency.value} ${scheduleTime.value} 检测，发现变化后立即更新。`
}

function runImmediateUpdate() {
  updateNotice.value = '已提交立即更新：正在检测数据库变化，检测完成后将创建新的数据更新批次和具体处理实例。'
}

watch(() => route.query.status, (value) => { statusFilter.value = String(value || '全部执行状态') })
watch(() => route.query.batch, (value) => { batchFilter.value = String(value || '全部更新批次') })
watch(() => route.query.module, (value) => {
  moduleFilter.value = ['数据处理', '图谱构建'].includes(String(value)) ? String(value) : '数据处理'
  scopeFilter.value = moduleFilter.value === '数据处理' ? '全部数据域' : '全部图谱对象'
})
</script>

<template>
  <div class="task-center">
    <section class="auto-update-monitor" aria-label="图谱自动更新策略与最近变化">
      <header><div class="monitor-statuses"><span><i></i><strong>数据库连接正常</strong></span></div><em>最近健康检查 10:42 · 最近更新完成 02:18</em></header>
      <div class="auto-update-body">
        <article class="latest-change"><span>最近一次检测 · 共 25,140 条源数据变化</span><strong>新增 18,420　修改 6,408　删除 312</strong><p><b>新增论文 12,846</b><b>新增专家 2,418</b><b>新增专利 / 项目 3,156</b></p><button type="button" @click="changeDrawerOpen=true">查看具体变更数据 →</button></article>
        <article class="update-schedule"><span>自动更新策略</span><strong>{{ scheduleFrequency }} {{ scheduleTime }} 检测并更新</strong><p>下一次：2026-07-15 {{ scheduleTime }} · 无变化则不创建更新批次</p></article>
        <div v-if="canManageUpdates" class="update-actions"><button type="button" @click="scheduleDialogOpen=true">更新策略</button><button type="button" @click="runImmediateUpdate">紧急更新</button><small>需图谱更新权限</small></div>
      </div>
    </section>
    <p v-if="updateNotice" class="update-feedback">{{ updateNotice }}</p>
    <section class="task-summary"><article v-for="item in summary" :key="item.label"><span>{{ item.label }}</span><strong>{{ item.value }}</strong><em v-if="item.hint">{{ item.hint }}</em></article></section>
    <nav class="task-categories task-center-primary-tabs" aria-label="任务中心分类">
      <button v-for="item in taskCategories" :key="item.value" type="button" :class="{ active: moduleFilter === item.value }" @click="selectCategory(item.value)">{{ item.label }}<em>{{ item.count }}</em></button>
    </nav>
    <section class="task-panel">
      <div class="task-filter"><input v-model="keyword" placeholder="搜索任务 ID、处理对象、来源表或规则" /><select v-model="batchFilter"><option>全部更新批次</option><option v-for="item in updateBatches" :key="item.id" :value="item.id">{{ item.name }}</option></select><select v-if="activeStage === '数据处理'" v-model="scopeFilter"><option>全部数据域</option><option>论文域</option><option>人才域</option><option>机构域</option><option>企业域</option><option>综合数据域</option></select><select v-else v-model="scopeFilter"><option>全部图谱对象</option><option>实体</option><option>关系</option><option>属性</option></select><select v-model="statusFilter"><option>全部执行状态</option><option>执行成功</option><option>执行中断</option></select><span>{{ filteredRows.length }} 个具体任务</span></div>
      <div class="task-table"><table><thead><tr><th>任务 ID</th><th>处理对象</th><th>{{ activeStage === '数据处理' ? '数据域 / 处理动作' : '图谱对象 / 处理动作' }}</th><th>当前节点</th><th>执行状态</th><th>模型结果置信度</th><th>处理时间</th><th>操作</th></tr></thead><tbody><tr v-for="row in filteredRows" :key="row.id" tabindex="0" @click="openTask(row)" @keydown.enter="openTask(row)"><td><code>{{ row.id }}</code><small>{{ row.batchId }}</small></td><td><strong>{{ row.objectName }}</strong><small>{{ row.objectId }}</small></td><td>{{ activeStage === '数据处理' ? row.dataDomain : `${row.kind} · ${row.objectType}` }}<small>{{ row.action }} · {{ row.sourceTable }}</small></td><td>{{ row.currentStep }}</td><td><span :class="row.executionStatus === '执行成功' ? 'execution-success' : 'execution-interrupted'">{{ row.executionStatus }}</span><small>{{ row.executionHint }}</small></td><td><strong :class="{ 'danger-text': row.confidenceDisplay !== '—' && Number(row.confidence) < 0.9 }">{{ row.confidenceDisplay }}</strong><small>{{ row.confidenceHint }}</small></td><td>{{ row.processedAt }}</td><td><button type="button" @click.stop="openTask(row)">查看结果与日志 →</button></td></tr><tr v-if="!filteredRows.length"><td class="empty-row" colspan="8">暂无符合条件的具体任务</td></tr></tbody></table></div>
    </section>
    <!-- <GraphVersionView v-else embedded /> -->

    <button v-if="changeDrawerOpen" class="task-update-mask" type="button" aria-label="关闭变更明细" @click="changeDrawerOpen=false" />
    <aside v-if="changeDrawerOpen" class="change-drawer">
      <header><div><span>最近一次自动更新</span><h2>具体变更数据</h2><p>检测时间 2026-07-14 02:00 · 更新完成 02:18</p></div><button type="button" @click="changeDrawerOpen=false">×</button></header>
      <section class="change-summary"><article><span>新增</span><strong>18,420</strong></article><article><span>修改</span><strong>6,408</strong></article><article><span>删除</span><strong>312</strong></article></section>
      <nav><button class="active" type="button">全部变更</button><button type="button">论文</button><button type="button">专家</button><button type="button">专利 / 项目</button></nav>
      <div class="change-table"><table><thead><tr><th>变更</th><th>数据类型</th><th>对象标识</th><th>具体数据</th><th>识别时间</th><th>操作</th></tr></thead><tbody><tr v-for="row in changeRows" :key="row.id" tabindex="0" @click="selectedChange=row" @keydown.enter="selectedChange=row"><td><em :class="row.change === '新增' ? 'is-add' : row.change === '修改' ? 'is-update' : 'is-delete'">{{ row.change }}</em></td><td>{{ row.type }}</td><td>{{ row.id }}</td><td>{{ row.content }}</td><td>{{ row.time }}</td><td><button type="button">查看详情 →</button></td></tr></tbody></table></div>
      <footer><span>共 25,140 条变更</span><RouterLink to="/task-detail/batch/UPD-20260714">查看完整更新任务 →</RouterLink></footer>
    </aside>

    <aside v-if="selectedChange" class="change-record-detail">
      <header><button type="button" @click="selectedChange=null">← 返回变更列表</button><button type="button" aria-label="关闭详情" @click="selectedChange=null">×</button></header>
      <div><span>{{ selectedChange.change }} · {{ selectedChange.type }}</span><h2>{{ selectedChange.content }}</h2><p>对象标识：{{ selectedChange.id }}</p></div>
      <dl><div><dt>来源数据表</dt><dd>{{ selectedChange.source }}</dd></div><div><dt>识别时间</dt><dd>2026-07-14 {{ selectedChange.time }}</dd></div><div><dt>变更字段</dt><dd>{{ selectedChange.field }}</dd></div><div><dt>变更前</dt><dd>{{ selectedChange.before }}</dd></div><div><dt>变更后</dt><dd>{{ selectedChange.after }}</dd></div><div><dt>后续处理</dt><dd>{{ selectedChange.result }}</dd></div></dl>
      <footer><RouterLink to="/task-detail/batch/UPD-20260714">查看完整更新任务 →</RouterLink></footer>
    </aside>

    <button v-if="scheduleDialogOpen" class="task-update-mask" type="button" aria-label="关闭更新时间设置" @click="scheduleDialogOpen=false" />
    <aside v-if="scheduleDialogOpen" class="schedule-dialog">
      <header><div><span>自动更新策略</span><h2>设置检测与更新时间</h2></div><button type="button" @click="scheduleDialogOpen=false">×</button></header>
      <div><label><span>更新频率</span><select v-model="scheduleFrequency"><option>每天</option><option>每12小时</option><option>每6小时</option><option>每周</option></select></label><label><span>执行时间</span><input v-model="scheduleTime" type="time" /></label></div>
      <footer><button type="button" @click="scheduleDialogOpen=false">取消</button><button class="primary" type="button" @click="saveUpdateSchedule">保存策略</button></footer>
    </aside>

  </div>
</template>

<style scoped>
.task-center{height:100%;overflow:auto;color:#17233b}.task-center>header{margin-bottom:13px}.task-center h1{margin:0;font-size:21px}.task-center header p{margin:4px 0 0;color:#66758f;font-size:12px}.task-summary{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-bottom:10px}.task-summary article{display:grid;gap:2px;padding:9px 12px;border:1px solid #bdd7ff;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}.task-summary span{color:#61708a;font-size:11px;line-height:1.2}.task-summary strong{font-size:20px;line-height:1.1}.task-summary em{color:#8290a7;font-size:10px;font-style:normal;line-height:1.2}.task-panel{overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:#fff}.task-filter{display:grid;grid-template-columns:minmax(260px,1fr) 160px 150px auto;align-items:center;gap:10px;padding:13px;border-bottom:1px solid #dce8f8;background:#f7fbff}.task-filter input,.task-filter select{height:34px;padding:0 10px;border:1px solid #bdd7ff;border-radius:6px;background:#fff;color:#273957}.task-filter>span{color:#71809a;font-size:11px}.task-table{max-height:calc(100vh - 280px);overflow:auto}.task-table table{width:100%;border-collapse:collapse;font-size:12px}.task-table thead{position:sticky;z-index:2;top:0}.task-table th,.task-table td{height:48px;padding:8px 11px;border-bottom:1px solid #e5edf8;text-align:left;white-space:nowrap}.task-table th{background:#eef5ff;color:#5a6c88}.task-table tbody tr{cursor:pointer}.task-table tbody tr:hover td{background:#f4f8ff}.task-table button{border:0;background:transparent;color:#165dff;cursor:pointer}.progress{display:flex;align-items:center;gap:7px}.progress>i{position:relative;display:block;flex:0 0 96px;width:96px;height:7px;overflow:hidden;border-radius:999px;background:#eaf1fb}.progress-fill{position:absolute;inset:0 auto 0 0;display:block;border-radius:inherit;background:#165dff}.progress-fill.is-成功{background:#12b76a}.progress-fill.is-阻断{background:#f04438}.progress em{min-width:32px;color:#65738b;font-size:10px;font-style:normal}.status{display:inline-flex;padding:3px 8px;border-radius:999px;background:#eaf2ff;color:#165dff}.status.is-成功{background:#dcfae6;color:#067647}.status.is-阻断{background:#fee4e2;color:#b42318}@media(max-width:1100px){.task-summary{grid-template-columns:repeat(2,1fr)}.task-filter{grid-template-columns:1fr 1fr}.task-table{max-height:none}}
.task-table td small{display:block;margin-top:2px;color:#8290a7;font-size:9px}
.task-categories{display:flex;gap:4px;padding:0 13px;border-bottom:1px solid #dce8f8;background:#fff}.task-categories button{display:flex;align-items:center;gap:7px;padding:13px 12px 11px;border:0;border-bottom:2px solid transparent;background:transparent;color:#60708a;cursor:pointer}.task-categories button.active{border-color:#165dff;color:#165dff;font-weight:600}.task-categories em{min-width:20px;padding:1px 6px;border-radius:999px;background:#edf3fc;color:#71809a;font-size:10px;font-style:normal}.task-categories button.active em{background:#e6efff;color:#165dff}
.task-center{display:flex;box-sizing:border-box;min-height:0;overflow:hidden;padding-bottom:2px;flex-direction:column}.task-center>header,.auto-update-monitor,.task-summary{flex:0 0 auto}.task-panel{display:flex;flex:1;min-height:0;flex-direction:column}.task-categories,.task-filter{flex:0 0 auto}.task-table{flex:1;min-height:0;max-height:none;overflow:auto}
.task-center-primary-tabs{flex:0 0 auto;margin-bottom:12px;overflow:hidden;border:1px solid #bdd7ff;border-radius:8px;background:#fff}.task-center :deep(.version-page.is-embedded){flex:1;min-height:0}
.progress progress{display:block;width:112px;height:7px;overflow:hidden;border:0;border-radius:999px;background:#eaf1fb;appearance:none;-webkit-appearance:none}.progress progress::-webkit-progress-bar{border-radius:999px;background:#eaf1fb}.progress progress::-webkit-progress-value{border-radius:999px;background:#165dff}.progress progress::-moz-progress-bar{border-radius:999px;background:#165dff}.progress progress.is-成功::-webkit-progress-value{background:#12b76a}.progress progress.is-成功::-moz-progress-bar{background:#12b76a}.progress progress.is-阻断::-webkit-progress-value{background:#f04438}.progress progress.is-阻断::-moz-progress-bar{background:#f04438}
.task-center>header{display:flex;align-items:center;justify-content:space-between;gap:20px}.create-update{height:34px;padding:0 15px;border:0;border-radius:6px;background:#165dff;color:#fff;white-space:nowrap;cursor:pointer}.update-feedback{flex:0 0 auto;margin:0 0 12px;padding:9px 12px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3;color:#067647;font-size:11px}.progress>i{flex-basis:112px;width:112px;background:#eaf1fb}.task-update-mask{position:fixed;z-index:49;inset:0;border:0;background:rgba(16,36,76,.28)}.task-update-dialog{position:fixed;z-index:50;top:50%;left:50%;width:min(760px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.task-update-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:17px 19px;border-bottom:1px solid #dce8f8;background:#fff}.task-update-dialog header span{color:#165dff;font-size:10px}.task-update-dialog h2{margin:4px 0 0;font-size:18px}.task-update-dialog header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.task-update-dialog>nav{display:flex;align-items:center;gap:10px;padding:12px 19px;border-bottom:1px solid #dce8f8;background:#f4f8fd}.task-update-dialog>nav span{display:flex;align-items:center;gap:6px;color:#8290a7;font-size:10px}.task-update-dialog>nav span.active{color:#165dff;font-weight:600}.task-update-dialog>nav i{display:grid;place-items:center;width:22px;height:22px;border-radius:50%;background:#e6edf7;font-style:normal}.task-update-dialog>nav span.active i{background:#165dff;color:#fff}.task-update-dialog>nav b{color:#9cadc4}.update-form{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:18px}.update-form label{display:grid;gap:5px}.update-form label span{color:#5d6e87;font-size:10px}.update-form select,.update-form input{height:34px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766}.update-form section{grid-column:1/-1;padding:12px;border:1px solid #d7e4f5;border-radius:6px;background:#fff}.update-form section strong{font-size:11px}.update-form section p{margin:5px 0 0;color:#687892;font-size:10px;line-height:17px}.update-diff{padding:18px}.update-diff-summary{display:grid;grid-template-columns:repeat(4,1fr);gap:9px;margin-bottom:12px}.update-diff-summary article{display:grid;gap:4px;padding:11px;border:1px solid #d5e4f7;border-radius:6px;background:#fff}.update-diff-summary span{color:#71809a;font-size:10px}.update-diff-summary strong{font-size:20px}.update-diff table{width:100%;border-collapse:collapse;background:#fff;font-size:10px}.update-diff th,.update-diff td{padding:9px;border:1px solid #e1eaf5;text-align:left}.update-diff th{background:#f1f6fc}.update-diff>p{margin:11px 0 0;padding:10px;border-radius:6px;background:#eef5ff;color:#526783;font-size:10px;line-height:17px}.task-update-dialog>footer{display:flex;justify-content:flex-end;gap:8px;padding:12px 18px;border-top:1px solid #dce8f8;background:#fff}.task-update-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.task-update-dialog>footer .primary{border-color:#165dff;background:#165dff;color:#fff}
.auto-update-monitor{overflow:hidden;margin-bottom:10px;border:1px solid #b7d8c5;border-radius:8px;background:#fff}.auto-update-monitor>header{display:flex;align-items:center;justify-content:space-between;padding:6px 12px;border-bottom:1px solid #dceae2;background:#f0fbf4}.auto-update-monitor header>div{display:flex;align-items:center;gap:8px}.auto-update-monitor header i{width:8px;height:8px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12)}.auto-update-monitor header strong{font-size:12px}.auto-update-monitor header span,.auto-update-monitor header em{color:#5f7c6b;font-size:10px;font-style:normal}.auto-update-monitor>div{display:grid;grid-template-columns:1fr 1.2fr 1.7fr 1.2fr auto;align-items:center}.auto-update-monitor>div>span{display:grid;gap:3px;padding:10px 13px;border-right:1px solid #e1ebe5;color:#7a8b81;font-size:9px}.auto-update-monitor>div strong{overflow:hidden;color:#344b3e;font-size:10px;text-overflow:ellipsis;white-space:nowrap}.auto-update-monitor a{padding:0 13px;color:#165dff;font-size:10px;text-decoration:none;white-space:nowrap}
.auto-update-monitor>.auto-update-body{display:grid;grid-template-columns:minmax(0,1.7fr) minmax(260px,.8fr) auto;align-items:stretch}.auto-update-body article{display:grid;align-content:center;gap:3px;padding:8px 12px;border-right:1px solid #e1ebe5}.auto-update-body article>span{color:#74867b;font-size:9px}.auto-update-body article>strong{color:#2f493a;font-size:12px}.auto-update-body article p{display:flex;gap:6px;margin:0;color:#708177;font-size:9px}.latest-change p b{padding:2px 6px;border-radius:999px;background:#eef5ff;color:#315b95;font-weight:500}.latest-change button{width:max-content;padding:0;border:0;background:transparent;color:#165dff;font-size:9px;cursor:pointer}.update-actions{display:grid;grid-template-columns:auto auto;align-content:center;gap:6px;padding:8px 12px}.update-actions button{height:28px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;font-size:10px;cursor:pointer}.update-actions button.primary{border-color:#165dff;background:#165dff;color:#fff}.update-actions small{grid-column:1/-1;color:#819087;font-size:8px;text-align:right}.change-drawer{position:fixed;z-index:50;top:0;right:0;display:flex;width:min(760px,92vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}.change-drawer>header,.schedule-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.change-drawer header span,.schedule-dialog header span{color:#165dff;font-size:10px}.change-drawer h2,.schedule-dialog h2{margin:4px 0;font-size:18px}.change-drawer header p{margin:0;color:#71809a;font-size:10px}.change-drawer header button,.schedule-dialog header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.change-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:9px;padding:13px}.change-summary article{display:grid;gap:4px;padding:11px;border:1px solid #d6e3f4;border-radius:6px;background:#fff}.change-summary span{color:#71809a;font-size:9px}.change-summary strong{font-size:19px}.change-drawer>nav{display:flex;padding:0 13px;border-bottom:1px solid #dce8f8;background:#fff}.change-drawer>nav button{padding:10px;border:0;border-bottom:2px solid transparent;background:transparent;color:#61708a;font-size:10px;cursor:pointer}.change-drawer>nav button.active{border-color:#165dff;color:#165dff}.change-table{flex:1;min-height:0;overflow:auto;padding:13px}.change-table table{width:100%;border-collapse:collapse;background:#fff;font-size:10px}.change-table th,.change-table td{padding:10px;border-bottom:1px solid #e4ecf6;text-align:left}.change-table th{position:sticky;top:0;background:#f1f6fc;color:#5a6c88}.change-table em{display:inline-flex;padding:2px 6px;border-radius:999px;font-style:normal}.change-table .is-add{background:#e9f8ef;color:#067647}.change-table .is-update{background:#eaf2ff;color:#175cd3}.change-table .is-delete{background:#fee4e2;color:#b42318}.change-drawer>footer{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-top:1px solid #dce8f8;background:#fff}.change-drawer footer span{color:#71809a;font-size:9px}.change-drawer footer a{color:#165dff;font-size:10px;text-decoration:none}.schedule-dialog{position:fixed;z-index:50;top:50%;left:50%;width:min(560px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.schedule-dialog>div{display:grid;grid-template-columns:1fr 1fr;gap:12px;padding:17px}.schedule-dialog label{display:grid;gap:5px}.schedule-dialog label span{color:#60708a;font-size:10px}.schedule-dialog select,.schedule-dialog input{height:34px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766}.schedule-dialog section{grid-column:1/-1;padding:11px;border:1px solid #d6e3f4;border-radius:6px;background:#fff}.schedule-dialog section strong{font-size:11px}.schedule-dialog section p{margin:4px 0 0;color:#687892;font-size:10px;line-height:17px}.schedule-dialog .permission-note{border-color:#f3d29c;background:#fffaeb}.schedule-dialog>footer{display:flex;justify-content:flex-end;gap:7px;padding:12px 17px;border-top:1px solid #dce8f8;background:#fff}.schedule-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.schedule-dialog>footer .primary{border-color:#165dff;background:#165dff;color:#fff}@media(max-width:1200px){.auto-update-monitor>.auto-update-body{grid-template-columns:1fr 1fr}.update-actions{grid-column:1/-1;grid-template-columns:1fr 1fr}.update-actions small{text-align:left}}
.monitor-statuses{display:flex;align-items:center;gap:12px}.monitor-statuses>span{display:flex;align-items:center;gap:7px}.monitor-statuses>b{color:#668071;font-size:9px;font-weight:400}.auto-update-monitor .monitor-statuses i{display:block;flex:0 0 auto;width:7px;height:7px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 3px rgba(18,183,106,.12)}
.change-table tbody tr{cursor:pointer}.change-table tbody tr:hover td{background:#f4f8ff}.change-table td button{border:0;background:transparent;color:#165dff;font-size:9px;cursor:pointer;white-space:nowrap}.change-record-detail{position:fixed;z-index:51;top:0;right:0;display:flex;width:min(520px,88vw);height:100vh;background:#f8fbff;box-shadow:-16px 0 42px rgba(28,58,107,.28);flex-direction:column}.change-record-detail>header{display:flex;align-items:center;justify-content:space-between;padding:14px 17px;border-bottom:1px solid #dce8f8;background:#fff}.change-record-detail header button{border:0;background:transparent;color:#165dff;font-size:11px;cursor:pointer}.change-record-detail header button:last-child{display:grid;place-items:center;width:29px;height:29px;border-radius:5px;background:#f0f4fa;color:#344766;font-size:18px}.change-record-detail>div{padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.change-record-detail>div span{color:#165dff;font-size:10px}.change-record-detail h2{margin:6px 0;font-size:18px;line-height:27px}.change-record-detail>div p{margin:0;color:#71809a;font-size:10px}.change-record-detail dl{flex:1;margin:0;padding:15px;overflow:auto}.change-record-detail dl>div{display:grid;grid-template-columns:100px minmax(0,1fr);gap:12px;padding:13px;border-bottom:1px solid #e2eaf5;background:#fff}.change-record-detail dt{color:#71809a;font-size:10px}.change-record-detail dd{margin:0;color:#344766;font-size:11px;line-height:18px}.change-record-detail>footer{padding:14px 17px;border-top:1px solid #dce8f8;background:#fff;text-align:right}.change-record-detail footer a{color:#165dff;font-size:11px;text-decoration:none}
.task-filter{grid-template-columns:minmax(260px,1fr) 190px 120px 150px auto}.task-table code{color:#175cd3;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}.empty-row{height:90px!important;color:#8290a7;text-align:center!important}.status.is-已完成,.status.is-人工处理完成{background:#dcfae6;color:#067647}.status.is-待人工处理{background:#fff3d8;color:#b54708}
.task-filter--batch{grid-template-columns:minmax(320px,1fr) 170px 150px auto}.stage-state{display:inline-flex;padding:2px 7px;border-radius:999px;background:#eaf2ff;color:#175cd3;font-size:10px}.stage-state.is-已完成{background:#dcfae6;color:#067647}.stage-state.is-待审核{background:#fff3d8;color:#b54708}.status.is-待审核{background:#fee4e2;color:#b42318}.status.is-处理中{background:#eaf2ff;color:#175cd3}.danger-text{color:#b42318}.task-table td small code{font-size:9px}
.stage-state.is-已阻断{background:#fee4e2;color:#b42318}
.execution-success,.execution-interrupted{display:inline-flex;padding:2px 7px;border-radius:999px;font-size:10px}.execution-success{background:#dcfae6;color:#067647}.execution-interrupted{background:#fee4e2;color:#b42318}.task-table td{vertical-align:middle}
</style>
