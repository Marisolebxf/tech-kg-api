<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

import logoKg from "../../assets/images/logo-kg.png";
import { useAuthStore } from "../../stores/auth";

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();
const submitting = ref(false);
const feedback = ref(
  typeof route.query.error === "string" ? route.query.error : "",
);

const redirectPath = computed(() => {
  const value =
    typeof route.query.redirect === "string"
      ? route.query.redirect
      : "/overview";
  return value.startsWith("/") && !value.startsWith("//") ? value : "/overview";
});

function errorMessage(error: unknown): string {
  if (typeof error === "object" && error !== null && "response" in error) {
    const detail = (error as { response?: { data?: { detail?: string } } })
      .response?.data?.detail;
    if (detail) return detail;
  }
  return error instanceof Error
    ? error.message
    : "登录服务暂时不可用，请稍后重试";
}

async function login() {
  submitting.value = true;
  feedback.value = "";
  try {
    await authStore.startLogin(redirectPath.value);
  } catch (error) {
    feedback.value = errorMessage(error);
    submitting.value = false;
  }
}

onMounted(async () => {
  try {
    const profile = await authStore.loadCurrentUser(true);
    if (profile) await router.replace(redirectPath.value);
  } catch (error) {
    feedback.value = errorMessage(error);
  }
});
</script>

<template>
  <main class="login-page">
    <section class="login-intro" aria-label="平台介绍">
      <div class="login-brand">
        <img :src="logoKg" alt="" />
        <span>亿级知识图谱平台</span>
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
          <li><strong>OAuth2</strong><span>统一用户中心授权</span></li>
        </ul>
      </div>
      <footer>深圳市科技创新资源知识图谱平台</footer>
    </section>

    <section class="login-panel" aria-label="登录">
      <div class="login-card">
        <span class="login-card__badge">统一身份认证</span>
        <h2>欢迎登录</h2>
        <p>系统将跳转到统一用户中心完成身份验证。账号密码不会提交给本平台。</p>
        <div class="login-card__security">
          <i aria-hidden="true">✓</i>
          <span
            ><strong>安全授权</strong>通过 OAuth2
            授权码模式登录，访问令牌仅保存在后端会话中。</span
          >
        </div>
        <p v-if="feedback" class="login-card__error" role="alert">
          {{ feedback }}
        </p>
        <button
          type="button"
          :disabled="submitting || authStore.loading"
          @click="login"
        >
          {{ submitting ? "正在跳转…" : "使用统一用户中心登录" }}
        </button>
        <small>登录即表示你已获得访问本系统的组织授权。</small>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login-page {
  display: grid;
  grid-template-columns: minmax(460px, 1.2fr) minmax(420px, 0.8fr);
  min-height: 100vh;
  color: #172b4d;
  background: #f4f8ff;
}

.login-intro {
  position: relative;
  display: grid;
  align-content: space-between;
  min-height: 100vh;
  padding: 42px clamp(44px, 7vw, 110px);
  overflow: hidden;
  color: #fff;
  background:
    radial-gradient(
      circle at 76% 24%,
      rgba(73, 193, 255, 0.34),
      transparent 24%
    ),
    radial-gradient(
      circle at 16% 78%,
      rgba(105, 94, 255, 0.3),
      transparent 28%
    ),
    linear-gradient(145deg, #092a64 0%, #0d52b5 52%, #168ee0 100%);
}

.login-intro::after {
  position: absolute;
  inset: 0;
  opacity: 0.18;
  background-image:
    linear-gradient(rgba(255, 255, 255, 0.16) 1px, transparent 1px),
    linear-gradient(90deg, rgba(255, 255, 255, 0.16) 1px, transparent 1px);
  background-size: 48px 48px;
  content: "";
  mask-image: linear-gradient(
    135deg,
    transparent 8%,
    #000 48%,
    transparent 92%
  );
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
  color: #8ed6ff;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.18em;
}
.login-intro h1 {
  max-width: 620px;
  margin: 0;
  font-size: clamp(38px, 4vw, 62px);
  line-height: 1.17;
  letter-spacing: -0.03em;
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
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.08);
  backdrop-filter: blur(10px);
}
.login-intro li strong {
  font-size: 23px;
}
.login-intro li span {
  color: rgba(236, 247, 255, 0.72);
  font-size: 11px;
}
.login-intro footer {
  color: rgba(228, 243, 255, 0.58);
  font-size: 11px;
}

.login-panel {
  display: grid;
  place-items: center;
  padding: 48px;
}
.login-card {
  width: min(390px, 100%);
  padding: 42px;
  border: 1px solid #d8e6f7;
  border-radius: 18px;
  background: rgba(255, 255, 255, 0.94);
  box-shadow: 0 26px 70px rgba(23, 72, 138, 0.13);
}
.login-card__badge {
  display: inline-flex;
  padding: 5px 10px;
  border-radius: 999px;
  background: #eaf3ff;
  color: #165dff;
  font-size: 11px;
  font-weight: 600;
}
.login-card h2 {
  margin: 22px 0 9px;
  color: #162b4d;
  font-size: 30px;
}
.login-card > p {
  margin: 0;
  color: #73839a;
  font-size: 13px;
  line-height: 1.8;
}
.login-card__security {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 11px;
  margin: 28px 0;
  padding: 14px;
  border: 1px solid #dce9fa;
  border-radius: 10px;
  background: #f7fbff;
  color: #667993;
  font-size: 11px;
  line-height: 1.65;
}
.login-card__security i {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #e5f8ee;
  color: #079455;
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
  border-radius: 7px;
  background: #fff0ee;
  color: #b42318;
}
.login-card button {
  width: 100%;
  height: 46px;
  border: 0;
  border-radius: 8px;
  background: linear-gradient(90deg, #165dff, #168ee0);
  color: #fff;
  font: 600 14px inherit;
  cursor: pointer;
  box-shadow: 0 10px 24px rgba(22, 93, 255, 0.22);
}
.login-card button:hover {
  filter: brightness(1.04);
}
.login-card button:disabled {
  cursor: wait;
  opacity: 0.65;
}
.login-card small {
  display: block;
  margin-top: 17px;
  color: #9aa7b8;
  font-size: 10px;
  text-align: center;
}

@media (max-width: 900px) {
  .login-page {
    grid-template-columns: 1fr;
  }
  .login-intro {
    min-height: 340px;
    padding: 28px;
  }
  .login-intro__content {
    margin: 48px 0;
  }
  .login-intro h1 {
    font-size: 34px;
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
