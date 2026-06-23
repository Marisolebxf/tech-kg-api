<script setup lang="ts">
import type { RelationModeOption } from '../types/directRelation'

const props = defineProps<{
  mode: RelationModeOption
  codeLanguage: 'python' | 'node' | 'curl'
  codeExample: string
  requestRows: Array<[string, string, string, string]>
  responseRows: Array<[string, string, string]>
}>()

defineEmits<{
  codeChange: [language: 'python' | 'node' | 'curl']
}>()
</script>

<template>
  <section class="panel api-panel">
    <div class="panel-header">
      <div>
        <h2>接口说明</h2>
        <p>{{ mode.subtitle }}</p>
      </div>
      <div class="api-path">
        <span>接口路径：</span>
        <code>{{ mode.path }}</code>
      </div>
    </div>

    <div class="api-meta">
      <div><span>子功能名称</span><strong>{{ mode.label }}</strong></div>
      <div><span>请求方法</span><strong>GET</strong></div>
      <div><span>返回格式</span><strong>JSON</strong></div>
    </div>

    <div class="schema-grid">
      <div class="schema-card">
        <h3>请求参数</h3>
        <table>
          <thead>
            <tr>
              <th>字段名</th>
              <th>类型</th>
              <th>必填</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in requestRows" :key="row[0]">
              <td>{{ row[0] }}</td>
              <td>{{ row[1] }}</td>
              <td>{{ row[2] }}</td>
              <td>{{ row[3] }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div class="schema-card">
        <h3>返回字段</h3>
        <table>
          <thead>
            <tr>
              <th>字段路径</th>
              <th>类型</th>
              <th>说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in responseRows" :key="row[0]">
              <td>{{ row[0] }}</td>
              <td>{{ row[1] }}</td>
              <td>{{ row[2] }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="code-card">
      <div class="code-header">
        <h3>代码示例</h3>
        <div class="code-tabs">
          <button class="mini-tab" :class="{ active: codeLanguage === 'python' }" type="button" @click="$emit('codeChange', 'python')">Python</button>
          <button class="mini-tab" :class="{ active: codeLanguage === 'node' }" type="button" @click="$emit('codeChange', 'node')">Node.js</button>
          <button class="mini-tab" :class="{ active: codeLanguage === 'curl' }" type="button" @click="$emit('codeChange', 'curl')">cURL</button>
        </div>
      </div>
      <pre>{{ codeExample }}</pre>
    </div>
  </section>
</template>
