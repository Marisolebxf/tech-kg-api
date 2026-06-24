<script setup lang="ts">
import { highlightCodeLine } from '../../utils/code-highlight'

defineProps<{ lines: string[] }>()
</script>

<template>
  <div v-for="(line, index) in lines" :key="index" class="developer-code-line">
    <span class="developer-code-number">{{ index + 1 }}</span>
    <code class="developer-code-text" v-html="highlightCodeLine(line || ' ')" />
  </div>
</template>
