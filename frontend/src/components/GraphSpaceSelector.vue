<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'

import { useAuthStore } from '../stores/auth'
import { useGraphSpaceStore } from '../stores/graphSpace'

const graphSpaceStore = useGraphSpaceStore()
const authStore = useAuthStore()

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
      :trigger-props="{ contentClass: 'app-space-select-popup' }"
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

/* arco 控件不透传 scoped data-v 到视图元素，类选择器匹配不上
   （旧 .app-space-select__input{width} 是死规则），必须经包裹层 :deep 下钻。
   a-cascader 的触发器内部同样渲染 SelectView，选择器口径不变 */
.app-space-select :deep(.arco-select-view) {
  width: 200px;
}

/* arco 的 .arco-select-view-value 默认 display:flex——text-overflow 对 flex 容器
   无效，长空间名会被 overflow:hidden 硬裁半个字且无省略号；改回块级让 arco
   自带的 ellipsis 真正生效（完整名悬停包裹层 title 查看） */
.app-space-select :deep(.arco-select-view-value) {
  display: block;
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
   cascader 弹层是 inline-flex 的 .arco-cascader-panel，列只有 min-width 没有
   上限——超长空间名会把弹层撑出屏幕。给面板封顶宽度，列随之收缩，选项 label
   补 overflow+ellipsis 截断；arco 选项 <li> 原生带 title=label，悬停看全名。 */
/* cascader 内部 mergeProps 把 popup-offset 硬编码为 4（外部 triggerProps 覆盖
   不掉），弹层顶边贴着触发框；下拉打开时触发框的蓝色聚焦边框+光晕正好压在弹层
   顶边上，视觉上像弹层中间突出一小块蓝色。给弹层顶部垫 6px 透明间距（4+6=10px），
   让聚焦光晕（约 4px）与弹层边框之间留出干净的页面底色分隔。 */
.app-space-select-popup {
  padding-top: 6px;
}

.app-space-select-popup .arco-cascader-panel {
  max-width: min(360px, 80vw);
}

.app-space-select-popup .arco-cascader-option-label {
  overflow: hidden;
  text-overflow: ellipsis;
}
</style>
