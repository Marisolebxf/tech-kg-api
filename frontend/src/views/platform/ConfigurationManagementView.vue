<script setup lang="ts">
import { computed, ref } from 'vue'
import { useToast } from '../../composables/use-toast'
import { useFormValidation, type Rules } from '../../composables/use-form-validation'
import FormField from '../../components/form-field.vue'

type ConfigStatus = '正常' | '停用' | '异常'
type ConfigItem = {
  id: string
  category: string
  name: string
  description: string
  type: string
  endpoint: string
  owner: string
  updatedAt: string
  status: ConfigStatus
  usage: string
  secret?: boolean
}

const categories = [
  { key: '大模型服务', label: '大模型服务', icon: 'LLM', count: 1 },
  { key: '数据源', label: '数据源连接', icon: 'DB', count: 4 },
  { key: '模型服务', label: '模型与抽取服务', icon: 'AI', count: 3 },
  // { key: 'Schema', label: 'Schema 与字典', icon: 'SC', count: 5 },
  { key: '调度', label: '调度与运行策略', icon: 'CR', count: 2 },
]

const items = ref<ConfigItem[]>([
  { id: 'LLM-01', category: '大模型服务', name: '大模型服务', description: '科技文本抽取与综合分析使用的大模型', type: '智谱 GLM', endpoint: 'glm-4.7-flash · https://open.bigmodel.cn/api/paas/v4', owner: '算法平台组', updatedAt: '2026-08-17 09:30', status: '正常', usage: '默认抽取模型', secret: true },
  { id: 'DS-MAIN', category: '数据源', name: '主库 · techkg', description: '科技专家、机构、论文、专利、项目等要素统一存储', type: 'MySQL', endpoint: 'mysql.internal:3306/techkg', owner: '数据平台组', updatedAt: '2026-08-17 09:30', status: '正常', usage: '主数据源', secret: true },
  { id: 'DS-PAPER', category: '数据源', name: '论文合作库 · gkx_local', description: '论文作者合作网络数据，独立 MySQL 实例', type: 'MySQL', endpoint: 'mysql.internal:3306/gkx_local', owner: '数据平台组', updatedAt: '2026-08-17 09:30', status: '正常', usage: '论文合作构建', secret: true },
  { id: 'DS-GKX', category: '数据源', name: '科技要素库 · gkx_element', description: '科技要素扩展数据，专家/机构/成果等明细', type: 'MySQL', endpoint: 'mysql.internal:3306/gkx_element', owner: '数据平台组', updatedAt: '2026-08-17 09:30', status: '正常', usage: '要素扩展', secret: true },
  { id: 'DS-GRAPH', category: '数据源', name: '图数据库 · trs-graph', description: 'NebulaGraph，通过 trs-graph-service REST API 访问', type: 'NebulaGraph', endpoint: 'http://localhost:8090/techkg', owner: '数据平台组', updatedAt: '2026-08-17 09:30', status: '正常', usage: '图谱存储', secret: true },
  { id: 'MODEL-LLM-01', category: '模型服务', name: '科技文本抽取大模型', description: '实体、关系、事件与属性联合抽取', type: 'LLM / OpenAI API', endpoint: 'llm-gateway.internal/v1', owner: '算法平台组', updatedAt: '2026-07-20 14:05', status: '正常', usage: '默认抽取模型', secret: true },
  { id: 'MODEL-EMB-02', category: '模型服务', name: '中文语义向量模型', description: '实体召回、相似度计算与消歧', type: 'Embedding', endpoint: 'embedding.internal/v1/embed', owner: '算法平台组', updatedAt: '2026-07-18 13:47', status: '正常', usage: '5 条 Pipeline' },
  { id: 'MODEL-NER-01', category: '模型服务', name: '科技领域 NER', description: '专家、机构、论文及技术术语识别', type: 'NER Service', endpoint: 'ner.internal/v2/extract', owner: '知识工程组', updatedAt: '2026-07-17 10:11', status: '停用', usage: '备用模型' },
  { id: 'SCHEMA-PROD', category: 'Schema', name: '生产图谱 Schema', description: '生产环境实体、关系及属性约束', type: 'Graph Schema', endpoint: 'tech-kg-schema v1.8', owner: '图谱治理组', updatedAt: '2026-07-20 17:20', status: '正常', usage: '12 类实体 · 43 类关系' },
  { id: 'DICT-ORG-02', category: 'Schema', name: '机构类型标准字典', description: '高校、科研院所、企业等类型映射', type: 'Dictionary', endpoint: 'dict-org-category v2.4', owner: '图谱治理组', updatedAt: '2026-07-18 15:30', status: '正常', usage: '128 条映射' },
  { id: 'RULE-DQ-01', category: 'Schema', name: '图谱入库质量规则', description: '必填、唯一性、证据与置信度规则', type: 'Rule Set', endpoint: 'kg-quality-rules v1.3', owner: '质量管理组', updatedAt: '2026-07-15 12:06', status: '正常', usage: '36 条规则' },
  { id: 'SCHEDULE-DEFAULT', category: '调度', name: '生产默认调度策略', description: '错峰运行、失败重试与告警通知', type: 'Schedule Policy', endpoint: 'Asia/Shanghai · 02:00', owner: '平台运维组', updatedAt: '2026-07-19 08:15', status: '正常', usage: '9 条 Pipeline' },
  { id: 'RUNTIME-LARGE', category: '调度', name: '大批量运行资源组', description: '适用于百万级以上批量抽取任务', type: 'Runtime Profile', endpoint: '16 worker · 64 GB', owner: '平台运维组', updatedAt: '2026-07-12 16:55', status: '正常', usage: '并发上限 4' },
])

// const activeCategory = ref('数据源')
const activeCategory = ref('模型服务')
const keyword = ref('')
const statusFilter = ref('全部状态')
const selected = ref<ConfigItem | null>(null)
const dialogOpen = ref(false)
const feedback = ref('')
const testingId = ref('')
const form = ref({ name: '', type: 'MySQL 8.0', endpoint: '', owner: '知识工程组', description: '', username: '', secret: '' })

const visibleItems = computed(() => items.value.filter((item) => {
  const matchCategory = item.category === activeCategory.value
  const query = keyword.value.trim().toLowerCase()
  const matchKeyword = !query || `${item.name}${item.id}${item.type}${item.endpoint}`.toLowerCase().includes(query)
  const matchStatus = statusFilter.value === '全部状态' || item.status === statusFilter.value
  return matchCategory && matchKeyword && matchStatus
}))

const summary = computed(() => ({
  total: items.value.length,
  healthy: items.value.filter((item) => item.status === '正常').length,
  warning: items.value.filter((item) => item.status === '异常').length,
  references: 28,
}))

const formRules: Rules = {
  name: { required: '请填写配置名称' },
  endpoint: { required: '请填写连接地址' },
}
const { visibleError: formVisibleError, validate: validateForm, touch: touchForm, clearErrors: clearFormErrors } = useFormValidation(form, formRules)

function openCreate() {
  form.value = { name: '', type: activeCategory.value === '数据源' ? 'MySQL 8.0' : activeCategory.value === '模型服务' ? 'LLM API' : 'Graph Schema', endpoint: '', owner: '知识工程组', description: '', username: '', secret: '' }
  clearFormErrors()
  dialogOpen.value = true
}

function saveConfig() {
  if (!validateForm()) return
  const prefix = activeCategory.value === '数据源' ? 'DS' : activeCategory.value === '模型服务' ? 'MODEL' : activeCategory.value === 'Schema' ? 'SCHEMA' : 'SCHEDULE'
  items.value.unshift({
    id: `${prefix}-${String(items.value.length + 1).padStart(2, '0')}`,
    category: activeCategory.value,
    name: form.value.name,
    description: form.value.description || '新建平台配置',
    type: form.value.type,
    endpoint: form.value.endpoint,
    owner: form.value.owner,
    updatedAt: '刚刚',
    status: '正常',
    usage: '尚未引用',
    secret: Boolean(form.value.secret),
  })
  dialogOpen.value = false
  feedback.value = `“${form.value.name}”已保存，可在 Pipeline 中引用。`
}

function testConnection(item: ConfigItem) {
  testingId.value = item.id
  feedback.value = ''
  window.setTimeout(() => {
    testingId.value = ''
    item.status = '正常'
    feedback.value = `${item.name}连接测试成功，延迟 38 ms。`
  }, 650)
}

function toggleItem(item: ConfigItem) {
  item.status = item.status === '停用' ? '正常' : '停用'
  feedback.value = `${item.name}已${item.status === '停用' ? '停用' : '启用'}。`
}

// ===== 大模型服务 + 数据源 抽屉 =====
const { showToast } = useToast()
type CoreDrawer = 'llm' | 'datasource' | null
const coreDrawerOpen = ref<CoreDrawer>(null)

const llmProviders = [
  { value: 'zhipu', label: '智谱 GLM', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4.7-flash' },
  { value: 'openai', label: 'OpenAI 兼容', baseUrl: '', model: 'gpt-4o-mini' },
  { value: 'self', label: '自部署模型', baseUrl: '', model: '' },
]

const llmConfig = ref({
  provider: 'zhipu',
  apiKey: '',
  apiKeySet: true,
  baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
  model: 'glm-4.7-flash',
  maxTokens: 2048,
  timeout: 40,
  showAdvanced: false,
})

const llmTesting = ref(false)

const llmRules = computed<Rules>(() => ({
  apiKey: llmConfig.value.apiKeySet ? {} : { required: '请填写 API Key' },
  baseUrl: {
    required: '请填写 Base URL',
    pattern: { regex: /^https?:\/\/.+/, message: '请输入合法的 URL（以 http:// 或 https:// 开头）' },
  },
  model: { required: '请填写模型名' },
}))
const { visibleError: llmVisibleError, validate: validateLlm, touch: touchLlm, clearErrors: clearLlmErrors } = useFormValidation(llmConfig, llmRules)

function onLlmProviderChange() {
  const p = llmProviders.find((item) => item.value === llmConfig.value.provider)
  if (p) {
    llmConfig.value.baseUrl = p.baseUrl
    llmConfig.value.model = p.model
  }
  clearLlmErrors()
}

function resetApiKey() {
  llmConfig.value.apiKey = ''
  llmConfig.value.apiKeySet = false
  clearLlmErrors()
}

function testLlm() {
  if (!validateLlm()) return
  llmTesting.value = true
  window.setTimeout(() => {
    llmTesting.value = false
    llmConfig.value.apiKeySet = true
    feedback.value = `大模型连接测试成功，模型 ${llmConfig.value.model} 返回正常。`
    showToast('大模型连接测试成功', 'success')
  }, 850)
}

function saveLlm() {
  if (!validateLlm()) return
  llmConfig.value.apiKeySet = true
  llmConfig.value.apiKey = ''
  const llmItem = items.value.find((item) => item.id === 'LLM-01')
  if (llmItem) {
    const p = llmProviders.find((item) => item.value === llmConfig.value.provider)
    llmItem.type = p?.label ?? llmConfig.value.provider
    llmItem.endpoint = `${llmConfig.value.model} · ${llmConfig.value.baseUrl}`
    llmItem.updatedAt = '刚刚'
  }
  coreDrawerOpen.value = null
  feedback.value = `大模型配置已保存，当前模型 ${llmConfig.value.model}。`
  showToast('大模型配置已保存', 'success')
}

type DatasourceKey = 'main' | 'paper_coop' | 'gkx_element' | 'graph'
type DatasourceDef = {
  key: DatasourceKey
  label: string
  type: 'MySQL' | 'NebulaGraph (trs-graph)'
  description: string
  fields: Array<{ key: string; label: string; type?: 'text' | 'password' | 'number'; placeholder?: string }>
}

const datasourceDefs: DatasourceDef[] = [
  {
    key: 'main',
    label: '主库 · techkg',
    type: 'MySQL',
    description: '科技专家、机构、论文、专利、项目等要素统一存储',
    fields: [
      { key: 'host', label: '主机地址', placeholder: 'mysql.internal' },
      { key: 'port', label: '端口', placeholder: '3306', type: 'number' },
      { key: 'database', label: '数据库名', placeholder: 'techkg' },
      { key: 'username', label: '用户名', placeholder: 'root' },
      { key: 'password', label: '密码', type: 'password', placeholder: '加密保存' },
    ],
  },
  {
    key: 'paper_coop',
    label: '论文合作库 · gkx_local',
    type: 'MySQL',
    description: '论文作者合作网络数据，独立 MySQL 实例',
    fields: [
      { key: 'host', label: '主机地址', placeholder: 'mysql.internal' },
      { key: 'port', label: '端口', placeholder: '3306', type: 'number' },
      { key: 'database', label: '数据库名', placeholder: 'gkx_local' },
      { key: 'username', label: '用户名', placeholder: 'root' },
      { key: 'password', label: '密码', type: 'password', placeholder: '加密保存' },
    ],
  },
  {
    key: 'gkx_element',
    label: '科技要素库 · gkx_element',
    type: 'MySQL',
    description: '科技要素扩展数据，专家/机构/成果等明细',
    fields: [
      { key: 'host', label: '主机地址', placeholder: 'mysql.internal' },
      { key: 'port', label: '端口', placeholder: '3306', type: 'number' },
      { key: 'database', label: '数据库名', placeholder: 'gkx_element' },
      { key: 'username', label: '用户名', placeholder: 'root' },
      { key: 'password', label: '密码', type: 'password', placeholder: '加密保存' },
    ],
  },
  {
    key: 'graph',
    label: '图数据库 · trs-graph',
    type: 'NebulaGraph (trs-graph)',
    description: 'NebulaGraph，通过 trs-graph-service REST API 访问',
    fields: [
      { key: 'baseUrl', label: '服务地址', placeholder: 'http://localhost:8090' },
      { key: 'space', label: '图空间', placeholder: 'techkg' },
      { key: 'apiKey', label: 'API Key', type: 'password', placeholder: 'X-API-Key 鉴权' },
      { key: 'timeout', label: '超时（秒）', placeholder: '30', type: 'number' },
    ],
  },
]

const itemIdToDsKey: Record<string, DatasourceKey> = {
  'DS-MAIN': 'main',
  'DS-PAPER': 'paper_coop',
  'DS-GKX': 'gkx_element',
  'DS-GRAPH': 'graph',
}

const activeDsKey = ref<DatasourceKey>('main')
const datasourceValues = ref<Record<DatasourceKey, Record<string, string>>>({
  main: { host: 'mysql.internal', port: '3306', database: 'techkg', username: 'root', password: '' },
  paper_coop: { host: 'mysql.internal', port: '3306', database: 'gkx_local', username: 'root', password: '' },
  gkx_element: { host: 'mysql.internal', port: '3306', database: 'gkx_element', username: 'root', password: '' },
  graph: { baseUrl: 'http://localhost:8090', space: 'techkg', apiKey: '', timeout: '30' },
})
const datasourcePasswordSet = ref<Record<DatasourceKey, boolean>>({
  main: true,
  paper_coop: true,
  gkx_element: true,
  graph: true,
})
const dsTesting = ref<DatasourceKey | null>(null)
const dsAdvancedOpen = ref(false)

const activeDsDef = computed(() => datasourceDefs.find((item) => item.key === activeDsKey.value)!)
const activeDsValues = computed(() => datasourceValues.value[activeDsKey.value])
const dsRules = computed<Rules>(() => {
  const rules: Rules = {}
  for (const field of activeDsDef.value.fields) {
    if (field.type === 'password') continue
    if (field.key === 'port') {
      rules[field.key] = {
        required: `请填写${field.label}`,
        pattern: { regex: /^\d+$/, message: '端口必须是数字' },
        min: { value: 1, message: '端口范围 1-65535' },
        max: { value: 65535, message: '端口范围 1-65535' },
      }
    } else if (field.type === 'number') {
      rules[field.key] = {
        required: `请填写${field.label}`,
        pattern: { regex: /^\d+$/, message: `${field.label}必须是数字` },
      }
    } else {
      rules[field.key] = { required: `请填写${field.label}` }
    }
  }
  return rules
})
const { visibleError: dsVisibleError, validate: validateDs, touch: touchDs, clearErrors: clearDsErrors } = useFormValidation(activeDsValues, dsRules)
const dsStatusList = computed(() => datasourceDefs.map((item) => ({
  key: item.key,
  label: item.label,
  type: item.type,
  configured: datasourcePasswordSet.value[item.key],
})))
const dsConfiguredCount = computed(() => dsStatusList.value.filter((item) => item.configured).length)

function switchDs(key: DatasourceKey) {
  activeDsKey.value = key
  clearDsErrors()
}

function testDs(key: DatasourceKey) {
  if (!validateDs()) return
  dsTesting.value = key
  window.setTimeout(() => {
    dsTesting.value = null
    if (activeDsDef.value.fields.some((f) => f.type === 'password')) {
      datasourcePasswordSet.value[key] = true
      datasourceValues.value[key].password = ''
    }
    feedback.value = `${activeDsDef.value.label} 连接测试成功。`
    showToast(`${activeDsDef.value.label} 连接测试成功`, 'success')
  }, 800)
}

function saveDs() {
  if (!validateDs()) return
  const key = activeDsKey.value
  if (activeDsDef.value.fields.some((f) => f.type === 'password')) {
    datasourcePasswordSet.value[key] = true
    datasourceValues.value[key].password = ''
  }
  const dsItemId = Object.entries(itemIdToDsKey).find(([, v]) => v === key)?.[0]
  const dsItem = items.value.find((item) => item.id === dsItemId)
  if (dsItem) dsItem.updatedAt = '刚刚'
  feedback.value = `${activeDsDef.value.label} 配置已保存。`
  showToast(`${activeDsDef.value.label} 配置已保存`, 'success')
}

function saveAllDs() {
  feedback.value = `数据来源配置已全部保存（${dsConfiguredCount.value}/${datasourceDefs.length} 已配置）。`
  showToast('数据来源配置已保存', 'success')
  coreDrawerOpen.value = null
}

function handleItemClick(item: ConfigItem) {
  if (item.category === '大模型服务') {
    coreDrawerOpen.value = 'llm'
    return
  }
  if (item.category === '数据源') {
    const dsKey = itemIdToDsKey[item.id]
    if (dsKey) {
      activeDsKey.value = dsKey
      coreDrawerOpen.value = 'datasource'
      return
    }
  }
  selected.value = item
}
</script>

<template>
  <div class="configuration-page">
    <header class="page-header">
      <div><span>PLATFORM CONFIGURATION</span><h1>配置管理</h1><p>统一管理 Pipeline 运行依赖的数据源、模型服务、Schema、字典及调度策略。</p></div>
      <button class="primary" type="button" @click="openCreate">＋ 新建配置</button>
    </header>

    <section class="summary-grid">
      <article><i class="blue">∑</i><div><span>配置总数</span><strong>{{ summary.total }}</strong><small>覆盖 4 类平台能力</small></div></article>
      <article><i class="green">✓</i><div><span>运行正常</span><strong>{{ summary.healthy }}</strong><small>最近检测 2 分钟前</small></div></article>
      <article><i class="orange">!</i><div><span>需要关注</span><strong>{{ summary.warning }}</strong><small>Kafka 连接延迟异常</small></div></article>
      <article><i class="purple">↗</i><div><span>Pipeline 引用</span><strong>{{ summary.references }}</strong><small>跨 11 条生产流程</small></div></article>
    </section>

    <p v-if="feedback" class="feedback"><span>✓</span>{{ feedback }}<button type="button" @click="feedback=''">×</button></p>

    <section class="config-workbench">
      <aside class="category-nav">
        <header><strong>配置分类</strong><span>按能力域管理</span></header>
        <button v-for="category in categories" :key="category.key" type="button" :class="{ active: activeCategory === category.key }" @click="activeCategory=category.key;selected=null">
          <i>{{ category.icon }}</i><span><strong>{{ category.label }}</strong><small>{{ category.key === '大模型服务' ? 'API Key、模型与调用参数' : category.key === '数据源' ? 'MySQL 与图数据库连接' : category.key === '模型服务' ? 'LLM、向量与抽取模型' : category.key === 'Schema' ? '图谱约束、字典与规则' : '定时、重试与资源配置' }}</small></span><em>{{ items.filter(item => item.category === category.key).length }}</em>
        </button>
        <section><b>凭据安全</b><p>密码与 API Key 使用密钥中心加密保存，页面仅展示脱敏值。</p><a href="#" @click.prevent="feedback='已打开凭据访问审计。'">查看访问审计 →</a></section>
      </aside>

      <main class="config-list">
        <header><div><h2>{{ categories.find(item => item.key === activeCategory)?.label }}</h2><span>{{ visibleItems.length }} 项配置</span></div><nav><input v-model="keyword" placeholder="搜索名称、标识或地址" /><select v-model="statusFilter"><option>全部状态</option><option>正常</option><option>异常</option><option>停用</option></select></nav></header>
        <div class="table-wrap">
          <table>
            <thead><tr><th>配置名称</th><th>类型 / 地址</th><th>状态</th><th>引用情况</th><th>负责人 / 更新时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in visibleItems" :key="item.id" @click="handleItemClick(item)">
                <td><div class="config-name"><i>{{ item.category === '大模型服务' ? 'LLM' : item.category === '数据源' ? 'DB' : item.category === '模型服务' ? 'AI' : item.category === 'Schema' ? 'SC' : 'CR' }}</i><span><strong>{{ item.name }}</strong><small>{{ item.id }} · {{ item.description }}</small></span></div></td>
                <td><strong class="type-name">{{ item.type }}</strong><code>{{ item.endpoint }}</code></td>
                <td><span class="status" :class="`is-${item.status}`"><i />{{ item.status }}</span></td>
                <td>{{ item.usage }}</td>
                <td><span>{{ item.owner }}</span><small class="updated">{{ item.updatedAt }}</small></td>
                <td><button class="link" type="button" @click.stop="handleItemClick(item)">管理</button></td>
              </tr>
              <tr v-if="!visibleItems.length"><td class="empty" colspan="6">没有符合条件的配置</td></tr>
            </tbody>
          </table>
        </div>
      </main>
    </section>

    <button v-if="selected || dialogOpen || coreDrawerOpen" class="mask" type="button" aria-label="关闭" @click="selected=null;dialogOpen=false;coreDrawerOpen=null" />
    <aside v-if="selected" class="detail-drawer">
      <header><div><span>{{ selected.id }}</span><h2>{{ selected.name }}</h2><p>{{ selected.description }}</p></div><button type="button" @click="selected=null">×</button></header>
      <section class="health-card"><i :class="`is-${selected.status}`" /><div><strong>{{ selected.status === '正常' ? '配置可用' : selected.status === '异常' ? '连接存在异常' : '配置已停用' }}</strong><span>最近健康检查：2 分钟前</span></div><button type="button" :disabled="testingId === selected.id" @click="testConnection(selected)">{{ testingId === selected.id ? '测试中…' : '测试连接' }}</button></section>
      <div class="detail-form">
        <label><span>配置名称</span><input v-model="selected.name" /></label>
        <label><span>服务类型</span><input v-model="selected.type" /></label>
        <label class="wide"><span>连接地址 / 版本</span><input v-model="selected.endpoint" /></label>
        <label class="wide"><span>配置说明</span><textarea v-model="selected.description" /></label>
        <label><span>负责人</span><input v-model="selected.owner" /></label>
        <label><span>访问凭据</span><input :value="selected.secret ? '••••••••••••••••' : '无需凭据'" readonly /></label>
      </div>
      <section class="reference-card"><header><strong>引用关系</strong><span>{{ selected.usage }}</span></header><p>配置变更将在下次 Pipeline 运行时生效。删除前需先解除所有生产流程引用。</p></section>
      <footer><button type="button" @click="toggleItem(selected)">{{ selected.status === '停用' ? '启用配置' : '停用配置' }}</button><button class="primary" type="button" @click="feedback=`${selected.name}的修改已保存。`;selected=null">保存修改</button></footer>
    </aside>

    <aside v-if="dialogOpen" class="create-dialog">
      <header><div><span>NEW CONFIGURATION</span><h2>新建{{ categories.find(item => item.key === activeCategory)?.label }}</h2></div><button type="button" @click="dialogOpen=false">×</button></header>
      <div class="dialog-form">
        <FormField label="配置名称" required :error="formVisibleError('name')" class="dialog-field"><input v-model="form.name" placeholder="例如：科技项目数据仓库" @blur="touchForm('name')" /></FormField>
        <FormField label="连接类型" required :error="formVisibleError('type')" class="dialog-field"><select v-model="form.type"><option>MySQL 8.0</option><option>PostgreSQL</option><option>REST API</option><option>Kafka</option><option>S3 / OSS</option><option>LLM API</option><option>Graph Schema</option></select></FormField>
        <FormField label="连接地址 / 版本" required :error="formVisibleError('endpoint')" class="dialog-field wide"><input v-model="form.endpoint" placeholder="主机地址、Topic、Bucket 或服务 URL" @blur="touchForm('endpoint')" /></FormField>
        <FormField label="访问账号" class="dialog-field"><input v-model="form.username" placeholder="可选" /></FormField>
        <FormField label="密码 / API Key" class="dialog-field"><input v-model="form.secret" type="password" placeholder="加密保存" /></FormField>
        <FormField label="负责人" class="dialog-field"><input v-model="form.owner" /></FormField>
        <FormField label="说明" class="dialog-field wide"><textarea v-model="form.description" placeholder="说明数据范围、用途或变更影响" /></FormField>
      </div>
      <footer><button type="button" @click="dialogOpen=false">取消</button><button class="primary" type="button" @click="saveConfig">保存并测试</button></footer>
    </aside>

    <aside v-if="coreDrawerOpen === 'llm'" class="core-drawer">
      <header><div><span>CORE CONFIGURATION</span><h2>大模型服务</h2><p>科技文本抽取、综合分析与企业背景关联使用的大模型配置</p></div><button type="button" @click="coreDrawerOpen=null">×</button></header>
      <div class="core-drawer__body">
        <section class="core-section">
          <FormField label="服务商" required class="core-field">
            <select v-model="llmConfig.provider" @change="onLlmProviderChange">
              <option v-for="item in llmProviders" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
          </FormField>
          <FormField label="API Key" required :error="llmVisibleError('apiKey')" class="core-field wide">
            <div class="secret-row">
              <input v-if="!llmConfig.apiKeySet" v-model="llmConfig.apiKey" type="password" placeholder="请输入 API Key" @blur="touchLlm('apiKey')" />
              <input v-else value="••••••••••••••••" readonly />
              <button v-if="llmConfig.apiKeySet" type="button" class="link" @click="resetApiKey">重置</button>
            </div>
          </FormField>
          <FormField label="Base URL" required :error="llmVisibleError('baseUrl')" class="core-field wide"><input v-model="llmConfig.baseUrl" placeholder="例如 https://open.bigmodel.cn/api/paas/v4" @blur="touchLlm('baseUrl')" /></FormField>
          <FormField label="模型名" required :error="llmVisibleError('model')" class="core-field wide"><input v-model="llmConfig.model" placeholder="例如 glm-4.7-flash" @blur="touchLlm('model')" /></FormField>
        </section>
        <section class="core-section core-section--advanced">
          <header><button type="button" class="link" @click="llmConfig.showAdvanced=!llmConfig.showAdvanced">{{ llmConfig.showAdvanced ? '收起高级配置 ▲' : '展开高级配置 ▼' }}</button></header>
          <div v-if="llmConfig.showAdvanced" class="core-section__inner">
            <FormField label="最大 token 数" class="core-field"><input v-model.number="llmConfig.maxTokens" type="number" min="1" /></FormField>
            <FormField label="超时（秒）" class="core-field"><input v-model.number="llmConfig.timeout" type="number" min="1" /></FormField>
          </div>
        </section>
      </div>
      <footer>
        <button type="button" :disabled="llmTesting" @click="testLlm">{{ llmTesting ? '测试中…' : '测试连接' }}</button>
        <button class="primary" type="button" @click="saveLlm">保存配置</button>
      </footer>
    </aside>

    <aside v-if="coreDrawerOpen === 'datasource'" class="core-drawer core-drawer--wide">
      <header><div><span>CORE CONFIGURATION</span><h2>数据来源</h2><p>平台依赖的 3 个 MySQL 库和 1 个图数据库（trs-graph / NebulaGraph）</p></div><button type="button" @click="coreDrawerOpen=null">×</button></header>
      <nav class="ds-tabs">
        <button v-for="item in dsStatusList" :key="item.key" type="button" :class="{ active: activeDsKey === item.key }" @click="switchDs(item.key)">
          <span>{{ item.label }}</span>
          <em :class="['ds-tab__status', item.configured ? 'is-ok' : 'is-warn']">{{ item.configured ? '已配置' : '未配置' }}</em>
        </button>
      </nav>
      <div class="core-drawer__body">
        <section class="core-section">
          <header class="core-section__title"><strong>{{ activeDsDef.label }}</strong><span>{{ activeDsDef.type }} · {{ activeDsDef.description }}</span></header>
          <FormField v-for="field in activeDsDef.fields" :key="field.key" :label="field.label" :required="field.type !== 'password'" :error="dsVisibleError(field.key)" :class="['core-field', { wide: field.type === 'password' }]">
            <div v-if="field.type === 'password'" class="secret-row">
              <input v-if="!datasourcePasswordSet[activeDsKey]" v-model="datasourceValues[activeDsKey][field.key]" type="password" :placeholder="field.placeholder" />
              <input v-else value="••••••••••••••••" readonly />
              <button v-if="datasourcePasswordSet[activeDsKey]" type="button" class="link" @click="datasourcePasswordSet[activeDsKey]=false">重置</button>
            </div>
            <input v-else v-model="datasourceValues[activeDsKey][field.key]" :type="field.type || 'text'" :placeholder="field.placeholder" @blur="touchDs(field.key)" />
          </FormField>
        </section>
        <section class="core-section core-section--advanced">
          <header><button type="button" class="link" @click="dsAdvancedOpen=!dsAdvancedOpen">{{ dsAdvancedOpen ? '收起连接池配置 ▲' : '展开连接池配置 ▼' }}</button></header>
          <div v-if="dsAdvancedOpen" class="core-section__inner">
            <p class="core-note">连接池上限、超时与重试策略沿用平台默认值；如需调整，请联系平台运维组在调度策略中修改。</p>
          </div>
        </section>
      </div>
      <footer>
        <span class="btn-hint">{{ dsConfiguredCount }}/{{ datasourceDefs.length }} 已就绪</span>
        <button type="button" :disabled="dsTesting === activeDsKey" @click="testDs(activeDsKey)">{{ dsTesting === activeDsKey ? '测试中…' : '测试当前连接' }}</button>
        <button type="button" @click="saveDs">保存当前配置</button>
        <button class="primary" type="button" @click="saveAllDs">全部保存并关闭</button>
      </footer>
    </aside>
  </div>
</template>

<style scoped>
.configuration-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;color:#17233b;flex-direction:column}.page-header{display:flex;flex:0 0 auto;align-items:flex-end;justify-content:space-between;margin-bottom:12px}.page-header span{color:#165dff;font-size:9px;letter-spacing:.12em}.page-header h1{margin:3px 0 0;font-size:22px}.page-header p{margin:4px 0 0;color:#66758f;font-size:11px}.primary{border-color:#165dff!important;background:#165dff!important;color:#fff!important}.page-header button{height:34px;padding:0 14px;border:0;border-radius:6px;cursor:pointer}.summary-grid{display:grid;flex:0 0 auto;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}.summary-grid article{display:flex;align-items:center;gap:11px;padding:10px 13px;border:1px solid #bdd7ff;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}.summary-grid article>i{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;font-style:normal;font-weight:700}.summary-grid .blue{background:#eaf2ff;color:#165dff}.summary-grid .green{background:#dcfae6;color:#067647}.summary-grid .orange{background:#fff3d8;color:#b54708}.summary-grid .purple{background:#f4f3ff;color:#5925dc}.summary-grid article>div{display:grid;grid-template-columns:1fr auto;flex:1;gap:2px}.summary-grid span,.summary-grid small{color:#71809a;font-size:9px}.summary-grid strong{grid-row:1/3;grid-column:2;font-size:20px}.feedback{display:flex;align-items:center;gap:8px;margin:0 0 10px;padding:8px 11px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3;color:#067647;font-size:10px}.feedback span{display:grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#12b76a;color:#fff}.feedback button{margin-left:auto;border:0;background:transparent;color:#067647;cursor:pointer}.config-workbench{display:grid;flex:1;min-height:0;grid-template-columns:248px minmax(0,1fr);overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:#fff}.category-nav{display:flex;min-height:0;border-right:1px solid #dce8f8;background:#f8fbff;flex-direction:column}.category-nav>header{display:grid;gap:3px;padding:14px;border-bottom:1px solid #dce8f8}.category-nav>header strong{font-size:13px}.category-nav>header span{color:#8290a7;font-size:9px}.category-nav>button{display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:9px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #edf2f8;background:transparent;color:#344766;text-align:left;cursor:pointer}.category-nav>button.active{background:#eaf2ff;box-shadow:inset 3px 0 #165dff}.category-nav>button>i{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;background:#fff;color:#526783;font-size:9px;font-style:normal;font-weight:700}.category-nav>button.active>i{background:#165dff;color:#fff}.category-nav>button>span{display:grid;gap:3px}.category-nav>button strong{font-size:11px}.category-nav>button small{color:#8290a7;font-size:8px}.category-nav>button em{min-width:20px;padding:2px 6px;border-radius:99px;background:#e7eef8;color:#71809a;font-size:9px;font-style:normal;text-align:center}.category-nav>section{margin:auto 12px 12px;padding:11px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.category-nav>section b{font-size:10px}.category-nav>section p{margin:4px 0 6px;color:#71809a;font-size:9px;line-height:15px}.category-nav>section a{color:#165dff;font-size:9px;text-decoration:none}.config-list{display:flex;min-width:0;min-height:0;flex-direction:column}.config-list>header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #dce8f8;background:#fff}.config-list>header>div{display:flex;align-items:baseline;gap:8px}.config-list h2{margin:0;font-size:15px}.config-list>header span{color:#8290a7;font-size:9px}.config-list nav{display:flex;gap:7px}.config-list input,.config-list select{height:31px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font-size:10px}.config-list input{width:210px}.table-wrap{flex:1;min-height:0;overflow:auto}.table-wrap table{width:100%;border-collapse:collapse;font-size:10px}.table-wrap thead{position:sticky;z-index:2;top:0}.table-wrap th,.table-wrap td{padding:10px 11px;border-bottom:1px solid #e7eef7;text-align:left;vertical-align:middle}.table-wrap th{background:#f2f7fd;color:#60708a;font-weight:600;white-space:nowrap}.table-wrap tbody tr{cursor:pointer}.table-wrap tbody tr:hover td{background:#f7faff}.config-name{display:flex;align-items:center;gap:9px;min-width:210px}.config-name>i{display:grid;place-items:center;flex:0 0 auto;width:29px;height:29px;border-radius:7px;background:#eaf2ff;color:#175cd3;font-size:8px;font-style:normal;font-weight:700}.config-name>span{display:grid;gap:3px}.config-name strong{font-size:11px}.config-name small,.updated{display:block;color:#8290a7;font-size:8px}.type-name{display:block;color:#40516d;font-size:10px}.table-wrap code{display:block;max-width:210px;margin-top:3px;overflow:hidden;color:#71809a;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.status{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:99px}.status>i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.is-正常{background:#dcfae6;color:#067647}.status.is-异常{background:#fee4e2;color:#b42318}.status.is-停用{background:#eef1f5;color:#667085}.link{border:0;background:transparent;color:#165dff;font-size:10px;cursor:pointer}.empty{height:100px;color:#8290a7;text-align:center!important}.mask{position:fixed;z-index:40;inset:0;border:0;background:rgba(16,36,76,.24)}.detail-drawer{position:fixed;z-index:41;top:0;right:0;display:flex;width:min(500px,90vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}.detail-drawer>header,.create-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.detail-drawer>header span,.create-dialog>header span{color:#165dff;font-size:9px}.detail-drawer h2,.create-dialog h2{margin:4px 0;font-size:18px}.detail-drawer>header p{margin:0;color:#71809a;font-size:10px}.detail-drawer>header button,.create-dialog>header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.health-card{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;gap:10px;margin:14px 16px 0;padding:12px;border:1px solid #cfe4d7;border-radius:7px;background:#fff}.health-card>i{width:9px;height:9px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12)}.health-card>i.is-异常{background:#f04438;box-shadow:0 0 0 4px rgba(240,68,56,.12)}.health-card>i.is-停用{background:#98a2b3;box-shadow:none}.health-card>div{display:grid;gap:3px}.health-card strong{font-size:11px}.health-card span{color:#71809a;font-size:9px}.health-card button{height:29px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#165dff;font-size:9px;cursor:pointer}.detail-form,.dialog-form{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:16px}.detail-form label,.dialog-form label{display:grid;gap:5px}.detail-form label span,.dialog-form label span{color:#60708a;font-size:9px}.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{box-sizing:border-box;width:100%;height:33px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font:10px inherit}.detail-form textarea,.dialog-form textarea{height:65px;padding-top:8px;resize:none}.wide{grid-column:1/-1}.dialog-form .kg-field,.detail-form .kg-field{display:grid;gap:5px}.dialog-form .kg-field__label,.detail-form .kg-field__label{color:#60708a;font-size:9px}.dialog-form .kg-field__error,.detail-form .kg-field__error{font-size:9px}.dialog-form .kg-field.wide,.detail-form .kg-field.wide{grid-column:1/-1}.reference-card{margin:0 16px;padding:12px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.reference-card header{display:flex;justify-content:space-between}.reference-card strong{font-size:10px}.reference-card span{color:#165dff;font-size:9px}.reference-card p{margin:5px 0 0;color:#71809a;font-size:9px;line-height:16px}.detail-drawer>footer,.create-dialog>footer{display:flex;justify-content:flex-end;gap:8px;margin-top:auto;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.detail-drawer>footer button,.create-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.create-dialog{position:fixed;z-index:42;top:50%;left:50%;width:min(650px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.create-dialog>footer{margin-top:0}.create-dialog button:disabled{opacity:.5;cursor:not-allowed}
.core-drawer{position:fixed;z-index:43;top:0;right:0;display:flex;width:min(520px,90vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}
.core-drawer--wide{width:min(640px,92vw)}
.core-drawer>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}
.core-drawer>header span{color:#165dff;font-size:9px;letter-spacing:.12em}
.core-drawer h2{margin:4px 0;font-size:18px}
.core-drawer>header p{margin:0;color:#7a8aa3;font-size:11px}
.core-drawer>header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}
.core-drawer__body{flex:1;min-height:0;overflow:auto;padding:16px}
.core-section{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:14px;border:1px solid #e0e9f5;border-radius:8px;background:#fff}
.core-section+.core-section{margin-top:11px}
.core-section--advanced{padding:0;border-color:#e8eef7;background:#fbfdff}
.core-section--advanced>header{padding:9px 14px;border-bottom:1px solid #eef2f8}
.core-section__inner{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:14px}
.core-section__title{display:grid;gap:3px;grid-column:1/-1;margin-bottom:4px;padding-bottom:9px;border-bottom:1px solid #eef2f8}
.core-section__title strong{font-size:13px;color:#1d2b4a}
.core-section__title span{color:#7a8aa3;font-size:10px}
.core-section label{display:grid;gap:5px}
.core-section label.wide,.core-section .kg-field.wide{grid-column:1/-1}
.core-section label>span{color:#60708a;font-size:10px}
.core-section label>span em{color:#f53f3f;font-style:normal;margin-left:2px}
.core-section input,.core-section select{box-sizing:border-box;width:100%;height:34px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font:12px inherit}
.core-section input:read-only{background:#f4f7fc;color:#9aa4b3}
.core-section .kg-field{gap:5px}
.core-section .kg-field__label{color:#60708a;font-size:10px}
.core-section .kg-field__error{font-size:10px}
.secret-row{display:flex;align-items:center;gap:8px}
.secret-row input{flex:1}
.core-note{grid-column:1/-1;margin:0;color:#7a8aa3;font-size:10px;line-height:18px}
.core-drawer>footer{display:flex;justify-content:flex-end;gap:8px;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}
.core-drawer>footer button{height:34px;padding:0 13px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;cursor:pointer;font-size:12px}
.core-drawer>footer button:disabled{opacity:.5;cursor:not-allowed}
.core-drawer>footer .primary{border-color:#165dff;background:#165dff;color:#fff}
.btn-hint{margin-right:auto;color:#b54708;font-size:10px;line-height:34px}
.ds-tabs{display:flex;flex-wrap:wrap;gap:6px;padding:11px 14px;border-bottom:1px solid #e3ebf6;background:#fff}
.ds-tabs button{display:flex;align-items:center;gap:6px;padding:7px 12px;border:1px solid #d8e1ee;border-radius:99px;background:#fff;color:#52647f;font-size:11px;cursor:pointer}
.ds-tabs button.active{border-color:#165dff;background:#eaf2ff;color:#165dff;font-weight:600}
.ds-tab__status{padding:1px 7px;border-radius:99px;background:#f4f6fa;color:#7a8aa3;font-size:9px;font-style:normal}
.ds-tab__status.is-ok{background:#dcfae6;color:#067647}
.ds-tab__status.is-warn{background:#fff3d8;color:#b54708}@media(max-width:1100px){.summary-grid{grid-template-columns:repeat(2,1fr)}.config-workbench{grid-template-columns:210px minmax(0,1fr)}.core-drawer{width:100vw}.core-section{grid-template-columns:1fr}.core-section__inner{grid-template-columns:1fr}}
</style>
