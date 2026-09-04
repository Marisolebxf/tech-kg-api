<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { IconSearch } from '@arco-design/web-vue/es/icon'
import {
  createLlmConfig,
  currentUserId,
  deleteLlmConfig,
  listLlmConfigs,
  setDefaultLlmConfig,
  testLlmConfig,
  updateLlmConfig,
  verifyLlmConfig,
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
  verifyEmbeddingConfig,
  type EmbeddingConfig,
} from '../../api/embeddingConfig'
import {
  bindGraphSpace,
  createGraphSpace,
  listGraphSpaceItems,
  unbindGraphSpace,
  type GraphSpaceItem,
} from '../../api/graphSpace'
import { currentUserIsAdmin } from '../../api/currentUser'
import { useToast } from '../../composables/use-toast'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'

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
  { key: '语言模型', label: '语言模型', icon: 'AI', hint: 'LLM 语言模型配置' },
  { key: '向量模型', label: '向量模型', icon: 'EM', hint: 'embedding 向量模型配置' },
  { key: 'MySQL 数据源', label: 'MySQL 数据源', icon: 'MY', hint: 'MySQL 关系库连接' },
  { key: '向量数据空间', label: '向量数据空间', icon: 'ML', hint: 'Milvus 向量数据库' },
  { key: '图数据空间', label: '图数据空间', icon: 'GS', hint: '我的图空间绑定' },
]

// 响应式跟随 auth store（profile 异步加载，一次性赋值会把 admin 恒判 false——
// 免登录部署下绑定入口/新建空间入口不渲染）
const isAdmin = computed(() => currentUserIsAdmin())
const graphSpaces = ref<GraphSpaceItem[]>([])
const spaceDialogOpen = ref(false)
const newSpaceName = ref('')
const bindTarget = ref('')
const spaceWorking = ref(false)

const items = ref<ConfigItem[]>([])
const activeCategory = ref('语言模型')
const keyword = ref('')
const statusFilter = ref<string | undefined>('全部状态')
const selected = ref<ConfigItem | null>(null)
const dialogOpen = ref(false)
const testingId = ref('')
const saving = ref(false)

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
const configFormRef = ref()
const detailFormRef = ref()
const verifying = ref(false)
const verified = ref(false)
const configFormRules = {
  name: [{ required: true, message: '请输入配置名称' }],
  baseUrl: [{ required: true, message: '请输入 Base URL' }],
  model: [{ required: true, message: '请输入模型名称' }],
  apiKey: [{ required: true, message: '请输入 API Key' }],
  host: [{ required: true, message: '请输入主机地址' }],
  username: [{ required: true, message: '请输入用户名' }],
}
const detailFormRules = configFormRules

const isModelKind = computed(() => activeCategory.value === '语言模型' || activeCategory.value === '向量模型')
const canVerifyForm = computed(() =>
  Boolean(String(form.value.baseUrl || '').trim() && String(form.value.model || '').trim() && String(form.value.apiKey || '').trim()))

// 模型配置要求"验证通过才能保存"；任何字段改动都会使已验证状态失效，需重新验证。
watch(form, () => { verified.value = false }, { deep: true })

const isGraphSpaceCategory = computed(() => activeCategory.value === '图数据空间')

const mySpaces = computed(() => graphSpaces.value.filter((item) => item.mine))
const bindableSpaces = computed(() => graphSpaces.value.filter((item) => !item.mine))

const formKind = computed<ConfigKind | null>(() => {
  switch (activeCategory.value) {
    case '语言模型':
      return 'llm'
    case '向量模型':
      return 'embedding'
    case 'MySQL 数据源':
      return 'mysql'
    case '向量数据空间':
      return 'milvus'
    default:
      return null
  }
})

const visibleItems = computed(() => items.value.filter((item) => {
  const matchCategory = item.category === activeCategory.value
  const query = keyword.value.trim().toLowerCase()
  const endpointOrUrl = item.baseUrl || item.host || item.uri || item.endpoint
  const matchKeyword = !query || `${item.name}${item.id}${item.type}${endpointOrUrl}${item.model || ''}`.toLowerCase().includes(query)
  const matchStatus = !statusFilter.value || statusFilter.value === '全部状态' || item.status === statusFilter.value
  return matchCategory && matchKeyword && matchStatus
}))

function defaultIcon(kind: ConfigKind) {
  return kind === 'llm' ? 'AI' : kind === 'embedding' ? 'EM' : kind === 'mysql' ? 'MY' : 'ML'
}

function categoryCount(key: string) {
  if (key === '图数据空间') {
    return graphSpaces.value.filter((item) => item.mine).length
  }
  return items.value.filter((i) => i.category === key).length
}

function buildUsage(kind: ConfigKind, isDefault: boolean): string {
  if (isDefault) {
    if (kind === 'llm') return '默认语言模型'
    if (kind === 'embedding') return '默认向量模型'
    return kind === 'mysql' ? '默认 MySQL 数据源' : '默认向量库'
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
    return { ...common, category: '语言模型', type: 'LLM API', endpoint: c.baseUrl, baseUrl: c.baseUrl, model: c.model, hasApiKey: c.hasApiKey, apiKeyMasked: c.apiKeyMasked }
  }
  if (kind === 'embedding') {
    const c = cfg as EmbeddingConfig
    return { ...common, category: '向量模型', type: 'Embedding API', endpoint: c.baseUrl, baseUrl: c.baseUrl, model: c.model, dimensions: c.dimensions, hasApiKey: c.hasApiKey, apiKeyMasked: c.apiKeyMasked }
  }
  if (kind === 'mysql') {
    const c = cfg as MysqlDatasource
    return { ...common, category: 'MySQL 数据源', type: 'MySQL 数据源', endpoint: `${c.host}:${c.port}`, host: c.host, port: c.port, defaultDatabase: c.defaultDatabase, username: c.username, hasPassword: c.hasPassword, passwordMasked: c.passwordMasked }
  }
  const c = cfg as MilvusConfig
  return { ...common, category: '向量数据空间', type: 'Milvus 向量库', endpoint: c.uri || '(env)', uri: c.uri, defaultDb: c.defaultDb, hasToken: c.hasToken, tokenMasked: c.tokenMasked }
}

async function loadByCategory(key: string) {
  if (key === '图数据空间') {
    await loadGraphSpaces()
    return
  }
  const others = items.value.filter((i) => i.category !== key)
  let loaded: ConfigItem[] = []
  try {
    if (key === '语言模型') {
      loaded = (await listLlmConfigs(currentUserId())).map((c) => toConfigItem('llm', c))
    } else if (key === '向量模型') {
      loaded = (await listEmbeddingConfigs(currentUserId())).map((c) => toConfigItem('embedding', c))
    } else if (key === 'MySQL 数据源') {
      loaded = (await listMysqlDatasources(currentUserId())).map((c) => toConfigItem('mysql', c))
    } else if (key === '向量数据空间') {
      loaded = (await listMilvusConfigs(currentUserId())).map((c) => toConfigItem('milvus', c))
    }
  } catch (err) {
    showToast(`加载配置失败：${(err as Error).message}`, 'warning')
  }
  items.value = [...loaded, ...others]
}

async function loadGraphSpaces() {
  try {
    graphSpaces.value = await listGraphSpaceItems()
  } catch (err) {
    showToast(`加载图空间失败：${(err as Error).message}`, 'warning')
  }
}

async function createSpace() {
  const name = newSpaceName.value.trim()
  if (!name) return
  spaceWorking.value = true
  try {
    await createGraphSpace(name)
    showToast(`图数据空间“${name}”已创建并绑定。空间建好后有秒级传播延迟，随后即可在任务触发时选择。`, 'success')
    spaceDialogOpen.value = false
    newSpaceName.value = ''
    await loadGraphSpaces()
  } catch (err) {
    showToast(`创建失败：${(err as Error).message}`, 'warning')
  } finally {
    spaceWorking.value = false
  }
}

async function bindSpace() {
  const name = bindTarget.value
  if (!name) return
  spaceWorking.value = true
  try {
    await bindGraphSpace(name)
    showToast(`图数据空间“${name}”已绑定。`)
    bindTarget.value = ''
    await loadGraphSpaces()
  } catch (err) {
    showToast(`绑定失败：${(err as Error).message}`, 'warning')
  } finally {
    spaceWorking.value = false
  }
}

async function unbindSpace(name: string) {
  if (!window.confirm(`确认解除与图数据空间“${name}”的绑定？仅解除绑定，不会删除图数据空间数据。`)) return
  try {
    await unbindGraphSpace(name)
    showToast(`已解除与“${name}”的绑定（图数据空间数据保留）。`)
    await loadGraphSpaces()
  } catch (err) {
    showToast(`解除绑定失败：${(err as Error).message}`, 'warning')
  }
}

async function switchCategory(key: string) {
  activeCategory.value = key
  selected.value = null
  // 首屏已并行加载全部分类，点击切换不再重拉；仅当本地没有该分类数据（首屏加载失败）时补拉。
  // 增删改后的刷新由各 mutation 内的 loadByCategory 覆盖。
  if (key === '图数据空间') {
    if (!graphSpaces.value.length) await loadGraphSpaces()
    return
  }
  if (!items.value.some((item) => item.category === key)) await loadByCategory(key)
}

function emptyForm(kind: ConfigKind): ConfigForm {
  if (kind === 'llm') {
    return { name: '', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'glm-4.7-flash', apiKey: '', description: '', isDefault: false }
  }
  if (kind === 'embedding') {
    return { name: '', baseUrl: 'https://open.bigmodel.cn/api/paas/v4', model: 'embedding-3', dimensions: 1024, apiKey: '', description: '', isDefault: false }
  }
  if (kind === 'mysql') {
    return { name: '', host: '127.0.0.1', port: 3306, defaultDatabase: '', username: 'root', password: '', owner: '平台运维组', description: '', isDefault: false }
  }
  return { name: '', uri: '', token: '', defaultDb: 'default', owner: '平台运维组', description: '', isDefault: false }
}

function openCreate() {
  if (isGraphSpaceCategory.value) {
    newSpaceName.value = ''
    spaceDialogOpen.value = true
    return
  }
  form.value = emptyForm(formKind.value || 'llm')
  verified.value = false
  dialogOpen.value = true
}

async function verifyForm() {
  const kind = formKind.value
  if (kind !== 'llm' && kind !== 'embedding') return
  const validationErrors = await configFormRef.value?.validate()
  if (validationErrors) return
  verifying.value = true
  try {
    const payload = {
      baseUrl: String(form.value.baseUrl || '').trim(),
      model: String(form.value.model || '').trim(),
      apiKey: String(form.value.apiKey || '').trim(),
    }
    const result = kind === 'llm'
      ? await verifyLlmConfig(payload, currentUserId())
      : await verifyEmbeddingConfig(payload, currentUserId())
    if (result.ok) {
      verified.value = true
      showToast(`验证成功，延迟 ${result.latencyMs ?? '-'} ms，可以保存。`, 'success')
    } else {
      verified.value = false
      showToast(`验证失败：${result.error ?? '未知错误'}`, 'warning')
    }
  } catch (err) {
    verified.value = false
    showToast(`验证请求失败：${(err as Error).message}`, 'warning')
  } finally {
    verifying.value = false
  }
}

async function saveConfig() {
  const validationErrors = await configFormRef.value?.validate()
  if (validationErrors) return
  const kind = formKind.value
  if (!kind) return
  if ((kind === 'llm' || kind === 'embedding') && !verified.value) return
  if (!String(form.value.name).trim()) return
  saving.value = true
  try {
    if (kind === 'llm') {
      await createLlmConfig({
        name: String(form.value.name).trim(),
        baseUrl: String(form.value.baseUrl).trim(),
        model: String(form.value.model).trim(),
        apiKey: String(form.value.apiKey || '').trim(),
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
  const validationErrors = await detailFormRef.value?.validate()
  if (validationErrors) return
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

/** 首屏并行加载全部四类，让分类计数固定展示（loadByCategory 是替换式合并，并发会互相覆盖）。 */
async function loadAllCategories() {
  const [llm, embedding, mysql, milvus] = await Promise.allSettled([
    listLlmConfigs(currentUserId()),
    listEmbeddingConfigs(currentUserId()),
    listMysqlDatasources(currentUserId()),
    listMilvusConfigs(currentUserId()),
  ])
  const loaded: ConfigItem[] = []
  const failed: string[] = []
  if (llm.status === 'fulfilled') loaded.push(...llm.value.map((c) => toConfigItem('llm', c)))
  else failed.push('语言模型')
  if (embedding.status === 'fulfilled') loaded.push(...embedding.value.map((c) => toConfigItem('embedding', c)))
  else failed.push('向量模型')
  if (mysql.status === 'fulfilled') loaded.push(...mysql.value.map((c) => toConfigItem('mysql', c)))
  else failed.push('MySQL 数据源')
  if (milvus.status === 'fulfilled') loaded.push(...milvus.value.map((c) => toConfigItem('milvus', c)))
  else failed.push('向量数据空间')
  if (failed.length) showToast(`加载${[...new Set(failed)].join('、')}配置失败`, 'warning')
  items.value = loaded
}

onMounted(() => {
  void loadAllCategories()
  void loadGraphSpaces()
})
</script>

<template>
  <div class="configuration-page">
    <header class="page-header">
      <div><span>PLATFORM CONFIGURATION</span><h1>配置管理</h1><p>统一管理 Pipeline 运行依赖的语言模型、向量模型、MySQL 数据源、向量数据空间与图数据空间。配置项真正驱动抽取脚本的 context 注入。</p></div>
    </header>

    <section class="config-workbench">
      <aside class="category-nav">
        <header><strong>配置分类</strong><span>按能力域管理</span></header>
        <button v-for="category in categories" :key="category.key" type="button" :class="{ active: activeCategory === category.key }" :title="`${category.label}：${category.hint}`" @click="switchCategory(category.key)">
          <i>{{ category.icon }}</i><span><strong>{{ category.label }}</strong><small>{{ category.hint }}</small></span><em>{{ categoryCount(category.key) }}</em>
        </button>
      </aside>

      <main class="config-list">
        <header><div><h2>{{ categories.find(item => item.key === activeCategory)?.label }}</h2><span>{{ isGraphSpaceCategory ? `${mySpaces.length} 个已绑定空间` : `${visibleItems.length} 项配置` }}</span></div><nav v-if="!isGraphSpaceCategory"><a-input v-model="keyword" class="config-search-input" :max-length="SEARCH_KEYWORD_MAX_LENGTH" aria-label="搜索名称、标识或地址" placeholder="搜索名称、标识或地址"><template #prefix><IconSearch /></template></a-input><a-select v-model="statusFilter" allow-clear placeholder="全部状态"><a-option value="全部状态">全部状态</a-option><a-option value="正常">正常</a-option><a-option value="异常">异常</a-option><a-option value="停用">停用</a-option></a-select><button class="primary create-entry" type="button" @click="openCreate">＋ 新建配置</button></nav><nav v-else class="bind-nav"><a-select v-if="isAdmin && bindableSpaces.length" v-model="bindTarget" placeholder="绑定已有图数据空间" allow-clear><a-option v-for="space in bindableSpaces" :key="space.name" :value="space.name">{{ space.name }}</a-option></a-select><button v-if="isAdmin && bindableSpaces.length" type="button" :disabled="spaceWorking" @click="bindSpace">绑定</button><button class="primary" type="button" @click="spaceDialogOpen = true">＋ 新建图数据空间</button></nav></header>
        <div v-if="isGraphSpaceCategory" class="table-wrap space-table">
          <table>
            <thead><tr><th>图数据空间</th><th>绑定状态</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="space in mySpaces" :key="space.name">
                <td><div class="config-name"><i>GS</i><span><strong>{{ space.name }}</strong><small>NebulaGraph 图空间</small></span></div></td>
                <td><span class="status is-正常"><i />已绑定</span></td>
                <td><button class="link" type="button" @click="unbindSpace(space.name)">解除绑定</button></td>
              </tr>
              <tr v-if="!mySpaces.length"><td class="empty" colspan="3">还没有绑定的图数据空间，点击右上角“新建图数据空间”创建一个</td></tr>
            </tbody>
          </table>
          <p class="space-hint">新建图数据空间会真实执行 CREATE SPACE（创建后有秒级传播延迟）；解除绑定只取消关联，不会删除图数据空间数据。</p>
        </div>
        <div v-else class="table-wrap">
          <table>
            <thead><tr><th>配置名称</th><th>类型 / 地址</th><th>状态</th><th>引用情况</th><th>更新时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in visibleItems" :key="item.id" @click="selected=item">
                <td><div class="config-name"><i>{{ defaultIcon(item.kind) }}</i><span><strong>{{ item.name }}<b v-if="item.isDefault" class="default-tag">默认</b></strong><small>{{ item.id }} · {{ item.description }}</small></span></div></td>
                <td><strong class="type-name">{{ item.type }}<template v-if="item.model"> · {{ item.model }}</template></strong><code>{{ item.baseUrl || item.host && `${item.host}:${item.port}` || item.uri || item.endpoint }}</code></td>
                <td><span class="status" :class="`is-${item.status}`"><i />{{ item.status }}</span></td>
                <td>{{ item.usage }}</td>
                <td><span>{{ item.owner }}</span><small class="updated">{{ item.updatedAt }}</small></td>
                <td>
                  <div class="row-actions">
                    <button class="link" type="button" @click.stop="selected=item">管理</button>
                    <button class="link" type="button" @click.stop="toggleItem(item)">{{ item.status === '停用' ? '启用' : '停用' }}</button>
                    <button class="link danger" type="button" @click.stop="removeConfig(item)">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!visibleItems.length"><td class="empty" colspan="6">没有符合条件的配置</td></tr>
            </tbody>
          </table>
        </div>
      </main>
    </section>

    <Teleport to="body">
      <button v-if="selected" class="mask" type="button" aria-label="关闭" @click="selected=null" />
      <aside v-if="selected" class="detail-drawer">
      <header><div><span>{{ selected.id }}</span><h2>{{ selected.name }}<b v-if="selected.isDefault" class="default-tag">默认</b></h2></div><button type="button" @click="selected=null">×</button></header>
      <div class="detail-drawer-body">
        <section class="health-card"><i :class="`is-${selected.status}`" /><div><strong>{{ selected.status === '正常' ? '配置可用' : selected.status === '异常' ? '连接存在异常' : '配置已停用' }}</strong><span>后端真实探活</span></div><button type="button" :disabled="testingId === selected.id" @click="testConnection(selected)">{{ testingId === selected.id ? '测试中…' : '测试连接' }}</button></section>
        <a-form ref="detailFormRef" :model="selected" :rules="detailFormRules" class="detail-form" layout="vertical">
          <a-form-item field="name" label="配置名称" required><input aria-label="name" v-model="selected.name" /></a-form-item>
          <a-form-item label="服务类型"><input aria-label="input-field" :value="selected.type" readonly /></a-form-item>
          <template v-if="selected.kind === 'llm' || selected.kind === 'embedding'">
            <a-form-item class="wide" field="baseUrl" label="Base URL" required><input aria-label="baseUrl" v-model="selected.baseUrl" /></a-form-item>
            <a-form-item field="model" label="模型" required><input aria-label="model" v-model="selected.model" /></a-form-item>
            <a-form-item v-if="selected.kind === 'embedding'" label="维度"><input aria-label="number-input" v-model.number="selected.dimensions" type="number" /></a-form-item>
            <a-form-item label="访问凭据"><input aria-label="input-field" :value="selected.apiKeyMasked || (selected.hasApiKey ? '••••••••' : '未设置')" readonly /></a-form-item>
            <a-form-item class="wide" label="更新 API Key（留空保留原值）"><input aria-label="输入新 Key 覆盖原值" v-model="selected.apiKey" type="password" placeholder="输入新 Key 覆盖原值" /></a-form-item>
          </template>
          <template v-else-if="selected.kind === 'mysql'">
            <a-form-item field="host" label="主机" required><input aria-label="host" v-model="selected.host" /></a-form-item>
            <a-form-item label="端口"><input aria-label="number-input" v-model.number="selected.port" type="number" /></a-form-item>
            <a-form-item label="默认库"><input aria-label="defaultDatabase" v-model="selected.defaultDatabase" /></a-form-item>
            <a-form-item field="username" label="用户名" required><input aria-label="username" v-model="selected.username" /></a-form-item>
            <a-form-item label="访问凭据"><input aria-label="input-field" :value="selected.passwordMasked || (selected.hasPassword ? '••••••••' : '未设置')" readonly /></a-form-item>
            <a-form-item class="wide" label="更新密码（留空保留原值）"><input aria-label="输入新密码覆盖原值" v-model="selected.password" type="password" placeholder="输入新密码覆盖原值" /></a-form-item>
          </template>
          <template v-else>
            <a-form-item class="wide" label="URI"><input aria-label="留空回退 env MILVUS_*" v-model="selected.uri" placeholder="留空回退 env MILVUS_*" /></a-form-item>
            <a-form-item label="默认库"><input aria-label="defaultDb" v-model="selected.defaultDb" /></a-form-item>
            <a-form-item label="访问凭据"><input aria-label="input-field" :value="selected.tokenMasked || (selected.hasToken ? '••••••••' : '未设置')" readonly /></a-form-item>
            <a-form-item class="wide" label="更新 Token（留空保留原值）"><input aria-label="输入新 Token 覆盖原值" v-model="selected.token" type="password" placeholder="输入新 Token 覆盖原值" /></a-form-item>
          </template>
          <a-form-item class="wide" label="配置说明"><a-textarea v-model="selected.description" /></a-form-item>
        </a-form>
        <section class="reference-card"><header><strong>引用关系</strong><span>{{ selected.usage }}</span></header><p>配置变更将在下次脚本调用时生效（context 按触发时所选数据源 / 图空间 / Milvus / LLM / embedding 注入）。</p></section>
      </div>
      <footer>
        <button v-if="!selected.isDefault" type="button" @click="setAsDefault(selected)">设为默认</button>
        <button type="button" @click="toggleItem(selected)">{{ selected.status === '停用' ? '启用配置' : '停用配置' }}</button>
        <button type="button" @click="removeConfig(selected)">删除</button>
        <button class="primary" type="button" :disabled="saving" @click="saveDetail">{{ saving ? '保存中…' : '保存修改' }}</button>
      </footer>
      </aside>
    </Teleport>

    <Teleport to="body">
      <button v-if="spaceDialogOpen" class="mask create-dialog-mask" type="button" aria-label="关闭新建图空间弹窗" @click="spaceDialogOpen=false" />
      <aside v-if="spaceDialogOpen" class="create-dialog space-dialog">
        <header><div><h2>新建图数据空间</h2></div><button type="button" @click="spaceDialogOpen=false">×</button></header>
        <a-form class="dialog-form" layout="vertical" :model="{}">
          <a-form-item class="wide" label="图数据空间名称" required>
            <input aria-label="仅字母、数字、下划线，以字母或下划线开头" v-model="newSpaceName" placeholder="仅字母、数字、下划线，以字母或下划线开头" />
          </a-form-item>
          <p class="space-dialog-hint">将真实执行 CREATE SPACE 并自动绑定到你的账号；空间创建后有秒级传播延迟。</p>
        </a-form>
        <footer><button type="button" @click="spaceDialogOpen=false">取消</button><button class="primary" type="button" :disabled="!newSpaceName.trim() || spaceWorking" @click="createSpace">{{ spaceWorking ? '创建中…' : '创建' }}</button></footer>
      </aside>
      <button v-if="dialogOpen" class="mask create-dialog-mask" type="button" aria-label="关闭新建配置弹窗" @click="dialogOpen=false" />
      <aside v-if="dialogOpen" class="create-dialog config-create-dialog">
      <header><div><span>NEW CONFIGURATION</span><h2>新建{{ categories.find(item => item.key === activeCategory)?.label }}</h2></div><button type="button" @click="dialogOpen=false">×</button></header>
      <a-form ref="configFormRef" :model="form" :rules="configFormRules" class="dialog-form config-create-form" layout="vertical">
        <template v-if="formKind === 'llm' || formKind === 'embedding'">
          <a-form-item class="wide" field="name" label="配置名称" required><input aria-label="例如：科技文本抽取大模型" v-model="form.name" placeholder="例如：科技文本抽取大模型" /></a-form-item>
          <a-form-item class="wide" field="baseUrl" label="Base URL" required><input aria-label="baseUrl" v-model="form.baseUrl" /></a-form-item>
          <a-form-item field="model" label="模型" required><input aria-label="model" v-model="form.model" /></a-form-item>
          <a-form-item v-if="formKind === 'embedding'" field="dimensions" label="维度"><input aria-label="number-input" v-model.number="form.dimensions" type="number" /></a-form-item>
          <a-form-item class="wide" field="apiKey" label="API Key" required><input aria-label="必填；验证通过后才能保存，明文入库脱敏展示" v-model="form.apiKey" type="password" placeholder="必填；验证通过后才能保存，明文入库脱敏展示" /></a-form-item>
        </template>
        <template v-else-if="formKind === 'mysql'">
          <a-form-item class="wide" field="name" label="配置名称" required><input aria-label="name" v-model="form.name" /></a-form-item>
          <a-form-item field="host" label="主机" required><input aria-label="host" v-model="form.host" /></a-form-item>
          <a-form-item label="端口"><input aria-label="number-input" v-model.number="form.port" type="number" /></a-form-item>
          <a-form-item label="默认库"><input aria-label="defaultDatabase" v-model="form.defaultDatabase" /></a-form-item>
          <a-form-item field="username" label="用户名" required><input aria-label="username" v-model="form.username" /></a-form-item>
          <a-form-item class="wide" label="密码"><input aria-label="password" v-model="form.password" type="password" /></a-form-item>
        </template>
        <template v-else-if="formKind === 'milvus'">
          <a-form-item class="wide" field="name" label="配置名称" required><input aria-label="name" v-model="form.name" /></a-form-item>
          <a-form-item class="wide" label="URI"><input aria-label="留空回退 env MILVUS_*" v-model="form.uri" placeholder="留空回退 env MILVUS_*" /></a-form-item>
          <a-form-item label="默认库"><input aria-label="defaultDb" v-model="form.defaultDb" /></a-form-item>
          <a-form-item class="wide" label="Token"><input aria-label="token" v-model="form.token" type="password" /></a-form-item>
        </template>
        <a-form-item class="wide" label="说明"><a-textarea v-model="form.description" :max-length="200" show-word-limit :auto-size="{ minRows: 3, maxRows: 5 }" /></a-form-item>
        <a-form-item class="wide" field="isDefault"><a-checkbox v-model="form.isDefault" class="default-config-checkbox">设为默认（同一类别仅一条默认生效）</a-checkbox></a-form-item>
      </a-form>
      <footer>
        <button type="button" @click="dialogOpen=false">取消</button>
        <template v-if="isModelKind">
          <button type="button" :disabled="verifying || !canVerifyForm" @click="verifyForm">{{ verifying ? '验证中…' : '验证连接' }}</button>
          <button class="primary" type="button" :disabled="!verified || saving" @click="saveConfig">{{ saving ? '保存中…' : verified ? '保存' : '验证通过后可保存' }}</button>
        </template>
        <button v-else class="primary" type="button" :disabled="!form.name || saving" @click="saveConfig">{{ saving ? '保存中…' : '保存' }}</button>
      </footer>
      </aside>
    </Teleport>
  </div>
</template>

<style scoped>
.configuration-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;color:#17233b;flex-direction:column}.page-header{display:flex;flex:0 0 auto;align-items:flex-end;justify-content:space-between;margin-bottom:12px}.page-header span{color:#165dff;font-size:9px;letter-spacing:.12em}.page-header h1{margin:3px 0 0;font-size:22px}.page-header p{margin:4px 0 0;color:#66758f;font-size:11px}.primary{border-color:#165dff!important;background:#165dff!important;color:#fff!important}.config-workbench{display:grid;flex:1;min-height:0;grid-template-columns:248px minmax(0,1fr);overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:#fff}.category-nav{display:flex;min-height:0;border-right:1px solid #dce8f8;background:#f8fbff;flex-direction:column}.category-nav>header{display:grid;gap:3px;padding:14px;border-bottom:1px solid #dce8f8}.category-nav>header strong{font-size:13px}.category-nav>header span{color:#8290a7;font-size:9px}.category-nav>button{display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:9px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #edf2f8;background:transparent;color:#344766;text-align:left;cursor:pointer}.category-nav>button.active{background:#eaf2ff;box-shadow:inset 3px 0 #165dff}.category-nav>button>i{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;background:#fff;color:#526783;font-size:9px;font-style:normal;font-weight:700}.category-nav>button.active>i{background:#165dff;color:#fff}.category-nav>button>span{display:grid;gap:3px}.category-nav>button strong{font-size:11px}.category-nav>button small{color:#8290a7;font-size:8px}.category-nav>button em{min-width:20px;padding:2px 6px;border-radius:99px;background:#e7eef8;color:#71809a;font-size:9px;font-style:normal;text-align:center}.config-list{display:flex;min-width:0;min-height:0;flex-direction:column}.config-list>header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #dce8f8;background:#fff}.config-list>header>div{display:flex;align-items:baseline;gap:8px}.config-list h2{margin:0;font-size:15px}.config-list>header span{color:#8290a7;font-size:9px}.config-list nav{display:flex;gap:7px;align-items:center}.config-list nav button{height:31px;padding:0 12px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;font-size:10px;cursor:pointer}.config-list input,.config-list select{height:31px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font-size:10px}.config-list input{width:210px}.table-wrap{flex:1;min-height:0;overflow:auto}.table-wrap table{width:100%;border-collapse:collapse;font-size:10px}.table-wrap thead{position:sticky;z-index:2;top:0}.table-wrap th,.table-wrap td{padding:10px 11px;border-bottom:1px solid #e7eef7;text-align:left;vertical-align:middle}.table-wrap th{background:#f2f7fd;color:#60708a;font-weight:600;white-space:nowrap}.table-wrap tbody tr{cursor:pointer}.table-wrap tbody tr:hover td{background:#f7faff}.config-name{display:flex;align-items:center;gap:9px;min-width:210px}.config-name>i{display:grid;place-items:center;flex:0 0 auto;width:29px;height:29px;border-radius:7px;background:#eaf2ff;color:#175cd3;font-size:8px;font-style:normal;font-weight:700}.config-name>span{display:grid;gap:3px}.config-name strong{font-size:11px}.config-name small,.updated{display:block;color:#8290a7;font-size:8px}.type-name{display:block;color:#40516d;font-size:10px}.table-wrap code{display:block;max-width:210px;margin-top:3px;overflow:hidden;color:#71809a;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.status{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:99px}.status>i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.is-正常{background:#dcfae6;color:#067647}.status.is-异常{background:#fee4e2;color:#b42318}.status.is-停用{background:#eef1f5;color:#667085}.link{border:0;background:transparent;color:#165dff;font-size:10px;cursor:pointer}.empty{height:100px;color:#8290a7;text-align:center!important}.mask{position:fixed;z-index:40;inset:0;border:0;background:rgba(16,36,76,.24)}.detail-drawer{position:fixed;z-index:41;top:0;right:0;display:flex;width:min(500px,90vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}.detail-drawer>header,.create-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.detail-drawer>header span,.create-dialog>header span{color:#165dff;font-size:9px}.detail-drawer h2,.create-dialog h2{margin:4px 0;font-size:18px}.detail-drawer>header button,.create-dialog>header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.health-card{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;gap:10px;margin:14px 16px 0;padding:12px;border:1px solid #cfe4d7;border-radius:7px;background:#fff}.health-card>i{width:9px;height:9px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12)}.health-card>i.is-异常{background:#f04438;box-shadow:0 0 0 4px rgba(240,68,56,.12)}.health-card>i.is-停用{background:#98a2b3;box-shadow:none}.health-card>div{display:grid;gap:3px}.health-card strong{font-size:11px}.health-card span{color:#71809a;font-size:9px}.health-card button{height:29px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#165dff;font-size:9px;cursor:pointer}.detail-form,.dialog-form{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:16px}.detail-form label,.dialog-form label{display:grid;gap:5px}.detail-form label span,.dialog-form label span{color:#60708a;font-size:9px}.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{box-sizing:border-box;width:100%;height:33px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font:10px inherit}.detail-form textarea,.dialog-form textarea{height:65px;padding-top:8px;resize:none}.wide{grid-column:1/-1}.reference-card{margin:0 16px;padding:12px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.reference-card header{display:flex;justify-content:space-between}.reference-card strong{font-size:10px}.reference-card span{color:#165dff;font-size:9px}.reference-card p{margin:5px 0 0;color:#71809a;font-size:9px;line-height:16px}.detail-drawer>footer,.create-dialog>footer{display:flex;justify-content:flex-end;gap:8px;margin-top:auto;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.detail-drawer>footer button,.create-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.create-dialog{position:fixed;z-index:42;top:50%;left:50%;width:min(650px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.create-dialog>footer{margin-top:0}.create-dialog button:disabled{opacity:.5;cursor:not-allowed}.default-tag{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:99px;background:#fff3d8;color:#b54708;font-size:8px;font-weight:600;font-style:normal}.checkbox{display:flex;flex-direction:row;align-items:center;gap:8px}.checkbox input{width:auto;height:14px}.checkbox span{color:#344766;font-size:10px}@media(max-width:1100px){.config-workbench{grid-template-columns:210px minmax(0,1fr)}}
</style>
<style scoped>
/* DESIGN_RULES: configuration management page contract. */
.configuration-page{padding:0;color:#1d2129}.page-header{align-items:center;margin-bottom:16px}.page-header>div{display:none}.page-header button{height:32px;margin-right:auto;margin-left:0;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px}
.config-workbench{grid-template-columns:240px minmax(0,1fr);border-color:#e5e6eb;border-radius:6px}.category-nav{border-color:#e5e6eb;background:#f7f8fa}
.category-nav>header{gap:4px;padding:16px}.category-nav>header strong{font-size:16px;line-height:24px}.category-nav>header span{font-size:12px;line-height:20px}
.category-nav>button{box-sizing:border-box;grid-template-columns:20px minmax(0,1fr) auto;gap:8px;width:calc(100% - 16px);height:56px;min-height:56px;margin-right:8px;margin-left:8px;padding:4px 16px;border:1px solid transparent;border-radius:4px;font-size:14px;line-height:22px}.category-nav>header+button{margin-top:4px}.category-nav>button+button{margin-top:4px}.category-nav>button.active{border-color:#fff;background:#e8f3ff;box-shadow:none;color:#165dff;font-weight:500}
.category-nav>button>i{width:20px;height:20px;border-radius:4px;font-size:12px}.category-nav>button>span{display:grid;min-width:0;gap:4px}.category-nav>button strong{display:block;overflow:hidden;font-size:14px;line-height:22px;text-overflow:ellipsis;white-space:nowrap}.category-nav>button small{display:block;overflow:hidden;color:#86909c;font-size:12px;line-height:20px;font-weight:400;text-overflow:ellipsis;white-space:nowrap}.category-nav>button em{padding:0;border-radius:0;background:transparent;font-size:12px;line-height:20px}
.config-list>header{min-height:56px;box-sizing:border-box;gap:16px;padding:8px 16px}.config-list h2{font-size:16px;line-height:24px;font-weight:600}.config-list>header span{font-size:12px;line-height:20px}.config-list nav{gap:16px}
.config-list input,.config-list select{height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px}
.table-wrap table{font-size:14px;line-height:22px}.table-wrap th,.table-wrap td{height:40px;padding:0 16px}.table-wrap th{background:#f7f8fa;color:#1d2129;font-weight:500}.config-name{gap:8px}.config-name>i{width:28px;height:28px;border-radius:4px;font-size:12px}.config-name strong,.type-name,.link{font-size:14px;line-height:22px}.config-name small,.updated,.table-wrap code{font-size:12px;line-height:20px}
.status{gap:6px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px;white-space:nowrap}.status.is-正常,.status.is-异常,.status.is-停用{background:transparent}
/* 行内操作列：管理/停用/删除 并排，删除用警示红 */
.row-actions{display:flex;gap:12px;align-items:center;white-space:nowrap}.row-actions .link{padding:0;height:auto}.link.danger{color:#f53f3f}
/* 窄视口下禁止压扁表格列（否则中文逐字换行"竖排"）：列内容不足时改为横向滚动 */
.table-wrap:not(.space-table) table{min-width:1020px}
.detail-drawer{width:min(640px,calc(100vw - 48px));background:#fff}.create-dialog{width:min(640px,calc(100vw - 48px));border-radius:8px;background:#fff}
.create-dialog>header{height:56px;box-sizing:border-box;padding:8px 24px}.detail-drawer>header{min-height:56px;height:auto;box-sizing:border-box;padding:8px 24px}.detail-drawer>header span,.create-dialog>header span{font-size:12px;line-height:20px}.detail-drawer h2,.create-dialog h2{font-size:16px;line-height:24px}
.detail-form,.dialog-form{gap:16px;padding:24px}.detail-form label,.dialog-form label{gap:8px}.detail-form label span,.dialog-form label span,.checkbox span{font-size:14px;line-height:22px}
.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px;font:14px/22px inherit}.detail-form textarea,.dialog-form textarea{height:72px;padding:8px 12px}
.reference-card{margin:0 24px;padding:16px;border-radius:6px}.reference-card strong{font-size:14px;line-height:22px}.reference-card span,.reference-card p{font-size:12px;line-height:20px}
.detail-drawer>footer,.create-dialog>footer{height:64px;box-sizing:border-box;gap:16px;padding:0 24px}.detail-drawer>footer button,.create-dialog>footer button{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px}
.default-tag{border-radius:4px;font-size:12px;line-height:20px}
.config-search-input.arco-input-wrapper{box-sizing:border-box;width:180px;min-width:180px;max-width:180px;height:32px;min-height:32px;padding:0 12px;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:0 0 180px}
.config-search-input.arco-input-wrapper:hover{border-color:#4080ff!important;background:#fff!important}
.config-search-input.arco-input-wrapper:focus-within,.config-search-input.arco-input-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.config-search-input.arco-input-wrapper :deep(.arco-input-prefix){padding-right:8px;color:#4e5969}.config-search-input.arco-input-focus :deep(.arco-input-prefix){color:#165dff}
.config-search-input.arco-input-wrapper :deep(.arco-input-prefix svg){width:16px;height:16px;font-size:16px}
.config-search-input.arco-input-wrapper :deep(.arco-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:none!important}
/* Isolate the status Arco Select from native search-input styles. */
/* 列表头操作按钮（新建配置/绑定）：与输入框同规格，禁止换行与压缩导致文字溢出 */
.config-list nav button{height:32px;padding:0 16px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px;white-space:nowrap;flex-shrink:0}
.config-list nav :deep(.arco-select){width:140px;min-width:140px;flex-shrink:0}
/* 注意：Arco select 根节点同时挂 arco-select 与 arco-select-view，两条规则同特异性，
   这里绝不能再写 width:100%，否则会覆盖上一条的 width:140px，把新建按钮挤出视口。 */
.config-list nav :deep(.arco-select-view){box-sizing:border-box;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff}
.config-list nav :deep(.arco-select-view-input){height:100%!important;min-height:0!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important}
.config-list nav :deep(.arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;pointer-events:none!important}
.config-list nav :deep(.arco-select-view-value){min-width:0;line-height:30px}
@media(max-width:1024px){.config-workbench{grid-template-columns:84px minmax(0,1fr)}.category-nav>header span,.category-nav>button span,.category-nav>button em{display:none}.category-nav>button{grid-template-columns:20px;width:52px;height:40px;min-height:40px;margin-right:auto;margin-left:auto;justify-content:center;padding:0}}
.dialog-form :deep(.arco-form-item){margin-bottom:0}.dialog-form :deep(.arco-form-item-layout-vertical>.arco-form-item-label-col){margin-bottom:8px}
.dialog-form .default-config-checkbox{display:inline-flex!important;flex-direction:row!important;align-items:center!important;justify-content:flex-start;gap:0!important;white-space:nowrap}
.config-create-form input:not([type="checkbox"]){box-sizing:border-box;width:100%;height:32px;padding:0 12px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;color:#1d2129;font-family:inherit;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0;outline:none;box-shadow:none;transition:border-color .1s ease,box-shadow .1s ease}
.config-create-form input:not([type="checkbox"]):hover{border-color:#4080ff}.config-create-form input:not([type="checkbox"]):focus,.config-create-form input:not([type="checkbox"]):focus-visible{border-color:#165dff;outline:none;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.config-create-form :deep(.arco-textarea-wrapper){box-sizing:border-box;width:100%;height:auto;min-height:80px;max-height:none;border:1px solid #e5e6eb;border-radius:4px;background:#fff!important;box-shadow:none;transition:border-color .1s ease,box-shadow .1s ease}.config-create-form :deep(.arco-textarea-wrapper:hover){border-color:#4080ff}.config-create-form :deep(.arco-textarea-wrapper.arco-textarea-focus){border-color:#165dff;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.config-create-form :deep(textarea.arco-textarea){box-sizing:border-box;width:100%;height:auto;min-height:78px;padding:8px 12px 28px;background:#fff!important;color:#1d2129;font-family:inherit;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0;resize:vertical;overflow-y:auto}.config-create-form :deep(.arco-textarea-word-limit){right:12px;bottom:6px;color:#86909c;font-size:12px;line-height:20px;font-weight:400;letter-spacing:0}
.create-dialog>header{align-items:center;padding:0 24px}.create-dialog>header>div{display:flex;height:24px;align-items:center}.create-dialog>header span{display:none}.create-dialog h2{margin:0;font-size:16px;line-height:24px}
.config-create-dialog>header>button{display:grid;width:32px;height:32px;padding:0;border:0;background:transparent;color:#4e5969;font-size:20px;line-height:1;place-items:center}.config-create-dialog>header>button:hover{background:transparent;color:#165dff}.config-create-dialog>header>button:focus-visible{background:transparent;outline:2px solid rgba(22,93,255,.16);outline-offset:2px}
.create-dialog>footer{align-items:center;padding:16px 24px}
.create-dialog-mask{z-index:49;background:rgba(16,38,76,.42);backdrop-filter:blur(2px);cursor:pointer}.create-dialog{z-index:50}
/* 详情抽屉：中间内容区可滚动，footer 钉底（表单超一屏时原来会溢出不可滚） */
/* 抽屉三段式布局：header/footer 钉住、body 独占剩余空间滚动。
   此前 body 用 flex-basis:auto（内容高），header 又被 padding 撑到 ~120px，
   三段总高超出 100vh → footer（保存修改/设为默认/停用/删除）被挤出视口外，
   表现为"没有保存按钮/没有设为默认"。basis:0 强制 body 只分剩余空间。 */
/* 抽屉与遮罩已 Teleport 到 body：留在页面内时 fixed 定位会被 .app-stage 的
   backdrop-filter 接管成包含块，抽屉只钉在页面卡片区域（顶部导航遮不住、
   底部留缝），几何随外层布局漂移。Teleport 后 fixed 直接相对视口钉满全高 */
.detail-drawer{display:flex;flex-direction:column;top:0;bottom:0;height:auto;overflow:hidden}
.detail-drawer>header{flex:0 0 auto;box-sizing:border-box}
.detail-drawer-body{flex:1 1 0;min-height:0;overflow-y:auto;padding-bottom:32px;box-sizing:border-box}
.detail-drawer-body .detail-form{padding-bottom:0}
.detail-drawer>footer{flex:0 0 auto;margin-top:0}
/* 新建弹窗：限高 + 表单区内部滚动（原来 overflow:hidden 直接裁掉超高表单） */
.create-dialog{display:flex;max-height:min(88vh,760px);flex-direction:column}
.create-dialog .dialog-form{flex:1 1 auto;min-height:0;overflow:auto}
.create-dialog>footer{margin-top:auto}
/* 图空间分类 */
.bind-nav{display:flex;gap:8px;align-items:center}.bind-nav :deep(.arco-select){width:200px;min-width:200px}.bind-nav button{height:32px;padding:0 16px;border:1px solid #bdd0ea;border-radius:4px;font-size:14px;cursor:pointer}
.space-hint{margin:12px 16px;color:#86909c;font-size:12px;line-height:20px}
.space-dialog-hint{grid-column:1/-1;margin:0;color:#86909c;font-size:12px;line-height:20px}
</style>
<style>
/* The wrapper is the only visible shell; global native-input rules must not restyle Arco's inner field. */
.app-workspace .configuration-page .config-list .config-search-input.arco-input-wrapper input.arco-input{box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .configuration-page .config-list .config-search-input.arco-input-wrapper input.arco-input:focus{border:0!important;background:transparent!important;box-shadow:none!important;outline:0!important}
</style>
