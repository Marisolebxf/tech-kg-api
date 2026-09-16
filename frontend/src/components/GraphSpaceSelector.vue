<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'

import { useAuthStore } from '../stores/auth'
import { useGraphSpaceStore } from '../stores/graphSpace'

const graphSpaceStore = useGraphSpaceStore()
const authStore = useAuthStore()

const options = computed(() => graphSpaceStore.spaces)
const showEmpty = computed(
  () =>
    !graphSpaceStore.loading &&
    !graphSpaceStore.loadError &&
    graphSpaceStore.initialized &&
    !graphSpaceStore.spaces.length,
)

onMounted(() => {
  void graphSpaceStore.ensureLoaded()
})

// 换号后空间可见集变化：重拉列表并归一当前值（越权访问另有后端 403 防线）
watch(
  () => authStore.profile?.user?.id,
  () => void graphSpaceStore.ensureLoaded(true),
)
</script>

<template>
  <div
    class="app-space-select"
    :title="graphSpaceStore.loadError ? `图空间列表加载失败，当前使用默认空间 ${graphSpaceStore.current}` : '切换当前工作图空间'"
  >
    <span class="app-space-select__label">图空间</span>
    <a-select
      class="app-space-select__input"
      :model-value="graphSpaceStore.current"
      placeholder="图空间"
      :loading="graphSpaceStore.loading"
      :scrollbar="false"
      :disabled="graphSpaceStore.loading"
      @change="(value: unknown) => graphSpaceStore.setCurrent(String(value ?? ''))"
    >
      <a-option v-if="showEmpty" disabled>暂无可用图空间</a-option>
      <a-option v-for="item in options" :key="item" :value="item">{{ item }}</a-option>
    </a-select>
  </div>
</template>

<style scoped>
.app-space-select {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.app-space-select__label {
  color: #4e5969;
  font-size: 12px;
  white-space: nowrap;
}

.app-space-select__input {
  width: 160px;
}
</style>
