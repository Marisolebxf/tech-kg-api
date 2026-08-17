<script setup lang="ts">
defineProps<{
  label: string
  required?: boolean
  error?: string
  hint?: string
}>()
</script>

<template>
  <label class="kg-field" :class="{ 'kg-field--error': error }">
    <span class="kg-field__label">
      {{ label }}
      <em v-if="required" class="kg-field__required">*</em>
    </span>
    <div class="kg-field__control"><slot /></div>
    <span v-if="error" class="kg-field__error">{{ error }}</span>
    <span v-else-if="hint" class="kg-field__hint">{{ hint }}</span>
  </label>
</template>
