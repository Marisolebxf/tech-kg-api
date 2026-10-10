<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useResizeObserver } from '@vueuse/core'

import { useAuthStore } from '../stores/auth'
import { useGraphSpaceStore } from '../stores/graphSpace'

const graphSpaceStore = useGraphSpaceStore()
const authStore = useAuthStore()

const selector = ref<HTMLElement>()
const popupWidth = ref(280)
const triggerElement = computed(() => selector.value?.querySelector<HTMLElement>('.arco-select-view'))
// 弹层在 body 下，不能继承选择框宽度；按实际外框宽同步，窄屏收缩后也保持同宽。
useResizeObserver(triggerElement, ([entry]) => {
  const width = entry?.target.getBoundingClientRect().width
  if (width && width > 0) popupWidth.value = width
})

const options = computed(() => graphSpaceStore.groups)
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
  () => [authStore.profile?.user?.id, authStore.profile?.businessIds?.join(','), authStore.profile?.platformRole, authStore.profile?.businessRbacEnabled].join('|'),
  () => {
    if (!authStore.profile) return
    graphSpaceStore.bindUser(String(authStore.profile.user?.id ?? ''))
    void graphSpaceStore.ensureLoaded(true)
  },
)
</script>

<template>
  <div
    ref="selector"
    class="app-space-select"
    :title="graphSpaceStore.loadError ? '图空间列表加载失败，请重试' : graphSpaceStore.current ? `切换当前工作图空间：${graphSpaceStore.current}` : '切换当前工作图空间'"
  >
    <span class="app-space-select__label">图空间</span>
    <a-cascader
      class="app-space-select__input"
      aria-label="图空间"
      :model-value="graphSpaceStore.current"
      :options="options"
      :placeholder="showEmpty ? '暂无可用图空间' : '图空间'"
      :loading="graphSpaceStore.loading"
      :disabled="graphSpaceStore.loading"
      :show-path="false"
      :trigger-props="{ contentClass: 'app-space-select-popup', contentStyle: { width: `${popupWidth}px` } }"
      @change="(value: unknown) => graphSpaceStore.setCurrent(String(value ?? ''))"
    />
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

/* 同时锁定 flex 基准和宽高，选中长名称、加载及空状态都不改变触发栏大小。 */
.app-space-select :deep(.arco-select-view) {
  box-sizing: border-box;
  flex: 0 0 280px;
  width: 280px;
  min-width: 0;
  max-width: 280px;
  height: 32px;
}

/* arco 的 .arco-select-view-value 默认 display:flex——text-overflow 对 flex 容器
   无效，长空间名会被 overflow:hidden 硬裁半个字且无省略号；改回块级让 arco
   自带的 ellipsis 真正生效（完整名悬停包裹层 title 查看） */
.app-space-select :deep(.arco-select-view-value) {
  display: block;
  min-width: 0;
}

/* Arco 保留零宽 input 接收键盘事件；全局 input:focus 会给它画蓝色阴影，
   叠在选中名称前。只清理内部 input，焦点提示仍由外层 SelectView 提供。 */
.app-space-select :deep(.arco-select-view-input) {
  min-width: 0;
  padding: 0 !important;
  border: 0 !important;
  background: transparent !important;
  outline: none !important;
  box-shadow: none !important;
  caret-color: transparent;
}

.app-space-select :deep(.arco-select-view-input-hidden) {
  height: 0 !important;
  min-height: 0 !important;
  opacity: 0;
  pointer-events: none;
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
    flex: 0 1 280px;
    width: min(280px, 100%);
  }
}

</style>

<style>
/* 弹层 teleport 到 body，经 contentClass 限定范围。面板与上方外框同宽，
   目录切换、名称长度和选项数量只影响省略号/滚动，不再改变弹层大小。 */
.app-space-select-popup .arco-cascader-panel {
  width: 100%;
  height: 200px;
}

.app-space-select-popup .arco-cascader-panel-column {
  box-sizing: border-box;
  flex: 0 0 55%;
  width: 55%;
  min-width: 0;
}

.app-space-select-popup .arco-cascader-panel-column:first-child {
  /* 280px 下约 126px，扣除 Arco 的 46px 内边距后仍可展示五个汉字。 */
  flex-basis: 45%;
  width: 45%;
}

.app-space-select-popup .arco-cascader-option {
  min-width: 0;
}

.app-space-select-popup .arco-cascader-option-label {
  min-width: 0;
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}
</style>
