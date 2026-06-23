<script setup lang="ts">
import type { SidebarItem } from '../types/directRelation'

defineProps<{
  items: SidebarItem[]
}>()
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <div class="brand-logo" aria-hidden="true">
        <span>KG</span>
      </div>
      <div>
        <div class="brand-title">知识图谱平台</div>
        <div class="brand-subtitle">Knowledge Graph Platform</div>
      </div>
    </div>

    <nav class="nav">
      <button
        v-for="item in items"
        :key="item.label"
        class="nav-item"
        :class="{ active: item.active }"
        type="button"
      >
        <span class="nav-dot" />
        <span>{{ item.label }}</span>
      </button>
    </nav>

    <div class="user-card">
      <div class="user-label">当前账号</div>
      <div class="user-name">Ben</div>
    </div>
  </aside>
</template>
