<script setup lang="ts">
import { computed } from 'vue'

import { highlightJsonValue } from '../../utils/code-highlight'

const props = defineProps<{ value: unknown }>()

const html = computed(() => highlightJsonValue(props.value ?? {}))
</script>

<template>
  <pre class="api-panel code-panel" v-html="html" />
</template>
