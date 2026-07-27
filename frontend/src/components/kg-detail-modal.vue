<script setup lang="ts">
export interface DetailModalPayload {
  title: string
  entityType: string
  relations: string
  confidence: string
  updatedAt: string
  evidence?: string[]
}

defineProps<{
  open: boolean
  payload: DetailModalPayload | null
}>()

const emit = defineEmits<{
  close: []
}>()
</script>

<template>
  <Teleport to="body">
    <div v-if="open && payload" class="kg-modal" @click.self="emit('close')">
      <section class="kg-modal__panel" role="dialog" aria-modal="true" :aria-label="payload.title">
        <header class="kg-modal__header">
          <div>
            <h2>{{ payload.title }}</h2>
            <p>{{ payload.entityType }}</p>
          </div>
          <button type="button" aria-label="关闭详情" @click="emit('close')">×</button>
        </header>
        <div class="kg-modal__body">
          <dl class="kg-modal__meta">
            <div><dt>命中关系</dt><dd>{{ payload.relations }}</dd></div>
            <div><dt>置信度</dt><dd>{{ payload.confidence }}</dd></div>
            <div><dt>更新时间</dt><dd>{{ payload.updatedAt }}</dd></div>
          </dl>
          <section v-if="payload.evidence?.length" class="kg-modal__evidence">
            <h3>证据链</h3>
            <ul>
              <li v-for="(line, index) in payload.evidence" :key="index">{{ line }}</li>
            </ul>
          </section>
        </div>
        <footer class="kg-modal__footer">
          <button type="button" class="kg-button kg-button--secondary" @click="emit('close')">关闭</button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<style scoped>
.kg-modal {
  position: fixed;
  inset: 0;
  z-index: 9999;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(16, 38, 76, 0.42);
  backdrop-filter: blur(2px);
}

.kg-modal__panel {
  width: min(480px, 100%);
  overflow: hidden;
  border: 1px solid rgba(167, 201, 250, 0.96);
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: var(--shadow-panel);
}

.kg-modal__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  padding: 16px 18px;
  border-bottom: 1px solid var(--border);
  background: linear-gradient(90deg, rgba(22, 93, 255, 0.08), transparent 48%);
}

.kg-modal__header h2 {
  margin: 0;
  color: var(--text-primary);
  font-size: 18px;
  line-height: 26px;
}

.kg-modal__header p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}

.kg-modal__header button {
  width: 32px;
  height: 32px;
  border: 0;
  border-radius: 999px;
  background: var(--surface-subtle);
  color: var(--text-secondary);
  font-size: 22px;
  line-height: 1;
  cursor: pointer;
}

.kg-modal__body {
  padding: 16px 18px;
}

.kg-modal__meta {
  display: grid;
  gap: 10px;
  margin: 0;
}

.kg-modal__meta div {
  display: grid;
  grid-template-columns: 88px minmax(0, 1fr);
  gap: 8px;
}

.kg-modal__meta dt {
  color: var(--text-tertiary);
  font-size: 12px;
}

.kg-modal__meta dd {
  margin: 0;
  color: var(--text-primary);
  font-size: 13px;
}

.kg-modal__evidence {
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--border);
}

.kg-modal__evidence h3 {
  margin: 0 0 8px;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}

.kg-modal__evidence ul {
  display: grid;
  gap: 6px;
  margin: 0;
  padding-left: 18px;
  color: var(--text-secondary);
  font-size: 13px;
  line-height: 20px;
}

.kg-modal__footer {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 18px 16px;
  border-top: 1px solid var(--border);
}
</style>
