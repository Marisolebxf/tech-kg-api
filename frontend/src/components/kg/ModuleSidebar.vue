<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute, RouterLink } from 'vue-router'

import sidebarLogo from '../../assets/sidebar/logo.png'
import sidebarMenu from '../../assets/sidebar/menu.png'
import navFlowIcon from '../../assets/sidebar/nav-flow.png'
import navGraphIcon from '../../assets/sidebar/nav-graph.png'
import navReasonIcon from '../../assets/sidebar/nav-reason.png'
import chatIcon from '../../assets/sidebar/chat.png'
import { KG_MODULES } from '../../config/kg-modules'

const route = useRoute()
const inferMenuExpanded = ref(true)

const activeRouteName = computed(() => String(route.name ?? ''))

function toggleInferMenu() {
  inferMenuExpanded.value = !inferMenuExpanded.value
}
</script>

<template>
  <aside class="sidebar">
    <div class="brand">
      <img class="brand-logo" :src="sidebarLogo" alt="" aria-hidden="true" />
      <span class="brand-title">知识图谱平台</span>
      <img class="brand-menu-icon" :src="sidebarMenu" alt="" aria-hidden="true" />
    </div>

    <nav class="nav-main">
      <div class="nav-root"><span class="nav-icon"><img :src="navFlowIcon" alt="" aria-hidden="true" /></span>流程编排<i>›</i></div>
      <div class="nav-root"><span class="nav-icon"><img :src="navGraphIcon" alt="" aria-hidden="true" /></span>图谱服务</div>
      <div class="nav-root active-root">
        <span class="nav-icon"><img :src="navReasonIcon" alt="" aria-hidden="true" /></span>
        知识推理服务
        <button
          class="nav-toggle"
          type="button"
          :aria-expanded="inferMenuExpanded"
          aria-label="展开或收起知识推理服务列表"
          @click="toggleInferMenu"
        >
          <i :class="{ expanded: inferMenuExpanded }">›</i>
        </button>
      </div>
      <div v-show="inferMenuExpanded" class="nav-branch">
        <RouterLink
          v-for="module in KG_MODULES"
          :key="module.code"
          :to="module.path"
          class="nav-branch-item"
          :class="{ selected: activeRouteName === module.routeName }"
        >
          {{ module.navLabel }}
        </RouterLink>
      </div>
    </nav>

    <div class="user-box">
      <span class="avatar"></span>
      <strong>Ben</strong>
      <img class="chat-icon" :src="chatIcon" alt="" aria-hidden="true" />
    </div>
  </aside>
</template>
