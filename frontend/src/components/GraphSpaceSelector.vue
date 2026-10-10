<script setup lang="ts">
import type { CascaderOption } from '@arco-design/web-vue'

import { computed, onMounted, watch } from 'vue'

import { useAuthStore } from '../stores/auth'
import { useGraphSpaceStore } from '../stores/graphSpace'

const graphSpaceStore = useGraphSpaceStore()
const authStore = useAuthStore()

// 恒两级级联、组名在左列露出——与公网主栈一致（2026-10-10 口径：组名可见性
// 优先于紧凑，单分组时左列只有一行也保留；右缘溢出由弹层右对齐 CSS 兜住）
const options = computed(() => graphSpaceStore.groups)

/** 回显只显示空间名。arco 2.58 cascader 没有 show-path prop（早期传的
    :show-path="false" 是无效属性从未生效），默认把整条路径「未归属空间 / dev2」
    回显进 200px 触发框——分组前缀近半宽度，真实空间名反被挤成省略号，
    看起来像框里卡了个占位符。format-label 拿到路径数组，取末级叶子即可。 */
function formatLabel(path: CascaderOption[]): string {
  return String(path[path.length - 1]?.label ?? '')
}
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
      :format-label="formatLabel"
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

/* 打开下拉时 arco 聚焦内部隐藏 input 做键盘导航，空 input 的光标竖线
   （默认 #1d2129 灰蓝）正好叠在回显文本第一个字母处，像一条选择线；
   该 input 只读且不可见，光标无意义，透明掉 */
.app-space-select :deep(.arco-select-view-input) {
  caret-color: transparent;
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
  /* arco 面板定高 200px，行高 36px 只装 5.56 行——第 6 行被拦腰截断，半截浅灰
     字形在弹层底边像条残影/占位带。改成 6 整行（216px 内容 + 2px 上下边框），
     列滚动区同步放高，长列表照常滚动。 */
  height: 218px;
}

.app-space-select-popup .arco-cascader-column-content {
  max-height: 216px;
}

.app-space-select-popup .arco-cascader-option-label {
  overflow: hidden;
  text-overflow: ellipsis;
}

/* cascader 把 position:'bl' 硬编码进 mergeProps（triggerProps 覆盖不掉），弹层
   左缘对齐触发器左缘、向右铺 360px，auto-fit 又把它推到贴死屏幕右缘——阴影被裁，
   看着就是右侧溢出。顶栏右缘内边距恒 32px（实测 1280~1920 四档视口），直接把
   teleport 到 body 的定位层右对齐到输入框右缘，宽窄（单列/双列）自适应；
   left 必须用 !important 压掉 arco 每次重算写入的 inline left。手机端布局
   不同（label 隐藏、输入框拉伸），维持原生 auto-fit。 */
@media (min-width: 768px) {
  body > .arco-trigger-popup:has(.app-space-select-popup) {
    left: auto !important;
    right: 32px;
  }
}
</style>
