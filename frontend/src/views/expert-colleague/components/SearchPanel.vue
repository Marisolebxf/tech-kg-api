<script setup lang="ts">
import type { ColleagueInferenceResult } from '../types'

defineProps<{
  result: ColleagueInferenceResult
  running?: boolean
}>()

const emit = defineEmits<{
  search: []
  config: []
}>()
</script>

<template>
  <section class="search-panel">
    <div class="search-panel__body">
      <label class="search-panel__field">
        <span>子功能名称：</span>
        <select>
          <option>{{ result.featureName }}</option>
        </select>
      </label>
      <div class="search-panel__actions">
        <button class="kg-button kg-button--secondary" type="button" @click="emit('config')">参数设置</button>
        <button class="kg-button" type="button" @click="emit('search')">
          {{ running ? '测试中...' : '执行测试' }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.search-panel {
  padding: 0 var(--space-16) var(--space-4);
}

.search-panel__body {
  display: grid;
  grid-template-columns: 420px minmax(220px, 1fr);
  gap: var(--space-12);
  align-items: end;
}

.search-panel__field {
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: center;
  gap: var(--space-8);
  color: var(--text-primary);
  font-size: 14px;
  line-height: 22px;
}

.search-panel__field input,
.search-panel__field select {
  width: 100%;
  height: var(--control-height);
  padding: 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: var(--text-primary);
  background: var(--surface);
  outline: none;
}

.search-panel__field input:focus,
.search-panel__field select:focus {
  border-color: var(--primary);
  box-shadow: 0 0 0 2px var(--primary-subtle);
}

.search-panel__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-16);
}
</style>
