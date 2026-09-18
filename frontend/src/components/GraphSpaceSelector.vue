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
      aria-label="图空间"
      :model-value="graphSpaceStore.current"
      placeholder="图空间"
      :loading="graphSpaceStore.loading"
      :scrollbar="false"
      :disabled="graphSpaceStore.loading"
      :trigger-props="{ contentClass: 'app-space-select-popup' }"
      @change="(value: unknown) => graphSpaceStore.setCurrent(String(value ?? ''))"
    >
      <a-option v-if="showEmpty" disabled>暂无可用图空间</a-option>
      <a-option v-for="item in options" :key="item" :value="item" :title="item">{{ item }}</a-option>
    </a-select>
  </div>
</template>

<style scoped>
.app-space-select {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  /* 顶栏空间紧张时不被 flex 压缩 */
  flex: 0 0 auto;
}

.app-space-select__label {
  color: #4e5969;
  font-size: 12px;
  white-space: nowrap;
}

/* arco <a-select> 不透传 scoped data-v 到视图元素，类选择器匹配不上
   （旧 .app-space-select__input{width} 是死规则），必须经包裹层 :deep 下钻 */
.app-space-select :deep(.arco-select-view) {
  width: 200px;
}

@media (max-width: 767px) {
  .app-space-select {
    flex: 1 1 80px;
    min-width: 0;
  }

  .app-space-select__label {
    display: none;
  }

  .app-space-select :deep(.arco-select-view) {
    width: 100%;
    min-width: 0;
  }
}

</style>

<style>
/* 弹层 teleport 到 body，scoped 够不到，经 triggerProps contentClass 打标。
   选择框固定默认宽，超长空间名：触发栏截断（arco 自带省略号+title 悬停），
   下拉面板整体横向滚动查看（选项不省略，悬停 title 兜底）。 */
.app-space-select-popup .arco-select-dropdown-list-wrapper {
  overflow-x: auto;
}

.app-space-select-popup .arco-select-option {
  /* 按内容自然宽撑开以触发横向滚动，短选项仍占满整行可点 */
  width: max-content;
  min-width: 100%;
}

.app-space-select-popup .arco-select-option-content {
  overflow: visible;
}
</style>
