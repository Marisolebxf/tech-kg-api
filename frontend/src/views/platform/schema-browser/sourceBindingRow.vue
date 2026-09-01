<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import {
  listMysqlDatabases,
  listMysqlTableColumns,
  listMysqlTables,
  type MysqlColumn,
  type MysqlDatasource,
  type MysqlTable,
} from '../../../api/mysqlDatasource'
import { useToast } from '../../../composables/use-toast'
import type { SourceBindingRow } from './sourceBindingRows'

const props = defineProps<{
  modelValue: SourceBindingRow
  datasources: MysqlDatasource[]
  removable: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: SourceBindingRow): void
  (e: 'remove'): void
}>()

const { showToast } = useToast()

const row = computed(() => props.modelValue)

type ArcoSelectValue = string | number | boolean | Record<string, unknown> | Array<string | number | boolean | Record<string, unknown>>

function asString(value: ArcoSelectValue | undefined): string {
  return typeof value === 'string' ? value : ''
}

const databases = ref<string[]>([])
const tables = ref<MysqlTable[]>([])
const columns = ref<MysqlColumn[]>([])
const loadingDatabases = ref(false)
const loadingTables = ref(false)
const loadingColumns = ref(false)

function patch(update: Partial<SourceBindingRow>) {
  emit('update:modelValue', { ...props.modelValue, ...update })
}

async function loadDatabases() {
  databases.value = []
  if (!row.value.datasourceId) return
  loadingDatabases.value = true
  try {
    databases.value = await listMysqlDatabases(row.value.datasourceId)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '列库失败', 'warning')
  } finally {
    loadingDatabases.value = false
  }
}

async function loadTables() {
  tables.value = []
  if (!row.value.datasourceId || !row.value.databaseName) return
  loadingTables.value = true
  try {
    tables.value = await listMysqlTables(row.value.datasourceId, row.value.databaseName)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '列表失败', 'warning')
  } finally {
    loadingTables.value = false
  }
}

async function loadColumns() {
  columns.value = []
  if (!row.value.datasourceId || !row.value.databaseName || !row.value.tableName) return
  loadingColumns.value = true
  try {
    columns.value = await listMysqlTableColumns(
      row.value.datasourceId,
      row.value.tableName,
      row.value.databaseName,
    )
  } catch (error) {
    showToast(error instanceof Error ? error.message : '列信息加载失败', 'warning')
  } finally {
    loadingColumns.value = false
  }
}

function onDatasourceChange(value: ArcoSelectValue | undefined) {
  patch({ datasourceId: asString(value), databaseName: '', tableName: '', pkColumn: 'id', timeColumn: 'update_time' })
}

function onDatabaseChange(value: ArcoSelectValue | undefined) {
  patch({ databaseName: asString(value), tableName: '', pkColumn: 'id', timeColumn: 'update_time' })
}

function onTableChange(value: ArcoSelectValue | undefined) {
  patch({ tableName: asString(value), pkColumn: 'id', timeColumn: 'update_time' })
}

watch(
  () => row.value.datasourceId,
  () => {
    void loadDatabases()
  },
  { immediate: true },
)

watch(
  () => `${row.value.datasourceId}|${row.value.databaseName}`,
  () => {
    void loadTables()
  },
  { immediate: true },
)

watch(
  () => `${row.value.datasourceId}|${row.value.databaseName}|${row.value.tableName}`,
  () => {
    void loadColumns().then(applyColumnDefaults)
  },
  { immediate: true },
)

function applyColumnDefaults() {
  if (!columns.value.length) return
  const names = columns.value.map((column) => column.name)
  if (!names.includes(row.value.pkColumn)) {
    patch({ pkColumn: names.includes('id') ? 'id' : names[0] })
  }
  if (!names.includes(row.value.timeColumn)) {
    const preferred = ['update_time', 'updated_at', 'modified_at', 'gmt_modified'].find((name) =>
      names.includes(name),
    )
    patch({ timeColumn: preferred || '' })
  }
}
</script>

<template>
  <div class="source-binding-row">
    <a-select
      :model-value="row.datasourceId"
      class="source-binding-row__select source-binding-row__ds"
      placeholder="数据源"
      allow-search
      :loading="false"
      popup-container=".source-bindings"
      @change="onDatasourceChange"
    >
      <a-option v-for="ds in datasources" :key="ds.id" :value="ds.id" :label="`${ds.name}（${ds.host}）`">
        {{ ds.name }}（{{ ds.host }}）
      </a-option>
    </a-select>
    <a-select
      :model-value="row.databaseName"
      class="source-binding-row__select source-binding-row__db"
      placeholder="库"
      allow-search
      :loading="loadingDatabases"
      :disabled="!row.datasourceId"
      popup-container=".source-bindings"
      @change="onDatabaseChange"
    >
      <a-option v-for="db in databases" :key="db" :value="db">{{ db }}</a-option>
    </a-select>
    <a-select
      :model-value="row.tableName"
      class="source-binding-row__select source-binding-row__table"
      placeholder="表"
      allow-search
      :loading="loadingTables"
      :disabled="!row.databaseName"
      popup-container=".source-bindings"
      @change="onTableChange"
    >
      <a-option v-for="t in tables" :key="t.name" :value="t.name">{{ t.name }}</a-option>
    </a-select>
    <a-select
      :model-value="row.pkColumn"
      class="source-binding-row__select source-binding-row__col"
      placeholder="主键列"
      allow-search
      :loading="loadingColumns"
      :disabled="!row.tableName"
      popup-container=".source-bindings"
      @change="(value) => patch({ pkColumn: asString(value) })"
    >
      <a-option v-for="c in columns" :key="c.name" :value="c.name">{{ c.name }}</a-option>
    </a-select>
    <a-select
      :model-value="row.timeColumn"
      class="source-binding-row__select source-binding-row__col"
      placeholder="时间列（水位）"
      allow-search
      :loading="loadingColumns"
      :disabled="!row.tableName"
      popup-container=".source-bindings"
      @change="(value) => patch({ timeColumn: asString(value) })"
    >
      <a-option v-for="c in columns" :key="c.name" :value="c.name">{{ c.name }}</a-option>
    </a-select>
    <button
      v-if="removable"
      type="button"
      class="source-binding-row__remove"
      title="移除该绑定"
      @click="emit('remove')"
    >
      ×
    </button>
  </div>
</template>

<style scoped>
.source-binding-row{display:grid;grid-template-columns:minmax(0,1.1fr) minmax(0,0.9fr) minmax(0,1fr) minmax(90px,0.7fr) minmax(110px,0.8fr) 24px;gap:8px;align-items:center}
.source-binding-row__select{min-width:0}
.source-binding-row__select :deep(.arco-select-view){box-sizing:border-box;width:100%;height:32px;border:1px solid #e5e6eb;border-radius:4px;background:#fff;font-size:13px;line-height:22px}
.source-binding-row__remove{width:24px;height:24px;border:0;border-radius:4px;background:transparent;color:#e54848;font-size:16px;cursor:pointer}
.source-binding-row__remove:hover{background:#fff3f3}
</style>
