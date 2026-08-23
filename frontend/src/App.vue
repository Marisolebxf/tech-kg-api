<script setup lang="ts">
import { computed } from 'vue'
import { RouterView, useRoute } from 'vue-router'

import KgToast from './components/kg-toast.vue'
import AppLayout from './layouts/AppLayout.vue'

const route = useRoute()
const useBlankLayout = computed(() => route.meta.layout === 'blank')
</script>

<template>
  <RouterView v-if="useBlankLayout" />
  <AppLayout v-else />
  <KgToast />
</template>
