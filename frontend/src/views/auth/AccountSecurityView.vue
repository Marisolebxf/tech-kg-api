<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { getAccountSecurity, type AccountSecurityInfo } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const security = ref<AccountSecurityInfo | null>(null)
const loading = ref(true)
const feedback = ref('')

const user = computed(() => authStore.profile?.user)
const sessionRemaining = computed(() => {
  const seconds = security.value?.sessionRemainingSeconds
  if (seconds === null || seconds === undefined) return '本地开发会话'
  if (seconds <= 0) return '即将过期'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours > 0 ? `${hours} 小时 ${minutes} 分钟` : `${minutes} 分钟`
})

async function loadSecurity() {
  loading.value = true
  feedback.value = ''
  try {
    security.value = await getAccountSecurity()
  } catch (error) {
    feedback.value = error instanceof Error ? error.message : '账号安全信息加载失败。'
  } finally {
    loading.value = false
  }
}

function openUserCenter() {
  if (!security.value?.accountManagementUrl) return
  window.open(security.value.accountManagementUrl, '_blank', 'noopener,noreferrer')
}

onMounted(loadSecurity)
</script>

<template>
  <div class="security-page">
    <header class="security-hero">
      <div><span>ACCOUNT SECURITY</span><h1>账号与安全</h1><p>查看账号绑定和登录保护；密码与基础资料由统一用户中心集中管理。</p></div>
      <b v-if="security">{{ security.accountStatus === '正常' ? '安全状态正常' : '账号状态异常' }}</b>
    </header>

    <p v-if="feedback" class="message is-error">{{ feedback }}</p>
    <p v-else-if="loading" class="message">正在读取账号安全状态…</p>

    <template v-if="security && user">
      <section class="security-summary">
        <article><i>身</i><div><span>认证方式</span><strong>{{ security.authenticationMethod }}</strong><small>本平台不接收账号密码</small></div></article>
        <article><i>会</i><div><span>当前会话</span><strong>{{ sessionRemaining }}</strong><small>{{ security.sessionBackend === 'redis' ? 'Redis 服务端会话' : '本地开发会话' }}</small></div></article>
        <article><i>密</i><div><span>Cookie 保护</span><strong>HttpOnly{{ security.secureCookie ? ' · Secure' : '' }}</strong><small>令牌不会写入浏览器存储</small></div></article>
      </section>

      <section class="security-grid">
        <article class="security-card">
          <header><div><h2>账号绑定</h2><p>信息来自统一用户中心，只读展示。</p></div><span>{{ user.username }}</span></header>
          <div class="security-row"><i>邮</i><div><strong>电子邮箱</strong><span>{{ user.email || '尚未绑定' }}</span></div><b :class="{ pending: !security.emailBound }">{{ security.emailBound ? '已绑定' : '待完善' }}</b></div>
          <div class="security-row"><i>手</i><div><strong>手机号码</strong><span>{{ user.mobile || '尚未绑定' }}</span></div><b :class="{ pending: !security.mobileBound }">{{ security.mobileBound ? '已绑定' : '待完善' }}</b></div>
          <div class="security-row"><i>号</i><div><strong>账号状态</strong><span>用户编号 {{ user.id }}</span></div><b>{{ security.accountStatus }}</b></div>
        </article>

        <article class="security-card">
          <header><div><h2>密码与基础资料</h2><p>本系统不保存密码，也不提供本地改密接口。</p></div></header>
          <div class="managed-panel"><i>✓</i><div><strong>由{{ security.passwordManagedBy }}管理</strong><p>修改密码、绑定邮箱或手机时，将前往统一用户中心；完成后返回本平台同步即可。</p></div></div>
          <button class="primary-action" type="button" :disabled="!security.accountManagementUrl" @click="openUserCenter">前往统一用户中心管理</button>
        </article>

        <article class="security-card recommendations">
          <header><div><h2>安全建议</h2><p>根据当前账号资料生成。</p></div></header>
          <ul><li v-for="item in security.recommendations" :key="item"><i>✓</i><span>{{ item }}</span></li><li><i>✓</i><span>不要向任何人发送 Client Secret、Access Token 或 Session Cookie</span></li></ul>
        </article>
      </section>
    </template>
  </div>
</template>

<style scoped>
.security-page { height:100%;padding:6px;overflow:auto;color:#243854; }
.security-hero { display:flex;align-items:flex-end;justify-content:space-between;gap:24px;padding:24px 26px;border:1px solid #b9d5f7;border-radius:10px;background:linear-gradient(120deg,#edf5ff,#fff 56%,#eaf8ff);box-shadow:0 12px 28px rgba(48,105,194,.1); }
.security-hero span { color:#165dff;font-size:10px;font-weight:700;letter-spacing:.16em; }.security-hero h1 { margin:7px 0 5px;font-size:25px; }.security-hero p { margin:0;color:#71819a;font-size:12px; }.security-hero>b { padding:7px 11px;border-radius:999px;background:#e8f8ef;color:#067647;font-size:10px; }
.message { margin:14px 0 0;padding:12px 14px;border-radius:7px;background:#edf5ff;color:#175cd3;font-size:11px; }.message.is-error { background:#fff0ee;color:#b42318; }
.security-summary { display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:14px; }.security-summary article { display:grid;grid-template-columns:42px minmax(0,1fr);gap:12px;padding:16px;border:1px solid #d1e1f5;border-radius:9px;background:#fff;box-shadow:0 7px 18px rgba(48,105,194,.06); }.security-summary i { display:grid;place-items:center;width:42px;height:42px;border-radius:10px;background:#eaf2ff;color:#165dff;font-style:normal;font-weight:700; }.security-summary div { display:grid;gap:3px; }.security-summary span,.security-summary small { color:#8390a3;font-size:9px; }.security-summary strong { font-size:13px; }
.security-grid { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-top:14px;padding-bottom:20px; }.security-card { padding:18px;border:1px solid #c9ddf6;border-radius:9px;background:rgba(255,255,255,.94);box-shadow:0 8px 22px rgba(48,105,194,.07); }.security-card>header { display:flex;align-items:flex-start;justify-content:space-between;gap:12px;padding-bottom:13px;border-bottom:1px solid #e4edf8; }.security-card h2 { margin:0;font-size:14px; }.security-card header p { margin:5px 0 0;color:#8492a6;font-size:9px; }.security-card header>span { padding:4px 8px;border-radius:999px;background:#f1f6fd;color:#526783;font-size:9px; }
.security-row { display:grid;grid-template-columns:32px minmax(0,1fr) auto;align-items:center;gap:10px;padding:13px 2px;border-bottom:1px solid #edf2f8; }.security-row:last-child { border-bottom:0; }.security-row>i { display:grid;place-items:center;width:30px;height:30px;border-radius:7px;background:#f0f5fc;color:#526783;font-style:normal;font-size:10px; }.security-row div { display:grid;gap:4px; }.security-row strong { font-size:11px; }.security-row span { color:#7d8da5;font-size:9px; }.security-row>b { color:#067647;font-size:9px; }.security-row>b.pending { color:#b54708; }
.managed-panel { display:grid;grid-template-columns:34px minmax(0,1fr);gap:12px;margin-top:16px;padding:14px;border:1px solid #dce9fa;border-radius:8px;background:#f7fbff; }.managed-panel>i { display:grid;place-items:center;width:32px;height:32px;border-radius:50%;background:#e8f8ef;color:#067647;font-style:normal;font-weight:700; }.managed-panel strong { font-size:12px; }.managed-panel p { margin:5px 0 0;color:#71819a;font-size:10px;line-height:1.7; }.primary-action { width:100%;height:38px;margin-top:14px;border:0;border-radius:6px;background:#165dff;color:#fff;font-size:11px;cursor:pointer; }.primary-action:hover { background:#0f50e6; }
.primary-action:disabled { cursor:not-allowed;opacity:.55; }
.recommendations { grid-column:1/-1; }.recommendations ul { display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:9px;margin:14px 0 0;padding:0;list-style:none; }.recommendations li { display:flex;align-items:center;gap:9px;padding:10px 12px;border-radius:7px;background:#f7faff;color:#526783;font-size:10px; }.recommendations li i { display:grid;place-items:center;width:19px;height:19px;border-radius:50%;background:#e8f8ef;color:#067647;font-style:normal;font-weight:700; }
@media (max-width:900px) { .security-summary,.security-grid { grid-template-columns:1fr; }.recommendations { grid-column:auto; }.recommendations ul { grid-template-columns:1fr; }.security-hero { align-items:flex-start;flex-direction:column; } }
</style>
