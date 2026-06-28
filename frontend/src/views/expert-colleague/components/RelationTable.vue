<script setup lang="ts">
import type { ColleagueRelation } from '../types'

defineProps<{
  rows: ColleagueRelation[]
}>()
</script>

<template>
  <section class="kg-panel relation-table">
    <div class="kg-panel__header">
      <h2 class="kg-panel__title">同事关系列表</h2>
      <span class="kg-muted">按关系强度排序</span>
    </div>

    <div class="relation-table__scroll">
      <table>
        <thead>
          <tr>
            <th>专家</th>
            <th>机构</th>
            <th>部门</th>
            <th>关系类型</th>
            <th>证据来源</th>
            <th>合作时间</th>
            <th>强度</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in rows" :key="row.id">
            <td class="relation-table__name">{{ row.name }}</td>
            <td>{{ row.organization }}</td>
            <td>{{ row.department }}</td>
            <td><span class="relation-table__tag">{{ row.relationType }}</span></td>
            <td>{{ row.evidence }}</td>
            <td>{{ row.cooperationYears }}</td>
            <td>
              <div class="relation-table__score">
                <span>{{ row.strength }}</span>
                <i :style="{ width: `${row.strength}%` }" />
              </div>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
.relation-table__scroll {
  max-height: 260px;
  overflow: auto;
}

table {
  width: 100%;
  min-width: 960px;
  border-collapse: collapse;
}

th,
td {
  height: 44px;
  padding: 0 var(--space-16);
  border-bottom: 1px solid var(--border);
  text-align: left;
  white-space: nowrap;
}

th {
  color: var(--text-tertiary);
  background: var(--surface-subtle);
  font-size: 12px;
  font-weight: 500;
}

td {
  color: var(--text-secondary);
  font-size: 13px;
}

.relation-table__name {
  color: var(--text-primary);
  font-weight: 600;
}

.relation-table__tag {
  display: inline-flex;
  align-items: center;
  height: 24px;
  padding: 0 var(--space-8);
  border-radius: var(--radius-sm);
  color: var(--primary);
  background: var(--primary-subtle);
  font-size: 12px;
}

.relation-table__score {
  display: grid;
  grid-template-columns: 30px 88px;
  align-items: center;
  gap: var(--space-8);
}

.relation-table__score span {
  color: var(--text-primary);
  font-weight: 600;
}

.relation-table__score i {
  display: block;
  height: 6px;
  border-radius: 999px;
  background: var(--primary);
}
</style>
