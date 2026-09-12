<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import KgToast from './components/kg-toast.vue'
import AppLayout from './layouts/AppLayout.vue'
import { usePortalIntegration } from './portal/usePortalIntegration'

const route = useRoute()
const useBlankLayout = computed(() => route.meta.layout === 'blank')
const { isEmbedded, portalStatusText } = usePortalIntegration()
const embeddedPageTitle = computed(() => String(route.meta.title ?? '亿级知识图谱平台'))
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
        <div class="portal-embedded-page-title">{{ embeddedPageTitle }}</div>
        <section
          class="app-workspace portal-embedded-workspace"
          :aria-label="embeddedPageTitle"
        >
          <RouterView />
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
  grid-template-rows: 22px minmax(0, 1fr);
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
