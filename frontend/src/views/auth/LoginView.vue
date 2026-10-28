<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";

import logoKg from "../../assets/images/logo-kg.png";
import { useAuthStore } from "../../stores/auth";
import { safeLoginTarget } from "../../router/loginTarget";
import { getLoginConfig } from "../../api/auth";
import { usePortalLogin } from "../../composables/usePortalLogin";
import { portalBridge } from "../../portal/iframeBridge";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const submitting = ref(false);
const loginMode = ref<"oauth" | "portal" | null>(null);
const configLoading = ref(true);
const portalLogin = usePortalLogin(async (target) => {
  await router.replace(target);
  return route.name !== "login";
});
const { waiting, status: portalStatus, error: portalError } = portalLogin;
function normalizeLoginFeedback(value: unknown): string {
  if (typeof value !== "string") return "";
  // 未建立本系统会话也是正常登录入口；兼容旧书签中的过期提示，避免误报。
  if (value === "登录状态已失效或已超时，请重新登录") return "";
  if (/request failed|network error|status code 5\d\d|failed to fetch/i.test(value)) {
    return "登录服务暂时不可用，请确认后端服务已启动后重试";
  }
  return value;
}

const feedback = ref(normalizeLoginFeedback(route.query.error));

const redirectPath = computed(() => safeLoginTarget(route.query.redirect));

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const response = (error as {
      response?: { status?: number; data?: { detail?: string; msg?: string } };
    }).response;
    const message = response?.data?.detail || response?.data?.msg;
    if (message) return message;
    if (response?.status && response.status >= 500) {
      return "登录服务暂时不可用，请确认后端服务已启动后重试";
    }
  }
  return "登录服务暂时不可用，请确认网络和后端服务后重试";
}

async function login() {
  if (submitting.value || authStore.loading || waiting.value || configLoading.value) return;
  if (!loginMode.value) {
    feedback.value = "";
    await loadLoginConfig();
    return;
  }
  submitting.value = true;
  feedback.value = "";
  // 旧书签可能指向已下线的 /admin 管理端路径，此时回退到平台总览
  const target = redirectPath.value && !redirectPath.value.startsWith("/admin") ? redirectPath.value : "/overview";
  if (loginMode.value === "portal" && !portalBridge.isInIframe) {
    portalLogin.start(target);
    submitting.value = false;
    return;
  }
  try {
    if (await authStore.loadCurrentUser(true)) {
      await router.replace(target);
      if (route.name !== "login" || authStore.isAuthenticated) return;
    }
    await authStore.startLogin(target);
  } catch (error) {
    feedback.value = errorMessage(error);
  } finally {
    submitting.value = false;
  }
}

function resetSubmitting() {
  submitting.value = false;
}

async function loadLoginConfig() {
  configLoading.value = true;
  try {
    loginMode.value = (await getLoginConfig()).mode;
  } catch (error) {
    feedback.value = errorMessage(error);
  } finally {
    configLoading.value = false;
  }
}

watch(() => route.query.error, (error) => {
  feedback.value = normalizeLoginFeedback(error);
  resetSubmitting();
});

onMounted(async () => {
  window.addEventListener("pageshow", resetSubmitting);
  void loadLoginConfig();
  try {
    await authStore.loadCurrentUser(true);
  } catch (error) {
    feedback.value = errorMessage(error);
  }
});

onBeforeUnmount(() => window.removeEventListener("pageshow", resetSubmitting));
</script>

<template>
  <main class="login-page">
    <section class="login-intro" aria-label="平台介绍">
      <div class="login-brand">
        <img :src="logoKg" alt="" />
        <span>亿级科技知识图谱引擎</span>
      </div>
      <div class="login-intro__content">
        <p class="login-kicker">TECHNOLOGY KNOWLEDGE GRAPH</p>
        <h1>统一连接科技实体、关系与业务服务</h1>
        <p>
          从图谱构建、Schema 管理到九大关系应用，在同一个受控工作空间中完成。
        </p>
        <ul>
          <li><strong>亿级</strong><span>实体与关系统一治理</span></li>
          <li><strong>9 类</strong><span>标书业务场景覆盖</span></li>
          <li><strong>统一认证</strong><span>按账号权限访问</span></li>
        </ul>
      </div>
      <footer>深圳市科技创新资源知识图谱平台</footer>
    </section>

    <section class="login-panel" aria-label="登录">
      <div class="login-card">
        <span class="login-card__badge">统一身份认证</span>
        <h2>欢迎登录</h2>
        <p>系统将通过统一登录入口完成身份验证。账号密码由统一用户中心管理。</p>
        <div class="login-card__security">
          <i aria-hidden="true">✓</i>
          <span
            ><strong>统一身份</strong>登录后使用当前账号已获授权的功能和数据。</span
          >
        </div>
        <p v-if="feedback || portalError" class="login-card__error" role="alert">
          {{ feedback || portalError }}
        </p>
        <p v-if="waiting" class="login-card__status" role="status">{{ portalStatus }}</p>
        <div class="login-portals">
          <button type="button" :disabled="submitting || authStore.loading || configLoading || waiting" @click="login">
            <strong>{{ loginMode === null && !configLoading ? '重试登录入口' : '进入平台' }}</strong><b>{{ waiting ? '等待登录…' : submitting ? '跳转中…' : configLoading ? '准备中…' : '进入 →' }}</b>
          </button>
          <button v-if="waiting" type="button" @click="portalLogin.cancel">取消等待</button>
        </div>
        <small>登录即表示你已获得访问本系统的组织授权。</small>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  grid-template-columns: minmax(460px, 1.2fr) minmax(420px, 0.8fr);
  /* The app root locks document scrolling; this standalone page must own it. */
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  overflow-x: hidden;
  overflow-y: auto;
  -webkit-overflow-scrolling: touch;
  color: var(--gkx-text-primary);
  background: var(--gkx-bg-page);
}

.login-intro {
  position: relative;
  display: grid;
  align-content: space-between;
  min-height: 100vh;
  padding: 42px clamp(44px, 7vw, 110px);
  overflow: hidden;
  color: #fff;
  background: var(--gkx-primary);
}

.login-intro::after {
  position: absolute;
  inset: 0;
  opacity: 0.1;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.16) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.16) 1px, transparent 1px);
  background-size: 48px 48px;
  content: "";
}

.login-brand,
.login-intro__content,
.login-intro footer {
  position: relative;
  z-index: 1;
}
.login-brand {
  display: flex;
  align-items: center;
  gap: 13px;
  font-size: 18px;
  font-weight: 600;
}
.login-brand img {
  width: 38px;
  height: 38px;
  object-fit: contain;
}
.login-intro__content {
  max-width: 650px;
}
.login-kicker {
  margin: 0 0 18px;
  color: rgba(255, 255, 255, 0.72);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0;
}
.login-intro h1 {
  max-width: 620px;
  margin: 0;
  font-size: 32px;
  line-height: 1.17;
  letter-spacing: 0;
}
.login-intro__content > p:not(.login-kicker) {
  max-width: 570px;
  margin: 26px 0 0;
  color: rgba(235, 246, 255, 0.82);
  font-size: 16px;
  line-height: 1.9;
}
.login-intro ul {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin: 42px 0 0;
  padding: 0;
  list-style: none;
}
.login-intro li {
  display: grid;
  gap: 5px;
  padding: 17px;
  border: 1px solid rgba(255, 255, 255, 0.18);
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.1);
}
.login-intro li strong {
  font-size: 23px;
}
.login-intro li span {
  color: rgba(236, 247, 255, 0.72);
  font-size: 12px;
}
.login-intro footer {
  color: rgba(228, 243, 255, 0.58);
  font-size: 12px;
}

.login-panel {
  display: grid;
  place-items: center;
  padding: 48px;
}
.login-card {
  width: min(390px, 100%);
  padding: 42px;
  border: 1px solid rgba(255, 255, 255, 0.92);
  border-radius: 8px;
  background: #fff;
  box-shadow: none;
}
.login-card__badge {
  display: inline-flex;
  padding: 5px 10px;
  border-radius: 999px;
  background: #eaf3ff;
  color: #004ecc;
  font-size: 12px;
  font-weight: 600;
}
.login-card h2 {
  margin: 22px 0 9px;
  color: var(--gkx-text-primary);
  font-size: 28px;
}
.login-card > p {
  margin: 0;
  color: var(--gkx-text-secondary);
  font-size: 12px;
  line-height: 1.8;
}
.login-card__security {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 11px;
  margin: 28px 0;
  padding: 14px;
  border: 1px solid #dce9fa;
  border-radius: 6px;
  background: var(--gkx-bg-subtle);
  color: var(--gkx-text-secondary);
  font-size: 12px;
  line-height: 1.65;
}
.login-card__security i {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e5f8ee;
  color: #067647;
  font-style: normal;
  font-weight: 700;
}
.login-card__security strong {
  display: block;
  margin-bottom: 2px;
  color: #2a4264;
}
.login-card .login-card__error {
  margin: -12px 0 18px;
  padding: 10px 12px;
  border-radius: 4px;
  background: #fff0ee;
  color: #b42318;
}
.login-portals{display:grid;gap:10px}.login-portals button{display:flex;align-items:center;justify-content:space-between;width:100%;height:58px;padding:0 18px;border:1px solid #dce8f8;border-radius:6px;background:#fff;color:var(--gkx-text-primary);text-align:left;cursor:pointer}.login-portals button:hover{border-color:var(--gkx-primary);background:#f7faff}.login-portals button:disabled{opacity:.6;cursor:not-allowed}.login-portals strong{font-size:14px}.login-portals b{color:var(--gkx-primary);font-size:12px;white-space:nowrap}
.login-card .login-card__status {
  margin: 0 0 16px;
  color: var(--gkx-text-secondary);
  line-height: 1.7;
}
.login-card small {
  display: block;
  margin-top: 17px;
  color: #9aa7b8;
  font-size: 12px;
  text-align: center;
}

@media (max-width: 900px) {
  .login-page {
    grid-template-columns: minmax(0, 1fr);
    /* 窄屏两段各自按内容撑高、整体可滚，intro 不被网格压缩导致内容溢出
       （对齐 main ae8679d 的登录页移动端滚动修复）。 */
    grid-template-rows: max-content max-content;
    align-content: start;
  }
  .login-intro {
    min-height: 0;
    padding: 28px;
  }
  .login-intro__content {
    margin: 24px 0 0;
  }
  .login-intro h1 {
    font-size: 32px;
  }
  .login-intro ul,
  .login-intro footer {
    display: none;
  }
  .login-panel {
    padding: 32px 20px;
  }
}
</style>
