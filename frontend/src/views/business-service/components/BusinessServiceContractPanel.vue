<script setup lang="ts">
import type { ServiceModule } from "../service-modules";
import iconSelectArrow from "../../../assets/icons/icon-select-arrow.svg";

defineProps<{
  moduleInfo: ServiceModule;
  modules: ServiceModule[];
  curlSample: string;
}>();

defineEmits<{
  selectModule: [key: string];
}>();
</script>

<template>
  <section class="developer-view">
    <div class="developer-view__meta">
      <label>
        <span>子功能名称：</span>
        <select
          class="select-with-icon"
          :value="moduleInfo.key"
          @change="
            $emit('selectModule', ($event.target as HTMLSelectElement).value)
          "
        >
          <option v-for="item in modules" :key="item.key" :value="item.key">
            {{ item.title }}查询接口
          </option>
        </select>
        <img
          class="select-icon"
          :src="iconSelectArrow"
          alt=""
          aria-hidden="true"
        />
      </label>
      <label>
        <span>接口路径：</span>
        <input :value="moduleInfo.endpoint" readonly />
      </label>
      <span>请求方法： {{ moduleInfo.method }}</span>
    </div>
    <div class="developer-view__cards">
      <section class="kg-panel">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">请求参数</h2>
        </div>
        <div class="developer-view__table-scroll">
          <table class="prototype-table prototype-table--request">
            <colgroup>
              <col class="col-name" />
              <col class="col-type" />
              <col class="col-required" />
              <col class="col-description" />
            </colgroup>
            <thead>
              <tr>
                <th>参数名</th>
                <th>类型</th>
                <th>必填</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="field in moduleInfo.requestFields" :key="field.name">
                <td>{{ field.name }}</td>
                <td>{{ field.type }}</td>
                <td>{{ field.required ?? "否" }}</td>
                <td>{{ field.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <section class="kg-panel">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">返回字段</h2>
        </div>
        <div class="developer-view__table-scroll">
          <table class="prototype-table prototype-table--response">
            <colgroup>
              <col class="col-name" />
              <col class="col-type" />
              <col class="col-description" />
            </colgroup>
            <thead>
              <tr>
                <th>字段名</th>
                <th>类型</th>
                <th>说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="field in moduleInfo.responseFields" :key="field.name">
                <td>{{ field.name }}</td>
                <td>{{ field.type }}</td>
                <td>{{ field.description }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>
    </div>

    <div class="developer-view__code-wrap">
      <section class="kg-panel developer-code">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">代码示例</h2>
        </div>
        <pre>{{ curlSample }}</pre>
      </section>
    </div>
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
  box-sizing: border-box;
  width: 100%;
  height: 32px;
  min-width: 0;
  padding: 0 34px 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
  font: inherit;
  line-height: 30px;
}

.developer-view__meta input[readonly] {
  padding-right: var(--space-12);
}

.developer-view__meta select {
  line-height: normal;
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

.developer-view__cards .kg-panel {
  position: relative;
  min-height: 0;
  overflow: hidden;
}

.developer-view__cards .kg-panel__header {
  position: absolute;
  z-index: 3;
  top: 0;
  right: 0;
  left: 0;
  height: 48px;
  border-bottom-color: transparent !important;
  background: #fff !important;
}

.developer-view__table-scroll {
  position: absolute;
  top: 48px;
  right: 0;
  bottom: 0;
  left: 0;
  overflow: auto;
}

.developer-code {
  min-height: 0;
  overflow: auto;
}

.developer-view__code-wrap {
  min-height: 0;
  box-sizing: border-box;
  width: 100%;
  padding: 0;
  overflow: hidden;
  border-radius: 0;
  background: transparent;
}

.developer-view__code-wrap .developer-code {
  box-sizing: border-box;
  width: 100%;
  height: 100%;
}

.prototype-table {
  width: 100%;
  border-collapse: collapse;
  table-layout: fixed;
}

.prototype-table--request .col-name {
  width: 24%;
}
.prototype-table--request .col-type {
  width: 16%;
}
.prototype-table--request .col-required {
  width: 10%;
}
.prototype-table--request .col-description {
  width: 50%;
}
.prototype-table--response .col-name {
  width: 30%;
}
.prototype-table--response .col-type {
  width: 20%;
}
.prototype-table--response .col-description {
  width: 50%;
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

.prototype-table thead {
  position: sticky;
  top: 0;
  z-index: 1;
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

  .developer-view__cards .kg-panel {
    height: min(440px, 58vh);
  }
}

/* Figma 567:862 developer contract layout. */
.developer-view {
  overflow: auto;
  grid-template-rows: 40px 332px minmax(250px, 1fr);
  gap: 16px;
  padding: 0 16px 16px;
}
.developer-view__cards {
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px !important;
  box-sizing: border-box;
  width: 100%;
  height: 332px;
  min-height: 332px;
  padding: 0 !important;
  overflow: visible;
  border-radius: 0 !important;
  background: transparent !important;
}
.developer-view__cards .kg-panel {
  position: static;
  overflow: hidden;
  border: 0 !important;
  border-radius: 8px !important;
  background: #fff !important;
  box-shadow: none !important;
}
.developer-view__cards .kg-panel__header {
  position: static;
  height: 48px;
  min-height: 48px;
  padding: 0 16px !important;
  background: #fff !important;
}
.developer-view__table-scroll {
  position: static;
  margin: 0 16px 16px;
  max-height: 304px;
  overflow: auto;
  -ms-overflow-style: none;
  scrollbar-width: none;
  scrollbar-color: transparent transparent;
  scrollbar-gutter: auto;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
}
.developer-view__table-scroll::-webkit-scrollbar {
  display: none;
  width: 0;
  height: 0;
}
.developer-view__table-scroll.kg-is-scrolling {
  scrollbar-width: none !important;
  scrollbar-color: transparent transparent !important;
  scrollbar-gutter: auto !important;
}
.developer-view__table-scroll.kg-is-scrolling::-webkit-scrollbar {
  display: none !important;
  width: 0 !important;
  height: 0 !important;
}
.developer-view__table-scroll.kg-is-scrolling::-webkit-scrollbar-thumb {
  background: transparent !important;
}
.developer-view__code-wrap {
  padding: 16px;
  border-radius: 8px;
}
.developer-view__code-wrap .developer-code {
  height: 100%;
  border: 0 !important;
  border-radius: 8px !important;
  background: #fff !important;
  box-shadow: none !important;
}
.developer-code .kg-panel__header {
  min-height: 48px !important;
  padding: 0 16px !important;
  border: 0 !important;
  background: #fff !important;
}
.prototype-table th,
.prototype-table td {
  height: 40px;
  padding: 0 12px;
  font-size: 12px;
  line-height: 20px;
  vertical-align: middle;
}
.prototype-table th {
  color: #4e5969;
  background: #f2f3f5;
  font-weight: 500;
}
.developer-code pre {
  min-height: 190px;
  padding: 16px 32px;
  color: #4e5969;
  background: #fff;
  font-size: 12px;
  line-height: 20px;
}
@media (max-width: 1180px) {
  .developer-view__cards {
    grid-template-columns: 1fr;
  }
  .developer-view__cards .kg-panel {
    height: auto;
  }
}

/* 请求参数/返回字段与代码示例共用同一套卡片和 16px 内容基线。 */
.developer-view__cards,
.developer-view__code-wrap {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
  padding: 0 !important;
}

.developer-view__cards > .kg-panel,
.developer-view__code-wrap > .developer-code {
  box-sizing: border-box;
  width: 100%;
  margin: 0;
}

.developer-view__cards .kg-panel__header,
.developer-view__code-wrap .kg-panel__header {
  box-sizing: border-box;
  width: 100%;
  height: 48px;
  min-height: 48px !important;
  margin: 0;
  padding: 0 16px !important;
}

.developer-view__table-scroll,
.developer-view__code-wrap .developer-code pre {
  box-sizing: border-box;
  width: calc(100% - 32px) !important;
  margin: 0 16px 16px !important;
}

.developer-view__table-scroll {
  right: auto !important;
  left: auto !important;
}

/* 与请求参数标题采用同一结构，不再通过整体位移补偿公共伪元素。 */
:global(.app-workspace) .developer-view__code-wrap .kg-panel__title {
  margin-left: 0 !important;
  padding-left: 11px !important;
}

:global(.app-workspace) .developer-view__code-wrap .kg-panel__title::before {
  left: 0 !important;
}
</style>
