<script setup lang="ts">
import DeleteConfirmDialog from '../../components/DeleteConfirmDialog.vue'
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useAuthStore } from '../../stores/auth'
import { IconSearch } from '@arco-design/web-vue/es/icon'
import ListPagination from '../../components/list-pagination.vue'
import { useClientPagination } from '../../composables/use-client-pagination'
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
import { useGraphSpaceStore } from '../../stores/graphSpace'
import { useToast } from '../../composables/use-toast'
import { SEARCH_KEYWORD_MAX_LENGTH } from '../../utils/searchInput'
import {
  numberOrNullForSubmit,
  portValueForSubmit,
  validateConfigFields,
  validateGraphSpaceName,
  type ConfigFieldErrors,
} from '../../utils/configFieldValidation'

type ConfigKind = 'llm' | 'embedding' | 'mysql'
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
  // 端口/维度编辑态是字符串：type="number" 的 v-model 会被 Vue 自动 parseFloat 成
  // number（castToNumber 不看 .number 修饰符），65 位数字折叠成 1e+64、位数校验
  // （FUNC-00462/00463）失效——模板一律显式字符串赋值；服务端回填是 number，
  // 提交由 portValueForSubmit / numberOrNullForSubmit 归一。
  dimensions?: number | string | null
  // mysql
  host?: string
  port?: number | string
  defaultDatabase?: string
  username?: string
  password?: string
  hasPassword?: boolean
  passwordMasked?: string
}

const { showToast } = useToast()
const graphSpaceStore = useGraphSpaceStore()

const categories = [
  { key: '语言模型', label: '语言模型', hint: 'LLM 语言模型配置' },
  { key: '向量模型', label: '向量模型', hint: 'embedding 向量模型配置' },
  { key: 'MySQL 数据源', label: 'MySQL 数据源', hint: 'MySQL 关系库连接' },
  { key: '图数据空间', label: '图数据空间', hint: '我的图空间绑定' },
]

// 响应式跟随 auth store（profile 异步加载，一次性赋值会把 admin 恒判 false——
// 免登录部署下绑定入口/新建空间入口不渲染）
const isAdmin = computed(() => currentUserIsAdmin())
const graphSpaces = ref<GraphSpaceItem[]>([])
const spaceDialogOpen = ref(false)
const newSpaceName = ref('')
const spaceSubmitAttempted = ref(false)
const bindTarget = ref('')
const spaceWorking = ref(false)

const items = ref<ConfigItem[]>([])
const activeCategory = ref('语言模型')
const keyword = ref('')
const submittedKeyword = ref('')
const statusFilter = ref<string | undefined>('全部状态')
const selected = ref<ConfigItem | null>(null)
const dialogOpen = ref(false)
const testingId = ref('')
const saving = ref(false)
const configTableRef = ref<HTMLElement | null>(null)
const tableHasMoreToScroll = ref(false)
const tableScrollActive = ref(false)
let scrollIdleTimer: ReturnType<typeof setTimeout> | undefined

function updateConfigTableScrollState() {
  const table = configTableRef.value
  if (!table || table.scrollWidth <= table.clientWidth + 1) {
    tableHasMoreToScroll.value = false
    return
  }
  // The action column is sticky, so scroll distance alone does not tell us
  // whether any data is still hidden behind it. Compare the last data column
  // with the visible edge of the action column instead.
  const lastDataColumn = table.querySelector<HTMLElement>('thead .config-time-col')
  const actionColumn = table.querySelector<HTMLElement>('thead .config-action-col')
  const dataRect = lastDataColumn?.getBoundingClientRect()
  const actionRect = actionColumn?.getBoundingClientRect()
  tableHasMoreToScroll.value = dataRect?.width && actionRect?.width
    ? dataRect.right > actionRect.left + 2
    : table.scrollWidth - table.clientWidth - table.scrollLeft > 1
}

function handleConfigTableScroll() {
  updateConfigTableScrollState()
  tableScrollActive.value = true
  clearTimeout(scrollIdleTimer)
  scrollIdleTimer = setTimeout(() => { tableScrollActive.value = false }, 700)
}

function submitConfigSearch() {
  submittedKeyword.value = keyword.value.trim()
  resetConfigPage()
}

type ConfigForm = {
  name?: string
  baseUrl?: string
  model?: string
  apiKey?: string
  dimensions?: number | string | null
  owner?: string
  description?: string
  host?: string
  port?: number | string
  defaultDatabase?: string
  username?: string
  password?: string
  isDefault?: boolean
}

const form = ref<ConfigForm>({})
const verifying = ref(false)
const verified = ref(false)
// 输入即校验（第一轮测试 FUNC-00404～00676 口径）：computed 错误随输入刷新，字段位提示并拦提交/验证。
// 之前挂在 a-form :rules 上——原生 input 不触发 arco 的 change 校验，只有提交时 validate() 兜底，「输入即校验」全缺失。
const createFieldErrors = computed<ConfigFieldErrors>(() =>
  formKind.value ? validateConfigFields(formKind.value, form.value, 'create') : {})
const hasCreateErrors = computed(() => Object.keys(createFieldErrors.value).length > 0)
const detailFieldErrors = computed<ConfigFieldErrors>(() =>
  selected.value && !isGraphSpaceCategory.value
    ? validateConfigFields(selected.value.kind, selected.value, 'detail')
    : {})
const hasDetailErrors = computed(() => Object.keys(detailFieldErrors.value).length > 0)
const spaceNameError = computed(() => {
  if (!spaceDialogOpen.value) return null
  // 空名称在点击创建后提示；非空输入仍保留即时格式/长度校验。
  if (!spaceSubmitAttempted.value && !newSpaceName.value.trim()) return null
  return validateGraphSpaceName(newSpaceName.value)
})

const isModelKind = computed(() => activeCategory.value === '语言模型' || activeCategory.value === '向量模型')
const canVerifyForm = computed(() =>
  Boolean(String(form.value.baseUrl || '').trim() && String(form.value.model || '').trim() && String(form.value.apiKey || '').trim())
  && !hasCreateErrors.value)

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
    default:
      return null
  }
})

const visibleItems = computed(() => items.value.filter((item) => {
  const matchCategory = item.category === activeCategory.value
  const query = submittedKeyword.value.toLowerCase()
  const endpointOrUrl = item.baseUrl || item.host || item.endpoint
  const matchKeyword = !query || `${item.name}${item.id}${item.type}${endpointOrUrl}${item.model || ''}`.toLowerCase().includes(query)
  const matchStatus = !statusFilter.value || statusFilter.value === '全部状态' || item.status === statusFilter.value
  return matchCategory && matchKeyword && matchStatus
}).sort((a, b) => Number(b.isDefault) - Number(a.isDefault)))

// 配置列表客户端分页；筛选/切类后回到第一页（图数据空间分类下 visibleItems 恒空，分页条自动隐藏）
const {
  page: configPage,
  pageSize: configPageSize,
  total: configTotal,
  pagedItems,
  resetPage: resetConfigPage,
  changePage: changeConfigPage,
  changePageSize: changeConfigPageSize,
} = useClientPagination(visibleItems, 10)
watch([submittedKeyword, statusFilter, activeCategory], resetConfigPage)
watch([pagedItems, activeCategory], async () => {
  await nextTick()
  updateConfigTableScrollState()
}, { flush: 'post' })

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
    return '默认 MySQL 数据源'
  }
  return '尚未引用'
}

function configStatus(status: string): ConfigStatus {
  if (status === '正常') return '正常'
  if (status === '停用') return '停用'
  return '异常'
}

function toConfigItem(kind: ConfigKind, cfg: LlmConfig | MysqlDatasource | EmbeddingConfig): ConfigItem {
  const common = {
    id: cfg.id,
    kind,
    name: cfg.name,
    description: cfg.description,
    owner: cfg.owner || '',
    updatedAt: cfg.updatedAt,
    status: configStatus(cfg.status),
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
  throw new Error(`未知配置类型：${kind}`)
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
    }
  } catch (err) {
    showToast(`加载配置失败：${(err as Error).message}`, 'error')
  }
  items.value = [...loaded, ...others]
}

async function loadGraphSpaces() {
  try {
    graphSpaces.value = await listGraphSpaceItems()
  } catch (err) {
    showToast(`加载图空间失败：${(err as Error).message}`, 'error')
  }
}

async function createSpace() {
  if (!isAdmin.value) {
    showToast('请线下向管理员申请创建图空间。', 'info')
    return
  }
  spaceSubmitAttempted.value = true
  if (spaceNameError.value) return
  const name = newSpaceName.value.trim()
  spaceWorking.value = true
  try {
    await createGraphSpace(name)
    showToast(`图数据空间“${name}”已创建并绑定。空间建好后有秒级传播延迟，随后即可在任务触发时选择。`, 'success')
    spaceDialogOpen.value = false
    newSpaceName.value = ''
    await loadGraphSpaces()
    // 平台总览页的全局图空间选择器同步出现新空间（创建即绑定）
    void graphSpaceStore.ensureLoaded(true)
  } catch (err) {
    showToast(`创建失败：${(err as Error).message}`, 'error')
  } finally {
    spaceWorking.value = false
  }
}

async function bindSpace() {
  if (!canChangeLegacyBinding()) return
  const name = bindTarget.value
  if (!name) return
  spaceWorking.value = true
  try {
    await bindGraphSpace(name)
    showToast(`图数据空间“${name}”已绑定。`)
    bindTarget.value = ''
    await loadGraphSpaces()
    // 绑定对所有用户生效：平台总览页全局图空间选择器立即出现该空间
    void graphSpaceStore.ensureLoaded(true)
  } catch (err) {
    showToast(`绑定失败：${(err as Error).message}`, 'error')
  } finally {
    spaceWorking.value = false
  }
}

function canChangeLegacyBinding(): boolean {
  if (!isAdmin.value || useAuthStore().profile?.businessRbacEnabled) {
    showToast('图空间业务归属由管理员通过 SQL 配置。', 'info')
    return false
  }
  return true
}

const unbindTarget = ref<GraphSpaceItem>()
const unbindVisible = ref(false)
const unbindSubmitting = ref(false)
const unbindError = ref('')
/** 解绑仅删当前用户本人的绑定行：图数据/向量库/已建任务全保留，其他用户的绑定
 *  不受影响；空间随即出现在「绑定已有图数据空间」下拉里，可随时绑回。 */
function removeSpaceBinding(space: GraphSpaceItem) {
  if (!canChangeLegacyBinding()) return
  unbindTarget.value = space
  unbindError.value = ''
  unbindVisible.value = true
}
async function confirmUnbindSpace() {
  const space = unbindTarget.value
  if (!space || unbindSubmitting.value) return
  unbindSubmitting.value = true
  unbindError.value = ''
  try {
    await unbindGraphSpace(space.name)
    unbindVisible.value = false
    showToast(`图数据空间“${space.name}”已解除绑定（图数据与任务保留，可随时重新绑定）。`, 'success')
    await loadGraphSpaces()
    // 可工作空间按用户隔离：全局选择器同步收敛；若解绑的正是当前所选空间，
    // store 归一会自动回退默认空间
    void graphSpaceStore.ensureLoaded(true)
  } catch (err) {
    unbindError.value = `解绑失败：${(err as Error).message}`
  } finally {
    unbindSubmitting.value = false
  }
}

/** 打开管理抽屉：编辑副本隔离列表项。直接绑列表项（共享引用）会把未保存的输入
 * （含非法值）实时串进页面卡片，关抽屉不保存后卡片残留脏值直到刷新。保存成功
 * 由 saveDetail 的 loadByCategory 用服务端数据回填列表。 */
function openDetail(item: ConfigItem) {
  selected.value = { ...item }
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
  return { name: '', description: '', isDefault: false }
}

function openCreate() {
  if (isGraphSpaceCategory.value) {
    newSpaceName.value = ''
    spaceSubmitAttempted.value = false
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
  if (hasCreateErrors.value) return
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
      showToast(`验证失败：${result.error ?? '未知错误'}`, 'error')
    }
  } catch (err) {
    verified.value = false
    showToast(`验证请求失败：${(err as Error).message}`, 'error')
  } finally {
    verifying.value = false
  }
}

async function saveConfig() {
  if (hasCreateErrors.value) return
  const kind = formKind.value
  if (!kind) return
  if ((kind === 'llm' || kind === 'embedding') && !verified.value) return
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
        dimensions: numberOrNullForSubmit(form.value.dimensions),
        apiKey: String(form.value.apiKey || '').trim(),
        description: String(form.value.description || '').trim(),
        isDefault: Boolean(form.value.isDefault),
      }, currentUserId())
    } else if (kind === 'mysql') {
      await createMysqlDatasource({
        name: String(form.value.name).trim(),
        host: String(form.value.host).trim(),
        port: portValueForSubmit(form.value.port),
        defaultDatabase: String(form.value.defaultDatabase || '').trim(),
        username: String(form.value.username).trim(),
        password: String(form.value.password || ''),
        owner: String(form.value.owner || '').trim(),
        description: String(form.value.description || '').trim(),
        isDefault: Boolean(form.value.isDefault),
      }, currentUserId())
    }
    dialogOpen.value = false
    showToast(`“${String(form.value.name)}”已保存。`, 'success')
    await loadByCategory(activeCategory.value)
  } catch (err) {
    showToast(`保存失败：${(err as Error).message}`, 'error')
  } finally {
    saving.value = false
  }
}

async function saveDetail() {
  if (!selected.value) return
  if (hasDetailErrors.value) return
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
        dimensions: numberOrNullForSubmit(item.dimensions), owner: item.owner, apiKey: item.apiKey || '', status: item.status,
      }, currentUserId())
      selected.value = { ...selected.value, ...toConfigItem('embedding', updated), apiKey: '' }
    } else if (item.kind === 'mysql') {
      const updated = await updateMysqlDatasource(item.id, {
        name: item.name, description: item.description, host: item.host || '', port: portValueForSubmit(item.port),
        defaultDatabase: item.defaultDatabase || '', username: item.username || '',
        password: item.password || '', owner: item.owner, status: item.status,
      }, currentUserId())
      selected.value = { ...selected.value, ...toConfigItem('mysql', updated), password: '' }
    }
    await loadByCategory(activeCategory.value)
    showToast(`“${item.name}”的修改已保存。`, 'success')
  } catch (err) {
    showToast(`保存失败：${(err as Error).message}`, 'error')
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
    } else {
      result = await testMysqlDatasource(item.id, currentUserId())
    }
    if (result.ok) {
      item.status = '正常'
      showToast(`${item.name} 连接测试成功，延迟 ${result.latencyMs ?? '-'} ms。`, 'success')
    } else {
      item.status = '异常'
      showToast(`${item.name} 连接失败：${result.error ?? '未知错误'}`, 'error')
    }
    // 探活结果同步列表卡片（抽屉编辑副本不再共享列表项引用）
    const listed = items.value.find((i) => i.id === item.id)
    if (listed) listed.status = item.status
  } catch (err) {
    showToast(`测试请求失败：${(err as Error).message}`, 'error')
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
    }
    showToast(`${item.name}已${nextStatus === '停用' ? '停用' : '启用'}。`, 'info')
    await loadByCategory(activeCategory.value)
  } catch (err) {
    showToast(`切换状态失败：${(err as Error).message}`, 'error')
  }
}

const defaultUpdating = ref(false)
const hasCategoryDefault = computed(() => items.value.some(item => item.category === activeCategory.value && item.isDefault))
function defaultSwitchDisabled(item: ConfigItem) {
  return defaultUpdating.value || (!item.isDefault && items.value.some(other => other.kind === item.kind && other.isDefault))
}
async function toggleDefault(item: ConfigItem, value: unknown) {
  const enabled = value === true
  if (defaultSwitchDisabled(item) || enabled === item.isDefault) return
  defaultUpdating.value = true
  try {
    let updated: ConfigItem
    if (item.kind === 'llm') {
      updated = toConfigItem('llm', enabled
        ? await setDefaultLlmConfig(item.id, currentUserId())
        : await updateLlmConfig(item.id, { isDefault: false }, currentUserId()))
    } else if (item.kind === 'embedding') {
      updated = toConfigItem('embedding', enabled
        ? await setDefaultEmbeddingConfig(item.id, currentUserId())
        : await updateEmbeddingConfig(item.id, { isDefault: false }, currentUserId()))
    } else {
      updated = toConfigItem('mysql', enabled
        ? await setDefaultMysqlDatasource(item.id, currentUserId())
        : await updateMysqlDatasource(item.id, { isDefault: false }, currentUserId()))
    }
    items.value = items.value.map(other => {
      if (other.id === item.id && other.kind === item.kind) return updated
      if (enabled && other.kind === item.kind) return { ...other, isDefault: false, usage: buildUsage(other.kind, false) }
      return other
    })
    if (selected.value?.id === item.id && selected.value.kind === item.kind) {
      selected.value = { ...selected.value, isDefault: updated.isDefault, usage: updated.usage }
    }
    if (enabled) resetConfigPage()
    showToast(`“${item.name}”已${enabled ? '设为默认' : '取消默认'}。`, 'success')
  } catch (err) {
    showToast(`更新默认配置失败：${(err as Error).message}`, 'error')
  } finally {
    defaultUpdating.value = false
  }
}

const deleteTarget = ref<ConfigItem>()
const deleteVisible = ref(false)
const deleteSubmitting = ref(false)
const deleteError = ref('')
function removeConfig(item: ConfigItem) {
  deleteTarget.value = item
  deleteError.value = ''
  deleteVisible.value = true
}
async function confirmDeleteConfig() {
  const item = deleteTarget.value
  if (!item || deleteSubmitting.value) return
  deleteSubmitting.value = true
  deleteError.value = ''

  try {
    if (item.kind === 'llm') {
      await deleteLlmConfig(item.id, currentUserId())
    } else if (item.kind === 'embedding') {
      await deleteEmbeddingConfig(item.id, currentUserId())
    } else if (item.kind === 'mysql') {
      await deleteMysqlDatasource(item.id, currentUserId())
    }
    deleteVisible.value = false
    showToast(`“${item.name}”已删除。`, 'success')
    selected.value = null
    await loadByCategory(activeCategory.value)
  } catch (err) {
    deleteError.value = `删除失败：${(err as Error).message}`
  } finally {
    deleteSubmitting.value = false
  }
}

/** 首屏并行加载全部三类，让分类计数固定展示（loadByCategory 是替换式合并，并发会互相覆盖）。 */
async function loadAllCategories() {
  const [llm, embedding, mysql] = await Promise.allSettled([
    listLlmConfigs(currentUserId()),
    listEmbeddingConfigs(currentUserId()),
    listMysqlDatasources(currentUserId()),
  ])
  const loaded: ConfigItem[] = []
  const failed: string[] = []
  if (llm.status === 'fulfilled') loaded.push(...llm.value.map((c) => toConfigItem('llm', c)))
  else failed.push('语言模型')
  if (embedding.status === 'fulfilled') loaded.push(...embedding.value.map((c) => toConfigItem('embedding', c)))
  else failed.push('向量模型')
  if (mysql.status === 'fulfilled') loaded.push(...mysql.value.map((c) => toConfigItem('mysql', c)))
  else failed.push('MySQL 数据源')
  if (failed.length) showToast(`加载${[...new Set(failed)].join('、')}配置失败`, 'error')
  items.value = loaded
}

onMounted(() => {
  window.addEventListener('resize', updateConfigTableScrollState)
  void nextTick(updateConfigTableScrollState)
  void loadAllCategories()
  void loadGraphSpaces()
})
onUnmounted(() => {
  window.removeEventListener('resize', updateConfigTableScrollState)
  clearTimeout(scrollIdleTimer)
})
</script>

<template>
  <div class="configuration-page">
    <section class="config-workbench">
      <aside class="category-nav">
        <header><strong>配置分类</strong></header>
        <button v-for="category in categories" :key="category.key" type="button" :class="{ active: activeCategory === category.key }" :title="`${category.label}：${category.hint}`" @click="switchCategory(category.key)">
          <span><strong>{{ category.label }}</strong></span><em>{{ categoryCount(category.key) }}</em>
        </button>
      </aside>

      <main class="config-list">
        <header><nav v-if="!isGraphSpaceCategory" class="config-list-actions"><button class="primary create-entry" type="button" @click="openCreate">＋ 新建配置</button><a-select v-model="statusFilter" allow-clear placeholder="全部状态"><a-option value="全部状态">全部状态</a-option><a-option value="正常">正常</a-option><a-option value="异常">异常</a-option><a-option value="停用">停用</a-option></a-select><form class="config-search-form" role="search" @submit.prevent="submitConfigSearch"><a-input v-model="keyword" class="config-search-input" :max-length="SEARCH_KEYWORD_MAX_LENGTH" aria-label="搜索名称、标识或地址" placeholder="搜索名称、标识或地址"><template #prefix><IconSearch /></template></a-input><button class="primary config-search-button" type="submit">查询</button></form></nav><nav v-else class="bind-nav"><button class="primary" type="button" @click="spaceDialogOpen = true">＋ 新建图数据空间</button><a-select v-if="isAdmin && bindableSpaces.length" v-model="bindTarget" placeholder="绑定已有图数据空间" allow-clear><a-option v-for="space in bindableSpaces" :key="space.name" :value="space.name">{{ space.name }}</a-option></a-select><button v-if="isAdmin && bindableSpaces.length" type="button" :disabled="spaceWorking" @click="bindSpace">绑定</button></nav></header>
        <div v-if="isGraphSpaceCategory" class="table-wrap space-table">
          <table>
            <thead><tr><th>图数据空间</th><th>绑定状态</th><th v-if="isAdmin">操作</th></tr></thead>
            <tbody>
              <tr v-for="space in mySpaces" :key="space.name">
                <td><div class="config-name"><span><strong>{{ space.name }}</strong><small>NebulaGraph 图空间</small></span></div></td>
                <td><span class="status is-正常"><i />已绑定</span></td>
                <td v-if="isAdmin"><div class="row-actions"><button class="link danger" type="button" :disabled="spaceWorking" @click="removeSpaceBinding(space)">解绑</button></div></td>
              </tr>
              <tr v-if="!mySpaces.length"><td class="empty" :colspan="isAdmin ? 3 : 2">还没有绑定的图数据空间，点击右上角“新建图数据空间”创建一个</td></tr>
            </tbody>
          </table>
          <p class="space-hint">{{ isAdmin ? '新建图数据空间会真实执行 CREATE SPACE（创建后有秒级传播延迟）；解绑仅移除本人的绑定关系（图数据与任务保留、其他用户不受影响），重新绑定用右上角“绑定已有图数据空间”。' : '新建图数据空间会真实执行 CREATE SPACE（创建后有秒级传播延迟）；绑定与解绑请联系管理员处理。' }}</p>
        </div>
        <div v-else ref="configTableRef" class="table-wrap config-table-wrap" :class="{ 'has-scroll-right': tableHasMoreToScroll, 'config-scroll--active': tableScrollActive }" @scroll.passive="handleConfigTableScroll">
          <table>
            <thead><tr><th>配置名称</th><th>标识</th><th>类型 / 地址</th><th class="config-status-col">状态</th><th class="config-usage-col">引用情况</th><th class="config-time-col">更新时间</th><th class="config-action-col">操作</th></tr></thead>
            <tbody>
              <tr v-for="item in pagedItems" :key="item.id">
                <td><div class="config-name"><span><strong>{{ item.name }}<b v-if="item.isDefault" class="default-tag">默认</b></strong><small v-if="item.description">{{ item.description }}</small></span></div></td>
                <td class="config-id-col">{{ item.id }}</td>
                <td><strong class="type-name">{{ item.type }}<template v-if="item.model"> · {{ item.model }}</template></strong><code>{{ item.baseUrl || item.host && `${item.host}:${item.port}` || item.endpoint }}</code></td>
                <td class="config-status-col"><span class="status" :class="`is-${item.status}`"><i />{{ item.status }}</span></td>
                <td class="config-usage-col">
                  <button
                    type="button"
                    class="config-default-toggle"
                    :class="{ 'is-default': item.isDefault }"
                    :disabled="defaultSwitchDisabled(item)"
                    :aria-pressed="item.isDefault"
                    :aria-busy="defaultUpdating"
                    :aria-label="item.isDefault ? `取消${item.name}的默认配置` : `将${item.name}设为默认配置`"
                    :title="!item.isDefault && hasCategoryDefault ? '请先关闭当前默认配置' : item.isDefault ? '取消默认配置' : '设为默认配置'"
                    @click.stop="toggleDefault(item, !item.isDefault)"
                  ><span class="config-default-toggle__dot" aria-hidden="true" />{{ item.isDefault ? '默认' : '设为默认' }}</button>
                </td>
                <td class="config-time-col"><span>{{ item.owner }}</span><small class="updated">{{ item.updatedAt }}</small></td>
                <td class="config-action-col">
                  <div class="row-actions">
                    <button class="link" type="button" @click.stop="openDetail(item)">管理</button>
                    <button class="link" type="button" @click.stop="toggleItem(item)">{{ item.status === '停用' ? '启用' : '停用' }}</button>
                    <button class="link danger" type="button" @click.stop="removeConfig(item)">删除</button>
                  </div>
                </td>
              </tr>
              <tr v-if="!visibleItems.length"><td class="empty" colspan="7">没有符合条件的配置</td></tr>
            </tbody>
          </table>
        </div>
        <ListPagination
          v-if="configTotal > 0"
          :total="configTotal"
          :page="configPage"
          :page-size="configPageSize"
          :show-jumper="false"
          :size-at-end="true"
          @change="changeConfigPage"
          @change-size="changeConfigPageSize"
        ><template #summary><span class="config-page-summary">共 {{ configTotal }} 条</span></template></ListPagination>
      </main>
    </section>

    <Teleport to="body">
      <button v-if="selected" class="mask" type="button" aria-label="关闭" @click="selected=null" />
      <aside v-if="selected" class="detail-drawer">
      <header><div><h2>{{ selected.name }}<b v-if="selected.isDefault" class="default-tag">默认</b></h2><span class="config-id">{{ selected.id }}</span></div><button type="button" @click="selected=null">×</button></header>
      <div class="detail-drawer-body">
        <section class="health-card"><i :class="`is-${selected.status}`" /><div><strong>{{ selected.status === '正常' ? '配置可用' : selected.status === '异常' ? '连接存在异常' : '配置已停用' }}</strong><span>后端真实探活</span></div><button type="button" :disabled="testingId === selected.id" @click="testConnection(selected)">{{ testingId === selected.id ? '测试中…' : '测试连接' }}</button></section>
        <a-form :model="selected" class="detail-form" layout="vertical">
          <a-form-item field="name" label="配置名称" required><input aria-label="name" v-model="selected.name" /><small v-if="detailFieldErrors.name" class="field-error">{{ detailFieldErrors.name }}</small></a-form-item>
          <a-form-item label="服务类型"><input aria-label="input-field" :value="selected.type" readonly /></a-form-item>
          <template v-if="selected.kind === 'llm' || selected.kind === 'embedding'">
            <a-form-item class="wide" field="baseUrl" label="Base URL" required><input aria-label="baseUrl" v-model="selected.baseUrl" /><small v-if="detailFieldErrors.baseUrl" class="field-error">{{ detailFieldErrors.baseUrl }}</small></a-form-item>
            <a-form-item field="model" label="模型" required><input aria-label="model" v-model="selected.model" /><small v-if="detailFieldErrors.model" class="field-error">{{ detailFieldErrors.model }}</small></a-form-item>
            <a-form-item v-if="selected.kind === 'embedding'" label="维度"><input aria-label="number-input" :value="selected.dimensions ?? ''" type="number" @input="selected.dimensions = ($event.target as HTMLInputElement).value" /><small v-if="detailFieldErrors.dimensions" class="field-error">{{ detailFieldErrors.dimensions }}</small></a-form-item>
            <a-form-item label="访问凭据"><input aria-label="input-field" :value="selected.apiKeyMasked || (selected.hasApiKey ? '••••••••' : '未设置')" readonly /></a-form-item>
            <a-form-item class="wide" label="更新 API Key（留空保留原值）"><input aria-label="输入新 Key 覆盖原值" v-model="selected.apiKey" type="password" placeholder="输入新 Key 覆盖原值" /><small v-if="detailFieldErrors.apiKey" class="field-error">{{ detailFieldErrors.apiKey }}</small></a-form-item>
          </template>
          <template v-else>
            <a-form-item field="host" label="主机" required><input aria-label="host" v-model="selected.host" /><small v-if="detailFieldErrors.host" class="field-error">{{ detailFieldErrors.host }}</small></a-form-item>
            <a-form-item label="端口"><input aria-label="number-input" :value="selected.port ?? ''" type="number" @input="selected.port = ($event.target as HTMLInputElement).value" /><small v-if="detailFieldErrors.port" class="field-error">{{ detailFieldErrors.port }}</small></a-form-item>
            <a-form-item label="默认库"><input aria-label="defaultDatabase" v-model="selected.defaultDatabase" /><small v-if="detailFieldErrors.defaultDatabase" class="field-error">{{ detailFieldErrors.defaultDatabase }}</small></a-form-item>
            <a-form-item field="username" label="用户名" required><input aria-label="username" v-model="selected.username" /><small v-if="detailFieldErrors.username" class="field-error">{{ detailFieldErrors.username }}</small></a-form-item>
            <a-form-item label="访问凭据"><input aria-label="input-field" :value="selected.passwordMasked || (selected.hasPassword ? '••••••••' : '未设置')" readonly /></a-form-item>
            <a-form-item class="wide" label="更新密码（留空保留原值）"><input aria-label="输入新密码覆盖原值" v-model="selected.password" type="password" placeholder="输入新密码覆盖原值" /><small v-if="detailFieldErrors.password" class="field-error">{{ detailFieldErrors.password }}</small></a-form-item>
          </template>
          <a-form-item class="wide" label="配置说明"><a-textarea v-model="selected.description" /><small v-if="detailFieldErrors.description" class="field-error">{{ detailFieldErrors.description }}</small></a-form-item>
        </a-form>
        <section class="reference-card"><header><strong>引用关系</strong><span>{{ selected.usage }}</span></header><p>配置变更将在下次脚本调用时生效（context 按触发时所选数据源 / 图空间 / LLM / embedding 注入；向量库随图空间自动同名创建）。</p></section>
      </div>
      <footer>
        <button class="primary" type="button" :disabled="saving || hasDetailErrors" @click="saveDetail">{{ saving ? '保存中…' : '保存修改' }}</button>
      </footer>
      </aside>
    </Teleport>

    <Teleport to="body">
      <button v-if="spaceDialogOpen" class="mask create-dialog-mask" type="button" aria-label="关闭新建图空间弹窗" @click="spaceDialogOpen=false" />
      <aside v-if="spaceDialogOpen" class="create-dialog space-dialog">
        <header><div><h2>新建图数据空间</h2></div><button type="button" @click="spaceDialogOpen=false">×</button></header>
        <a-form class="dialog-form" layout="vertical" :model="{}">
          <a-form-item class="wide" label="图数据空间名称" required>
            <div class="space-name-field">
              <input aria-label="仅字母、数字、下划线，以字母或下划线开头" v-model="newSpaceName" placeholder="仅字母、数字、下划线，以字母或下划线开头" :aria-invalid="Boolean(spaceNameError)" :aria-describedby="spaceNameError ? 'space-name-error' : undefined" />
              <small v-if="spaceNameError" id="space-name-error" class="field-error" role="alert">{{ spaceNameError }}</small>
            </div>
          </a-form-item>
          <p class="space-dialog-hint">将真实执行 CREATE SPACE 并自动绑定到你的账号；空间创建后有秒级传播延迟。</p>
        </a-form>
        <footer><button type="button" @click="spaceDialogOpen=false">取消</button><button class="primary" type="button" :disabled="spaceWorking" @click="createSpace">{{ spaceWorking ? '创建中…' : '创建' }}</button></footer>
      </aside>
      <button v-if="dialogOpen" class="mask create-dialog-mask" type="button" aria-label="关闭新建配置弹窗" @click="dialogOpen=false" />
      <aside v-if="dialogOpen" class="create-dialog config-create-dialog">
      <header><div><span>NEW CONFIGURATION</span><h2>新建{{ categories.find(item => item.key === activeCategory)?.label }}</h2></div><button type="button" @click="dialogOpen=false">×</button></header>
      <a-form :model="form" class="dialog-form config-create-form" layout="vertical">
        <template v-if="formKind === 'llm' || formKind === 'embedding'">
          <a-form-item class="wide" field="name" label="配置名称" required><input aria-label="例如：科技文本抽取大模型" v-model="form.name" placeholder="例如：科技文本抽取大模型" /></a-form-item>
          <a-form-item class="wide" field="baseUrl" label="Base URL" required><input aria-label="baseUrl" v-model="form.baseUrl" /><small v-if="createFieldErrors.baseUrl" class="field-error">{{ createFieldErrors.baseUrl }}</small></a-form-item>
          <a-form-item class="wide" field="model" label="模型" required><input aria-label="model" v-model="form.model" /><small v-if="createFieldErrors.model" class="field-error">{{ createFieldErrors.model }}</small></a-form-item>
          <a-form-item v-if="formKind === 'embedding'" field="dimensions" label="维度"><input aria-label="number-input" :value="form.dimensions ?? ''" type="number" @input="form.dimensions = ($event.target as HTMLInputElement).value" /><small v-if="createFieldErrors.dimensions" class="field-error">{{ createFieldErrors.dimensions }}</small></a-form-item>
          <a-form-item class="wide" field="apiKey" label="API Key" required><input aria-label="必填；验证通过后才能保存，明文入库脱敏展示" v-model="form.apiKey" type="password" placeholder="必填；验证通过后才能保存，明文入库脱敏展示" /></a-form-item>
        </template>
        <template v-else>
          <a-form-item class="wide" field="name" label="配置名称" required><input aria-label="name" v-model="form.name" /></a-form-item>
          <a-form-item field="host" label="主机" required><input aria-label="host" v-model="form.host" /><small v-if="createFieldErrors.host" class="field-error">{{ createFieldErrors.host }}</small></a-form-item>
          <a-form-item label="端口"><input aria-label="number-input" :value="form.port ?? ''" type="number" @input="form.port = ($event.target as HTMLInputElement).value" /><small v-if="createFieldErrors.port" class="field-error">{{ createFieldErrors.port }}</small></a-form-item>
          <a-form-item label="默认库"><input aria-label="defaultDatabase" v-model="form.defaultDatabase" /><small v-if="createFieldErrors.defaultDatabase" class="field-error">{{ createFieldErrors.defaultDatabase }}</small></a-form-item>
          <a-form-item field="username" label="用户名" required><input aria-label="username" v-model="form.username" /><small v-if="createFieldErrors.username" class="field-error">{{ createFieldErrors.username }}</small></a-form-item>
          <a-form-item class="wide" label="密码"><input aria-label="password" v-model="form.password" type="password" /><small v-if="createFieldErrors.password" class="field-error">{{ createFieldErrors.password }}</small></a-form-item>
        </template>
        <a-form-item class="wide" label="说明"><a-textarea v-model="form.description" :auto-size="{ minRows: 3, maxRows: 5 }" /><small v-if="createFieldErrors.description" class="field-error">{{ createFieldErrors.description }}</small></a-form-item>
        <a-form-item class="wide" field="isDefault"><a-checkbox v-model="form.isDefault" :disabled="hasCategoryDefault || defaultUpdating" class="default-config-checkbox">设为默认（同一类别仅一条默认生效）</a-checkbox></a-form-item>
      </a-form>
      <footer>
        <button type="button" @click="dialogOpen=false">取消</button>
        <template v-if="isModelKind">
          <button type="button" :disabled="verifying || !canVerifyForm" @click="verifyForm">{{ verifying ? '验证中…' : '验证连接' }}</button>
          <button class="primary" type="button" :disabled="!verified || saving || hasCreateErrors" @click="saveConfig">{{ saving ? '保存中…' : verified ? '保存' : '验证通过后可保存' }}</button>
        </template>
        <button v-else class="primary" type="button" :disabled="hasCreateErrors || saving" @click="saveConfig">{{ saving ? '保存中…' : '保存' }}</button>
      </footer>
      </aside>
    </Teleport>
    <DeleteConfirmDialog v-model:visible="deleteVisible" title="删除配置" :name="deleteTarget?.name || ''" :identifier="deleteTarget?.id" identifier-label="配置 ID" description="继续操作将永久删除该配置。请确认相关任务不再依赖此配置。" :loading="deleteSubmitting" :error="deleteError" @confirm="confirmDeleteConfig" />
    <DeleteConfirmDialog v-model:visible="unbindVisible" title="解除绑定" verb="解绑" warning="解绑不会删除任何图数据，可随时重新绑定。" :name="unbindTarget?.name || ''" description="仅解除你本人与该图数据空间的绑定关系：解绑后它不再出现在你的图空间选择器中；图数据、向量库、已建任务及其他用户的绑定均保留。" :loading="unbindSubmitting" :error="unbindError" @confirm="confirmUnbindSpace" />
  </div>
</template>

<style scoped>
.configuration-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;color:#17233b;flex-direction:column}.page-header{display:flex;flex:0 0 auto;align-items:flex-end;justify-content:space-between;margin-bottom:12px}.page-header span{color:#165dff;font-size:9px;letter-spacing:.12em}.page-header h1{margin:3px 0 0;font-size:22px}.page-header p{margin:4px 0 0;color:#66758f;font-size:11px}.primary{border-color:#165dff!important;background:#165dff!important;color:#fff!important}.config-workbench{display:grid;flex:1;min-height:0;grid-template-columns:248px minmax(0,1fr);overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:#fff}.category-nav{display:flex;min-height:0;border-right:1px solid #dce8f8;background:#f8fbff;flex-direction:column}.category-nav>header{display:grid;gap:3px;padding:14px;border-bottom:1px solid #dce8f8}.category-nav>header strong{font-size:13px}.category-nav>header span{color:#8290a7;font-size:9px}.category-nav>button{display:grid;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:9px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #edf2f8;background:transparent;color:#344766;text-align:left;cursor:pointer}.category-nav>button.active{background:#eaf2ff;box-shadow:inset 3px 0 #165dff}.category-nav>button>span{display:grid;gap:3px}.category-nav>button strong{font-size:11px}.category-nav>button small{color:#8290a7;font-size:8px}.category-nav>button em{min-width:20px;padding:2px 6px;border-radius:99px;background:#e7eef8;color:#71809a;font-size:9px;font-style:normal;text-align:center}.config-list{display:flex;min-width:0;min-height:0;flex-direction:column}.config-list>header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #dce8f8;background:#fff}.config-list>header>div{display:flex;align-items:baseline;gap:8px}.config-list h2{margin:0;font-size:15px}.config-list>header span{color:#8290a7;font-size:9px}.config-list nav{display:flex;flex:1;min-width:0;flex-wrap:wrap;gap:8px;align-items:center}.config-list nav button{height:31px;padding:0 12px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;font-size:10px;cursor:pointer}.config-list input,.config-list select{height:31px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font-size:10px}.config-list input{width:210px}.table-wrap{flex:1;min-height:0;overflow:auto}.table-wrap table{width:100%;border-collapse:collapse;font-size:10px}.table-wrap thead{position:sticky;z-index:2;top:0}.table-wrap th,.table-wrap td{padding:10px 11px;border-bottom:1px solid #e7eef7;text-align:left;vertical-align:middle}.table-wrap th{background:#f2f7fd;color:#60708a;font-weight:600;white-space:nowrap}.table-wrap tbody tr{cursor:pointer}.table-wrap tbody tr:hover td{background:#f7faff}.config-name{display:flex;align-items:center;gap:9px;min-width:210px}.config-name>span{display:grid;gap:3px}.config-name strong{font-size:11px}.config-name small,.updated{display:block;color:#8290a7;font-size:8px}.type-name{display:block;color:#40516d;font-size:10px}.table-wrap code{display:block;max-width:210px;margin-top:3px;overflow:hidden;color:#71809a;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.status{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:99px}.status>i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.is-正常{background:#dcfae6;color:var(--status-success)}.status.is-异常{background:#fee4e2;color:var(--status-danger)}.status.is-停用{background:#eef1f5;color:var(--status-neutral)}.link{border:0;background:transparent;color:#165dff;font-size:10px;cursor:pointer}.empty{height:100px;color:#8290a7;text-align:center!important}.mask{position:fixed;z-index:40;inset:0;border:0;background:rgba(16,36,76,.24)}.detail-drawer{position:fixed;z-index:41;top:0;right:0;display:flex;width:min(500px,90vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}.detail-drawer>header,.create-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.detail-drawer>header span,.create-dialog>header span{color:#165dff;font-size:9px}.detail-drawer h2,.create-dialog h2{margin:4px 0;font-size:18px}.detail-drawer>header button,.create-dialog>header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.health-card{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;gap:10px;margin:14px 16px 0;padding:12px;border:1px solid #cfe4d7;border-radius:7px;background:#fff}.health-card>i{width:9px;height:9px;border-radius:50%;background:var(--status-success);box-shadow:none}.health-card>i.is-异常{background:var(--status-danger);box-shadow:none}.health-card>i.is-停用{background:var(--status-neutral);box-shadow:none}.health-card>div{display:grid;gap:3px}.health-card strong{font-size:11px}.health-card span{color:#71809a;font-size:9px}.health-card button{height:29px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#165dff;font-size:9px;cursor:pointer}.detail-form,.dialog-form{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:16px}.detail-form label,.dialog-form label{display:grid;gap:5px}.detail-form label span,.dialog-form label span{color:#60708a;font-size:9px}.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{box-sizing:border-box;width:100%;height:33px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font:10px inherit}.detail-form textarea,.dialog-form textarea{height:65px;padding-top:8px;resize:none}.wide{grid-column:1/-1}.reference-card{margin:0 16px;padding:12px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.reference-card header{display:flex;justify-content:space-between}.reference-card strong{font-size:10px}.reference-card span{color:#165dff;font-size:9px}.reference-card p{margin:5px 0 0;color:#71809a;font-size:9px;line-height:16px}.detail-drawer>footer,.create-dialog>footer{display:flex;justify-content:flex-end;gap:8px;margin-top:auto;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.detail-drawer>footer button,.create-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.create-dialog{position:fixed;z-index:42;top:50%;left:50%;width:min(650px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.create-dialog>footer{margin-top:0}.create-dialog button:disabled{opacity:.5;cursor:not-allowed}.default-tag{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:99px;background:#fff3d8;color:#b54708;font-size:8px;font-weight:600;font-style:normal}.checkbox{display:flex;flex-direction:row;align-items:center;gap:8px}.checkbox input{width:auto;height:14px}.checkbox span{color:#344766;font-size:10px}@media(max-width:1100px){.config-workbench{grid-template-columns:210px minmax(0,1fr)}}

/* Compact fixed action column; free width belongs to data columns. */
.config-table-wrap :is(th,td).config-action-col{width:152px;min-width:152px;max-width:152px}
.config-usage-col :deep(.arco-switch){vertical-align:middle}
</style>
<style scoped>
/* DESIGN_RULES: configuration management page contract. */
.configuration-page{padding:0;color:#1d2129}.page-header{align-items:center;margin-bottom:16px}.page-header>div{display:none}.page-header button{height:32px;margin-right:auto;margin-left:0;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px}
.config-workbench{grid-template-columns:240px minmax(0,1fr);gap:0;border:0;border-radius:0;background:transparent}.category-nav{border:0;border-right:1px solid #e5e6eb;background:transparent}.config-list{overflow:hidden;border:0;border-radius:0;background:#fff}
.category-nav>header{display:flex;align-items:center;gap:0;padding:8px 16px;border-bottom:0}.category-nav>header strong{position:relative;padding-left:11px;font-size:16px;line-height:24px}.category-nav>header strong::before{position:absolute;top:5px;left:0;width:3px;height:14px;border-radius:1px;background:#165dff;content:""}
.category-nav>button{box-sizing:border-box;grid-template-columns:minmax(0,1fr) auto;align-items:center;gap:8px;width:calc(100% - 16px);height:56px;min-height:56px;margin-right:8px;margin-left:8px;padding:4px 16px;border:1px solid transparent;border-radius:4px;font-size:14px;line-height:22px;text-align:left}.category-nav>header+button{margin-top:4px}.category-nav>button+button{margin-top:4px}.category-nav>button.active{border-color:transparent;background:#e8f3ff;box-shadow:none;color:#165dff;font-weight:500}
.category-nav>button>span{display:flex;min-width:0;align-items:center;justify-content:flex-start}.category-nav>button strong{display:block;overflow:hidden;font-size:14px;line-height:22px;text-align:left;text-overflow:ellipsis;white-space:nowrap}.category-nav>button em{padding:0;border-radius:0;background:transparent;font-size:12px;line-height:20px}
.config-list>header{min-height:56px;box-sizing:border-box;justify-content:flex-end;gap:16px;padding:8px 16px}.config-list nav{gap:16px}.config-list-actions{width:100%}.config-list-actions .config-search-input{margin-left:auto}
.config-list input,.config-list select{height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px}
.table-wrap table{font-size:14px;line-height:22px}.table-wrap th,.table-wrap td{height:40px;padding:0 16px;border-bottom:1px solid #e5e6eb}.table-wrap th{background:#f7f8fa;color:#1d2129;font-weight:500}.config-name{min-width:0;gap:8px}.config-name strong,.type-name,.link{font-size:14px;line-height:22px}.config-name small,.updated,.table-wrap code{font-size:12px;line-height:20px}
.status{gap:6px;padding:0;border-radius:0;background:transparent;font-size:14px;line-height:22px;white-space:nowrap}.status.is-正常,.status.is-异常,.status.is-停用{background:transparent}
/* 行内操作列：管理/停用/删除 并排，删除用警示红 */
.row-actions{display:flex;gap:12px;align-items:center;white-space:nowrap}.row-actions .link{padding:0;height:auto}.link.danger{color:#f53f3f}
/* 与 Schema 管理表一致：所有列按内容语义自动分配，空间不足时由表格容器横向滚动。 */
.table-wrap table{width:100%;table-layout:auto}
.detail-drawer{width:min(640px,calc(100vw - 48px));background:#fff}.create-dialog{width:min(640px,calc(100vw - 48px));border-radius:8px;background:#fff}
.create-dialog>header{height:56px;box-sizing:border-box;padding:8px 24px}.detail-drawer>header{min-height:56px;height:auto;box-sizing:border-box;padding:8px 24px}.detail-drawer>header span,.create-dialog>header span{font-size:12px;line-height:20px}.detail-drawer h2,.create-dialog h2{font-size:16px;line-height:24px}
.detail-form,.dialog-form{gap:16px;padding:24px}.detail-form label,.dialog-form label{gap:8px}.detail-form label span,.dialog-form label span,.checkbox span{font-size:14px;line-height:22px}
.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{height:32px;padding:0 12px;border-color:#e5e6eb;border-radius:4px;font:14px/22px inherit}.detail-form textarea,.dialog-form textarea{height:72px;padding:8px 12px}
.reference-card{margin:0 24px;padding:16px;border-radius:6px}.reference-card strong{font-size:14px;line-height:22px}.reference-card span,.reference-card p{font-size:12px;line-height:20px}
.detail-drawer>footer,.create-dialog>footer{height:64px;box-sizing:border-box;gap:16px;padding:0 24px}.detail-drawer>footer button,.create-dialog>footer button{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px}
.default-tag{border-radius:4px;font-size:12px;line-height:20px}
.config-search-input.arco-input-wrapper{box-sizing:border-box;width:280px;min-width:0;max-width:100%;height:32px;min-height:32px;padding:0 12px;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;flex:1 1 240px}
.config-search-input.arco-input-wrapper:hover{border-color:#4080ff!important;background:#fff!important}
.config-search-input.arco-input-wrapper:focus-within,.config-search-input.arco-input-focus{border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.config-search-input.arco-input-wrapper :deep(.arco-input-prefix){padding-right:8px;color:#4e5969}.config-search-input.arco-input-focus :deep(.arco-input-prefix){color:#165dff}
.config-search-input.arco-input-wrapper :deep(.arco-input-prefix svg){width:16px;height:16px;font-size:16px}
.config-search-input.arco-input-wrapper :deep(.arco-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:none!important}
/* Isolate the status Arco Select from native search-input styles. */
/* 列表头操作按钮（新建配置/绑定）：与输入框同规格，禁止换行与压缩导致文字溢出 */
.config-list nav button{height:32px;padding:0 16px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px;white-space:nowrap;flex-shrink:0}
.config-list nav :deep(.arco-select){width:160px;min-width:160px;flex-shrink:0}
/* 注意：Arco select 根节点同时挂 arco-select 与 arco-select-view，两条规则同特异性，
   这里绝不能再写 width:100%，否则会覆盖上一条的 width:160px，把新建按钮挤出视口。 */
.config-list nav :deep(.arco-select-view){box-sizing:border-box;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff}
.config-list nav :deep(.arco-select-view-input){height:100%!important;min-height:0!important;padding:0!important;border:0!important;background:transparent!important;box-shadow:none!important}
.config-list nav :deep(.arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;pointer-events:none!important}
.config-list nav :deep(.arco-select-view-value){min-width:0;line-height:30px}
/* 窄侧栏（≤1024px）：图标已移除，改为只显示分类名（计数隐藏，超长省略） */
@media(max-width:1024px){.config-workbench{grid-template-columns:84px minmax(0,1fr)}.category-nav>header span,.category-nav>button em{display:none}.category-nav>button{grid-template-columns:minmax(0,1fr);height:40px;min-height:40px;justify-content:center;padding:0 8px}.category-nav>button strong{text-align:center}}
.dialog-form :deep(.arco-form-item){margin-bottom:0}.dialog-form :deep(.arco-form-item-layout-vertical>.arco-form-item-label-col){margin-bottom:8px}
.dialog-form .default-config-checkbox{display:inline-flex!important;flex-direction:row!important;align-items:center!important;justify-content:flex-start;gap:0!important;white-space:nowrap}
.config-create-form input:not([type="checkbox"]){box-sizing:border-box;width:100%;height:32px;padding:0 12px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;color:#1d2129;font-family:inherit;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0;outline:none;box-shadow:none;transition:border-color .1s ease,box-shadow .1s ease}
.config-create-form input:not([type="checkbox"]):hover{border-color:#4080ff}.config-create-form input:not([type="checkbox"]):focus,.config-create-form input:not([type="checkbox"]):focus-visible{border-color:#165dff;outline:none;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.config-create-form :deep(.arco-textarea-wrapper){box-sizing:border-box;width:100%;height:auto;min-height:80px;max-height:none;border:1px solid #e5e6eb;border-radius:4px;background:#fff!important;box-shadow:none;transition:border-color .1s ease,box-shadow .1s ease}.config-create-form :deep(.arco-textarea-wrapper:hover){border-color:#4080ff}.config-create-form :deep(.arco-textarea-wrapper.arco-textarea-focus){border-color:#165dff;box-shadow:0 0 0 2px rgba(22,93,255,.1)}
.config-create-form :deep(textarea.arco-textarea){box-sizing:border-box;width:100%;height:auto;min-height:78px;padding:8px 12px 28px;background:#fff!important;color:#1d2129;font-family:inherit;font-size:14px;line-height:22px;font-weight:400;letter-spacing:0;resize:vertical;overflow-y:auto}.config-create-form :deep(.arco-textarea-word-limit){right:12px;bottom:6px;color:#86909c;font-size:12px;line-height:20px;font-weight:400;letter-spacing:0}
.create-dialog>header{align-items:center;padding:0 24px}.create-dialog>header>div{display:flex;height:24px;align-items:center}.create-dialog>header span{display:none}.create-dialog h2{margin:0;font-size:16px;line-height:24px}
.config-create-dialog>header>button{display:grid;width:32px;height:32px;padding:0;border:0;background:transparent;color:#4e5969;font-size:20px;line-height:1;place-items:center}.config-create-dialog>header>button:hover{background:transparent;color:#165dff}.config-create-dialog>header>button:focus-visible{background:transparent;outline:2px solid rgba(22,93,255,.16);outline-offset:2px}
.space-dialog>header{align-items:center}
.space-dialog>header>button{display:grid;width:32px!important;min-width:32px;height:32px!important;min-height:32px!important;padding:0!important;border:0!important;background:transparent!important;color:#4e5969;font-size:20px;line-height:1;place-items:center}
.space-dialog>header>button:hover{background:transparent!important;color:#165dff}.space-dialog>header>button:focus-visible{background:transparent!important;outline:2px solid rgba(22,93,255,.16);outline-offset:2px}
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
.detail-drawer-body{display:flex;box-sizing:border-box;flex:1 1 0;min-height:0;gap:16px;overflow-y:auto;padding:16px 24px;flex-direction:column}
.detail-drawer-body .health-card,.detail-drawer-body .reference-card{margin:0}
.detail-drawer-body .detail-form{padding:0}
.detail-form :deep(.arco-form-item){margin-bottom:0}
.detail-form :deep(.arco-form-item-layout-vertical>.arco-form-item-label-col){margin-bottom:8px}
.detail-drawer>footer{flex:0 0 auto;margin-top:0;align-items:center}
/* 新建弹窗：限高 + 表单区内部滚动（原来 overflow:hidden 直接裁掉超高表单） */
.create-dialog{display:flex;max-height:min(88vh,760px);flex-direction:column}
.create-dialog .dialog-form{flex:1 1 auto;min-height:0;overflow:auto}
.create-dialog>footer{margin-top:auto}
/* 图空间分类。select 宽度按最长占位符「绑定已有图数据空间」(9 个汉字)定：
   扣除边框/内边距/下拉箭头后 input 需 ~160px+，200px 会把最后一个字裁掉(实测)。 */
.bind-nav{display:flex;width:100%;gap:16px;align-items:center}.bind-nav :deep(.arco-select){width:240px;min-width:240px}.bind-nav button{height:32px;padding:0 16px;border:1px solid #bdd0ea;border-radius:4px;font-size:14px;cursor:pointer}
.space-hint{margin:8px 16px;color:#86909c;font-size:12px;line-height:20px}
.space-dialog-hint{grid-column:1/-1;margin:0;color:#86909c;font-size:12px;line-height:20px}
.space-name-field{display:flex;width:100%;min-width:0;flex-direction:column;gap:4px}
/* 字段级校验提示（输入即校验，超长/异常字符/范围/必填） */
.dialog-form .field-error,.detail-form .field-error{display:block;color:#e4322d;font-size:12px;line-height:18px}

/* 新建配置弹窗文字层级：主 / 次 / 三级 / 禁用。 */
.config-create-dialog,.config-create-dialog :deep(*){font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;letter-spacing:0}
.config-create-dialog{color:#1d2129;font-size:14px;line-height:22px;font-weight:400}
.config-create-dialog h2{color:#1d2129;font-size:16px;line-height:24px;font-weight:600}
.config-create-dialog .config-create-form :deep(.arco-form-item-label),.config-create-dialog .config-create-form :deep(.arco-checkbox-label){color:#4e5969;font-size:14px;line-height:22px;font-weight:400}
.config-create-dialog .config-create-form input:not([type="checkbox"]),.config-create-dialog .config-create-form :deep(textarea.arco-textarea){color:#1d2129;font-size:14px;line-height:22px;font-weight:400}
.config-create-dialog .config-create-form input::placeholder,.config-create-dialog .config-create-form :deep(textarea.arco-textarea::placeholder){color:#86909c;opacity:1}
.config-create-dialog .config-create-form :deep(.arco-form-item-message),.config-create-dialog .config-create-form :deep(.arco-textarea-word-limit){font-size:12px;line-height:20px;font-weight:400}
.config-create-dialog .config-create-form :deep(.arco-textarea-word-limit){color:#86909c}
.config-create-dialog>header>button{color:#4e5969}.config-create-dialog>footer>button{color:#4e5969;font-size:14px;line-height:22px;font-weight:400}
.config-create-dialog :is(input,textarea,button):disabled,.config-create-dialog :deep(.arco-checkbox-disabled .arco-checkbox-label){color:#c9cdd4!important}
.config-create-dialog>footer>button:disabled{border-color:#e5e6eb!important;background:#f7f8fa!important;color:#c9cdd4!important;opacity:1}

/* 配置管理页字体、间距、圆角与阴影合同。 */
.configuration-page,.configuration-page :deep(*),.create-dialog,.create-dialog :deep(*){font-family:"PingFang SC","PingFang HK","Microsoft YaHei","Helvetica Neue",Arial,sans-serif;letter-spacing:0}
.configuration-page,.detail-drawer,.create-dialog{font-size:14px;line-height:22px;font-weight:400}
.configuration-page :is(button,input,textarea,select),.detail-drawer :is(button,input,textarea,select),.create-dialog :is(button,input,textarea,select){font-family:inherit;letter-spacing:0}
.config-list>header{background:transparent}
.category-nav>header strong,.detail-drawer h2,.create-dialog h2{font-size:16px;line-height:24px;font-weight:600}
.category-nav>button,.category-nav>button strong,.config-list nav button,.config-list nav :deep(.arco-select-view-value),.config-search-input :deep(.arco-input){font-size:14px;line-height:22px;font-weight:400}
.category-nav>button.active{font-weight:500}
.category-nav>button em{font-size:12px;line-height:20px;font-weight:400}
.config-name>span{min-width:160px;gap:4px}.config-name strong,.type-name,.table-wrap td,.row-actions .link{font-size:14px;line-height:22px;font-weight:400}.config-name small,.updated,.table-wrap code{font-size:12px;line-height:20px;font-weight:400}.table-wrap code{max-width:none;margin-top:4px;overflow:visible;font-family:inherit;text-overflow:clip;white-space:nowrap}
.row-actions{gap:8px}.default-tag{margin-left:8px;padding:0 4px;font-size:12px;line-height:20px;font-weight:500}
.config-list nav :deep(.arco-select-view-value){line-height:22px}
.detail-drawer>header button,.create-dialog>header button{width:32px;height:32px;border-radius:4px}
/* 详情抽屉右上角关闭按钮：去掉灰色底块（与新建弹窗关闭按钮一致） */
.detail-drawer>header>button{border:0;background:transparent;color:#4e5969;font-size:20px;line-height:1}
.detail-drawer>header>button:hover{background:transparent;color:#165dff}
/* 详情抽屉头部：黑色标题在上，蓝色唯一标识在标题下方 */
.detail-drawer>header h2{margin:0}
.detail-drawer>header .config-id{display:block;margin-top:2px;color:#165dff;font-size:12px;line-height:20px;font-weight:400}
.health-card{grid-template-columns:8px minmax(0,1fr) auto;gap:16px;margin:16px 24px 0;padding:16px;border-color:#e5e6eb;border-radius:6px;box-shadow:none}.health-card>i{width:8px;height:8px}.health-card>div{gap:4px}.health-card strong{font-size:14px;line-height:22px;font-weight:600}.health-card span{font-size:12px;line-height:20px;font-weight:400}.health-card button{height:32px;padding:0 16px;border-color:#e5e6eb;border-radius:4px;font-size:14px;line-height:22px;font-weight:400}
.detail-form,.dialog-form{gap:16px;padding:24px}.detail-form label,.dialog-form label{gap:8px}.detail-form label span,.dialog-form label span{font-size:14px;line-height:22px;font-weight:400}
.reference-card{margin:0 24px;padding:16px;border-color:#e5e6eb;border-radius:6px;box-shadow:none}.reference-card strong{font-size:14px;line-height:22px;font-weight:600}.reference-card span,.reference-card p,.space-hint,.space-dialog-hint{font-size:12px;line-height:20px;font-weight:400}
.detail-drawer>footer,.create-dialog>footer{gap:16px;padding:0 24px}.detail-drawer>footer button,.create-dialog>footer button{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px;font-weight:400}

/* 工作台留白与表格背景：操作区、数据行不使用额外底色，仅表头区分层级。 */
.category-nav>header{box-sizing:border-box;min-height:56px;padding:16px}
/* 列表、固定操作列和分页条共用不透明底色，横向滚动时避免内容透出。 */
.config-list{background:#fff}
.config-list>header{min-height:64px;padding:16px;margin:0;border-bottom:0;background:transparent!important}
.config-list-actions .create-entry{background:#165dff!important;color:#fff!important}
.config-list-actions :deep(.arco-select-view),
.config-list-actions .config-search-input{background:#fff!important}
.table-wrap{box-sizing:border-box;margin:0 16px;background:transparent}
.table-wrap th{background:#f7f8fa!important;color:#1d2129!important;font-weight:500!important}
.table-wrap table,
.table-wrap tbody,
.table-wrap tbody tr,
.table-wrap tbody td,
.table-wrap tbody tr:hover td{background:transparent}
.table-wrap:not(.space-table) .config-action-col{box-sizing:border-box;overflow:visible;white-space:nowrap}
/* 操作列与 Schema 管理表对齐：右侧固定列，横向滚动时操作不被遮挡。
   thead 整体吸顶（z2）须高于固定列 td（z3），否则纵向滚动时被操作单元格盖住。 */
.table-wrap:not(.space-table) thead{z-index:4}
.table-wrap:not(.space-table) th.config-action-col{position:sticky;right:0;background:#f7f8fa}
.table-wrap:not(.space-table) td.config-action-col{position:sticky;right:0;z-index:3;background:#fff}
/* 固定列左侧向内容区渐隐的阴影（与 Schema 管理表同视觉提示） */
.table-wrap.has-scroll-right :is(th,td).config-action-col::before{position:absolute;top:0;bottom:-1px;left:0;width:12px;content:"";pointer-events:none;transform:translateX(-100%);box-shadow:inset -10px 0 8px -8px rgba(78,89,105,.28)}
.config-action-col .row-actions{display:inline-flex;width:auto;min-width:max-content;align-items:center;overflow:visible}
.config-default-toggle{display:inline-flex;box-sizing:border-box;align-items:center;justify-content:center;gap:6px;min-width:88px;height:32px;padding:0 10px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:22px;font-weight:400;white-space:nowrap;cursor:pointer}
.config-default-toggle__dot{width:6px;height:6px;flex:0 0 6px;border:1px solid currentColor;border-radius:50%}
.config-default-toggle.is-default{border-color:#94bfff;background:#e8f3ff;color:#165dff;font-weight:500}
.config-default-toggle.is-default .config-default-toggle__dot{background:currentColor}
.config-default-toggle:hover:not(:disabled){border-color:#4080ff;color:#165dff}
.config-default-toggle:focus-visible{outline:2px solid #165dff;outline-offset:2px}
.config-default-toggle:disabled{border-color:#e5e6eb;background:#f7f8fa;color:#86909c;cursor:not-allowed}
.table-wrap th,.table-wrap td{box-sizing:border-box;padding-right:16px;padding-left:16px}
/* 配置列表在自身容器内横向滚动，内容按列单行展示，操作列仍固定。 */
.config-table-wrap{scrollbar-gutter:stable;scrollbar-width:thin;scrollbar-color:transparent transparent}
.config-table-wrap:hover,.config-table-wrap.config-scroll--active{scrollbar-color:rgba(78,89,105,.55) transparent}
.config-table-wrap::-webkit-scrollbar{width:8px;height:8px}
.config-table-wrap::-webkit-scrollbar-track{background:transparent}
.config-table-wrap::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background-color:transparent;background-clip:padding-box}
.config-table-wrap:hover::-webkit-scrollbar-thumb,.config-table-wrap.config-scroll--active::-webkit-scrollbar-thumb{background-color:rgba(78,89,105,.55)}
.config-table-wrap::-webkit-scrollbar-thumb:hover{background-color:rgba(78,89,105,.8)}
.config-table-wrap table{width:max-content;min-width:max(100%,1350px)}
.config-table-wrap :is(th,td){white-space:nowrap}
.config-table-wrap tbody tr{cursor:default}
.config-id-col{color:#4e5969}
/* 筛选输入框固定为紧凑宽度；查询与新建使用同一主按钮。 */
.config-search-form{display:flex;min-width:0;margin-left:auto;align-items:center;gap:16px}
.config-list-actions .config-search-input.arco-input-wrapper{width:240px;max-width:240px;margin-left:0;flex:0 1 240px}
.config-search-form .config-search-button{height:32px;padding:0 16px;border-radius:4px;font-size:14px;line-height:22px}
.config-search-form .config-search-button:hover{border-color:#4080ff!important;background:#4080ff!important}
/* 自定义分页摘要由父组件定位，避免插槽内容在共享分页组件中靠左。 */
.config-list :deep(.list-pagination){justify-content:flex-end}
.config-list :deep(.config-page-summary){margin-left:auto;white-space:nowrap}
@media (max-width: 767px) {
  .config-workbench {
    display: flex;
    flex-direction: column;
    overflow-y: auto;
  }

  .category-nav {
    flex: 0 0 auto;
    flex-direction: row;
    flex-wrap: wrap;
    align-items: center;
    gap: 8px;
    padding: 8px;
    border-right: 0;
    border-bottom: 1px solid #e5e6eb;
  }

  .category-nav > header {
    display: none;
  }

  .category-nav > button {
    grid-template-columns: minmax(0, 1fr);
    width: auto;
    margin: 0;
    padding: 0 8px;
  }

  .category-nav > button span {
    display: block;
    white-space: nowrap;
  }

  .config-list {
    flex: 1 0 auto;
    min-height: 320px;
  }

  .config-create-dialog > footer {
    flex: 0 0 auto;
    flex-wrap: wrap;
    height: auto;
    gap: 8px;
    padding: 12px 24px;
  }

  .config-create-dialog > footer > button {
    flex: 1 0 auto;
    white-space: nowrap;
  }

  .config-create-dialog > footer > .primary {
    flex-basis: 100%;
  }
}


/* Compact fixed action column; free width belongs to data columns. */
.config-table-wrap :is(th,td).config-action-col{width:152px;min-width:152px;max-width:152px}
.config-usage-col :deep(.arco-switch){vertical-align:middle}
</style>
<style>
/* The wrapper is the only visible shell; global native-input rules must not restyle Arco's inner field. */
.app-workspace .configuration-page .config-list .config-search-input.arco-input-wrapper input.arco-input{box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
.app-workspace .configuration-page .config-list .config-search-input.arco-input-wrapper input.arco-input:focus{border:0!important;background:transparent!important;box-shadow:none!important;outline:0!important}
/* Compact fixed action column; free width belongs to data columns. */
.config-table-wrap :is(th,td).config-action-col{width:152px;min-width:152px;max-width:152px}
.config-usage-col :deep(.arco-switch){vertical-align:middle}
</style>
