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

// 宽度跟随当前空间名：按字符估宽（全角≈14px、半角≈8px，14px 字号），加内边距+下拉箭头，
// clamp 到 [150, 340]px——名字短不塌陷、名字长尽量显示齐，超长走 arco 自带的 title 悬停
const selectWidth = computed(() => {
  const text = graphSpaceStore.current || '图空间'
  const textWidth = [...text].reduce((width, ch) => width + (ch.charCodeAt(0) > 0xff ? 14 : 8), 0)
  return `${Math.min(340, Math.max(150, textWidth + 56))}px`
})

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
    :style="{ '--space-select-w': selectWidth }"
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
      :trigger-props="{ autoFitPopupWidth: false, autoFitPopupMinWidth: true }"
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
  /* 顶栏空间紧张时不被 flex 压缩（宽度由下方 --space-select-w 控制） */
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
  width: var(--space-select-w, 160px);
}
</style>
