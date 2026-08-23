<script setup lang="ts">
import { Message } from '@arco-design/web-vue'
import { computed, onMounted, ref } from 'vue'

import { listPlatformMembers, setMemberAdmin, type PlatformMember } from '../../api/corrections'
import { getErrorMessage } from '../../api/http'
import { getExampleMembers } from '../../data/adminGovernanceExamples'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const loading = ref(false)
const changingId = ref('')
const members = ref<PlatformMember[]>([])
const dataMode = ref<'live' | 'example'>('live')
const exampleFallbackEnabled = import.meta.env.VITE_ADMIN_EXAMPLE_FALLBACK !== 'false'
const adminCount = computed(() => members.value.filter((item) => item.isAdmin).length)

function errorMessage(error: unknown) {
  return getErrorMessage(error, '操作失败')
}
async function load() {
  loading.value = true
  try {
    const result = await listPlatformMembers()
    if (result.items.length) { members.value = result.items; dataMode.value = 'live' }
    else if (exampleFallbackEnabled) applyExampleData()
    else { members.value = []; dataMode.value = 'live' }
  } catch (error) {
    if (exampleFallbackEnabled) applyExampleData()
    else Message.error(errorMessage(error))
  } finally { loading.value = false }
}
function applyExampleData() {
  const items = getExampleMembers()
  const user = authStore.profile?.user
  if (user && !items.some((item) => item.userId === String(user.id))) {
    items.unshift({ userId: String(user.id), username: user.username, nickname: user.nickname, email: user.email, isAdmin: true, lastSeenAt: new Date().toISOString() })
  }
  members.value = items
  dataMode.value = 'example'
}
async function toggleAdmin(member: PlatformMember) {
  const next = !member.isAdmin
  if (!window.confirm(`确认${next ? '设为' : '取消'}“${member.nickname || member.username}”的全局管理员权限吗？`)) return
  if (dataMode.value === 'example') { member.isAdmin = next; Message.success('示例成员权限已更新'); return }
  changingId.value = member.userId
  try { await setMemberAdmin(member.userId, next); member.isAdmin = next; Message.success('成员权限已更新') } catch (error) { Message.error(errorMessage(error)) } finally { changingId.value = '' }
}
if (exampleFallbackEnabled) applyExampleData()
onMounted(() => { void load() })
</script>

<template>
  <div class="member-page">
    <header class="page-heading"><a-button :loading="loading" @click="load">刷新</a-button></header>
    <section class="member-summary"><article><span>已登录成员</span><strong>{{ members.length }}</strong></article><article><span>全局管理员</span><strong>{{ adminCount }}</strong></article></section>
    <section class="member-panel"><div><table><colgroup><col class="col-member"><col class="col-id"><col class="col-email"><col class="col-time"><col class="col-role"><col class="col-action"></colgroup><thead><tr><th>成员</th><th>统一用户中心 ID</th><th>邮箱</th><th>最后访问</th><th>平台角色</th><th>操作</th></tr></thead><tbody><tr v-for="member in members" :key="member.userId"><td><span class="member-name">{{ member.nickname || member.username }}</span></td><td><code>{{ member.userId }}</code></td><td>{{ member.email || '—' }}</td><td class="time-cell">{{ member.lastSeenAt?.replace('T', ' ').slice(0, 16) || '—' }}</td><td><span class="role">{{ member.isAdmin ? '全局管理员' : '普通用户' }}</span></td><td><button class="member-action" type="button" :disabled="changingId === member.userId || (String(authStore.profile?.user.id) === member.userId && member.isAdmin)" @click="toggleAdmin(member)">{{ member.isAdmin ? '取消管理员' : '设为管理员' }}</button></td></tr><tr v-if="!members.length"><td colspan="6" class="empty">{{ loading ? '正在加载…' : '暂无成员记录；用户首次登录后会自动出现在这里。' }}</td></tr></tbody></table></div></section>
  </div>
</template>

<style scoped>
.member-page{display:flex;height:100%;min-height:0;flex-direction:column}.page-heading{display:flex;align-items:flex-end;justify-content:flex-end;margin-bottom:16px}.page-heading span{color:var(--gkx-primary);font-size:10px;letter-spacing:.12em}.page-heading em{margin-left:8px;padding:2px 6px;border-radius:3px;background:#e8f3ff;color:#165dff;font-size:9px;font-style:normal;letter-spacing:0}.page-heading h1{margin:4px 0;font-size:22px}.page-heading p{margin:0;color:var(--gkx-text-secondary);font-size:12px}.member-summary{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin-bottom:14px}.member-summary article{padding:16px;border:1px solid var(--gkx-border);border-radius:6px;background:#fff}.member-summary article{display:flex;align-items:center;justify-content:space-between}.member-summary article span{color:var(--gkx-text-secondary);font-size:12px}.member-summary article strong{font-size:24px}.member-panel{display:flex;flex:1;min-height:0;border:1px solid var(--gkx-border);border-radius:6px;background:#fff;flex-direction:column}.member-panel>div{min-height:0;overflow:auto}.member-panel table{width:100%;border-collapse:collapse;font-size:12px}.member-panel th,.member-panel td{padding:12px 12px;border-bottom:1px solid var(--gkx-border);text-align:left}.member-panel th{background:var(--gkx-bg-subtle);color:var(--gkx-text-secondary)}.member-panel td strong,.member-panel td small{display:block}.member-panel td small{margin-top:3px;color:var(--gkx-text-tertiary)}.role{display:inline-flex;padding:3px 8px;border-radius:99px;background:#eef1f5;color:#667085}.role.admin{background:#e8f3ff;color:#165dff}.empty{height:120px;text-align:center!important;color:var(--gkx-text-tertiary)}@media(max-width:850px){.member-summary{grid-template-columns:1fr 1fr}}
</style>

<style scoped>
.member-panel > div {
  background: var(--gkx-bg-subtle);
}
.member-panel table {
  table-layout: fixed;
  font-size: 14px !important;
}
.member-panel tbody {
  background: #fff;
}
.member-panel th,
.member-panel td {
  padding-right: 10px !important;
  padding-left: 10px !important;
  font-size: 14px !important;
  text-align: left !important;
}
.member-panel th:first-child,
.member-panel td:first-child {
  padding-left: 12px !important;
}
.member-panel .col-member,
.member-panel .col-id,
.member-panel .col-email,
.member-panel .col-time,
.member-panel .col-role,
.member-panel .col-action { width: 16.6667%; }
.member-panel td {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.member-name {
  display: block;
  overflow: hidden;
  font-weight: 400;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.time-cell {
  white-space: nowrap;
}
.role {
  display: inline;
  padding: 0;
  border: 0;
  border-radius: 0;
  background: transparent;
  color: inherit;
}
.member-action {
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--gkx-primary);
  font: inherit;
  white-space: nowrap;
  cursor: pointer;
}
.member-panel td small,
.member-panel td code,
.time-cell,
.role,
.member-action {
  font-size: 14px !important;
}
.member-action:disabled {
  opacity: .45;
  color: var(--gkx-primary);
  cursor: not-allowed;
}
</style>
