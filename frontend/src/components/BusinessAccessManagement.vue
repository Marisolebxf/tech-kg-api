<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useAuthStore } from '../stores/auth'
import { useGraphSpaceStore } from '../stores/graphSpace'
import { getErrorMessage } from '../api/http'
import { validateGraphSpaceName } from '../utils/configFieldValidation'
import { getBusinessAccessState, saveBusiness, saveBusinessMember, saveBusinessSpace, requestBusinessSpace, decideBusinessSpace, retryBusinessSpace, type BusinessAccessState, type BusinessRole } from '../api/businessAccess'
import GraphSpaceSelector from './GraphSpaceSelector.vue'

const auth = useAuthStore()
const graph = useGraphSpaceStore()
const isAdmin = computed(() => auth.isAdmin)
const state = ref<BusinessAccessState>({ businesses: [], members: [], spaces: [], requests: [], currentBusinessId: '' })
const busy = ref(false)
const error = ref('')
const success = ref('')
const business = ref({ clientId: '', name: '', enabled: true })
const member = ref({ userId: '', clientId: '', role: 'user' as BusinessRole })
const space = ref({ name: '', clientId: '', isSharedProduction: false })
const request = ref({ spaceName: '', reason: '' })
const requestBusinessId = ref('')
const notes = ref<Record<string, string>>({})
const requestError = computed(() => isAdmin.value && !requestBusinessId.value ? '请选择申请业务' : request.value.spaceName ? validateGraphSpaceName(request.value.spaceName) : '请输入图空间名称')
const statusLabels: Record<string, string> = { pending: '待审批', approved: '已批准', rejected: '已驳回', creating: '创建中', failed: '创建失败', created: '已创建', ready: '已创建', completed: '已完成' }
function statusLabel(status: string) { return statusLabels[status.toLowerCase()] || status }
async function load() { state.value = await getBusinessAccessState() }
async function run(action: () => Promise<unknown>) {
  if (busy.value) return
  busy.value = true; error.value = ''; success.value = ''
  try { await action(); await load(); await graph.ensureLoaded(true); success.value = '操作已完成' }
  catch (cause) { error.value = getErrorMessage(cause, '操作失败') }
  finally { busy.value = false }
}
onMounted(() => void run(load))
</script>

<template>
  <section class="business-access" aria-label="业务与图空间管理">
    <!-- 全局图空间切换入口：顶栏已撤、本组件在 RBAC 模式下替换整个图数据空间页，选择器挂头部保证仍可切换 -->
    <header><h2>业务与图空间</h2><GraphSpaceSelector /><button :disabled="busy" @click="run(load)">刷新</button></header>
    <p>同一业务的账号共享所属图空间；共享生产空间允许查询、开发维护写入与构建，人工审核由管理员处理。</p>
    <p v-if="error" role="alert" class="error">{{ error }}</p><p v-if="success" role="status">{{ success }}</p>
    <fieldset v-if="isAdmin" :disabled="busy">
      <legend>业务管理</legend>
      <form @submit.prevent="run(() => saveBusiness(business.clientId, { name: business.name, enabled: business.enabled }))">
        <label>业务标识<input v-model.trim="business.clientId" required maxlength="64" /></label>
        <label>业务名称<input v-model.trim="business.name" required maxlength="64" /></label>
        <label><input v-model="business.enabled" type="checkbox" />启用</label><button type="submit">保存业务</button>
      </form>
      <table><thead><tr><th>业务标识</th><th>业务名称</th><th>状态</th><th>操作</th></tr></thead><tbody><tr v-for="row in state.businesses" :key="row.clientId"><td>{{ row.clientId }}</td><td>{{ row.name }}</td><td>{{ row.enabled ? '启用' : '停用' }}</td><td><button @click="business = { ...row }">编辑</button></td></tr></tbody></table>
    </fieldset>
    <fieldset v-if="isAdmin" :disabled="busy">
      <legend>账号归属与角色</legend>
      <form @submit.prevent="run(() => saveBusinessMember(member.userId, { clientId: member.clientId || null, role: member.role }))">
        <label>统一认证用户 ID<input v-model.trim="member.userId" required list="business-account-list" /><datalist id="business-account-list"><option v-for="row in state.members" :key="row.userId" :value="row.userId">{{ row.nickname || row.username }}</option></datalist></label>
        <label>所属业务<select v-model="member.clientId"><option value="">未绑定</option><option v-for="row in state.businesses" :key="row.clientId" :value="row.clientId">{{ row.name }}（{{ row.clientId }}）</option></select></label>
        <label>角色<select v-model="member.role"><option value="user">普通角色</option><option value="developer">开发维护</option><option value="admin">管理员</option></select></label><button type="submit">保存账号绑定</button>
      </form>
      <table><thead><tr><th>账号</th><th>用户 ID</th><th>业务</th><th>角色</th><th>操作</th></tr></thead><tbody><tr v-for="row in state.members" :key="row.userId"><td>{{ row.nickname || row.username }}</td><td>{{ row.userId }}</td><td>{{ row.clientId || '未绑定' }}</td><td>{{ row.role === 'admin' ? '管理员' : row.role === 'developer' ? '开发维护' : '普通角色' }}</td><td><button @click="member = { userId: row.userId, clientId: row.clientId || '', role: row.role }">编辑</button></td></tr></tbody></table>
    </fieldset>
    <fieldset :disabled="busy">
      <legend>图空间归属</legend>
      <form v-if="isAdmin" @submit.prevent="run(() => saveBusinessSpace(space.name, { clientId: space.isSharedProduction ? null : space.clientId || null, isSharedProduction: space.isSharedProduction }))">
        <label>图空间名称<input v-model.trim="space.name" required list="business-space-list" /><datalist id="business-space-list"><option v-for="row in state.spaces" :key="row.name" :value="row.name" /></datalist></label>
        <label>所属业务<select v-model="space.clientId" :disabled="space.isSharedProduction"><option value="">未分配</option><option v-for="row in state.businesses" :key="row.clientId" :value="row.clientId">{{ row.name }}（{{ row.clientId }}）</option></select></label>
        <label><input v-model="space.isSharedProduction" type="checkbox" />共享生产空间</label><button type="submit">保存空间归属</button>
      </form>
      <table><thead><tr><th>空间</th><th>业务</th><th>类型</th><th v-if="isAdmin">操作</th></tr></thead><tbody><tr v-for="row in state.spaces" :key="row.name"><td>{{ row.name }}</td><td>{{ row.clientId || '—' }}</td><td>{{ row.isSharedProduction ? '共享生产' : '业务私有' }}</td><td v-if="isAdmin"><button @click="space = { ...row, clientId: row.clientId || '' }">编辑</button></td></tr></tbody></table>
    </fieldset>
    <fieldset :disabled="busy">
      <legend>新建空间申请</legend>
      <p v-if="!isAdmin && !state.currentBusinessId">当前账号尚未绑定业务；绑定后可提交空间申请。</p>
      <form v-else @submit.prevent="!requestError && run(() => requestBusinessSpace({ ...request, ...(isAdmin ? { clientId: requestBusinessId } : {}) }))">
        <label v-if="isAdmin">申请业务<select v-model="requestBusinessId" aria-label="申请业务" required><option value="">请选择业务</option><option v-for="row in state.businesses.filter(item => item.enabled)" :key="row.clientId" :value="row.clientId">{{ row.name }}（{{ row.clientId }}）</option></select></label><label>图空间名称<input v-model.trim="request.spaceName" required maxlength="64" /></label><label>申请说明<input v-model.trim="request.reason" maxlength="500" /></label><button type="submit" :disabled="Boolean(requestError)">提交申请</button>
        <small v-if="request.spaceName && requestError" class="error">{{ requestError }}</small>
      </form>
      <table><thead><tr><th>空间／业务</th><th>申请人／时间</th><th>状态</th><th>说明</th><th v-if="isAdmin">审批操作</th></tr></thead><tbody><tr v-for="row in state.requests" :key="row.id"><td>{{ row.spaceName }}<br />{{ row.clientId }}</td><td>{{ row.requestedBy }}<br />{{ row.createdAt }}</td><td>{{ statusLabel(row.status) }}</td><td>{{ row.reason }}<br />{{ row.reviewNote }}<span class="error">{{ row.lastError }}</span></td><td v-if="isAdmin"><template v-if="row.status.toLowerCase() === 'pending'"><input v-model="notes[row.id]" aria-label="审批说明" placeholder="审批说明" maxlength="500" /><button @click="run(() => decideBusinessSpace(row.id, true, notes[row.id] || ''))">批准</button><button @click="run(() => decideBusinessSpace(row.id, false, notes[row.id] || ''))">驳回</button></template><button v-if="row.canRetry ?? (row.status.toLowerCase() === 'failed')" @click="run(() => retryBusinessSpace(row.id))">重试创建</button></td></tr><tr v-if="!state.requests.length"><td :colspan="isAdmin ? 5 : 4">暂无空间申请</td></tr></tbody></table>
    </fieldset>
  </section>
</template>

<style scoped>
.business-access { padding: 24px; overflow: auto; color: #344054; }
header, form { display:flex; align-items:center; gap:12px; flex-wrap:wrap; }
header { justify-content:space-between; } h2 { margin:0; font-size:18px; }
fieldset { border:1px solid #e4e7ec; border-radius:8px; margin:20px 0; padding:16px; min-width:0; }
legend { font-weight:600; } label { display:flex; gap:8px; align-items:center; }
input, select, button { padding:7px 10px; border:1px solid #d0d5dd; border-radius:4px; }
button { background:#f0f5ff; color:#175cd3; cursor:pointer; } button:disabled { opacity:.5; cursor:default; }
table { width:100%; border-collapse:collapse; margin-top:14px; font-size:13px; } th,td { padding:10px; text-align:left; border-bottom:1px solid #eaecf0; overflow-wrap:anywhere; }
.error { color:#b42318; } td button { margin:3px; } p { line-height:1.6; }
</style>

