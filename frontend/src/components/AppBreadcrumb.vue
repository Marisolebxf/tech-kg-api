<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute, useRouter } from 'vue-router'

import { breadcrumbBackTarget, breadcrumbCrumbs } from '../composables/use-breadcrumb'

const route = useRoute()
const router = useRouter()
/** 层级链条（末项为当前页）。 */
const crumbs = computed(() =>
  breadcrumbCrumbs(route.path, String(route.meta.title ?? '亿级知识图谱')),
)
/** 应用内上一页（vue-router 写入 history.state.back）：优先原路返回。 */
const hasInAppHistory = computed(() => {
  void route.fullPath // 依赖路由：导航后重读 history.state
  const state = window.history.state as { back?: string | null } | null
  return state?.back != null
})
/** 兜底返回目标：最近一级不落回当前页的上级。 */
const backTarget = computed(() => breadcrumbBackTarget(route.path, crumbs.value))
const showBack = computed(() => hasInAppHistory.value || backTarget.value.to !== route.path)
const backTitle = computed(() =>
  hasInAppHistory.value ? '返回上一页' : `返回${backTarget.value.label}`,
)
function goBack() {
  if (hasInAppHistory.value) {
    router.back()
    return
  }
  void router.push(backTarget.value.to)
}
</script>

<template>
  <nav class="app-breadcrumb" aria-label="当前位置">
    <!-- 行首「<」返回：应用内原路返回；深链直达时回最近一级上级 -->
    <a-tooltip v-if="showBack" position="bottom" :content="backTitle">
      <button
        class="app-breadcrumb__back"
        type="button"
        :aria-label="backTitle"
        @click="goBack"
      >
      <svg
        viewBox="0 0 16 16"
        aria-hidden="true"
        fill="none"
        stroke="currentColor"
        stroke-width="1.5"
        stroke-linecap="round"
        stroke-linejoin="round"
      >
        <path d="M10 3.5 5.5 8l4.5 4.5" />
      </svg>
      </button>
    </a-tooltip>
    <span v-if="showBack" class="app-breadcrumb__divider" aria-hidden="true"></span>
    <template v-for="(item, index) in crumbs" :key="`${item.label}-${index}`">
      <span v-if="index > 0" class="app-breadcrumb__separator" aria-hidden="true">/</span>
      <RouterLink v-if="item.to" class="app-breadcrumb__link" :to="item.to">{{ item.label }}</RouterLink>
      <span v-else class="app-breadcrumb__current" aria-current="page">{{ item.label }}</span>
    </template>
    <!-- 平台总览页在行尾挂全局图空间选择器 -->
    <slot />
  </nav>
</template>

<style scoped>
/* Production breadcrumb: 12/20px, muted ancestors and a noninteractive current page. */
.app-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
  min-width: 0;
  height: 20px;
  color: #86909c;
  font-size: 12px;
}

/* 行首「<」返回按钮：与图标入口同款命中区，悬停变蓝 */
.app-breadcrumb__back {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  padding: 0;
  margin: 0;
  border: 0;
  border-radius: 2px;
  background: transparent;
  color: #86909c;
  cursor: pointer;
}

.app-breadcrumb__back svg {
  display: block;
  width: 16px;
  height: 16px;
}

.app-breadcrumb__back:hover {
  color: #165dff;
  background: #f2f3f5;
}

/* 返回动作与位置链之间的细分隔线 */
.app-breadcrumb__divider {
  flex: 0 0 auto;
  width: 1px;
  height: 12px;
  background: #e5e6eb;
}

.app-breadcrumb__separator {
  flex: 0 0 auto;
  color: #86909c;
  font-size: 12px;
  line-height: 20px;
}

.app-breadcrumb__link {
  flex: 0 0 auto;
  padding: 0;
  margin: 0;
  border-radius: 2px;
  color: #86909c;
  line-height: 20px;
  text-decoration: none;
  white-space: nowrap;
}

.app-breadcrumb__link:hover {
  color: #165dff;
  background: #f2f3f5;
  text-decoration: none;
}

.app-breadcrumb__current {
  flex: 0 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  color: #1d2129;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
}
</style>
