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
import { useToast } from '../../composables/use-toast'

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
  isLlm?: boolean
  baseUrl?: string
  model?: string
  apiKey?: string
  hasApiKey?: boolean
  apiKeyMasked?: string
  isDefault?: boolean
}

const { showToast } = useToast()

const categories = [
  { key: '模型服务', label: '模型与抽取服务', icon: 'AI' },
  { key: '调度', label: '调度与运行策略', icon: 'CR' },
]

const scheduleMockItems: ConfigItem[] = [
  { id: 'SCHEDULE-DEFAULT', category: '调度', name: '生产默认调度策略', description: '错峰运行、失败重试与告警通知', type: 'Schedule Policy', endpoint: 'Asia/Shanghai · 02:00', owner: '平台运维组', updatedAt: '2026-07-19 08:15', status: '正常', usage: '9 条 Pipeline' },
  { id: 'RUNTIME-LARGE', category: '调度', name: '大批量运行资源组', description: '适用于百万级以上批量抽取任务', type: 'Runtime Profile', endpoint: '16 worker · 64 GB', owner: '平台运维组', updatedAt: '2026-07-12 16:55', status: '正常', usage: '并发上限 4' },
]

const items = ref<ConfigItem[]>([])
const activeCategory = ref('模型服务')
const keyword = ref('')
const statusFilter = ref('全部状态')
const selected = ref<ConfigItem | null>(null)
const dialogOpen = ref(false)
const testingId = ref('')
const saving = ref(false)
const form = ref({
  name: '',
  baseUrl: '',
  model: 'glm-4.7-flash',
  apiKey: '',
  owner: '算法平台组',
  description: '',
  isDefault: false,
})

const isLlmCategory = computed(() => activeCategory.value === '模型服务')

const visibleItems = computed(() => items.value.filter((item) => {
  const matchCategory = item.category === activeCategory.value
  const query = keyword.value.trim().toLowerCase()
  const endpointOrUrl = item.baseUrl || item.endpoint
  const matchKeyword = !query || `${item.name}${item.id}${item.type}${endpointOrUrl}${item.model || ''}`.toLowerCase().includes(query)
  const matchStatus = statusFilter.value === '全部状态' || item.status === statusFilter.value
  return matchCategory && matchKeyword && matchStatus
}))

const summary = computed(() => ({
  total: items.value.filter((i) => i.category === activeCategory.value).length,
  healthy: items.value.filter((i) => i.category === activeCategory.value && i.status === '正常').length,
  warning: items.value.filter((i) => i.category === activeCategory.value && i.status === '异常').length,
  references: 28,
}))

function categoryCount(key: string) {
  return items.value.filter((i) => i.category === key).length
}

function toConfigItem(cfg: LlmConfig): ConfigItem {
  return {
    id: cfg.id,
    category: '模型服务',
    name: cfg.name,
    description: cfg.description,
    type: 'LLM API',
    endpoint: cfg.baseUrl,
    owner: cfg.owner || '算法平台组',
    updatedAt: cfg.updatedAt,
    status: (cfg.status === '正常' ? '正常' : cfg.status === '停用' ? '停用' : '异常') as ConfigStatus,
    usage: cfg.isDefault ? '默认抽取模型' : '尚未引用',
    isLlm: true,
    baseUrl: cfg.baseUrl,
    model: cfg.model,
    hasApiKey: cfg.hasApiKey,
    apiKeyMasked: cfg.apiKeyMasked,
    isDefault: cfg.isDefault,
  }
}

async function loadLlmConfigs() {
  try {
    const data = await listLlmConfigs(currentUserId())
    const llmItems = data.map(toConfigItem)
    const others = items.value.filter((i) => i.category !== '模型服务')
    items.value = [...llmItems, ...others]
  } catch (err) {
    showToast(`加载 LLM 配置失败：${(err as Error).message}`, 'warning')
  }
}

async function switchCategory(key: string) {
  activeCategory.value = key
  selected.value = null
  if (key === '模型服务') {
    await loadLlmConfigs()
  } else if (key === '调度') {
    const others = items.value.filter((i) => i.category !== '调度')
    items.value = [...others, ...scheduleMockItems]
  }
}

function openCreate() {
  if (isLlmCategory.value) {
    form.value = {
      name: '',
      baseUrl: 'https://open.bigmodel.cn/api/paas/v4',
      model: 'glm-4.7-flash',
      apiKey: '',
      owner: '算法平台组',
      description: '',
      isDefault: false,
    }
  } else {
    form.value = {
      name: '',
      baseUrl: '',
      model: '',
      apiKey: '',
      owner: '平台运维组',
      description: '',
      isDefault: false,
    }
  }
  dialogOpen.value = true
}

async function saveConfig() {
  if (!form.value.name.trim() || !form.value.baseUrl.trim()) return
  if (!isLlmCategory.value) {
    showToast('该类别暂未接通后端，仅模型服务支持保存。', 'warning')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.value.name.trim(),
      baseUrl: form.value.baseUrl.trim(),
      model: form.value.model.trim(),
      apiKey: form.value.apiKey.trim(),
      owner: form.value.owner.trim(),
      description: form.value.description.trim(),
      isDefault: form.value.isDefault,
      status: '正常' as const,
    }
    await createLlmConfig(payload, currentUserId())
    dialogOpen.value = false
    showToast(`“${payload.name}”已保存，下次 LLM 调用生效。`, 'success')
    await loadLlmConfigs()
  } catch (err) {
    showToast(`保存失败：${(err as Error).message}`, 'warning')
  } finally {
    saving.value = false
  }
}

async function saveDetail() {
  if (!selected.value || !selected.value.isLlm) {
    showToast('该类别暂未接通后端。', 'warning')
    return
  }
  const item = selected.value
  saving.value = true
  try {
    const payload = {
      name: item.name,
      description: item.description,
      baseUrl: item.baseUrl || '',
      model: item.model || '',
      owner: item.owner,
      apiKey: item.apiKey || '',
      status: item.status,
    }
    const updated = await updateLlmConfig(item.id, payload, currentUserId())
    selected.value = { ...selected.value, ...toConfigItem(updated), apiKey: '' }
    await loadLlmConfigs()
    showToast(`“${item.name}”的修改已保存。`, 'success')
  } catch (err) {
    showToast(`保存失败：${(err as Error).message}`, 'warning')
  } finally {
    saving.value = false
  }
}

async function testConnection(item: ConfigItem) {
  if (!item.isLlm) {
    showToast('该类别暂未接通后端测试。', 'warning')
    return
  }
  testingId.value = item.id
  try {
    const result = await testLlmConfig(item.id, currentUserId())
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
  if (!item.isLlm) {
    item.status = item.status === '停用' ? '正常' : '停用'
    showToast(`${item.name}已${item.status === '停用' ? '停用' : '启用'}。`, 'info')
    return
  }
  const nextStatus: ConfigStatus = item.status === '停用' ? '正常' : '停用'
  try {
    const updated = await updateLlmConfig(item.id, { status: nextStatus }, currentUserId())
    Object.assign(item, toConfigItem(updated))
    showToast(`${item.name}已${nextStatus === '停用' ? '停用' : '启用'}。`, 'info')
    await loadLlmConfigs()
  } catch (err) {
    showToast(`切换状态失败：${(err as Error).message}`, 'warning')
  }
}

async function setAsDefault(item: ConfigItem) {
  if (!item.isLlm) return
  try {
    await setDefaultLlmConfig(item.id, currentUserId())
    showToast(`“${item.name}”已设为默认，下次 LLM 调用生效。`, 'success')
    await loadLlmConfigs()
    const fresh = items.value.find((i) => i.id === item.id)
    if (fresh && selected.value) selected.value = { ...selected.value, ...fresh }
  } catch (err) {
    showToast(`设为默认失败：${(err as Error).message}`, 'warning')
  }
}

async function removeConfig(item: ConfigItem) {
  if (!item.isLlm) {
    showToast('该类别暂未接通后端。', 'warning')
    return
  }
  if (!window.confirm(`确认删除配置“${item.name}”？删除后不可恢复。`)) return
  try {
    await deleteLlmConfig(item.id, currentUserId())
    showToast(`“${item.name}”已删除。`, 'success')
    selected.value = null
    await loadLlmConfigs()
  } catch (err) {
    showToast(`删除失败：${(err as Error).message}`, 'warning')
  }
}

onMounted(() => {
  loadLlmConfigs()
})
</script>

<template>
  <div class="configuration-page">
    <header class="page-header">
      <div><span>PLATFORM CONFIGURATION</span><h1>配置管理</h1><p>统一管理 Pipeline 运行依赖的模型服务与调度策略。模型服务接通后端，配置项真正驱动 LLM 调用。</p></div>
      <button class="primary" type="button" @click="openCreate">＋ 新建配置</button>
    </header>

    <section class="summary-grid">
      <article><i class="blue">∑</i><div><span>配置总数</span><strong>{{ summary.total }}</strong><small>当前类别</small></div></article>
      <article><i class="green">✓</i><div><span>运行正常</span><strong>{{ summary.healthy }}</strong><small>当前类别</small></div></article>
      <article><i class="orange">!</i><div><span>需要关注</span><strong>{{ summary.warning }}</strong><small>异常配置</small></div></article>
      <article><i class="purple">↗</i><div><span>默认 LLM</span><strong>{{ items.find(i => i.isLlm && i.isDefault)?.name || '未设置' }}</strong><small>下次调用生效</small></div></article>
    </section>

    <section class="config-workbench">
      <aside class="category-nav">
        <header><strong>配置分类</strong><span>按能力域管理</span></header>
        <button v-for="category in categories" :key="category.key" type="button" :class="{ active: activeCategory === category.key }" @click="switchCategory(category.key)">
          <i>{{ category.icon }}</i><span><strong>{{ category.label }}</strong><small>{{ category.key === '模型服务' ? 'LLM 配置，接通后端' : '定时、重试与资源配置（mock）' }}</small></span><em>{{ categoryCount(category.key) }}</em>
        </button>
        <section><b>凭据安全</b><p>API Key 在数据库明文保存（第一版），页面仅展示脱敏值。后续将接入密钥中心。</p></section>
      </aside>

      <main class="config-list">
        <header><div><h2>{{ categories.find(item => item.key === activeCategory)?.label }}</h2><span>{{ visibleItems.length }} 项配置</span></div><nav><input v-model="keyword" placeholder="搜索名称、标识或地址" /><select v-model="statusFilter"><option>全部状态</option><option>正常</option><option>异常</option><option>停用</option></select></nav></header>
        <div class="table-wrap">
          <table>
            <thead><tr><th>配置名称</th><th>类型 / 地址</th><th>状态</th><th>引用情况</th><th>负责人 / 更新时间</th><th>操作</th></tr></thead>
            <tbody>
              <tr v-for="item in visibleItems" :key="item.id" @click="selected=item">
                <td><div class="config-name"><i>{{ item.category === '模型服务' ? 'AI' : 'CR' }}</i><span><strong>{{ item.name }}<b v-if="item.isDefault" class="default-tag">默认</b></strong><small>{{ item.id }} · {{ item.description }}</small></span></div></td>
                <td><strong class="type-name">{{ item.type }}<template v-if="item.model"> · {{ item.model }}</template></strong><code>{{ item.baseUrl || item.endpoint }}</code></td>
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
      <section class="health-card"><i :class="`is-${selected.status}`" /><div><strong>{{ selected.status === '正常' ? '配置可用' : selected.status === '异常' ? '连接存在异常' : '配置已停用' }}</strong><span>{{ selected.isLlm ? '后端真实探活' : '最近健康检查：2 分钟前' }}</span></div><button type="button" :disabled="testingId === selected.id || !selected.isLlm" @click="testConnection(selected)">{{ testingId === selected.id ? '测试中…' : '测试连接' }}</button></section>
      <div class="detail-form">
        <label><span>配置名称</span><input v-model="selected.name" /></label>
        <label><span>服务类型</span><input v-model="selected.type" /></label>
        <label v-if="selected.isLlm" class="wide"><span>Base URL</span><input v-model="selected.baseUrl" placeholder="https://open.bigmodel.cn/api/paas/v4" /></label>
        <label v-if="selected.isLlm"><span>模型</span><input v-model="selected.model" placeholder="glm-4.7-flash" /></label>
        <label v-if="!selected.isLlm" class="wide"><span>连接地址 / 版本</span><input v-model="selected.endpoint" /></label>
        <label class="wide"><span>配置说明</span><textarea v-model="selected.description" /></label>
        <label><span>负责人</span><input v-model="selected.owner" /></label>
        <label v-if="selected.isLlm"><span>访问凭据</span><input :value="selected.apiKeyMasked || (selected.hasApiKey ? '••••••••' : '未设置')" readonly /></label>
        <label v-if="selected.isLlm" class="wide"><span>更新 API Key（留空保留原值）</span><input v-model="selected.apiKey" type="password" placeholder="输入新 Key 覆盖原值" /></label>
      </div>
      <section class="reference-card"><header><strong>引用关系</strong><span>{{ selected.usage }}</span></header><p>配置变更将在下次 LLM 调用时生效（默认配置的单例会自动失效重建）。</p></section>
      <footer>
        <button v-if="selected.isLlm && !selected.isDefault" type="button" @click="setAsDefault(selected)">设为默认</button>
        <button type="button" @click="toggleItem(selected)">{{ selected.status === '停用' ? '启用配置' : '停用配置' }}</button>
        <button v-if="selected.isLlm" type="button" @click="removeConfig(selected)">删除</button>
        <button class="primary" type="button" :disabled="saving || !selected.isLlm" @click="saveDetail">{{ saving ? '保存中…' : '保存修改' }}</button>
      </footer>
    </aside>

    <aside v-if="dialogOpen" class="create-dialog">
      <header><div><span>NEW CONFIGURATION</span><h2>新建{{ categories.find(item => item.key === activeCategory)?.label }}</h2></div><button type="button" @click="dialogOpen=false">×</button></header>
      <div class="dialog-form">
        <template v-if="isLlmCategory">
          <label class="wide"><span>配置名称 *</span><input v-model="form.name" placeholder="例如：科技文本抽取大模型" /></label>
          <label class="wide"><span>Base URL *</span><input v-model="form.baseUrl" placeholder="https://open.bigmodel.cn/api/paas/v4" /></label>
          <label><span>模型 *</span><input v-model="form.model" placeholder="glm-4.7-flash" /></label>
          <label><span>负责人</span><input v-model="form.owner" /></label>
          <label class="wide"><span>API Key</span><input v-model="form.apiKey" type="password" placeholder="明文保存到数据库，页面脱敏展示" /></label>
          <label class="wide"><span>说明</span><textarea v-model="form.description" placeholder="说明用途或变更影响" /></label>
          <label class="wide checkbox"><input type="checkbox" v-model="form.isDefault" /><span>设为默认（同一时刻仅一条默认 LLM 生效）</span></label>
        </template>
        <template v-else>
          <p class="empty" style="grid-column:1/-1">该类别暂未接通后端，仅「模型服务」支持新建。</p>
        </template>
      </div>
      <footer><button type="button" @click="dialogOpen=false">取消</button><button class="primary" type="button" :disabled="!isLlmCategory || !form.name.trim() || !form.baseUrl.trim() || !form.model.trim() || saving" @click="saveConfig">{{ saving ? '保存中…' : '保存' }}</button></footer>
    </aside>
  </div>
</template>

<style scoped>
.configuration-page{display:flex;box-sizing:border-box;height:100%;min-height:0;overflow:hidden;color:#17233b;flex-direction:column}.page-header{display:flex;flex:0 0 auto;align-items:flex-end;justify-content:space-between;margin-bottom:12px}.page-header span{color:#165dff;font-size:9px;letter-spacing:.12em}.page-header h1{margin:3px 0 0;font-size:22px}.page-header p{margin:4px 0 0;color:#66758f;font-size:11px}.primary{border-color:#165dff!important;background:#165dff!important;color:#fff!important}.page-header button{height:34px;padding:0 14px;border:0;border-radius:6px;cursor:pointer}.summary-grid{display:grid;flex:0 0 auto;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:10px}.summary-grid article{display:flex;align-items:center;gap:11px;padding:10px 13px;border:1px solid #bdd7ff;border-radius:8px;background:linear-gradient(145deg,#fff,#f2f8ff)}.summary-grid article>i{display:grid;place-items:center;width:34px;height:34px;border-radius:8px;font-style:normal;font-weight:700}.summary-grid .blue{background:#eaf2ff;color:#165dff}.summary-grid .green{background:#dcfae6;color:#067647}.summary-grid .orange{background:#fff3d8;color:#b54708}.summary-grid .purple{background:#f4f3ff;color:#5925dc}.summary-grid article>div{display:grid;grid-template-columns:1fr auto;flex:1;gap:2px}.summary-grid span,.summary-grid small{color:#71809a;font-size:9px}.summary-grid strong{grid-row:1/3;grid-column:2;font-size:20px}.feedback{display:flex;align-items:center;gap:8px;margin:0 0 10px;padding:8px 11px;border:1px solid #a6f4c5;border-radius:6px;background:#ecfdf3;color:#067647;font-size:10px}.feedback span{display:grid;place-items:center;width:17px;height:17px;border-radius:50%;background:#12b76a;color:#fff}.feedback button{margin-left:auto;border:0;background:transparent;color:#067647;cursor:pointer}.config-workbench{display:grid;flex:1;min-height:0;grid-template-columns:248px minmax(0,1fr);overflow:hidden;border:1px solid #bdd7ff;border-radius:9px;background:#fff}.category-nav{display:flex;min-height:0;border-right:1px solid #dce8f8;background:#f8fbff;flex-direction:column}.category-nav>header{display:grid;gap:3px;padding:14px;border-bottom:1px solid #dce8f8}.category-nav>header strong{font-size:13px}.category-nav>header span{color:#8290a7;font-size:9px}.category-nav>button{display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:9px;width:100%;padding:11px 12px;border:0;border-bottom:1px solid #edf2f8;background:transparent;color:#344766;text-align:left;cursor:pointer}.category-nav>button.active{background:#eaf2ff;box-shadow:inset 3px 0 #165dff}.category-nav>button>i{display:grid;place-items:center;width:30px;height:30px;border-radius:7px;background:#fff;color:#526783;font-size:9px;font-style:normal;font-weight:700}.category-nav>button.active>i{background:#165dff;color:#fff}.category-nav>button>span{display:grid;gap:3px}.category-nav>button strong{font-size:11px}.category-nav>button small{color:#8290a7;font-size:8px}.category-nav>button em{min-width:20px;padding:2px 6px;border-radius:99px;background:#e7eef8;color:#71809a;font-size:9px;font-style:normal;text-align:center}.category-nav>section{margin:auto 12px 12px;padding:11px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.category-nav>section b{font-size:10px}.category-nav>section p{margin:4px 0 6px;color:#71809a;font-size:9px;line-height:15px}.category-nav>section a{color:#165dff;font-size:9px;text-decoration:none}.config-list{display:flex;min-width:0;min-height:0;flex-direction:column}.config-list>header{display:flex;align-items:center;justify-content:space-between;padding:12px 14px;border-bottom:1px solid #dce8f8;background:#fff}.config-list>header>div{display:flex;align-items:baseline;gap:8px}.config-list h2{margin:0;font-size:15px}.config-list>header span{color:#8290a7;font-size:9px}.config-list nav{display:flex;gap:7px}.config-list input,.config-list select{height:31px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font-size:10px}.config-list input{width:210px}.table-wrap{flex:1;min-height:0;overflow:auto}.table-wrap table{width:100%;border-collapse:collapse;font-size:10px}.table-wrap thead{position:sticky;z-index:2;top:0}.table-wrap th,.table-wrap td{padding:10px 11px;border-bottom:1px solid #e7eef7;text-align:left;vertical-align:middle}.table-wrap th{background:#f2f7fd;color:#60708a;font-weight:600;white-space:nowrap}.table-wrap tbody tr{cursor:pointer}.table-wrap tbody tr:hover td{background:#f7faff}.config-name{display:flex;align-items:center;gap:9px;min-width:210px}.config-name>i{display:grid;place-items:center;flex:0 0 auto;width:29px;height:29px;border-radius:7px;background:#eaf2ff;color:#175cd3;font-size:8px;font-style:normal;font-weight:700}.config-name>span{display:grid;gap:3px}.config-name strong{font-size:11px}.config-name small,.updated{display:block;color:#8290a7;font-size:8px}.type-name{display:block;color:#40516d;font-size:10px}.table-wrap code{display:block;max-width:210px;margin-top:3px;overflow:hidden;color:#71809a;font-size:8px;text-overflow:ellipsis;white-space:nowrap}.status{display:inline-flex;align-items:center;gap:5px;padding:3px 7px;border-radius:99px}.status>i{width:6px;height:6px;border-radius:50%;background:currentColor}.status.is-正常{background:#dcfae6;color:#067647}.status.is-异常{background:#fee4e2;color:#b42318}.status.is-停用{background:#eef1f5;color:#667085}.link{border:0;background:transparent;color:#165dff;font-size:10px;cursor:pointer}.empty{height:100px;color:#8290a7;text-align:center!important}.mask{position:fixed;z-index:40;inset:0;border:0;background:rgba(16,36,76,.24)}.detail-drawer{position:fixed;z-index:41;top:0;right:0;display:flex;width:min(500px,90vw);height:100vh;background:#f8fbff;box-shadow:-18px 0 46px rgba(28,58,107,.25);flex-direction:column}.detail-drawer>header,.create-dialog>header{display:flex;align-items:flex-start;justify-content:space-between;padding:18px;border-bottom:1px solid #dce8f8;background:#fff}.detail-drawer>header span,.create-dialog>header span{color:#165dff;font-size:9px}.detail-drawer h2,.create-dialog h2{margin:4px 0;font-size:18px}.detail-drawer>header p{margin:0;color:#71809a;font-size:10px}.detail-drawer>header button,.create-dialog>header button{width:29px;height:29px;border:0;border-radius:5px;background:#f0f4fa;font-size:19px;cursor:pointer}.health-card{display:grid;grid-template-columns:10px minmax(0,1fr) auto;align-items:center;gap:10px;margin:14px 16px 0;padding:12px;border:1px solid #cfe4d7;border-radius:7px;background:#fff}.health-card>i{width:9px;height:9px;border-radius:50%;background:#12b76a;box-shadow:0 0 0 4px rgba(18,183,106,.12)}.health-card>i.is-异常{background:#f04438;box-shadow:0 0 0 4px rgba(240,68,56,.12)}.health-card>i.is-停用{background:#98a2b3;box-shadow:none}.health-card>div{display:grid;gap:3px}.health-card strong{font-size:11px}.health-card span{color:#71809a;font-size:9px}.health-card button{height:29px;padding:0 10px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#165dff;font-size:9px;cursor:pointer}.detail-form,.dialog-form{display:grid;grid-template-columns:1fr 1fr;gap:11px;padding:16px}.detail-form label,.dialog-form label{display:grid;gap:5px}.detail-form label span,.dialog-form label span{color:#60708a;font-size:9px}.detail-form input,.detail-form textarea,.dialog-form input,.dialog-form select,.dialog-form textarea{box-sizing:border-box;width:100%;height:33px;padding:0 9px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#344766;font:10px inherit}.detail-form textarea,.dialog-form textarea{height:65px;padding-top:8px;resize:none}.wide{grid-column:1/-1}.reference-card{margin:0 16px;padding:12px;border:1px solid #d6e3f4;border-radius:7px;background:#fff}.reference-card header{display:flex;justify-content:space-between}.reference-card strong{font-size:10px}.reference-card span{color:#165dff;font-size:9px}.reference-card p{margin:5px 0 0;color:#71809a;font-size:9px;line-height:16px}.detail-drawer>footer,.create-dialog>footer{display:flex;justify-content:flex-end;gap:8px;margin-top:auto;padding:13px 16px;border-top:1px solid #dce8f8;background:#fff}.detail-drawer>footer button,.create-dialog>footer button{height:33px;padding:0 13px;border:1px solid #bdd0ea;border-radius:5px;background:#fff;color:#40516d;cursor:pointer}.create-dialog{position:fixed;z-index:42;top:50%;left:50%;width:min(650px,calc(100vw - 40px));overflow:hidden;border-radius:10px;background:#f8fbff;box-shadow:0 24px 70px rgba(28,58,107,.3);transform:translate(-50%,-50%)}.create-dialog>footer{margin-top:0}.create-dialog button:disabled{opacity:.5;cursor:not-allowed}.default-tag{display:inline-block;margin-left:6px;padding:1px 6px;border-radius:99px;background:#fff3d8;color:#b54708;font-size:8px;font-weight:600;font-style:normal}.checkbox{display:flex;flex-direction:row;align-items:center;gap:8px}.checkbox input{width:auto;height:14px}.checkbox span{color:#344766;font-size:10px}@media(max-width:1100px){.summary-grid{grid-template-columns:repeat(2,1fr)}.config-workbench{grid-template-columns:210px minmax(0,1fr)}}
</style>
