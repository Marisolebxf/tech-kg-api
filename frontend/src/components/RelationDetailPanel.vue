<script setup lang="ts">
import { computed } from 'vue'
import type { RelationScenario } from '../types/directRelation'

const props = defineProps<{
  scenario: RelationScenario | null
  activeTab: 'structured' | 'api'
}>()

defineEmits<{
  tabChange: [tab: 'structured' | 'api']
}>()

const structuredRows = computed(() => props.scenario?.detail_rows ?? [])

function renderValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.join('、')
  }
  return String(value ?? '')
}
</script>

<template>
  <section class="panel details-panel">
    <div class="panel-header">
      <div>
        <h2>结构化结果</h2>
        <p>{{ scenario?.last_test_time ? `最近测试时间：${scenario.last_test_time}` : '等待查询结果' }}</p>
      </div>
      <div class="tabs">
        <button class="tab" :class="{ active: activeTab === 'structured' }" type="button" @click="$emit('tabChange', 'structured')">
          结构化结果
        </button>
        <button class="tab" :class="{ active: activeTab === 'api' }" type="button" @click="$emit('tabChange', 'api')">
          API结果示例
        </button>
      </div>
    </div>

    <div v-if="activeTab === 'structured'" class="detail-table-wrap">
      <table class="detail-table">
        <tbody>
          <tr v-for="row in structuredRows" :key="row[0]">
            <th>{{ row[0] }}</th>
            <td>{{ renderValue(row[1]) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <div v-else class="api-example">
      <pre>{{ JSON.stringify(scenario?.api_example ?? {}, null, 2) }}</pre>
    </div>
  </section>
</template>
