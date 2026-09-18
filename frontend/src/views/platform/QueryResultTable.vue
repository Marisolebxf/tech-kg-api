<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button as AButton, Modal as AModal, Table as ATable } from '@arco-design/web-vue'
import type { TableColumnData } from '@arco-design/web-vue/es/table/interface'

const props = withDefaults(defineProps<{
  rows: Array<Record<string, unknown>>
  columns: string[]
  labels?: Record<string, string>
  page: number
  pageSize: number
  sortable?: boolean
  sortColumn?: string
  sortDirection?: 'asc' | 'desc'
  loading?: boolean
}>(), {
  labels: () => ({}), sortable: false, sortColumn: '', sortDirection: 'desc', loading: false,
})
const emit = defineEmits<{ sort: [column: string, direction: 'asc' | 'desc' | undefined] }>()
const selectedRow = ref<Record<string, unknown> | null>(null)
const detailsOpen = ref(false)
watch(() => props.rows, () => { detailsOpen.value = false })

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return 'NULL'
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
}
function isNumeric(column: string): boolean {
  return ['pagerank', 'rank', 'score', 'degree', 'out_degree', 'in_degree', 'count'].includes(column)
    || (props.rows.length > 0 && props.rows.every((row) => typeof row[column] === 'number' || row[column] == null))
}
const tableColumns = computed<TableColumnData[]>(() => [
  { title: '序号', dataIndex: '__index', width: 76, fixed: 'left', align: 'center' },
  ...props.columns.map((column, index): TableColumnData => ({
    title: props.labels[column] ?? column,
    dataIndex: `cell_${index}`,
    width: isNumeric(column) ? 160 : 300,
    align: isNumeric(column) ? 'right' : 'left',
    ellipsis: !['vid', '_id', 'id'].includes(column),
    tooltip: { position: 'top', contentStyle: { maxWidth: '480px', whiteSpace: 'pre-wrap', wordBreak: 'break-word' } },
    cellClass: isNumeric(column) ? 'query-cell-number' : 'query-cell-text',
    sortable: props.sortable ? {
      sorter: true,
      sortDirections: ['ascend', 'descend'],
      sortOrder: props.sortColumn === column ? (props.sortDirection === 'asc' ? 'ascend' : 'descend') : '',
    } : undefined,
  })),
  { title: '操作', dataIndex: '__action', width: 84, fixed: 'right', slotName: 'details', align: 'center' },
])
const tableRows = computed(() => props.rows.map((row, index) => ({
  __key: String(index),
  __index: (props.page - 1) * props.pageSize + index + 1,
  __raw: row,
  ...Object.fromEntries(props.columns.map((column, columnIndex) => [`cell_${columnIndex}`, formatCell(row[column])])),
})))
const tableWidth = computed(() => tableColumns.value.reduce((sum, column) => sum + (column.width ?? 0), 0))
function handleSort(field: string, direction: string): void {
  const column = props.columns[Number(field.replace('cell_', ''))]
  if (column) emit('sort', column, direction === 'ascend' ? 'asc' : direction === 'descend' ? 'desc' : undefined)
}
function showDetails(row: Record<string, unknown>): void {
  selectedRow.value = row
  detailsOpen.value = true
}
</script>

<template>
  <div class="query-result-table">
    <ATable
      :columns="tableColumns"
      :data="tableRows"
      row-key="__key"
      size="medium"
      :pagination="false"
      :bordered="{ wrapper: false, cell: false }"
      :hoverable="true"
      :loading="loading"
      :table-layout-fixed="true"
      :scroll="{ x: tableWidth }"
      :scrollbar="false"
      @sorter-change="handleSort"
    >
      <template #details="{ record }">
        <AButton type="text" size="small" @click="showDetails(record.__raw)">详情</AButton>
      </template>
    </ATable>
    <AModal v-model:visible="detailsOpen" title="记录详情" :footer="false" :width="640" :unmount-on-close="true">
      <dl class="query-record-details">
        <div v-for="column in columns" :key="column">
          <dt>{{ labels[column] ?? column }}</dt>
          <dd><pre>{{ formatCell(selectedRow?.[column]) }}</pre></dd>
        </div>
      </dl>
    </AModal>
  </div>
</template>

<style scoped>
.query-result-table{min-width:0;overflow:hidden}
.query-result-table :deep(.arco-table){color:var(--color-text-1)}
.query-result-table :deep(.arco-table-container){border:0;border-radius:0}
.query-result-table :deep(.arco-table-th){background:#f7f8fa;color:var(--color-text-1);font-weight:500}
.query-result-table :deep(.arco-table-th),.query-result-table :deep(.arco-table-td){height:40px!important;padding:0!important;border-color:var(--color-border-2)!important;font-size:14px;line-height:22px}
.query-result-table :deep(.arco-table-td){color:var(--color-text-2);background:var(--color-bg-2)}
.query-result-table :deep(.arco-table-tr:hover .arco-table-td){background:var(--color-fill-1)}
.query-result-table :deep(.query-cell-number){font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.query-result-table :deep(.arco-table-cell){box-sizing:border-box;height:39px;white-space:nowrap;padding:0 16px!important}
.query-record-details{margin:0;max-height:65vh;overflow:auto}
.query-record-details>div{display:grid;grid-template-columns:140px minmax(0,1fr);gap:16px;padding:12px 0;border-bottom:1px solid var(--color-border-2)}
.query-record-details dt{color:var(--color-text-3);overflow-wrap:anywhere}
.query-record-details dd{margin:0;min-width:0}
.query-record-details pre{margin:0;color:var(--color-text-1);font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:600px){.query-record-details>div{grid-template-columns:1fr;gap:8px}}
</style>
