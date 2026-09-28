<script setup lang="ts">
import { computed } from 'vue'
import { RouterLink, useRoute } from 'vue-router'

import { breadcrumbCrumbs, breadcrumbHomeTo } from '../composables/use-breadcrumb'

const route = useRoute()
/** 层级链条（首项图标由模板单独渲染；末项为当前页）。 */
const crumbs = computed(() =>
  breadcrumbCrumbs(route.path, String(route.meta.title ?? '亿级知识图谱')),
)
</script>

<template>
  <nav class="app-breadcrumb" aria-label="当前位置">
    <!-- 首项：<> 图标入口，回平台总览（Arco Breadcrumb 首项放图标的通用模式） -->
    <RouterLink
      class="app-breadcrumb__home"
      :to="breadcrumbHomeTo"
      aria-label="平台总览"
      title="平台总览"
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
        <path d="M6.2 4.2 2.8 8l3.4 3.8" />
        <path d="M9.8 4.2 13.2 8l-3.4 3.8" />
      </svg>
    </RouterLink>
    <template v-for="(item, index) in crumbs" :key="`${item.label}-${index}`">
      <span class="app-breadcrumb__separator" aria-hidden="true">/</span>
      <RouterLink v-if="item.to" class="app-breadcrumb__link" :to="item.to">{{ item.label }}</RouterLink>
      <span
        v-else-if="index === crumbs.length - 1"
        class="app-breadcrumb__current"
        aria-current="page"
      >{{ item.label }}</span>
      <span v-else class="app-breadcrumb__item">{{ item.label }}</span>
    </template>
    <!-- 平台总览页在行尾挂全局图空间选择器 -->
    <slot />
  </nav>
</template>

<style scoped>
/* Arco Design Breadcrumb 规范（@arco-design/web-vue es/breadcrumb/style）：
   inline-flex 布局、`/` 分隔（text-4 弱色）、可点项 hover 链接色 + 浅底、
   末项（当前页）text-1 加深并 500 字重。可点项用 padding/margin 负抵消留出悬停底色。 */
.app-breadcrumb {
  display: flex;
  align-items: center;
  gap: 8px;
  width: fit-content;
  max-width: 100%;
  min-width: 0;
  height: 22px;
  color: #4e5969;
  font-size: 14px;
}

.app-breadcrumb__home {
  display: inline-flex;
  flex: 0 0 auto;
  align-items: center;
  padding: 0 8px;
  margin: 0 -8px;
  border-radius: 2px;
  color: #4e5969;
}

.app-breadcrumb__home svg {
  display: block;
  width: 16px;
  height: 16px;
}

.app-breadcrumb__home:hover {
  color: #165dff;
  background: #f2f3f5;
}

.app-breadcrumb__separator {
  flex: 0 0 auto;
  color: #c9cdd4;
  font-size: 14px;
  line-height: 22px;
}

/* 分组等不可导航的中间级：仅展示层级，不响应指针 */
.app-breadcrumb__item {
  flex: 0 0 auto;
  color: #4e5969;
  line-height: 22px;
  white-space: nowrap;
}

.app-breadcrumb__link {
  flex: 0 0 auto;
  padding: 0 8px;
  margin: 0 -8px;
  border-radius: 2px;
  color: #4e5969;
  line-height: 22px;
  text-decoration: none;
  white-space: nowrap;
}

.app-breadcrumb__link:hover {
  color: #165dff;
  background: #f2f3f5;
  text-decoration: none;
}

.app-breadcrumb__current {
  flex: 0 0 auto;
  color: #1d2129;
  font-weight: 500;
  line-height: 22px;
  white-space: nowrap;
}
</style>
