<template>
  <main class="app-shell" :aria-label="title">
    <slot />
  </main>
</template>

<script setup lang="ts">
defineProps<{
  title: string
}>()
</script>

<style scoped>
.app-shell {
  width: 100%;
  height: 100%;
}
</style>
