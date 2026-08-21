<script setup lang="ts">
defineOptions({ inheritAttrs: false })

const model = defineModel<string>({ default: '' })
</script>

<template>
  <a-input
    v-model="model"
    v-bind="$attrs"
    class="gkx-input"
  />
</template>

<style scoped>
.gkx-input {
  width: 100%;
}

.gkx-input :deep(.arco-input) {
  padding-inline: 12px;
}
</style>
