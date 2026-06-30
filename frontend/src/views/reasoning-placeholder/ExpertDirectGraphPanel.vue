<script setup lang="ts">
import ExpertDirectGraphPanel from './components/ExpertDirectGraphPanel.vue'
import type { DirectRelationQueryResponse } from './expert-direct-types'

defineProps<{
  title: string
  loading: boolean
  errorMessage: string
  response: DirectRelationQueryResponse | null
}>()
</script>

<template>
  <ExpertDirectGraphPanel
    :title="title"
    :loading="loading"
    :error-message="errorMessage"
    :response="response"
  />
</template>
