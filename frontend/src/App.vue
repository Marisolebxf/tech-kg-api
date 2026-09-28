<script setup lang="ts">
import { computed, onErrorCaptured, ref } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import KgToast from './components/kg-toast.vue'
import GraphSpaceSelector from './components/GraphSpaceSelector.vue'
import AppLayout from './layouts/AppLayout.vue'
import { usePortalIntegration } from './portal/usePortalIntegration'

const route = useRoute()
const useBlankLayout = computed(() => route.meta.layout === 'blank')
const { isEmbedded, portalStatusText } = usePortalIntegration()
// 嵌入门户时不渲染 AppLayout，图空间选择器改挂嵌入态标题行右侧（口径同 AppLayout 面包屑行）
const isOverviewPage = computed(() => route.path === '/overview')
// 嵌入态没有 AppLayout 的 onErrorCaptured 兜底：视图渲染错误会直通全局 errorHandler
// 把门户里的整页炸成「页面启动异常」。这里补同款路由级错误边界。
const routeError = ref('')

onErrorCaptured((error) => {
  routeError.value = error instanceof Error ? error.message : String(error)
  return false
})
const embeddedPageTitle = computed(() => String(route.meta.title ?? '亿级科技知识图谱引擎'))
const showEmbeddedAuthState = computed(
  () => isEmbedded.value && route.name === 'login',
)
</script>

<template>
  <output v-if="showEmbeddedAuthState" class="portal-auth-state">
    <section>
      <span aria-hidden="true">!</span>
      <div>
        <h1>统一门户登录状态</h1>
        <p>{{ portalStatusText }}</p>
      </div>
    </section>
  </output>
  <div v-else-if="isEmbedded" class="portal-embedded-view">
    <main
      class="app-main portal-embedded-main"
      :class="{ 'is-overview-page': route.path === '/overview' }"
    >
      <section class="portal-embedded-stage">
        <div
          class="portal-embedded-title-row"
          :class="{ 'portal-embedded-title-row--with-select': isOverviewPage }"
        >
          <div class="portal-embedded-page-title">{{ embeddedPageTitle }}</div>
          <GraphSpaceSelector v-if="isOverviewPage" />
        </div>
        <section
          class="app-workspace portal-embedded-workspace"
          :aria-label="embeddedPageTitle"
        >
          <div v-if="routeError" class="route-error">
            <strong>页面渲染异常</strong>
            <span>{{ routeError }}</span>
          </div>
          <RouterView v-else />
        </section>
      </section>
    </main>
  </div>
  <RouterView v-else-if="useBlankLayout" />
  <AppLayout v-else />
  <KgToast />
</template>

<style scoped>
.portal-embedded-view {
  box-sizing: border-box;
  width: 100%;
  height: 100vh;
  height: 100dvh;
  min-height: 0;
  padding: 16px;
  overflow: hidden;
  background: var(--gkx-bg-page);
  scrollbar-gutter: auto;
}

.portal-embedded-main {
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
  scrollbar-gutter: auto;
}

.portal-embedded-workspace {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  padding: 16px;
  overflow: auto;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.8);
  scrollbar-width: none;
}

/* Keep the same second-layer surface as AppLayout's app-stage when the
   portal supplies the surrounding navigation. */
.portal-embedded-stage {
  box-sizing: border-box;
  position: relative;
  display: grid;
  /* 首行随标题行内容自适应：平台总览页右侧挂图空间选择器时撑到 32px，其余页 22px */
  grid-template-rows: minmax(22px, auto) minmax(0, 1fr);
  gap: 16px;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  padding: 16px 15px 16px 16px;
  border: 1px solid #fff;
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.48);
  backdrop-filter: blur(8px);
  overflow: hidden;
  scrollbar-gutter: auto;
}

.portal-embedded-title-row {
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  height: 22px;
}

/* 平台总览页：标题行右侧挂图空间选择器（a-select 默认 32px 高），与 AppLayout 面包屑行同款 */
.portal-embedded-title-row--with-select {
  width: 100%;
  height: 32px;
}

.portal-embedded-title-row--with-select > .app-space-select {
  margin-left: auto;
}

.portal-embedded-stage::after {
  content: "";
  position: absolute;
  z-index: 1;
  inset: 0;
  border: 1px solid #fff;
  border-radius: inherit;
  pointer-events: none;
}

.portal-embedded-page-title {
  min-width: 0;
  overflow: hidden;
  color: #59636f;
  font-size: 12px;
  line-height: 22px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.portal-embedded-workspace::-webkit-scrollbar {
  display: none;
}

.route-error {
  display: grid;
  align-content: center;
  gap: 10px;
  height: 100%;
  padding: 32px;
  color: #b42318;
  background: #fff7f6;
  border: 1px solid #fecdca;
  border-radius: var(--radius-md);
}

.route-error strong {
  font-size: 18px;
}

.route-error span {
  color: #912018;
  overflow-wrap: anywhere;
}

@media (max-width: 767px) {
  .portal-embedded-view {
    padding: 10px;
  }

  .portal-embedded-workspace {
    padding: 10px;
    border-radius: 6px;
  }

  .portal-embedded-stage {
    grid-template-rows: auto minmax(0, 1fr);
    gap: 8px;
    padding: 8px;
    border: 0;
    border-radius: 0;
  }
}

.portal-auth-state {
  display: grid;
  min-height: 100%;
  padding: 24px;
  place-items: center;
  background: #f5f8fd;
}

.portal-auth-state section {
  display: flex;
  max-width: 560px;
  gap: 14px;
  padding: 20px 24px;
  border: 1px solid #c8daf4;
  border-radius: 8px;
  background: #fff;
}

.portal-auth-state span {
  display: grid;
  flex: 0 0 30px;
  height: 30px;
  border-radius: 50%;
  place-items: center;
  color: #fff;
  background: #004ecc;
  font-weight: 700;
}

.portal-auth-state h1 { margin: 0 0 6px; font-size: 18px; }
.portal-auth-state p { margin: 0; color: #65758e; line-height: 1.7; }
</style>
