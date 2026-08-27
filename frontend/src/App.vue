<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import KgToast from './components/kg-toast.vue'
import AppLayout from './layouts/AppLayout.vue'
import { usePortalIntegration } from './portal/usePortalIntegration'

const route = useRoute()
const useBlankLayout = computed(() => route.meta.layout === 'blank')
const { isEmbedded, portalStatusText } = usePortalIntegration()
const showEmbeddedAuthState = computed(
  () => isEmbedded.value && route.name === 'login',
)
</script>

<template>
  <main v-if="showEmbeddedAuthState" class="portal-auth-state" role="status">
    <section>
      <span aria-hidden="true">!</span>
      <div>
        <h1>统一门户登录状态</h1>
        <p>{{ portalStatusText }}</p>
      </div>
    </section>
  </main>
  <div v-else-if="isEmbedded" class="portal-embedded-view">
    <RouterView />
  </div>
  <RouterView v-else-if="useBlankLayout" />
  <AppLayout v-else />
  <KgToast />
</template>

<style scoped>
.portal-embedded-view {
  width: 100%;
  min-height: 100%;
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
  background: #165dff;
  font-weight: 700;
}

.portal-auth-state h1 { margin: 0 0 6px; font-size: 18px; }
.portal-auth-state p { margin: 0; color: #65758e; line-height: 1.7; }
</style>
