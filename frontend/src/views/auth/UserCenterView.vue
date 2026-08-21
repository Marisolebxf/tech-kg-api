<script setup lang="ts">
import { computed, ref } from 'vue'

import avatarFallback from '../../assets/images/avatar-ben.png'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const syncing = ref(false)
const feedback = ref('')

const profile = computed(() => authStore.profile)
const user = computed(() => profile.value?.user)
const avatar = computed(() => user.value?.avatar || avatarFallback)

async function refreshProfile() {
  syncing.value = true
  feedback.value = ''
  try {
    await authStore.refresh()
    feedback.value = '用户和权限信息已同步。'
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '同步失败，请稍后重试。'
  } finally {
    syncing.value = false
  }
}
</script>

<template>
  <div class="user-center">
    <header class="user-center__hero">
      <div>
        <span>USER CENTER</span>
        <p>这里展示统一用户中心同步的身份、角色、机构和 API 权限。</p>
      </div>
      <button type="button" :disabled="syncing" @click="refreshProfile">
        {{ syncing ? '同步中…' : '同步最新权限' }}
      </button>
    </header>

    <p v-if="feedback" class="user-center__feedback">{{ feedback }}</p>

    <section v-if="user" class="profile-grid">
      <article class="profile-card profile-card--identity">
        <div class="profile-card__heading"><strong>身份信息</strong><span>统一用户中心</span></div>
        <div class="identity-block">
          <img :src="avatar" alt="用户头像" />
          <div><h2>{{ user.nickname || user.username }}</h2><p>@{{ user.username }}</p></div>
          <b>{{ user.status === 0 ? '账号正常' : '账号停用' }}</b>
        </div>
        <dl>
          <div><dt>用户编号</dt><dd>{{ user.id }}</dd></div>
          <div><dt>用户类型</dt><dd>{{ user.userType === 2 ? '机构用户' : '系统用户' }}</dd></div>
          <div><dt>手机号码</dt><dd>{{ user.mobile || '未填写' }}</dd></div>
          <div><dt>电子邮箱</dt><dd>{{ user.email || '未填写' }}</dd></div>
        </dl>
      </article>

      <article class="profile-card">
        <div class="profile-card__heading"><strong>角色</strong><span>{{ profile?.roles.length || 0 }} 项 · 应用 {{ profile?.appPermissions.roles.length || 0 }} / 机构 {{ profile?.orgPermissions.roles.length || 0 }}</span></div>
        <div v-if="profile?.roles.length" class="chip-list">
          <span v-for="role in profile.roles" :key="String(role.id)">
            <b>{{ role.name }}</b><small>{{ role.code }} · {{ role.type === 2 ? '机构角色' : '应用角色' }}</small>
          </span>
        </div>
        <p v-else class="empty-state">当前应用尚未分配角色。</p>
      </article>

      <article class="profile-card">
        <div class="profile-card__heading"><strong>关联机构</strong><span>{{ profile?.organizations.length || 0 }} 家</span></div>
        <div v-if="profile?.organizations.length" class="organization-list">
          <div v-for="organization in profile.organizations" :key="String(organization.id)">
            <strong>{{ organization.orgName || '未命名机构' }}</strong>
            <span>{{ organization.creditCode || '暂无统一社会信用代码' }}</span>
          </div>
        </div>
        <p v-else class="empty-state">当前账号没有关联机构。</p>
      </article>

      <article class="profile-card profile-card--permissions">
        <div class="profile-card__heading"><strong>API 操作权限</strong><span>{{ profile?.permissions.length || 0 }} 项</span></div>
        <div v-if="profile?.permissions.length" class="permission-list">
          <code v-for="permission in profile.permissions" :key="permission">{{ permission }}</code>
        </div>
        <p v-else class="empty-state">统一用户中心未返回操作权限标识。</p>
      </article>

      <article class="profile-card profile-card--permissions">
        <div class="profile-card__heading"><strong>授权菜单</strong><span>{{ profile?.menus.length || 0 }} 项</span></div>
        <div v-if="profile?.menus.length" class="menu-list">
          <span v-for="menu in profile.menus" :key="String(menu.id)">
            <b>{{ menu.name }}</b>
            <small>{{ menu.linkType === 1 ? '外部链接' : '内部链接' }} · {{ menu.path || '未配置路径' }}</small>
          </span>
        </div>
        <p v-else class="empty-state">统一用户中心未返回当前应用的菜单授权。</p>
      </article>
    </section>
  </div>
</template>

<style scoped>
.user-center { height: 100%; padding: 6px; overflow: auto; color: #243854; }
.user-center__hero { display: flex; align-items: flex-end; justify-content: space-between; gap: 24px; padding: 24px 26px; border: 1px solid #b9d5f7; border-radius: 10px; background: linear-gradient(120deg, #edf5ff, #fff 56%, #eaf8ff); box-shadow: 0 12px 28px rgba(48,105,194,.1); }
.user-center__hero span { color: #165dff; font-size: 10px; font-weight: 700; letter-spacing: .16em; }
.user-center__hero h1 { margin: 7px 0 5px; font-size: 25px; }
.user-center__hero p { margin: 0; color: #71819a; font-size: 12px; }
.user-center__hero button { height: 36px; padding: 0 15px; border: 1px solid #165dff; border-radius: 6px; background: #165dff; color: #fff; font-size: 12px; cursor: pointer; }
.user-center__hero button:disabled { opacity: .6; cursor: wait; }
.user-center__feedback { margin: 12px 0 0; padding: 10px 13px; border-radius: 7px; background: #eaf6ff; color: #175cd3; font-size: 11px; }
.profile-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 14px; padding-bottom: 20px; }
.profile-card { min-height: 210px; padding: 18px; border: 1px solid #c9ddf6; border-radius: 9px; background: rgba(255,255,255,.92); box-shadow: 0 8px 22px rgba(48,105,194,.07); }
.profile-card__heading { display: flex; align-items: center; justify-content: space-between; padding-bottom: 13px; border-bottom: 1px solid #e4edf8; }
.profile-card__heading strong { font-size: 14px; }
.profile-card__heading span { color: #8492a6; font-size: 10px; }
.identity-block { display: grid; grid-template-columns: 58px minmax(0,1fr) auto; align-items: center; gap: 13px; margin-top: 16px; }
.identity-block img { width: 58px; height: 58px; border: 3px solid #e6f1ff; border-radius: 50%; object-fit: cover; }
.identity-block h2 { margin: 0 0 4px; font-size: 18px; }.identity-block p { margin: 0; color: #7d8da5; font-size: 11px; }
.identity-block > b { padding: 4px 8px; border-radius: 999px; background: #e8f8ef; color: #067647; font-size: 9px; }
.profile-card dl { display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 10px; margin: 18px 0 0; }
.profile-card dl div { padding: 9px 10px; border-radius: 6px; background: #f6f9fd; }.profile-card dt { color: #8a98aa; font-size: 9px; }.profile-card dd { margin: 4px 0 0; overflow: hidden; color: #344761; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.chip-list { display: grid; gap: 9px; margin-top: 15px; }.chip-list > span { display: grid; gap: 4px; padding: 11px 12px; border: 1px solid #dce8f8; border-radius: 7px; background: #f9fbff; }.chip-list b { font-size: 12px; }.chip-list small { color: #8290a4; font-size: 9px; }
.organization-list { display: grid; gap: 9px; margin-top: 15px; }.organization-list > div { display: grid; gap: 5px; padding: 11px 12px; border-left: 3px solid #2e90fa; background: #f7faff; }.organization-list strong { font-size: 12px; }.organization-list span { color: #8290a4; font-size: 9px; }
.profile-card--permissions { grid-column: 1 / -1; min-height: 150px; }.permission-list { display: flex; flex-wrap: wrap; gap: 7px; margin-top: 15px; }.permission-list code { padding: 5px 8px; border: 1px solid #cfe0f7; border-radius: 5px; background: #eef5ff; color: #175cd3; font-size: 10px; }
.menu-list { display: grid; grid-template-columns: repeat(2,minmax(0,1fr)); gap: 9px; margin-top: 15px; }.menu-list>span { display:grid;gap:4px;padding:10px 12px;border:1px solid #dce8f8;border-radius:7px;background:#f9fbff; }.menu-list b { font-size:11px; }.menu-list small { overflow:hidden;color:#8290a4;font-size:9px;text-overflow:ellipsis;white-space:nowrap; }
.empty-state { margin: 28px 0 0; color: #96a2b3; font-size: 11px; text-align: center; }
@media (max-width: 900px) { .profile-grid { grid-template-columns: 1fr; }.profile-card--permissions { grid-column: auto; }.menu-list { grid-template-columns:1fr; }.user-center__hero { align-items: flex-start; flex-direction: column; } }
</style>
