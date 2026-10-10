<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { getBusinessAccessState, saveBusinessMember, saveBusinessSpace, type BusinessAccessState, type BusinessMember } from '../api/businessAccess'
import { useAuthStore } from '../stores/auth'
import { useGraphSpaceStore } from '../stores/graphSpace'
import { useToast } from '../composables/use-toast'

const state = ref<BusinessAccessState>({ businesses: [], members: [], spaces: [] })
const error = ref('')
const loading = ref(false)
const saving = ref('')
const spaceOwners = ref<Record<string, string>>({})
const { showToast } = useToast()
async function load() {
  loading.value = true
  error.value = ''
  try {
    state.value = await getBusinessAccessState()
    for (const member of state.value.members) member.clientIds ??= member.clientId ? [member.clientId] : []
    spaceOwners.value = Object.fromEntries(state.value.spaces.map((space) => [space.name, space.isSharedProduction ? '__public__' : space.clientId || '__unassigned__']))
  } catch (cause) { error.value = cause instanceof Error ? cause.message : '加载失败' }
  finally { loading.value = false }
}
async function saveMember(member: BusinessMember) {
  if (saving.value || member.role === 'developer' && !member.clientIds.length) return
  saving.value = `member:${member.userId}`
  try {
    await saveBusinessMember(member)
    showToast('成员业务权限已保存', 'success')
    if (String(useAuthStore().profile?.user.id) === member.userId) await useAuthStore().loadCurrentUser(true)
    await useGraphSpaceStore().ensureLoaded(true)
  } catch (cause) { showToast(cause instanceof Error ? cause.message : '保存失败', 'error') }
  finally { saving.value = '' }
}
async function saveSpace(name: string) {
  if (saving.value) return
  saving.value = `space:${name}`
  try {
    const owner = spaceOwners.value[name]
    await saveBusinessSpace(name, owner?.startsWith('__') ? null : owner || null, owner === '__public__')
    await useGraphSpaceStore().ensureLoaded(true)
    showToast('图空间归属已保存', 'success')
  } catch (cause) { showToast(cause instanceof Error ? cause.message : '保存失败', 'error') }
  finally { saving.value = '' }
}
onMounted(load)
</script>

<template>
  <section class="business-access-panel">
    <header><h2>业务权限</h2><a-button :loading="loading" @click="load">刷新</a-button></header>
    <a-alert v-if="error" type="error">{{ error }}</a-alert>
    <h3>成员与业务</h3>
    <p>开发人员可绑定多个业务；公共图空间始终只读。</p>
    <table><thead><tr><th>用户</th><th>角色</th><th>绑定业务</th><th>操作</th></tr></thead><tbody>
      <tr v-for="member in state.members" :key="member.userId">
        <td>{{ member.displayName || member.username || member.userId }}<small>{{ member.userId }}</small></td>
        <td><a-select v-model="member.role" aria-label="成员角色"><a-option value="user">普通用户</a-option><a-option value="developer">开发人员</a-option><a-option value="admin">管理员</a-option></a-select></td>
        <td><a-select v-model="member.clientIds" multiple :disabled="member.role !== 'developer'" aria-label="绑定业务" placeholder="选择业务（可多选）"><a-option v-for="business in state.businesses.filter(b => b.enabled)" :key="business.clientId" :value="business.clientId">{{ business.name }}</a-option></a-select></td>
        <td><a-button :disabled="!!saving || member.role === 'developer' && !member.clientIds.length" @click="saveMember(member)">保存</a-button></td>
      </tr>
    </tbody></table>
    <h3>图空间归属</h3>
    <p>未归属空间仅管理员可见。请核实实际业务后保存归属。</p>
    <table><thead><tr><th>图空间</th><th>所属目录</th><th>操作</th></tr></thead><tbody>
      <tr v-for="space in state.spaces" :key="space.name">
        <td>{{ space.name }}</td>
        <td><a-select v-model="spaceOwners[space.name]" aria-label="图空间归属"><a-option value="__public__">公共图空间</a-option><a-option value="__unassigned__">未归属空间</a-option><a-option v-for="business in state.businesses.filter(b => b.enabled)" :key="business.clientId" :value="business.clientId">{{ business.name }}</a-option></a-select></td>
        <td><a-button :disabled="!!saving" @click="saveSpace(space.name)">保存归属</a-button></td>
      </tr>
    </tbody></table>
  </section>
</template>

<style scoped>
.business-access-panel{padding:20px;overflow:auto;width:100%;box-sizing:border-box}.business-access-panel header{display:flex;justify-content:space-between;align-items:center}.business-access-panel h2{margin:0;font-size:18px}.business-access-panel p,small{color:#86909c}small{display:block;margin-top:4px}.business-access-panel table{width:100%;border-collapse:collapse}.business-access-panel th,.business-access-panel td{padding:12px;text-align:left;border-bottom:1px solid #e5e6eb}.business-access-panel th{background:#f7f8fa}.business-access-panel :deep(.arco-select-view){min-width:140px}.business-access-panel td:nth-child(3) :deep(.arco-select-view){min-width:260px}
</style>
