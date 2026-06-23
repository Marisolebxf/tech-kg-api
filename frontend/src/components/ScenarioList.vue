<script setup lang="ts">
import type { RelationScenario } from '../types/directRelation'

defineProps<{
  scenarios: RelationScenario[]
  selectedKey: string
}>()

defineEmits<{
  select: [key: string]
}>()

function displayValue(value: unknown) {
  if (Array.isArray(value)) {
    return value.join('、')
  }
  return String(value ?? '')
}
</script>

<template>
  <section class="panel result-panel">
    <div class="panel-header">
      <div>
        <h2>结果详情</h2>
        <p>按当前查询结果滚动展示多个关系场景</p>
      </div>
      <div class="panel-badge">共 {{ scenarios.length }} 条</div>
    </div>

    <div class="scenario-list">
      <button
        v-for="scenario in scenarios"
        :key="scenario.key"
        class="scenario-card"
        :class="{ active: scenario.key === selectedKey }"
        type="button"
        @click="$emit('select', scenario.key)"
      >
        <div class="scenario-card__title">
          <span>{{ scenario.label }}</span>
          <small>{{ scenario.last_test_time }}</small>
        </div>
        <dl class="scenario-card__grid">
          <template v-for="row in scenario.detail_rows" :key="row[0]">
            <dt>{{ row[0] }}</dt>
            <dd>{{ displayValue(row[1]) }}</dd>
          </template>
        </dl>
      </button>
    </div>
  </section>
</template>
