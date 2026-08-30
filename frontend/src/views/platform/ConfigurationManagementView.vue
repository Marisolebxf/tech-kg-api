<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import {
  createLlmConfig,
  currentUserId,
  deleteLlmConfig,
  listLlmConfigs,
  setDefaultLlmConfig,
  testLlmConfig,
  updateLlmConfig,
  type LlmConfig,
} from '../../api/llmConfig'
import {
  createMysqlDatasource,
  deleteMysqlDatasource,
  listMysqlDatasources,
  setDefaultMysqlDatasource,
  testMysqlDatasource,
  updateMysqlDatasource,
  type MysqlDatasource,
} from '../../api/mysqlDatasource'
import {
  createMilvusConfig,
  deleteMilvusConfig,
  listMilvusConfigs,
  setDefaultMilvusConfig,
  testMilvusConfig,
  updateMilvusConfig,
  type MilvusConfig,
} from '../../api/milvusConfig'
import {
  createEmbeddingConfig,
  deleteEmbeddingConfig,
  listEmbeddingConfigs,
  setDefaultEmbeddingConfig,
  testEmbeddingConfig,
  updateEmbeddingConfig,
  type EmbeddingConfig,
} from '../../api/embeddingConfig'
import { useToast } from '../../composables/use-toast'

type ConfigKind = 'llm' | 'embedding' | 'mysql' | 'milvus'
type ConfigStatus = '正常' | '停用' | '异常'

type ConfigItem = {
  id: string
  kind: ConfigKind
  category: string
  name: string
  description: string
  type: string
  endpoint: string
  owner: string
  updatedAt: string
  status: ConfigStatus
  usage: string
  isDefault: boolean
  // llm / embedding
  baseUrl?: string
  model?: string
  apiKey?: string
  hasApiKey?: boolean
  apiKeyMasked?: string
  dimensions?: number | null
  // mysql
  host?: string
  port?: number
  defaultDatabase?: string
  username?: string
  password?: string
  hasPassword?: boolean
  passwordMasked?: string
  // milvus
  uri?: string
  defaultDb?: string
  token?: string
  hasToken?: boolean
  tokenMasked?: string
}

const { showToast } = useToast()

const categories = [
  { key: '模型服务', label: '模型服务', icon: 'AI', hint: 'LLM 配置，接通后端' },
  { key: '抽取与向量模型', label: '抽取与向量模型', icon: 'EM', hint: 'embedding 模型配置' },
  { key: '数据源', label: '数据源', icon: 'DB', hint: 'MySQL / Milvus 配置' },
]

const items = ref<ConfigItem[]>([])
const activeCategory = ref('模型服务')
const keyword = ref('')
const statusFilter = ref('全部状态')
const selected = ref<ConfigItem | null>(null)
const dialogOpen = ref(false)
const testingId = ref('')
const saving = ref(false)
const formSubKind = ref<'mysql' | 'milvus'>('mysql')

type ConfigForm = {
  name?: string
  baseUrl?: string
  model?: string
  apiKey?: string
  dimensions?: number | null
  owner?: string
  description?: string
  host?: string
  port?: number
  defaultDatabase?: string
  username?: string
  password?: string
  uri?: string
  token?: string
  defaultDb?: string
  isDefault?: boolean
}

const form = ref<ConfigForm>({})

const isDataSourceCategory = computed(() => activeCategory.value === '数据源')

const formKind = computed<ConfigKind | null>(() => {
  switch (activeCategory.value) {
    case '模型服务':
      return 'llm'
    case '抽取与向量模型':
      return 'embedding'
    case '数据源':
      return formSubKind.value
    default:
      return null
  }
})

const visibleItems = computed(() => items.value.filter((item) => {
  const matchCategory = item.category === activeCategory.value
  const query = keyword.value.trim().toLowerCase()
  const endpointOrUrl = item.baseUrl || item.host || item.uri || item.endpoint
  const matchKeyword = !query || `${item.name}${item.id}${item.type}${endpointOrUrl}${item.model || ''}`.toLowerCase().includes(query)
  const matchStatus = statusFilter.value === '全部状态' || item.status === statusFilter.value
  return matchCategory && matchKeyword && matchStatus
}))

const summary = computed(() => ({
  total: items.value.filter((i) => i.category === activeCategory.value).length,
  healthy: items.value.filter((i) => i.category === activeCategory.value && i.status === '正常').length,
  warning: items.value.filter((i) => i.category === activeCategory.value && i.status === '异常').length,
}))

function defaultIcon(kind: ConfigKind) {
  return kind === 'llm' ? 'AI' : kind === 'embedding' ? 'EM' : kind === 'mysql' ? 'MY' : 'ML'
}

function categoryCount(key: string) {
  return items.value.filter((i) => i.category === key).length
}

function buildUsage(kind: ConfigKind, isDefault: boolean): string {
  if (isDefault) {
    return kind === 'llm' ? '默认抽取模型' : kind === 'embedding' ? '默认向量模型' : '默认数据源'
  }
  return '尚未引用'
}

function toConfigItem(kind: ConfigKind, cfg: LlmConfig | MysqlDatasource | MilvusConfig | EmbeddingConfig): ConfigItem {
  const common = {
    id: cfg.id,
    kind,
    name: cfg.name,
    description: cfg.description,
    owner: cfg.owner || '',
    updatedAt: cfg.updatedAt,
    status: (cfg.status === '正常' ? '正常' : cfg.status === '停用' ? '停用' : '异常') as ConfigStatus,
    isDefault: (cfg as { isDefault: boolean }).isDefault,
    usage: buildUsage(kind, (cfg as { isDefault: boolean }).isDefault),
  }
  if (kind === 'llm') {
    const c = cfg as LlmConfig
    return { ...common, category: '模型服务', type: 'LLM API', endpoint: c.baseUrl, baseUrl: c.baseUrl, model: c.model, hasApiKey: c.hasApiKey, apiKeyMasked: c.apiKeyMasked }
  }
  if (kind === 'embedding') {
    const c = cfg as EmbeddingConfig
    return { ...common, category: '抽取与向量模型', type: 'Embedding API', endpoint: c.baseUrl, baseUrl: c.baseUrl, model: c.model, dimensions: c.dimensions, hasApiKey: c.hasApiKey, apiKeyMasked: c.apiKeyMasked }
  }
  if (kind === 'mysql') {
    const c = cfg as MysqlDatasource
    return { ...common, category: '数据源', type: 'MySQL 数据源', endpoint: `${c.host}:${c.port}`, host: c.host, port: c.port, defaultDatabase: c.defaultDatabase, username: c.username, hasPassword: c.hasPassword, passwordMasked: c.passwordMasked }
  }
  const c = cfg as MilvusConfig
  return { ...common, category: '数据源', type: 'Milvus 配置', endpoint: c.uri || '(env)', uri: c.uri, defaultDb: c.defaultDb, hasToken: c.hasToken, tokenMasked: c.tokenMasked }
}

async function loadByCategory(key: string) {
  const others = items.value.filter((i) => i.category !== key)
  let loaded: ConfigItem[] = []
  try {
    if (key === '模型服务') {
      loaded = (await listLlmConfigs(currentUserId())).map((c) => toConfigItem('llm', c))
    } else if (key === '抽取与向量模型') {
      loaded = (await listEmbeddingConfigs(currentUserId())).map((c) => toConfigItem('embedding', c))
    } else if (key === '数据源') {
      const [mysql, milvus] = await Promise.all([listMysqlDatasources(currentUserId()), listMilvusConfigs(currentUserId())])
      loaded = [...mysql.map((c) => toConfigItem('mysql', c)), ...milvus.map((c) => toConfigItem('milvus', c))]
    }
  } catch (err) {
    showToast(`加载配置失败：${(err as Error).message}`, 'warning')
  }
  items.value = [...loaded, ...others]
}

async function switchCategory(key: string) {
  activeCategory.value = key
  selected.value = null
  await loadByCategory(key)
}

function emptyForm(kind: ConfigKind): ConfigForm {
  if (kind === 'llm') {
    return { name: '', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4.7-flash', apiKey: '', owner: '算法平台组', description: '', isDefault: false }
  }
  if (kind === 'embedding') {
    return { name: '', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'embedding-3', dimensions: 1024, apiKey: '', owner: '算法平台组', description: '', isDefault: false }
  }
  if (kind === 'mysql') {
    return { name: '', host: '127.0.0.1', port: 3306, defaultDatabase: '', username: 'root', password: '', owner: '平台运维组', description: '', isDefault: false }
  }
  return { name: '', uri: '', token: '', defaultDb: 'default', owner: '平台运维组', description: '', isDefault: false }
}

function openCreate() {
  if (isDataSourceCategory.value) {
    formSubKind.value = 'mysql'
  }
  form.value = emptyForm(formKind.value || 'llm')
  dialogOpen.value = true
}

function switchFormSubKind(kind: 'mysql' | 'milvus') {
  formSubKind.value = kind
  form.value = emptyForm(kind)
}

async function saveConfig() {
  const kind = formKind.value
  if (!kind) return
  if (!String(form.value.name).trim()) return
  saving.value = true
  try {
    if (kind === 'llm') {
      await createLlmConfig({
        name: String(form.value.name).trim(),
        baseUrl: String(form.value.baseUrl).trim(),
        model: String(form.value.model).trim(),
        apiKey: String(form.value.apiKey || '').trim(),
        owner: String(form.value.owner || '').trim(),
        description: String(form.value.description || '').trim(),
        isDefault: Boolean(form.value.isDefault),
      }, currentUserId())
    } else if (kind === 'embedding') {
      await createEmbeddingConfig({
        name: String(form.value.name).trim(),
        baseUrl: String(form.value.baseUrl).trim(),
        model: String(form.value.model).trim(),
        dimensions: form.value.dimensions == null ? null : Number(form.value.dimensions),
        apiKey: String(form.value.apiKey || '').trim(),
        owner: String(form.value.owner || '').trim(),
        description: String(form.value.description || '').trim(),
        isDefault: Boolean(form.value.isDefault),
      }, currentUserId())
    } else if (kind === 'mysql') {
      await createMysqlDatasource({
        name: String(form.value.name).trim(),
        host: String(form.value.host).trim(),
        port: Number(form.value.port || 3306),
        defaultDatabase: String(form.value.defaultDatabase || '').trim(),
        username: String(form.value.username).trim(),
        password: String(form.value.password || ''),
        owner: String(form.value.owner || '').trim(),
        description: String(form.value.description || '').trim(),
        isDefault: Boolean(form.value.isDefault),
      }, currentUserId())
    } else {
      await createMilvusConfig({
        name: String(form.value.name).trim(),
        uri: String(form.value.uri || '').trim(),
        token: String(form.value.token || ''),
        defaultDb: String(form.value.defaultDb || 'default').trim(),
        owner: String(form.value.owner || '').trim(),
        description: String(form.value.description || '').trim(),
        isDefault: Boolean(form.value.isDefault),
      }, currentUserId())
    }
    dialogOpen.value = false
    showToast(`“${String(form.value.name)}”已保存。`, 'success')
    await loadByCategory(activeCategory.value)
  } catch (err) {
    showToast(`保存失败：${(err as Error).message}`, 'warning')
  } finally {
    saving.value = false
  }
}

async function saveDetail() {
  if (!selected.value) return
  const item = selected.value
  saving.value = true
  try {
    if (item.kind === 'llm') {
      const updated = await updateLlmConfig(item.id, {
        name: item.name, description: item.description, baseUrl: item.baseUrl || '', model: item.model || '',
        owner: item.owner, apiKey: item.apiKey || '', status: item.status,
      }, currentUserId())
      selected.value = { ...selected.value, ...toConfigItem('llm', updated), apiKey: '' }
    } else if (item.kind === 'embedding') {
      const updated = await updateEmbeddingConfig(item.id, {
        name: item.name, description: item.description, baseUrl: item.baseUrl || '', model: item.model || '',
        dimensions: item.dimensions ?? null, owner: item.owner, apiKey: item.apiKey || '', status: item.status,
      }, currentUserId())
      selected.value = { ...selected.value, ...toConfigItem('embedding', updated), apiKey: '' }
    } else if (item.kind === 'mysql') {
      const updated = await updateMysqlDatasource(item.id, {
        name: item.name, description: item.description, host: item.host || '', port: Number(item.port || 3306),
        defaultDatabase: item.defaultDatabase || '', username: item.username || '',
        password: item.password || '', owner: item.owner, status: item.status,
      }, currentUserId())
      selected.value = { ...selected.value, ...toConfigItem('mysql', updated), password: '' }
    } else {
      const updated = await updateMilvusConfig(item.id, {
        name: item.name, description: item.description, uri: item.uri || '', token: item.token || '',
        defaultDb: item.defaultDb || 'default', owner: item.owner, status: item.status,
      }, currentUserId())
      selected.value = { ...selected.value, ...toConfigItem('milvus', updated), token: '' }
    }
    await loadByCategory(activeCategory.value)
    showToast(`“${item.name}”的修改已保存。`, 'success')
  } catch (err) {
    showToast(`保存失败：${(err as Error).message}`, 'warning')
  } finally {
    saving.value = false
  }
}

async function testConnection(item: ConfigItem) {
  testingId.value = item.id
  try {
    let result: { ok: boolean; latencyMs: number | null; error: string | null }
    if (item.kind === 'llm') {
      result = await testLlmConfig(item.id, currentUserId())
    } else if (item.kind === 'embedding') {
      result = await testEmbeddingConfig(item.id, currentUserId())
    } else if (item.kind === 'mysql') {
      result = await testMysqlDatasource(item.id, currentUserId())
    } else {
      result = await testMilvusConfig(item.id, currentUserId())
    }
    if (result.ok) {
      item.status = '正常'
      showToast(`${item.name} 连接测试成功，延迟 ${result.latencyMs ?? '-'} ms。`, 'success')
    } else {
      item.status = '异常'
      showToast(`${item.name} 连接失败：${result.error ?? '未知错误'}`, 'warning')
    }
  } catch (err) {
    showToast(`测试请求失败：${(err as Error).message}`, 'warning')
  } finally {
    testingId.value = ''
  }
}

async function toggleItem(item: ConfigItem) {
  const nextStatus: ConfigStatus = item.status === '停用' ? '正常' : '停用'
  try {
    if (item.kind === 'llm') {
      Object.assign(item, toConfigItem('llm', await updateLlmConfig(item.id, { status: nextStatus }, currentUserId())))
    } else if (item.kind === 'embedding') {
      Object.assign(item, toConfigItem('embedding', await updateEmbeddingConfig(item.id, { status: nextStatus }, currentUserId())))
    } else if (item.kind === 'mysql') {
      Object.assign(item, toConfigItem('mysql', await updateMysqlDatasource(item.id, { status: nextStatus }, currentUserId())))
    } else {
      Object.assign(item, toConfigItem('milvus', await updateMilvusConfig(item.id, { status: nextStatus }, currentUserId())))
    }
    showToast(`${item.name}已${nextStatus === '停用' ? '停用' : '启用'}。`, 'info')
    await loadByCategory(activeCategory.value)
  } catch (err) {
    showToast(`切换状态失败：${(err as Error).message}`, 'warning')
  }
}

async function setAsDefault(item: ConfigItem) {
  try {
    if (item.kind === 'llm') {
      await setDefaultLlmConfig(item.id, currentUserId())
    } else if (item.kind === 'embedding') {
      await setDefaultEmbeddingConfig(item.id, currentUserId())
    } else if (item.kind === 'mysql') {
      await setDefaultMysqlDatasource(item.id, currentUserId())
    } else {
      await setDefaultMilvusConfig(item.id, currentUserId())
    }
    showToast(`“${item.name}”已设为默认。`, 'success')
    await loadByCategory(activeCategory.value)
    const fresh = items.value.find((i) => i.id === item.id)
    if (fresh && selected.value) selected.value = { ...selected.value, ...fresh }
  } catch (err) {
    showToast(`设为默认失败：${(err as Error).message}`, 'warning')
  }
}

async function removeConfig(item: ConfigItem) {
  if (!window.confirm(`确认删除配置“${item.name}”？删除后不可恢复。`)) return
  try {
    if (item.kind === 'llm') {
      await deleteLlmConfig(item.id, currentUserId())
    } else if (item.kind === 'embedding') {
      await deleteEmbeddingConfig(item.id, currentUserId())
    } else if (item.kind === 'mysql') {
      await deleteMysqlDatasource(item.id, currentUserId())
    } else {
      await deleteMilvusConfig(item.id, currentUserId())
    }
    showToast(`“${item.name}”已删除。`, 'success')
    selected.value = null
    await loadByCategory(activeCategory.value)
  } catch (err) {
    showToast(`删除失败：${(err as Error).message}`, 'warning')
  }
}

onMounted(() => {
  loadByCategory('模型服务')
})
</script>

<template>
  <div class="configuration-page">
    <header class="page-header">
      <div><span>PLATFORM CONFIGURATION</span><h1>配置管理</h1><p>统一管理 Pipeline 运行依赖的模型服务、向量模型与数据源。配置项真正驱动抽取脚本的 context 注入。</p></div>
      <button class="primary" type="button" @click="openCreate">＋ 新建配置</button>
    </header>

    <section class="summary-grid">
      <article><i class="blue">∑</i><div><span>配置总数</span><strong>{{ summary.total }}</strong><small>当前类别</small></div></article>
      <article><i class="green">✓</i><div><span>运行正常</span><strong>{{ summary.healthy }}</strong><small>当前类别</small></div></article>
      <article><i class="orange">!</i><div><span>需要关注</span><strong>{{ summary.warning }}</strong><small>异常配置</small></div></article>
      <article><i class="purple">↗</i><div><span>默认配置</span><strong>{{ items.find(i => i.category === activeCategory && i.isDefault)?.name || '未设置' }}</strong><small>下次调用生效</small></div></article>
    </section>

    <section class="config-workbench">
      <aside class="category-nav">
        <header><strong>配置分类</strong><span>按能力域管理</span></header>
        <button v-for="category in categories" :key="category.key" type="button" :class="{ active: activeCategory === category.key }" @click="switchCategory(category.key)">
          <i>{{ category.icon }}</i><span><strong>{{ category.label }}</strong><small>{{ category.hint }}</small></span><em>{{ categoryCount(category.key) }}</em>
        </button>
        <section><b>凭据安全</b><p>API Key / 密码 / Token 在数据库明文保存（第一版），页面仅展示脱敏值。后续将接入密钥中心。</p></section>
      </aside>

      <main class="config-list">
        <header><div><h2>{{ categories.find(item => item.key === activeCategory)?.label }}</h2><span>{{ visibleItems.length }} 项配置</span></div><nav><input v-model="keyword" placeholder="搜索名称、标识或地址" /><select v-model="statusFilter"><option>全部状态</option><option>正常</option><option>异常</option><option>停用</option></select></nav></header>
        <div class="table-wrap">
          <table>
            <thead><tr><th>配置名称</th><th>类型 / 地址</th><th>状态</th><th>引用情况</th><th>负责人 / 更新时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in visibleItems" :key="item.id" @click="selected=item">
                <td><div class="config-name"><i>{{ defaultIcon(item.kind) }}</i><span><strong>{{ item.name }}<b v-if="item.isDefault" class="default-tag">默认</b></strong><small>{{ item.id }} · {{ item.description }}</small></span></div></td>
                <td><strong class="type-name">{{ item.type }}<template v-if="item.model"> · {{ item.model }}</template></strong><code>{{ item.baseUrl || item.host && `${item.host}:${item.port}` || item.uri || item.endpoint }}</code></td>
                <td><span class="status" :class="`is-${item.status}`"><i />{{ item.status }}</span></td>
                <td>{{ item.usage }}</td>
                <td><span>{{ item.owner }}</span><small class="updated">{{ item.updatedAt }}</small></td>
                <td><button class="link" type="button" @click.stop="selected=item">管理</button></td>
              </tr>
              <tr v-if="!visibleItems.length"><td class="empty" colspan="6">没有符合条件的配置</td></tr>
            </tbody>
          </table>
        </div>
      </main>
    </section>

    <button v-if="selected || dialogOpen" class="mask" type="button" aria-label="关闭" @click="selected=null;dialogOpen=false" />
    <aside v-if="selected" class="detail-drawer">
      <header><div><span>{{ selected.id }}</span><h2>{{ selected.name }}<b v-if="selected.isDefault" class="default-tag">默认</b></h2><p>{{ selected.description }}</p></div><button type="button" @click="selected=null">×</button></header>
      <section class="health-card"><i :class="`is-${selected.status}`" /><div><strong>{{ selected.status === '正常' ? '配置可用' : selected.status === '异常' ? '连接存在异常' : '配置已停用' }}</strong><span>后端真实探活</span></div><button type="button" :disabled="testingId === selected.id" @click="testConnection(selected)">{{ testingId === selected.id ? '测试中…' : '测试连接' }}</button></section>
      <div class="detail-form">
        <label><span>配置名称</span><input v-model="selected.name" /></label>
        <label><span>服务类型</span><input :value="selected.type" readonly /></label>
        <template v-if="selected.kind === 'llm' || selected.kind === 'embedding'">
          <label class="wide"><span>Base URL</span><input v-model="selected.baseUrl" /></label>
          <label><span>模型</span><input v-model="selected.model" /></label>
          <label v-if="selected.kind === 'embedding'"><span>维度</span><input v-model.number="selected.dimensions" type="number" /></label>
          <label><span>访问凭据</span><input :value="selected.apiKeyMasked || (selected.hasApiKey ? '••••••••' : '未设置')" readonly /></label>
          <label class="wide"><span>更新 API Key（留空保留原值）</span><input v-model="selected.apiKey" type="password" placeholder="输入新 Key 覆盖原值" /></label>
        </template>
        <template v-else-if="selected.kind === 'mysql'">
          <label><span>主机</span><input v-model="selected.host" /></label>
          <label><span>端口</span><input v-model.number="selected.port" type="number" /></label>
          <label><span>默认库</span><input v-model="selected.defaultDatabase" /></label>
          <label><span>用户名</span><input v-model="selected.username" /></label>
          <label><span>访问凭据</span><input :value="selected.passwordMasked || (selected.hasPassword ? '••••••••' : '未设置')" readonly /></label>
          <label class="wide"><span>更新密码（留空保留原值）</span><input v-model="selected.password" type="password" placeholder="输入新密码覆盖原值" /></label>
        </template>
        <template v-else>
          <label class="wide"><span>URI</span><input v-model="selected.uri" placeholder="留空回退 env MILVUS_*" /></label>
          <label><span>默认库</span><input v-model="selected.defaultDb" /></label>
          <label><span>访问凭据</span><input :value="selected.tokenMasked || (selected.hasToken ? '••••••••' : '未设置')" readonly /></label>
          <label class="wide"><span>更新 Token（留空保留原值）</span><input v-model="selected.token" type="password" placeholder="输入新 Token 覆盖原值" /></label>
        </template>
        <label class="wide"><span>配置说明</span><textarea v-model="selected.description" /></label>
        <label><span>负责人</span><input v-model="selected.owner" /></label>
      </div>
      <section class="reference-card"><header><strong>引用关系</strong><span>{{ selected.usage }}</span></header><p>配置变更将在下次脚本调用时生效（context 按触发时所选数据源 / 图空间 / Milvus / LLM / embedding 注入）。</p></section>
      <footer>
        <button v-if="!selected.isDefault" type="button" @click="setAsDefault(selected)">设为默认</button>
        <button type="button" @click="toggleItem(selected)">{{ selected.status === '停用' ? '启用配置' : '停用配置' }}</button>
        <button type="button" @click="removeConfig(selected)">删除</button>
        <button class="primary" type="button" :disabled="saving" @click="saveDetail">{{ saving ? '保存中…' : '保存修改' }}</button>
      </footer>
    </aside>

    <aside v-if="dialogOpen" class="create-dialog">
      <header><div><span>NEW CONFIGURATION</span><h2>新建{{ categories.find(item => item.key === activeCategory)?.label }}</h2></div><button type="button" @click="dialogOpen=false">×</button></header>
      <div class="dialog-form">
        <template v-if="isDataSourceCategory">
          <nav class="subkind-toggle">
            <button type="button" :class="{ active: formSubKind === 'mysql' }" @click="switchFormSubKind('mysql')">MySQL 数据源</button>
            <button type="button" :class="{ active: formSubKind === 'milvus' }" @click="switchFormSubKind('milvus')">Milvus 配置</button>
          </nav>
        </template>
        <template v-if="formKind === 'llm' || formKind === 'embedding'">
          <label class="wide"><span>配置名称 *</span><input v-model="form.name" placeholder="例如：科技文本抽取大模型" /></label>
          <label class="wide"><span>Base URL *</span><input v-model="form.baseUrl" /></label>
          <label><span>模型 *</span><input v-model="form.model" /></label>
          <label v-if="formKind === 'embedding'"><span>维度</span><input v-model.number="form.dimensions" type="number" /></label>
          <label><span>负责人</span><input v-model="form.owner" /></label>
          <label class="wide"><span>API Key</span><input v-model="form.apiKey" type="password" placeholder="明文保存到数据库，页面脱敏展示" /></label>
        </template>
        <template v-else-if="formKind === 'mysql'">
          <label class="wide"><span>配置名称 *</span><input v-model="form.name" /></label>
          <label><span>主机 *</span><input v-model="form.host" /></label>
          <label><span>端口</span><input v-model.number="form.port" type="number" /></label>
          <label><span>默认库</span><input v-model="form.defaultDatabase" /></label>
          <label><span>用户名 *</span><input v-model="form.username" /></label>
          <label><span>负责人</span><input v-model="form.owner" /></label>
          <label class="wide"><span>密码</span><input v-model="form.password" type="password" /></label>
        </template>
        <template v-else-if="formKind === 'milvus'">
          <label class="wide"><span>配置名称 *</span><input v-model="form.name" /></label>
          <label class="wide"><span>URI</span><input v-model="form.uri" placeholder="留空回退 env MILVUS_*" /></label>
          <label><span>默认库</span><input v-model="form.defaultDb" /></label>
          <label><span>负责人</span><input v-model="form.owner" /></label>
          <label class="wide"><span>Token</span><input v-model="form.token" type="password" /></label>
        </template>
        <label class="wide"><span>说明</span><textarea v-model="form.description" /></label>
        <label class="wide checkbox"><input type="checkbox" v-model="form.isDefault" /><span>设为默认（同一类别仅一条默认生效）</span></label>
      </div>
      <footer><button type="button" @click="dialogOpen=false">取消</button><button class="primary" type="button" :disabled="!form.name || saving" @click="saveConfig">{{ saving ? '保存中…' : '保存' }}</button></footer>
    </aside>
  </div>
</template>

<style scoped>
.configuration-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;color:#17233b;flex-direction:column}.page-header{display:flex;flex:0 0 auto;align-items:flex-end;justify-content:space-between;margin-bottom:12px}.page-header span{color:#165dff;font-size:9px;letter-spacing:.12em}.page-header h1{margin:3px 0 0;font-size:22px}.page-header p{margin:4px 0 0;color:#66758f;font-size:11px}.primary{border-color:#165dff!important;background:#165dff!important;color:#fff!important}.page-header button{height:34px;padding:0 14px;border:0;border-radius:6px;cursor:pointer}.summary-grid{display:grid;flex:0 0 auto;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}.summary-grid article{display:flex;align-items:center;gap:11px;padding:10px 13px;border:1px solid #bdd7ff;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}.summary-grid article>i{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;font-style:normal;font-weight:700}.summary-grid .blue{background:#eaf2ff;color:#165dff}.summary-grid .green{background:#dcfae6;color:#067647}.summary-grid .orange{background:#fff3d8;color:#b54708}.summary-grid .purple{background:#f4f3ff;color:#5925dc}.summary-grid article>div{display:grid;grid-template-columns:1fr auto;flex:1;gap:2px}.summary-grid span,.summary-grid small{color:#71809a;font-size:9px}.summary-grid strong{grid-row:1/3;grid-column:2;font-size:20px}.config-workbench{display:grid;flex:1;min-height:0;grid-template-columns:248px minmax(0,1fr);overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:#fff}.category-nav{display:flex;min-height:0;border-right:1px solid #dce8f8;background:#f8fbff;flex-direction:column}.category-nav>header{display:grid;gap:3px;padding:14px;border-bottom:1px solid #dce8f8}.category-nav>header strong{font-size:13px}.category-nav>header span{color:#8290a7;font-size:9px}.category-nav>button{display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:9px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #edf2f8;background:transparent;color:#344766;text-align:left;cursor:pointer}.category-nav>button.active{background:#eaf2ff;box-shadow:inset 3px 0 #165dff}.category-nav>button>i{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;background:#fff;color:#526783;font-size:9px;font-style:normal;font-weight:700}.category-nav>button.active>i{background:#165dff;color:#fff}.category-nav>button>span{display:grid;gap:3px}.category-nav>button strong{font-size:11px}.category-nav>button small{color:#8290a7;font-size:8px}.category-nav>button em{min-width:20px;padding:2px 6px;border-radius:99px;background:#e7eef8;color:#71809a;font-size:9px;font-style:normal;text-align:center}.category-nav>section{margin:auto 12px 12px;padding:11px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.category-nav>section b{font-size:10px}.category-nav>section p{margin:4px 0 6px;color:#71809a;font-size:9px;line-height:15px}.config-list{display:flex;min-width:0;min-height:0;flex-direction:column}.config-list>header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #dce8f8;background:#fff}.config-list>header>div{display:flex;align-items:baseline;gap:8px}.config-list h2{margin:0;font-size:15px}.config-list>header span{color:#8290a7;font-size:9px}.config-list nav{display:flex;gap:7px}.config-list input,.config-list select{height:31px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font-size:10px}.config-list input{width:210px}.table-wrap{flex:1;min-height:0;overflow:auto}.table-wrap table{width:100%;border-collapse:collapse;font-size:10px}.table-wrap thead{position:sticky;z-index:2;top:0}.table-wrap th,.table-wrap td{padding:10px 11px;border-bottom:1px solid #e7eef7;text-align:left;vertical-align:middle}.table-wrap th{background:#f2f7fd;color:#60708a;font-weight:600;white-space:nowrap}.table-wrap tbody tr{cursor:pointer}.table-wrap tbody tr:hover td{background:#f7faff}.config-name{display:flex;align-items:center;gap:9px;min-width:210px}.config-name>i{display:grid;place-items:center;flex:0 0 auto;width:29px;height:29px;border-radius:7px;background:#eaf2ff;color:#175cd3;font-size:8px;font-style:normal;font-weight:700}.config-name>span{display:grid;gap:3px}.config-name strong{font-size:11px}.config-name small,.updated{display:block;color:#8290a7;font-size:8px}.type-name{display:block;color:#40516d;font-size:10px}.table-wrap code{display:block;max-width:210px;margin-top:3px;overflow:hidden;color:#71809a;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.status{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:99px}.status>i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.is-正常{background:#dcfae6;color:#067647}.status.is-异常{background:#fee4e2;color:#b42318}.status.is-停用{background:#eef1f5;color:#667085}.link{border:0;background:transparent;color:#165dff;font-size:10px;cursor:pointer}.empty{height:100px;color:#8290a7;text-align:center!important}.mask{position:fixed;z-index:40;inset:0;border:0;background:rgba(16,36,76,.24)}.detail-drawer{position:fixed;z-index:41;top:0;right:0;display:flex;width:min(500px,90vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}.detail-drawer>header,.create-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.detail-drawer>header span,.create-dialog>header span{color:#165dff;font-size:9px}.detail-drawer h2,.create-dialog h2{margin:4px 0;font-size:18px}.detail-drawer>header p{margin:0;color:#71809a;font-size:10px}.detail-drawer>header button,.create-dialog>header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.health-card{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;gap:10px;margin:14px 16px 0;padding:12px;border:1px solid #cfe4d7;border-radius:7px;background:#fff}.health-card>i{width:9px;height:9px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12)}.health-card>i.is-异常{background:#f04438;box-shadow:0 0 0 4px rgba(240,68,56,.12)}.health-card>i.is-停用{background:#98a2b3;box-shadow:none}.health-card>div{display:grid;gap:3px}.health-card strong{font-size:11px}.health-card span{color:#71809a;font-size:9px}.health-card button{height:29px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#165dff;font-size:9px;cursor:pointer}.detail-form,.dialog-form{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:16px}.detail-form label,.dialog-form label{display:grid;gap:5px}.detail-form label span,.dialog-form label span{color:#60708a;font-size:9px}.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{box-sizing:border-box;width:100%;height:33px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font:10px inherit}.detail-form textarea,.dialog-form textarea{height:65px;padding-top:8px;resize:none}.wide{grid-column:1/-1}.reference-card{margin:0 16px;padding:12px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.reference-card header{display:flex;justify-content:space-between}.reference-card strong{font-size:10px}.reference-card span{color:#165dff;font-size:9px}.reference-card p{margin:5px 0 0;color:#71809a;font-size:9px;line-height:16px}.detail-drawer>footer,.create-dialog>footer{display:flex;justify-content:flex-end;gap:8px;margin-top:auto;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.detail-drawer>footer button,.create-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.create-dialog{position:fixed;z-index:42;top:50%;left:50%;width:min(650px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.create-dialog>footer{margin-top:0}.create-dialog button:disabled{opacity:.5;cursor:not-allowed}.default-tag{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:99px;background:#fff3d8;color:#b54708;font-size:8px;font-weight:600;font-style:normal}.checkbox{display:flex;flex-direction:row;align-items:center;gap:8px}.checkbox input{width:auto;height:14px}.checkbox span{color:#344766;font-size:10px}.subkind-toggle{grid-column:1/-1;display:flex;gap:8px;margin-bottom:4px}.subkind-toggle button{flex:1;height:32px;border:1px solid #bdd0ea;border-radius:6px;background:#fff;color:#40516d;font-size:10px;cursor:pointer}.subkind-toggle button.active{border-color:#165dff;background:#165dff;color:#fff}@media(max-width:1100px){.summary-grid{grid-template-columns:repeat(2,1fr)}.config-workbench{grid-template-columns:210px minmax(0,1fr)}}
</style>
