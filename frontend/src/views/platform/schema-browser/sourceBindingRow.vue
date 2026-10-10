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
  readonly?: boolean
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

/** 数据源触发器悬停提示：显示「名称（host）」而非 id */
function dsLabel(id: string): string {
  const ds = props.datasources.find((item) => item.id === id)
  return ds ? `${ds.name}（${ds.host}）` : ''
}

const databases = ref<string[]>([])
const tables = ref<MysqlTable[]>([])
const columns = ref<MysqlColumn[]>([])
const loadingDatabases = ref(false)
const loadingTables = ref(false)
const loadingColumns = ref(false)

function patch(update: Partial<SourceBindingRow>) {
  if (props.readonly) return
  emit('update:modelValue', { ...props.modelValue, ...update })
}

async function loadDatabases() {
  if (props.readonly) return
  databases.value = []
  if (!row.value.datasourceId) return
  loadingDatabases.value = true
  try {
    databases.value = await listMysqlDatabases(row.value.datasourceId)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '列库失败', 'error')
  } finally {
    loadingDatabases.value = false
  }
}

async function loadTables() {
  if (props.readonly) return
  tables.value = []
  if (!row.value.datasourceId || !row.value.databaseName) return
  loadingTables.value = true
  try {
    tables.value = await listMysqlTables(row.value.datasourceId, row.value.databaseName)
  } catch (error) {
    showToast(error instanceof Error ? error.message : '列表失败', 'error')
  } finally {
    loadingTables.value = false
  }
}

async function loadColumns() {
  if (props.readonly) return
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
    showToast(error instanceof Error ? error.message : '列信息加载失败', 'error')
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
  // pk/时间列的默认纠正合并成一次 patch：两次连续 patch 都基于同一份
  // props.modelValue（props 异步更新），第二次 emit 会把第一次的改动整个
  // 覆盖掉——主键列停留在表中不存在的 'id'、时间列退回 'update_time'，
  // 即「绑定显示 id、保存后变 u_id」的错位来源
  const update: Partial<SourceBindingRow> = {}
  if (!names.includes(row.value.pkColumn)) {
    update.pkColumn = names.includes('id') ? 'id' : names[0]
  }
  if (!names.includes(row.value.timeColumn)) {
    const preferred = ['update_time', 'updated_at', 'modified_at', 'gmt_modified'].find((name) =>
      names.includes(name),
    )
    update.timeColumn = preferred || ''
  }
  if (Object.keys(update).length) patch(update)
}
</script>

<template>
  <div class="source-binding-row">
    <a-select
      :model-value="row.datasourceId"
      class="source-binding-row__select source-binding-row__ds"
      :title="dsLabel(row.datasourceId)"
      placeholder="数据源"
      allow-search
      :loading="false"
      :disabled="readonly"
      popup-container=".schema-modal"
      @change="onDatasourceChange"
    >
      <a-option v-for="ds in datasources" :key="ds.id" :value="ds.id" :label="`${ds.name}（${ds.host}）`" :title="`${ds.name}（${ds.host}）`">
        {{ ds.name }}（{{ ds.host }}）
      </a-option>
    </a-select>
    <a-select
      :model-value="row.databaseName"
      class="source-binding-row__select source-binding-row__db"
      :title="row.databaseName"
      placeholder="库"
      allow-search
      :loading="loadingDatabases"
      :disabled="readonly || !row.datasourceId"
      popup-container=".schema-modal"
      @change="onDatabaseChange"
    >
      <a-option v-for="db in databases" :key="db" :value="db" :title="db">{{ db }}</a-option>
    </a-select>
    <a-select
      :model-value="row.tableName"
      class="source-binding-row__select source-binding-row__table"
      :title="row.tableName"
      placeholder="表"
      allow-search
      :loading="loadingTables"
      :disabled="readonly || !row.databaseName"
      popup-container=".schema-modal"
      @change="onTableChange"
    >
      <a-option v-for="t in tables" :key="t.name" :value="t.name" :title="t.name">{{ t.name }}</a-option>
    </a-select>
    <a-select
      :model-value="row.pkColumn"
      class="source-binding-row__select source-binding-row__col"
      :title="row.pkColumn"
      placeholder="主键列"
      allow-search
      :loading="loadingColumns"
      :disabled="readonly || !row.tableName"
      popup-container=".schema-modal"
      @change="(value) => patch({ pkColumn: asString(value) })"
    >
      <a-option v-for="c in columns" :key="c.name" :value="c.name" :title="c.name">{{ c.name }}</a-option>
    </a-select>
    <a-select
      :model-value="row.timeColumn"
      class="source-binding-row__select source-binding-row__col"
      :title="row.timeColumn"
      placeholder="时间列（可空）"
      allow-search
      allow-clear
      :loading="loadingColumns"
      :disabled="readonly || !row.tableName"
      popup-container=".schema-modal"
      @change="(value) => patch({ timeColumn: asString(value) })"
      @clear="() => patch({ timeColumn: '' })"
    >
      <a-option v-for="c in columns" :key="c.name" :value="c.name" :title="c.name">{{ c.name }}</a-option>
    </a-select>
    <button
      v-if="removable"
      type="button"
      class="source-binding-row__remove"
      title="移除该绑定"
      :disabled="readonly"
      @click="emit('remove')"
    >
      ×
    </button>
  </div>
</template>

<style scoped>
/* 列宽下限收窄（合计 546px ≤ 弹窗正文宽），行不再设 min-width——
   窄屏不再整行横滚；超长名触发器内省略号，悬停 title 出全名（2026-10-10
   测试反馈「绑定来源表下面的左右滑块异常」，弃横向滚动改悬停看全） */
.source-binding-row{display:grid;grid-template-columns:minmax(104px,1.1fr) minmax(88px,0.8fr) minmax(104px,1fr) minmax(78px,0.6fr) minmax(116px,0.8fr) 24px;gap:8px;align-items:center}
.source-binding-row__select{min-width:0}
:deep(.source-binding-row__select.arco-select-view){display:inline-flex;box-sizing:border-box;align-items:center;width:100%;min-width:0;height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;font-size:14px;line-height:22px;box-shadow:none!important}
:deep(.source-binding-row__select.arco-select-view:hover){border-color:#4080ff!important;background:#fff!important}
:deep(.source-binding-row__select.arco-select-view:focus-within),:deep(.source-binding-row__select.arco-select-view-focus){border-color:#165dff!important;background:#fff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
:deep(.source-binding-row__select.arco-select-view .arco-select-view-input){box-sizing:border-box;width:100%;height:auto!important;min-height:0!important;padding:0!important;border:0!important;border-radius:0!important;background:transparent!important;color:#1d2129;font-size:14px!important;line-height:22px!important;box-shadow:none!important;outline:0!important}
:deep(.source-binding-row__select.arco-select-view .arco-select-view-input:focus),:deep(.source-binding-row__select.arco-select-view .arco-select-view-input:focus-visible){border:0!important;background:transparent!important;box-shadow:none!important;outline:0!important}
:deep(.source-binding-row__select.arco-select-view .arco-select-view-input-hidden){position:absolute!important;width:0!important;height:0!important;min-height:0!important;padding:0!important;border:0!important;opacity:0!important;box-shadow:none!important;outline:0!important;pointer-events:none!important}
:deep(.source-binding-row__select.arco-select-view .arco-select-view-value),:deep(.source-binding-row__select.arco-select-view .arco-select-view-placeholder){min-width:0;overflow:hidden;background:transparent!important;font-size:14px;line-height:30px;font-weight:400;text-overflow:ellipsis;white-space:nowrap}
.source-binding-row__remove{width:24px;height:24px;border:0;border-radius:4px;background:transparent;color:#e54848;font-size:16px;cursor:pointer}
.source-binding-row__remove:hover{background:#fff3f3}
.source-binding-row__remove:disabled{color:#a9aeb8;background:#f2f3f5;cursor:not-allowed}
</style>
