<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'

import iconCalendar from '../../assets/icons/icon-calendar.svg'
import iconClose from '../../assets/icons/icon-close.svg'
import iconCopy from '../../assets/icons/icon-copy.svg'
import iconInfo from '../../assets/icons/icon-info.svg'
import iconModalSetting from '../../assets/icons/icon-modal-setting.svg'
import iconSelectArrow from '../../assets/icons/icon-select-arrow.svg'
import flowReasoning from '../../assets/icons/技术方案-关系推理.svg'
import flowStandardize from '../../assets/icons/技术方案-标准化处理.svg'
import flowOutput from '../../assets/icons/技术方案-结果输出.svg'
import flowInput from '../../assets/icons/技术方案-输入数据.svg'
import flowArrow from '../../assets/icons/技术方案-箭头.svg'

const route = useRoute()

const activeView = ref<'test' | 'developer'>('test')
const resultMode = ref<'structured' | 'api'>('structured')
const activeCode = ref<'python' | 'node' | 'curl'>('python')
const showConfigModal = ref(false)
const showTechModal = ref(false)
const copied = ref(false)

const title = computed(() => String(route.meta.title ?? '知识推理模块'))
const featureName = computed(() => String(route.meta.featureName ?? `${title.value}推理构建`))
const codeSamples = computed(() => ({
  python: `# Python 调用模板
# url = "待后端确认接口地址"
# payload = {
#     "待定义字段": "待接入参数"
# }
# response = requests.post(url, json=payload)
# print(response.json())`,
  node: `// Node.js 调用模板
// const url = "待后端确认接口地址";
// const payload = {
//   待定义字段: "待接入参数",
// };
// const response = await fetch(url, {
//   method: "POST",
//   headers: { "Content-Type": "application/json" },
//   body: JSON.stringify(payload),
// });
// console.log(await response.json());`,
  curl: `# cURL 调用模板
# curl -X POST "待后端确认接口地址" \\
#   -H "Content-Type: application/json" \\
#   -d '{
#     "待定义字段": "待接入参数"
#   }'`,
}))

async function handleCopyCode() {
  try {
    await navigator.clipboard?.writeText(codeSamples.value[activeCode.value])
  } catch {
    // Keep prototype feedback even when browser blocks clipboard access.
  }
  copied.value = true
  window.setTimeout(() => {
    copied.value = false
  }, 1200)
}
</script>

<template>
  <div class="reasoning-placeholder">
    <header class="reasoning-placeholder__toolbar">
      <div class="kg-tabs" role="tablist" aria-label="功能视图">
        <button class="kg-tabs__item" :class="{ 'is-active': activeView === 'test' }" type="button" @click="activeView = 'test'">算法测试</button>
        <button class="kg-tabs__item" :class="{ 'is-active': activeView === 'developer' }" type="button" @click="activeView = 'developer'">开发者接口</button>
      </div>
      <button class="kg-button kg-button--text reasoning-placeholder__tech" type="button" @click="showTechModal = true">
        <img :src="iconInfo" alt="" aria-hidden="true" />
        技术方案
      </button>
    </header>

    <section v-if="activeView === 'test'" class="reasoning-placeholder__controls">
      <label>
        <span>子功能名称：</span>
        <select class="select-with-icon">
          <option>{{ featureName }}</option>
        </select>
        <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
        <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
      </label>
      <div class="reasoning-placeholder__actions">
        <button class="kg-button kg-button--secondary" type="button" @click="showConfigModal = true">参数设置</button>
        <button class="kg-button" type="button">执行测试</button>
      </div>
    </section>

    <main v-if="activeView === 'test'" class="reasoning-placeholder__main">
      <section class="kg-panel reasoning-placeholder__graph">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">测试结果预览</h2>
          <div class="reasoning-placeholder__time">最近测试时间：待执行</div>
        </div>
        <div class="reasoning-placeholder__canvas">
          <div class="reasoning-placeholder__empty">
            <strong>{{ title }}</strong>
            <span>图谱渲染占位区</span>
            <p>后续由各模块接入后端数据，在这里渲染真实图谱。</p>
          </div>
        </div>
      </section>

      <aside class="kg-panel reasoning-placeholder__detail">
        <div class="kg-panel__header">
          <h2 class="kg-panel__title">结果详情</h2>
          <div class="reasoning-placeholder__tabs">
            <button :class="{ 'is-active': resultMode === 'structured' }" type="button" @click="resultMode = 'structured'">结构化结果</button>
            <button :class="{ 'is-active': resultMode === 'api' }" type="button" @click="resultMode = 'api'">API结果示例</button>
          </div>
        </div>
        <dl v-if="resultMode === 'structured'" class="reasoning-placeholder__table">
          <div><dt>模块名称</dt><dd>{{ title }}</dd></div>
          <div><dt>接口路径</dt><dd>待后端确认</dd></div>
          <div><dt>数据来源</dt><dd>待接入</dd></div>
          <div><dt>实体数据</dt><dd>待接入</dd></div>
          <div><dt>关系数据</dt><dd>待接入</dd></div>
          <div><dt>渲染状态</dt><dd>占位框架</dd></div>
        </dl>
        <pre v-else class="reasoning-placeholder__code">{
  "module": "{{ title }}",
  "endpoint": "待后端确认",
  "request": "待定义",
  "response": "待定义",
  "status": "placeholder"
}</pre>
      </aside>
    </main>

    <section v-else class="reasoning-placeholder__developer">
      <div class="reasoning-placeholder__developer-meta">
        <label>
          <span>子功能名称：</span>
          <select class="select-with-icon"><option>{{ featureName }}</option></select>
          <img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" />
          <img class="field-info-icon" :src="iconInfo" alt="" aria-hidden="true" />
        </label>
        <label>
          <span>接口路径：</span>
          <input value="待后端确认" readonly />
        </label>
        <span>请求方法： POST</span>
      </div>

      <div class="reasoning-placeholder__developer-cards">
        <section class="kg-panel">
          <div class="kg-panel__header"><h2 class="kg-panel__title">请求参数</h2></div>
          <div class="reasoning-placeholder__table-wrap">
            <table class="reasoning-placeholder__developer-table">
              <thead><tr><th>字段名</th><th>类型</th><th>必填</th><th>说明</th></tr></thead>
              <tbody>
                <tr><td>待定义字段</td><td>待定义</td><td>待定</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待定</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待定</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待定</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待定</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待定</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待定</td><td>待后端补充</td></tr>
              </tbody>
            </table>
          </div>
        </section>
        <section class="kg-panel">
          <div class="kg-panel__header"><h2 class="kg-panel__title">返回字段</h2></div>
          <div class="reasoning-placeholder__table-wrap">
            <table class="reasoning-placeholder__developer-table">
              <thead><tr><th>字段名</th><th>类型</th><th>说明</th></tr></thead>
              <tbody>
                <tr><td>待定义字段</td><td>待定义</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待后端补充</td></tr>
                <tr><td>待定义字段</td><td>待定义</td><td>待后端补充</td></tr>
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
        <pre>{{ codeSamples[activeCode] }}</pre>
      </section>
    </section>

    <div v-if="showConfigModal || showTechModal" class="modal-mask" @click.self="showConfigModal = false; showTechModal = false">
      <section v-if="showConfigModal" class="modal modal--config" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2><img :src="iconModalSetting" alt="" aria-hidden="true" />测试参数设置</h2>
          <div class="modal__header-extra">
            <span class="modal__required"><span>*</span> 为必填项</span>
            <button type="button" @click="showConfigModal = false"><img :src="iconClose" alt="" aria-hidden="true" /></button>
          </div>
        </header>
        <div class="modal__body config-form">
          <label><span><i>*</i>参数项</span><select><option>待选择</option></select><img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" /></label>
          <label><span><i></i>参数项</span><input placeholder="待填写" /></label>
          <label><span><i></i>参数项</span><select><option>待选择</option></select><img class="select-icon" :src="iconSelectArrow" alt="" aria-hidden="true" /></label>
          <label><span><i></i>时间范围</span><input placeholder="开始时间        - 结束时间" /><img class="calendar-icon" :src="iconCalendar" alt="" aria-hidden="true" /></label>
        </div>
        <footer class="modal__footer">
          <button class="kg-button kg-button--secondary" type="button" @click="showConfigModal = false">取消</button>
          <button class="kg-button" type="button" @click="showConfigModal = false">保存并执行</button>
        </footer>
      </section>

      <section v-if="showTechModal" class="modal modal--tech" role="dialog" aria-modal="true">
        <header class="modal__header">
          <h2>技术方案</h2>
          <button type="button" @click="showTechModal = false"><img :src="iconClose" alt="" aria-hidden="true" /></button>
        </header>
        <div class="modal__body">
          <h3 class="modal__section-title">功能描述</h3>
          <p class="modal__desc">{{ title }}模块技术方案占位区。后续由各模块补充数据来源、推理规则、结果结构与异常处理说明。</p>
          <h3 class="modal__section-title">推理流程</h3>
          <div class="flow-steps">
            <div class="flow-step"><img :src="flowInput" alt="" /><strong>输入数据</strong><span>待接入参数</span></div>
            <img class="flow-step__arrow flow-step__arrow--one" :src="flowArrow" alt="" />
            <div class="flow-step"><img :src="flowStandardize" alt="" /><strong>标准化处理</strong><span>待定义规则</span></div>
            <img class="flow-step__arrow flow-step__arrow--two" :src="flowArrow" alt="" />
            <div class="flow-step"><img :src="flowReasoning" alt="" /><strong>关系推理</strong><span>待接入逻辑</span></div>
            <img class="flow-step__arrow flow-step__arrow--three" :src="flowArrow" alt="" />
            <div class="flow-step"><img :src="flowOutput" alt="" /><strong>结果输出</strong><span>待返回结构</span></div>
          </div>
        </div>
      </section>
    </div>
  </div>
</template>

<style scoped>
.reasoning-placeholder {
  display: flex;
  flex-direction: column;
  height: 100%;
  gap: var(--space-12);
}

.reasoning-placeholder__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--space-16);
}

.reasoning-placeholder__toolbar {
  min-height: 46px;
}

.reasoning-placeholder__controls {
  display: grid;
  grid-template-columns: 420px minmax(220px, 1fr);
  gap: var(--space-12);
  align-items: end;
  min-height: 44px;
  padding: 0 var(--space-16) var(--space-4);
}

.reasoning-placeholder__controls label {
  position: relative;
  display: grid;
  grid-template-columns: max-content minmax(0, 1fr) 14px;
  align-items: center;
  gap: var(--space-8);
}

.reasoning-placeholder__controls select {
  width: 100%;
  height: var(--control-height);
  padding: 0 34px 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: var(--surface);
  color: var(--text-primary);
}

.reasoning-placeholder__tech {
  gap: 4px;
}

.reasoning-placeholder__tech img,
.field-info-icon {
  width: 14px;
  height: 14px;
  object-fit: contain;
}

.select-with-icon {
  appearance: none;
  -webkit-appearance: none;
  background-image: none;
  cursor: pointer;
}

.select-icon,
.calendar-icon {
  position: absolute;
  right: 10px;
  width: 14px;
  height: 14px;
  pointer-events: none;
  object-fit: contain;
}

.select-icon {
  top: 50%;
  transform: translateY(-50%);
}

.reasoning-placeholder__controls .select-icon,
.reasoning-placeholder__developer-meta label .select-icon {
  right: 28px;
}

.reasoning-placeholder__actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-16);
}

.reasoning-placeholder__main {
  display: grid;
  grid-template-columns: minmax(0, 1.6fr) minmax(0, 1fr);
  gap: var(--space-16);
  flex: 1;
  min-height: 0;
  padding: var(--space-16);
  border-radius: var(--radius-md);
  background: var(--surface-subtle);
  overflow: hidden;
}

.reasoning-placeholder__graph,
.reasoning-placeholder__detail {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow: hidden;
}

.reasoning-placeholder__time {
  color: var(--text-tertiary);
}

.reasoning-placeholder__canvas {
  display: grid;
  flex: 1;
  min-height: 0;
  margin: 0 var(--space-16) var(--space-16);
  place-items: center;
  background: var(--surface);
}

.reasoning-placeholder__empty {
  display: grid;
  width: 360px;
  min-height: 180px;
  place-items: center;
  padding: var(--space-24);
  border: 1px dashed #b5d3fc;
  border-radius: var(--radius-lg);
  color: var(--text-secondary);
  text-align: center;
}

.reasoning-placeholder__empty strong {
  color: var(--text-primary);
  font-size: 18px;
}

.reasoning-placeholder__empty p {
  margin: 0;
  line-height: 24px;
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

.reasoning-placeholder__table {
  margin: 0;
  overflow-x: hidden;
  overflow-y: auto;
}

.reasoning-placeholder__table div {
  display: grid;
  grid-template-columns: 112px minmax(0, 1fr);
  min-height: 44px;
  border-bottom: 1px solid var(--border);
}

.reasoning-placeholder__table dt,
.reasoning-placeholder__table dd {
  display: flex;
  align-items: center;
  margin: 0;
  padding: 0 var(--space-16);
  min-width: 0;
  overflow-wrap: anywhere;
  word-break: break-word;
}

.reasoning-placeholder__table dt {
  justify-content: flex-end;
  border-right: 1px solid var(--border);
  color: var(--text-tertiary);
}

.reasoning-placeholder__code {
  flex: 1;
  min-height: 0;
  margin: 0;
  padding: var(--space-16) 24px;
  overflow: auto;
  color: #52c41a;
  background: var(--surface);
  font-family: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
  font-size: 13px;
  line-height: 24px;
  white-space: pre-wrap;
}

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
.reasoning-placeholder__developer-meta select,
.config-form input,
.config-form select {
  height: var(--control-height);
  padding: 0 var(--space-12);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  color: #86909c;
  background: var(--surface);
  font-weight: 400;
}

.reasoning-placeholder__developer-meta select,
.config-form select {
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
  color: #95c47a;
  font-size: 13px;
  line-height: 24px;
  white-space: pre;
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

.modal-mask {
  position: fixed;
  inset: 0;
  z-index: 20;
  display: grid;
  place-items: center;
  background: rgba(29, 33, 41, 0.42);
}

.modal {
  overflow: hidden;
  border-radius: var(--radius-lg);
  background: var(--surface);
  box-shadow: 0 18px 48px rgba(29, 33, 41, 0.2);
}

.modal--config {
  width: 560px;
}

.modal--tech {
  width: 780px;
}

.modal__header,
.modal__footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 56px;
  padding: 0 var(--space-16);
  border-bottom: 1px solid var(--border);
}

.modal__header h2 {
  display: inline-flex;
  align-items: center;
  gap: var(--space-8);
  margin: 0;
  font-size: 16px;
  font-weight: 500;
}

.modal__header h2 img {
  width: 24px;
  height: 24px;
}

.modal__header-extra {
  display: inline-flex;
  align-items: center;
  gap: var(--space-12);
}

.modal__required {
  color: var(--text-tertiary);
  font-size: 12px;
}

.modal__required span,
.config-form i {
  color: var(--danger);
  font-style: normal;
}

.modal__header button {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 0;
  cursor: pointer;
  background: transparent;
}

.modal__header button img {
  width: 16px;
  height: 16px;
}

.modal__body {
  padding: var(--space-16);
}

.modal__footer {
  justify-content: flex-end;
  gap: var(--space-12);
  border-top: 1px solid var(--border);
  border-bottom: 0;
}

.config-form {
  display: grid;
  gap: var(--space-16);
}

.config-form label {
  position: relative;
  display: grid;
  grid-template-columns: 96px 1fr;
  align-items: center;
  gap: var(--space-8);
}

.config-form label span {
  display: inline-flex;
  color: #86909c;
  font-weight: 400;
}

.config-form input::placeholder {
  color: #86909c;
  opacity: 1;
}

.config-form option {
  color: #86909c;
}

.config-form i {
  width: 10px;
}

.config-form .select-icon {
  right: 10px;
}

.calendar-icon {
  right: 10px;
}

.modal__section-title {
  position: relative;
  margin: 0 0 var(--space-12);
  padding-left: var(--space-12);
  font-size: 14px;
  font-weight: 500;
}

.modal__section-title::before {
  position: absolute;
  left: 0;
  width: 3px;
  height: 16px;
  border-radius: 2px;
  background: var(--primary);
  content: "";
}

.modal__desc {
  margin: 0 0 var(--space-20);
  padding: var(--space-16);
  border-radius: var(--radius-md);
  color: var(--text-secondary);
  background: var(--surface-subtle);
  line-height: 24px;
}

.flow-steps {
  position: relative;
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--space-16);
}

.flow-step {
  min-height: 136px;
  padding: var(--space-16);
  border: 1px solid var(--border);
  border-radius: var(--radius-md);
  text-align: center;
}

.flow-step img {
  width: 38px;
  height: 38px;
  margin-bottom: var(--space-12);
}

.flow-step strong,
.flow-step span {
  display: block;
}

.flow-step strong {
  margin-bottom: var(--space-12);
}

.flow-step span {
  color: var(--text-secondary);
  line-height: 22px;
}

.flow-step__arrow {
  position: absolute;
  top: 67px;
  width: 14px;
  height: 9px;
  opacity: 0.86;
}

.flow-step__arrow--one {
  left: calc(25% - 15px);
}

.flow-step__arrow--two {
  left: calc(50% - 7px);
}

.flow-step__arrow--three {
  left: calc(75% + 1px);
}
</style>
