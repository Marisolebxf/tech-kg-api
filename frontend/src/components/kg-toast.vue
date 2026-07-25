<script setup lang="ts">
import { useToast } from '../composables/use-toast'

const { toasts, dismissToast } = useToast()
</script>

<template>
  <div class="kg-toast-stack" aria-live="polite">
    <article
      v-for="item in toasts"
      :key="item.id"
      :class="['kg-toast', `kg-toast--${item.tone}`]"
    >
      <span>{{ item.message }}</span>
      <button type="button" aria-label="关闭" @click="dismissToast(item.id)">×</button>
    </article>
  </div>
</template>

<style scoped>
.kg-toast-stack {
  position: fixed;
  top: 20px;
  right: 20px;
  z-index: 10000;
  display: grid;
  gap: 10px;
  width: min(360px, calc(100vw - 32px));
  pointer-events: none;
}

.kg-toast {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(22, 93, 255, 0.18);
  border-radius: var(--radius-md);
  background: rgba(255, 255, 255, 0.98);
  box-shadow: var(--shadow-card);
  color: var(--text-primary);
  font-size: 13px;
  line-height: 20px;
  pointer-events: auto;
}

.kg-toast--success {
  border-color: rgba(0, 180, 42, 0.24);
}

.kg-toast--warning {
  border-color: rgba(255, 125, 0, 0.24);
}

.kg-toast button {
  flex: 0 0 auto;
  width: 24px;
  height: 24px;
  border: 0;
  border-radius: 999px;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 18px;
  line-height: 1;
  cursor: pointer;
}

.kg-toast button:hover {
  background: var(--surface-subtle);
  color: var(--text-primary);
}
</style>
