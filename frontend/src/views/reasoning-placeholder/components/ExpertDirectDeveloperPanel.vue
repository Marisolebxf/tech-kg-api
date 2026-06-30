<script setup lang="ts">
import { computed, ref } from 'vue'

import iconCopy from '../../../assets/icons/icon-copy.svg'
import iconInfo from '../../../assets/icons/icon-info.svg'
import iconSelectArrow from '../../../assets/icons/icon-select-arrow.svg'

import type { DocField } from '../expert-direct-types'

const props = defineProps<{
  featureName: string
  endpoint: string
  requestFields: DocField[]
  responseFields: DocField[]
  codeSamples: Record<'python' | 'node' | 'curl', string>
}>()

const activeCode = ref<'python' | 'node' | 'curl'>('python')
const copied = ref(false)

const currentCode = computed(() => props.codeSamples[activeCode.value])

async function handleCopyCode() {
  try {
    await navigator.clipboard?.writeText(currentCode.value)
  } catch {
    // ignore clipboard restrictions
  }
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1200)
}
</script>

<template>
  <section class="reasoning-placeholder__developer">
    <div class="reasoning-placeholder__developer-meta">
      <label>
        <span>子功能名称：</span>
        <select class="select-with-icon">
          <option>{{ featureName }}</option>
        </select>
        <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
        <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
      </label>
      <label>
        <span>接口路径：</span>
        <input :value="endpoint" readonly />
      </label>
      <span>请求方法： POST</span>
    </div>

    <div class="reasoning-placeholder__developer-cards">
      <section class="kg-panel">
        <div class="kg-panel__header"><h2 class="kg-panel__title">请求参数</h2></div>
        <div class="reasoning-placeholder__table-wrap">
          <table class="reasoning-placeholder__developer-table">
            <thead>
              <tr><th>字段名</th><th>类型</th><th>必填</th><th>说明</th></tr>
            </thead>
            <tbody>
              <tr v-for="field in requestFields" :key="field.name">
                <td>{{ field.name }}</td>
                <td>{{ field.type }}</td>
                <td>{{ field.required ?? '-' }}</td>
                <td>{{ field.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="kg-panel">
        <div class="kg-panel__header"><h2 class="kg-panel__title">返回字段</h2></div>
        <div class="reasoning-placeholder__table-wrap">
          <table class="reasoning-placeholder__developer-table">
            <thead>
              <tr><th>字段名</th><th>类型</th><th>说明</th></tr>
            </thead>
            <tbody>
              <tr v-for="field in responseFields" :key="field.name">
                <td>{{ field.name }}</td>
                <td>{{ field.type }}</td>
                <td>{{ field.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <section class="kg-panel reasoning-placeholder__developer-code">
      <div class="kg-panel__header">
        <h2 class="kg-panel__title">代码示例</h2>
        <div class="reasoning-placeholder__tabs">
          <button :class="{ 'is-active': activeCode === 'python' }" type="button" @click="activeCode = 'python'">Python</button>
          <button :class="{ 'is-active': activeCode === 'node' }" type="button" @click="activeCode = 'node'">Node.js</button>
          <button :class="{ 'is-active': activeCode === 'curl' }" type="button" @click="activeCode = 'curl'">cURL</button>
        </div>
      </div>
      <button class="reasoning-placeholder__copy" :class="{ 'is-copied': copied }" type="button" @click="handleCopyCode">
        <span v-if="copied" aria-hidden="true">✓</span>
        <img v-else :src="iconCopy" alt="" aria-hidden="true" />
      </button>
      <pre>{{ currentCode }}</pre>
    </section>
  </section>
</template>

<style scoped>
.reasoning-placeholder__developer {
  position: relative;
  display: grid;
  grid-template-rows: 44px minmax(0, 1.4fr) minmax(0, 1fr);
  gap: var(--space-16);
  flex: 1;
  min-height: 0;
  padding: 0 var(--space-16) var(--space-16);
  overflow: hidden;
}

.reasoning-placeholder__developer::before {
  position: absolute;
  z-index: 0;
  top: calc(44px + var(--space-16));
  right: var(--space-16);
  bottom: var(--space-16);
  left: var(--space-16);
  border-radius: var(--radius-md);
  background: var(--surface-subtle);
  content: "";
}

.reasoning-placeholder__developer > * {
  position: relative;
  z-index: 1;
}

.reasoning-placeholder__developer-meta {
  display: grid;
  grid-template-columns: 420px 1fr 160px;
  gap: 48px;
  align-items: center;
  min-height: 44px;
}

.reasoning-placeholder__developer-meta label {
  position: relative;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr) 14px;
  align-items: center;
  gap: var(--space-8);
}

.reasoning-placeholder__developer-meta input,
.reasoning-placeholder__developer-meta select {
  height: var(--control-height);
  padding: 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: #86909c;
  background: var(--surface);
  font-weight: 400;
}

.reasoning-placeholder__developer-meta select {
  appearance: none;
  -webkit-appearance: none;
  padding-right: 34px;
  background-image: none;
}

.reasoning-placeholder__developer-cards {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: var(--space-16);
  min-height: 0;
  padding: var(--space-16) var(--space-16) 0;
  overflow: hidden;
}

.reasoning-placeholder__developer-cards > .kg-panel,
.reasoning-placeholder__developer-code {
  overflow: hidden;
}

.reasoning-placeholder__table-wrap {
  height: calc(100% - 52px);
  margin: 0 6px var(--space-16);
  overflow: auto;
}

.reasoning-placeholder__developer-table {
  width: 100%;
  table-layout: fixed;
  border-collapse: collapse;
}

.reasoning-placeholder__developer-table th,
.reasoning-placeholder__developer-table td {
  height: 36px;
  padding: 0 var(--space-16);
  border-bottom: 1px solid var(--border);
  overflow: hidden;
  text-align: left;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reasoning-placeholder__developer-table thead th {
  position: sticky;
  top: 0;
  z-index: 1;
}

.reasoning-placeholder__developer-table th {
  color: var(--text-secondary);
  background: var(--surface-muted);
  font-weight: 400;
}

.reasoning-placeholder__developer-code {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  margin: 0 var(--space-16) var(--space-16);
}

.reasoning-placeholder__developer-code pre {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: var(--space-16) 32px;
  overflow: auto;
  color: #526b95;
  font-size: 13px;
  line-height: 24px;
  white-space: pre;
}

.reasoning-placeholder__tabs {
  display: inline-flex;
  padding: 2px;
  border-radius: var(--radius-sm);
  background: var(--surface-subtle);
}

.reasoning-placeholder__tabs button {
  height: 28px;
  padding: 0 var(--space-12);
  border: 0;
  border-radius: var(--radius-sm);
  cursor: pointer;
  color: var(--text-secondary);
  background: transparent;
}

.reasoning-placeholder__tabs .is-active {
  color: var(--primary);
  background: var(--surface);
}

.reasoning-placeholder__copy {
  position: absolute;
  right: 22px;
  bottom: 22px;
  z-index: 1;
  display: grid;
  width: 40px;
  height: 40px;
  place-items: center;
  border: 0;
  border-radius: 50%;
  cursor: pointer;
  background: var(--surface);
  box-shadow: 0 8px 18px rgba(29, 33, 41, 0.16);
}

.reasoning-placeholder__copy img {
  width: 16px;
  height: 16px;
}

.reasoning-placeholder__copy span {
  color: var(--success);
  font-size: 20px;
  font-weight: 600;
}

.select-with-icon {
  appearance: none;
  -webkit-appearance: none;
  background-image: none;
  cursor: pointer;
}

.select-icon {
  position: absolute;
  top: 50%;
  right: 28px;
  width: 14px;
  height: 14px;
  pointer-events: none;
  object-fit: contain;
  transform: translateY(-50%);
}

.field-info-icon {
  width: 14px;
  height: 14px;
  object-fit: contain;
}
</style>
