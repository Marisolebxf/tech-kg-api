<script setup lang="ts">
import type { ServiceModule } from '../service-modules'
import iconSelectArrow from '../../../assets/icons/icon-select-arrow.svg'

defineProps<{
  moduleInfo: ServiceModule
  modules: ServiceModule[]
  curlSample: string
}>()

defineEmits<{
  selectModule: [key: string]
}>()
</script>

<template>
  <section class="developer-view">
    <div class="developer-view__meta">
      <label>
        <span>子功能名称：</span>
        <select class="select-with-icon" :value="moduleInfo.key" @change="$emit('selectModule', ($event.target as HTMLSelectElement).value)">
          <option v-for="item in modules" :key="item.key" :value="item.key">{{ item.title }}查询接口</option>
        </select>
        <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
      </label>
      <label>
        <span>接口路径：</span>
        <input :value="moduleInfo.endpoint" readonly />
      </label>
      <span>请求方法： {{ moduleInfo.method }}</span>
    </div>
    <div class="developer-view__cards">
      <section class="kg-panel">
      <div class="kg-panel__header"><h2 class="kg-panel__title">请求参数</h2></div>
      <table class="prototype-table">
        <thead>
          <tr><th>参数名</th><th>类型</th><th>必填</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="field in moduleInfo.requestFields" :key="field.name">
            <td>{{ field.name }}</td>
            <td>{{ field.type }}</td>
            <td>{{ field.required ?? '否' }}</td>
            <td>{{ field.description }}</td>
          </tr>
        </tbody>
      </table>
      </section>

      <section class="kg-panel">
      <div class="kg-panel__header"><h2 class="kg-panel__title">返回字段</h2></div>
      <table class="prototype-table">
        <thead>
          <tr><th>字段名</th><th>类型</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr v-for="field in moduleInfo.responseFields" :key="field.name">
            <td>{{ field.name }}</td>
            <td>{{ field.type }}</td>
            <td>{{ field.description }}</td>
          </tr>
        </tbody>
      </table>
      </section>
    </div>

    <section class="kg-panel developer-code">
      <div class="kg-panel__header"><h2 class="kg-panel__title">代码示例</h2></div>
      <pre>{{ curlSample }}</pre>
    </section>
  </section>
</template>

<style scoped>
.developer-view {
  display: grid;
  grid-template-rows: 40px minmax(0, 1.35fr) minmax(0, 1fr);
  gap: 12px;
  padding: 0 14px 14px;
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.developer-view__meta {
  display: grid;
  grid-template-columns: minmax(360px, 460px) minmax(360px, 1fr) max-content;
  align-items: center;
  gap: 36px;
  min-height: 40px;
  color: var(--text-secondary);
  font-size: 14px;
}

.developer-view__meta label {
  position: relative;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr);
  align-items: center;
  gap: var(--space-8);
  min-width: 0;
}

.developer-view__meta input,
.developer-view__meta select {
  width: 100%;
  height: 32px;
  min-width: 0;
  padding: 0 34px 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
}

.select-with-icon {
  appearance: none;
  -webkit-appearance: none;
  background-image: none;
}

.select-icon {
  position: absolute;
  top: 50%;
  right: 10px;
  width: 14px;
  height: 14px;
  transform: translateY(-50%);
  pointer-events: none;
}

.developer-view__cards {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  min-height: 0;
  overflow: hidden;
}

.developer-view__cards .kg-panel,
.developer-code {
  min-height: 0;
  overflow: auto;
}

.prototype-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.prototype-table th,
.prototype-table td {
  padding: 13px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text-secondary);
  text-align: left;
  font-size: 14px;
  line-height: 20px;
  vertical-align: top;
  overflow-wrap: anywhere;
}

.prototype-table th {
  color: var(--text-primary);
  background: #f7f9fc;
  font-weight: 600;
}

.prototype-table td:first-child {
  color: var(--text-primary);
  font-family: Consolas, Monaco, monospace;
}

.developer-code pre {
  margin: 0;
  padding: 14px 16px;
  color: #2f3442;
  background: #f7f9fc;
  font-family: Consolas, Monaco, monospace;
  font-size: 13px;
  line-height: 1.65;
  white-space: pre-wrap;
  overflow: auto;
}

@media (max-width: 1180px) {
  .developer-view,
  .developer-view__meta,
  .developer-view__cards {
    grid-template-columns: 1fr;
  }

  .developer-view {
    grid-template-rows: auto auto minmax(260px, 1fr);
    overflow: auto;
  }
}
</style>
