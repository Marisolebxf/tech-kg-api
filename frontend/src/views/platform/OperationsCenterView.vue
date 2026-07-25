<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { getReviewBatch, getReviewCategory, getReviewConfidence, reviewRecords } from './manual-review-data'

type CenterMode = 'alerts' | 'review'

const props = defineProps<{ mode: CenterMode }>()
const route = useRoute()
const keyword = ref(String(route.query.keyword || ''))
const status = ref('全部状态')
const domain = ref('全部业务域')
const reviewCategory = ref('全部处理分类')
const batchFilter = ref(String(route.query.batch || '全部更新批次'))
const reviewTab = ref(route.query.tab === 'history' ? '历史记录' : '待处理')
const severity = ref('全部风险')
const actionFeedback = ref('')
const alertCategory = ref('全部异常')
const blockingOnly = ref(false)

const alertCategories = ['全部异常', '数据质量', 'Schema 校验', '大模型抽取', '实体对齐', '图谱入库', '服务运行']

const alertRows = [
  { id: 'ALT-0714-018', level: '高风险', category: '大模型抽取', module: '图谱构建', node: '大模型抽取', domain: '论文', batch: 'UPD-20260714', reason: '同一模型与 Prompt 版本连续产生不符合 Schema 的批量输出', impact: '流程级 · 326 条受影响', strategy: '当前节点及下游已阻断', owner: '张建图', time: '07-14 10:24', status: '待处理', blocked: true, target: '/tasks?module=图谱构建&batch=UPD-20260714' },
  { id: 'ALT-0714-014', level: '中风险', category: '数据质量', module: '数据处理', node: '质量检验', domain: '论文', batch: 'UPD-20260714', reason: '385 条记录命中唯一性、必填或枚举规则', impact: '任务级 · 385 条已隔离', strategy: '其他任务继续执行', owner: '李质量', time: '07-14 09:48', status: '待处理', blocked: false, target: '/tasks?module=数据处理&batch=UPD-20260714' },
  { id: 'ALT-0713-012', level: '中风险', category: '服务运行', module: '服务调用', node: '专家关系 Tool', domain: '人才', batch: 'CALL-20260713-1058', reason: 'P95 响应耗时超过 2 秒阈值', impact: '调用级 · 18 次慢调用', owner: '李运维', time: '07-13 10:58', status: '处理中', blocked: false, target: '/graph-tools' },
  { id: 'ALT-0713-106', level: '中风险', category: '实体对齐', module: '图谱构建', node: '实体消歧', domain: '专利', batch: 'UPD-20260713', reason: '候选实体置信度低于 0.75', impact: '任务级 · 42 个候选已处理', owner: '王审核', time: '07-13 18:06', status: '已关闭', blocked: false, target: '/tasks?module=图谱构建&batch=UPD-20260713' },
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
  reviewCategory.value = '全部处理分类'
  batchFilter.value = '全部更新批次'
  severity.value = '全部风险'
  alertCategory.value = '全部异常'
  blockingOnly.value = false
}

const filteredAlertRows = computed(() => alertRows.filter((row) => {
    const text = Object.values(row).join(' ')
    return (!keyword.value || text.includes(keyword.value))
      && (alertCategory.value === '全部异常' || text.includes(alertCategory.value))
      && (severity.value === '全部风险' || text.includes(severity.value))
      && (!blockingOnly.value || row.blocked)
      && (status.value === '全部状态' || text.includes(status.value))
      && (domain.value === '全部业务域' || text.includes(domain.value.replace('域', '')))
      && (!route.query.batch || text.includes(String(route.query.batch)))
}))

const reviewRows = computed(() => reviewRecords.map((row) => {
  const batch = getReviewBatch(row.batch)
  const confidence = getReviewConfidence(row)
  return {
    ...row,
    category: getReviewCategory(row),
    dataWindow: batch?.dataWindow ?? '-',
    confidenceValue: confidence.value,
    confidenceLabel: confidence.label,
    confidenceSource: confidence.source,
  }
}))

const reviewCategories = computed(() => [...new Set(reviewRows.value.map((row) => row.category))])
const pendingReviewCount = computed(() => reviewRows.value.filter((row) => row.status === '待处理').length)
const historyReviewCount = computed(() => reviewRows.value.filter((row) => row.status === '已完成').length)

const getReviewCategoryClass = (category: string) => {
  if (category === '结果低于阈值') return 'is-low-confidence'
  if (category.includes('抽取')) return 'is-extraction'
  if (category.includes('Schema')) return 'is-schema'
  if (category.includes('标准化') || category.includes('枚举')) return 'is-normalization'
  if (category === '其他流程异常') return 'is-other'
  return ''
}

const filteredReviewRows = computed(() => reviewRows.value.filter((row) => {
  const text = Object.values(row).join(' ')
  const inTab = reviewTab.value === '历史记录' ? row.status === '已完成' : row.status !== '已完成'
  return inTab
    && (!keyword.value || text.includes(keyword.value))
    && (status.value === '全部状态' || row.status === status.value)
    && (reviewCategory.value === '全部处理分类' || row.category === reviewCategory.value)
    && (batchFilter.value === '全部更新批次' || row.batch === batchFilter.value)
}))

const selectReviewTab = (tab: '待处理' | '历史记录') => {
  reviewTab.value = tab
  status.value = '全部状态'
}

watch(() => route.query.batch, (value) => { batchFilter.value = String(value || '全部更新批次') })
watch(() => route.query.keyword, (value) => { keyword.value = String(value || '') })
watch(() => route.query.tab, (value) => {
  reviewTab.value = value === 'history' ? '历史记录' : '待处理'
  status.value = '全部状态'
})
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

    <section class="ops-panel">
      <div v-if="mode === 'alerts'" class="alert-tabs"><nav><button v-for="item in alertCategories" :key="item" type="button" :class="{ active:alertCategory===item }" @click="alertCategory=item">{{ item }}</button></nav><label><input v-model="blockingOnly" type="checkbox" />仅看已阻断</label></div>
      <nav v-else class="review-tabs" aria-label="人工处理分类"><button type="button" :class="{ active: reviewTab === '待处理' }" @click="selectReviewTab('待处理')">待处理 <em>{{ pendingReviewCount }}</em></button><button type="button" :class="{ active: reviewTab === '历史记录' }" @click="selectReviewTab('历史记录')">历史记录 <em>{{ historyReviewCount }}</em></button></nav>
      <div :class="['ops-filter', { 'is-review': mode === 'review' }]">
        <input v-model="keyword" :placeholder="mode === 'review' ? '搜索处理实例 ID、对象或来源记录' : '搜索批次、对象、异常原因'" />
        <select v-if="mode === 'alerts'" v-model="severity"><option>全部风险</option><option>高风险</option><option>中风险</option><option>低风险</option></select>
        <select v-else v-model="batchFilter"><option>全部更新批次</option><option>UPD-20260714</option><option>UPD-20260713</option></select>
        <select v-if="mode === 'review'" v-model="reviewCategory"><option>全部处理分类</option><option v-for="item in reviewCategories" :key="item">{{ item }}</option></select>
        <select v-if="mode === 'alerts'" v-model="domain"><option>全部业务域</option><option>人才域</option><option>论文域</option><option>企业域</option></select>
        <select v-if="mode === 'alerts'" v-model="status"><option>全部状态</option><option>待处理</option><option>处理中</option><option>已关闭</option></select>
        <button type="button" @click="resetFilters">清空筛选</button>
      </div>

      <div v-if="mode === 'alerts'" class="ops-table-scroll"><table>
        <thead><tr><th>异常编号 / 风险</th><th>异常类型</th><th>模块 / 节点</th><th>业务域</th><th>任务批次</th><th>异常说明</th><th>影响范围 / 阻断策略</th><th>责任人</th><th>发生时间</th><th>状态</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in filteredAlertRows" :key="row.id"><td><strong>{{ row.id }}</strong><small :class="`level-${row.level}`">{{ row.level }}</small></td><td><b>{{ row.category }}</b></td><td><b>{{ row.module }}</b><small>{{ row.node }}</small></td><td>{{ row.domain }}</td><td><code>{{ row.batch }}</code></td><td class="alert-reason">{{ row.reason }}</td><td class="alert-impact"><strong>{{ row.impact }}</strong><small>{{ row.strategy || (row.blocked ? '阻断当前节点及下游' : '不阻断流程，按告警策略处理') }}</small></td><td>{{ row.owner }}</td><td>{{ row.time }}</td><td><span :class="['alert-status', `is-${row.status}`]">{{ row.status }}</span></td><td><div class="alert-actions"><RouterLink :to="row.target">查看诊断</RouterLink><RouterLink v-if="row.status !== '已关闭' && row.module !== '服务调用'" :to="`/manual-review?batch=${row.batch}`">人工审核</RouterLink></div></td></tr></tbody>
      </table></div>

      <div v-else class="ops-review-table-scroll"><table>
        <thead><tr><th>处理实例 ID</th><th>待处理对象</th><th>处理类型</th><th>来源记录</th><th>所属更新批次</th><th>数据更新时间范围</th><th>结果置信度</th><th>处理人</th><th>状态</th><th>{{ reviewTab === '历史记录' ? '完成时间' : '提交时间' }}</th><th>操作</th></tr></thead>
        <tbody><tr v-for="row in filteredReviewRows" :key="row.id"><td><code>{{ row.id }}</code></td><td><strong>{{ row.object }}</strong><small>{{ row.objectType }} · {{ row.objectId }}</small></td><td class="review-type-cell"><span :class="getReviewCategoryClass(row.category)">{{ row.category }}</span></td><td>{{ row.sourceTable }}<small>{{ row.sourceRecordId }}</small></td><td><code>{{ row.batch }}</code></td><td>{{ row.dataWindow }}</td><td class="review-confidence-cell"><b>{{ row.confidenceValue }}</b><em v-if="row.confidenceLabel">{{ row.confidenceLabel }}</em></td><td>{{ row.handler }}</td><td><span :class="['review-status', `is-${row.status}`]">{{ row.status }}</span></td><td>{{ row.completedAt || row.updatedAt }}</td><td><RouterLink class="link" :to="`/manual-review/task/${row.id}`">{{ row.status === '已完成' ? '查看记录' : '进入处理' }} →</RouterLink></td></tr><tr v-if="!filteredReviewRows.length"><td class="review-empty" colspan="11">暂无符合条件的{{ reviewTab }}</td></tr></tbody>
      </table></div>

      <footer v-if="mode === 'alerts'" class="alert-pagination"><span>每页显示　<select><option>20</option><option>50</option><option>100</option></select>　共 158 条异常</span><nav><button type="button" disabled>上一页</button><button class="active" type="button">1</button><button type="button">2</button><button type="button">3</button><button type="button">…</button><button type="button">8</button><button type="button">下一页</button></nav></footer>
      <footer v-else class="review-pagination"><span>共 {{ filteredReviewRows.length }} 条</span><nav><button type="button" disabled>上一页</button><button class="active" type="button">1</button><button type="button">下一页</button></nav></footer>
    </section>

  </div>
</template>

<style scoped>
.ops-page{height:100%;overflow:auto;padding-bottom:2px;color:#16233b}.ops-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}.ops-head h1{margin:0;font-size:20px}.ops-head p{margin:3px 0 0;color:#61708a;font-size:13px}.primary,.ops-filter button{height:34px;padding:0 16px;border:0;border-radius:6px;background:#165dff;color:#fff;cursor:pointer}.ops-metrics{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px;margin-bottom:14px}.ops-metrics.is-alerts{grid-template-columns:repeat(6,minmax(0,1fr))}.ops-metrics article{display:grid;gap:7px;padding:18px;border:1px solid #bdd7ff;border-radius:9px;background:linear-gradient(145deg,#fff,#f2f8ff);box-shadow:0 8px 20px rgba(48,105,194,.09)}.ops-metrics span{color:#61708a;font-size:14px}.ops-metrics strong{font-size:27px}.ops-metrics em{color:#7890b5;font-size:12px;font-style:normal}.ops-feedback{margin:-3px 0 12px;padding:9px 12px;border:1px solid #b2ccff;border-radius:6px;background:#f0f5ff;color:#344f7a;font-size:12px}.ops-panel{overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:rgba(255,255,255,.94);box-shadow:0 12px 28px rgba(48,105,194,.1)}.ops-filter{display:grid;grid-template-columns:minmax(260px,1fr) repeat(3,160px) auto;gap:10px;padding:14px;border-bottom:1px solid #dce9ff;background:#f7fbff}.ops-filter input,.ops-filter select{height:34px;padding:0 10px;border:1px solid #bdd7ff;border-radius:6px;background:#fff;color:#273957}.ops-table-scroll{max-height:430px;overflow:auto}table{width:100%;border-collapse:collapse;font-size:13px}th,td{height:52px;padding:10px 14px;border-bottom:1px solid #e5edf8;text-align:left;white-space:nowrap}th{position:sticky;z-index:2;top:0;background:#f4f8fd;color:#5a6c88;font-weight:600}td{color:#273957}td small{display:block;margin-top:4px;color:#7b89a1}.alert-reason{min-width:240px;white-space:normal;line-height:19px}.alert-actions{display:grid;gap:5px}.alert-tabs{display:flex;align-items:center;justify-content:space-between;gap:16px;padding:0 14px;border-bottom:1px solid #dce9ff}.alert-tabs nav{display:flex;overflow:auto}.alert-tabs button{padding:13px 14px;border:0;border-bottom:2px solid transparent;background:transparent;color:#52647f;white-space:nowrap;cursor:pointer}.alert-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.alert-tabs label{color:#5f6f88;font-size:12px;white-space:nowrap}.alert-tabs input{margin-right:6px}.level-严重,.level-警告,.level-提示{width:max-content;padding:2px 7px;border-radius:10px}.level-严重{background:#fee4e2!important;color:#d92d20!important}.level-警告{background:#fff3d8!important;color:#dc6803!important}.level-提示{background:#eaf2ff!important;color:#175cd3!important}.alert-status{padding:3px 8px;border-radius:10px;background:#edf2f7;color:#52647f}.alert-status.is-待处理{background:#fff0e8;color:#c4320a}.alert-status.is-处理中{background:#eaf2ff;color:#175cd3}.alert-status.is-已关闭{background:#e9f8ef;color:#067647}.alert-pagination{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;background:#fff;color:#687892;font-size:12px}.alert-pagination nav{display:flex;gap:5px}.alert-pagination button,.alert-pagination select{height:29px;padding:0 10px;border:1px solid #d3deee;border-radius:4px;background:#fff;color:#52647f}.alert-pagination button.active{border-color:#165dff;color:#165dff}.alert-pagination button:disabled{opacity:.45}td a,.link{border:0;background:transparent;color:#165dff;cursor:pointer;text-decoration:none}.danger{color:#d92d20}.success{color:#079455}@media(max-width:1280px){.ops-metrics.is-alerts{grid-template-columns:repeat(3,1fr)}}@media(max-width:1100px){.ops-metrics{grid-template-columns:repeat(2,1fr)}.ops-filter{grid-template-columns:1fr 1fr}.ops-panel{overflow:hidden}}
.review-context{display:flex;align-items:center;justify-content:space-between;gap:16px;margin-bottom:12px;padding:12px 14px;border:1px solid #b2ccff;border-radius:7px;background:#f0f5ff}.review-context div{display:grid;gap:3px}.review-context strong{font-size:13px}.review-context span{color:#65738b;font-size:11px}.review-context a{color:#165dff;font-size:12px;text-decoration:none;white-space:nowrap}
.review-evidence{min-width:260px;max-width:360px;white-space:normal;line-height:19px}.review-status{display:inline-flex;padding:3px 8px;border-radius:10px;background:#edf2f7;color:#52647f}.review-status.is-待处理{background:#fff0e8;color:#c4320a}.review-status.is-已完成{background:#e9f8ef;color:#067647}
.link-disabled{color:#98a2b3;font-size:12px;cursor:default}
.review-severity{min-width:230px;max-width:300px;white-space:normal}.review-severity small{margin:0 0 6px}.review-severity span{display:block;color:#65738b;font-size:11px;line-height:17px}
.review-mask{position:fixed;z-index:49;inset:0;border:0;background:rgba(16,36,76,.24)}.review-drawer{position:fixed;z-index:50;top:0;right:0;display:grid;grid-template-rows:auto minmax(0,1fr) auto;width:620px;height:100vh;background:#f8fbff;box-shadow:-18px 0 42px rgba(34,74,132,.22)}.review-drawer>header{display:flex;justify-content:space-between;padding:20px;border-bottom:1px solid #dce8f8;background:#fff}.review-drawer header span{color:#165dff;font-size:11px}.review-drawer h2{margin:6px 0 3px;font-size:19px}.review-drawer header p{margin:0;color:#70809a;font-size:12px}.review-drawer header>button{width:30px;height:30px;border:0;border-radius:5px;background:#f0f4fa;font-size:20px;cursor:pointer}.review-body{overflow:auto;padding:16px}.review-body section,.review-compare article{padding:14px;border:1px solid #dce8f8;border-radius:7px;background:#fff}.review-body h3{margin:0 0 8px;font-size:14px}.review-body p,.review-body li{color:#61708a;font-size:12px;line-height:20px}.review-compare{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin:12px 0}.review-compare span{display:block;margin-bottom:9px;color:#70809a;font-size:11px}.review-compare strong{font-size:13px}.review-compare em{color:#d92d20;font-size:11px;font-style:normal}.review-compare input,.review-compare textarea{width:100%;padding:8px;border:1px solid #bdd0ea;border-radius:5px;font:inherit}.review-compare textarea{min-height:90px;margin-top:8px;resize:vertical}.review-success{padding:10px 12px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3!important;color:#067647!important}.review-drawer>footer{display:flex;justify-content:flex-end;gap:8px;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.review-drawer>footer button{height:34px;padding:0 13px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;cursor:pointer}.review-drawer>footer .primary{border-color:#165dff;background:#165dff;color:#fff}@media(max-width:720px){.review-drawer{width:94vw}.review-compare{grid-template-columns:1fr}}
.ops-page{display:flex;box-sizing:border-box;min-height:0;overflow:hidden;padding-bottom:2px;flex-direction:column}.ops-head,.ops-metrics,.ops-feedback,.review-context{flex:0 0 auto}.ops-panel{display:flex;flex:1;min-height:0;flex-direction:column}.alert-tabs,.ops-filter,.alert-pagination,.review-tabs,.review-pagination{flex:0 0 auto}.ops-table-scroll,.ops-review-table-scroll{flex:1;min-height:0;max-height:none;overflow:auto}.ops-filter.is-review{grid-template-columns:minmax(280px,1fr) 170px 220px auto}.ops-review-table-scroll table{min-width:1900px}.review-tabs{display:flex;gap:4px;padding:0 14px;border-bottom:1px solid #dce9ff;background:#fff}.review-tabs button{display:flex;align-items:center;gap:7px;padding:13px 15px 11px;border:0;border-bottom:2px solid transparent;background:transparent;color:#60708a;cursor:pointer}.review-tabs button.active{border-color:#165dff;color:#165dff;font-weight:600}.review-tabs em{padding:1px 7px;border-radius:99px;background:#edf3fc;color:#71809a;font-size:10px;font-style:normal}.review-tabs button.active em{background:#e6efff;color:#165dff}.review-pagination{display:flex;align-items:center;justify-content:space-between;padding:11px 14px;border-top:1px solid #e4ecf6;background:#fff;color:#71809a;font-size:11px}.review-pagination nav{display:flex;gap:5px}.review-pagination button{height:28px;padding:0 10px;border:1px solid #d3deee;border-radius:4px;background:#fff;color:#52647f}.review-pagination button.active{border-color:#165dff;color:#165dff}.review-pagination button:disabled{opacity:.45}.review-empty{height:100px!important;color:#8290a7;text-align:center!important}.ops-review-table-scroll td code{color:#175cd3;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.review-type-cell{min-width:170px}.review-type-cell>span{display:inline-flex;padding:3px 9px;border-radius:99px;background:#eaf2ff;color:#175cd3;font-size:11px}.review-type-cell>span.is-low-confidence{background:#fff3d8;color:#b54708}.review-type-cell>span.is-extraction{background:#fef3f2;color:#b42318}.review-type-cell>span.is-schema{background:#edf0ff;color:#444ce7}.review-type-cell>span.is-normalization{background:#ecfdf3;color:#067647}.review-type-cell>span.is-other{background:#f2f4f7;color:#475467}
.ops-review-table-scroll table{min-width:1900px}.review-risk-explain{display:grid;flex:0 0 auto;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;margin-bottom:12px}.review-risk-explain>div{display:grid;gap:3px;padding:11px 14px;border:1px solid #b9d2f4;border-radius:7px;background:#f7fbff}.review-risk-explain strong{color:#344861;font-size:11px}.review-risk-explain span{color:#6d7c93;font-size:9px;line-height:16px}.review-confidence-cell{min-width:190px;white-space:normal}.review-confidence-cell>b{display:inline-block;margin-right:7px;font-size:13px}.review-confidence-cell>small{display:inline;color:#718098}.review-confidence-cell>span{display:block;margin-top:4px;color:#78869b;font-size:9px;line-height:15px}@media(max-width:900px){.review-risk-explain{grid-template-columns:1fr}}
.alert-impact{min-width:260px;max-width:340px;white-space:normal}.alert-impact strong,.alert-impact small{display:block;line-height:18px}.alert-impact small{color:#718099}.review-risk-explain{grid-template-columns:repeat(2,minmax(0,1fr))}.review-risk-explain>div:first-child{border-color:#f5b8b3;background:#fff5f4}.review-risk-explain>div:first-child strong{color:#d92d20}.review-risk-explain>div:nth-child(2){border-color:#f3d08a;background:#fffaf0}.review-risk-explain>div:nth-child(2) strong{color:#b54708}.review-type{min-width:150px}.review-confidence-cell{min-width:130px}.review-confidence-cell>em{display:block;width:max-content;margin-top:5px;padding:2px 7px;border-radius:9px;background:#fff3d8;color:#b54708;font-size:9px;font-style:normal}
.level-高风险{width:max-content;padding:2px 7px;border-radius:10px;background:#fee4e2;color:#d92d20}.level-中风险{width:max-content;padding:2px 7px;border-radius:10px;background:#fff3d8;color:#b54708}.level-低风险{width:max-content;padding:2px 7px;border-radius:10px;background:#eaf2ff;color:#175cd3}
.ops-review-table-scroll table{min-width:1900px}
</style>
