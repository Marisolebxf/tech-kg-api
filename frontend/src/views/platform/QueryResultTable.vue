<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { Modal as AModal, Table as ATable } from '@arco-design/web-vue'
import type { TableColumnData } from '@arco-design/web-vue/es/table/interface'
import { getGraphNode, unwrapApiResponse, type ApiResponse, type GraphNode } from '../../api/graphSearch'
import { getErrorMessage } from '../../api/http'
import { collectQueryEntityReferences, queryEntityName, type QueryEntityReference } from '../../utils/queryRecordEntities'

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
  space?: string
  queryStatement?: string
  algorithmName?: string
  jobId?: string
}>(), {
  labels: () => ({}), sortable: false, sortColumn: '', sortDirection: 'desc', loading: false,
  space: '', queryStatement: '', algorithmName: '', jobId: '',
})
const emit = defineEmits<{ sort: [column: string, direction: 'asc' | 'desc' | undefined] }>()
const tableRoot = ref<HTMLElement | null>(null)
const hasHiddenColumns = ref(false)
const scrollActive = ref(false)
const viewportHeight = ref(280)
let scrollIdleTimer: ReturnType<typeof setTimeout> | undefined
let resizeObserver: ResizeObserver | undefined
function updateColumnShadow(): void {
  const scroller = tableRoot.value?.querySelector<HTMLElement>('.arco-table-content')
  hasHiddenColumns.value = !!scroller && scroller.scrollWidth - scroller.clientWidth - scroller.scrollLeft > 1
}
function updateTableViewport(): void {
  if (!tableRoot.value) return
  // Keep the scrollbar above pagination within the visible query viewport.
  viewportHeight.value = Math.max(200, window.innerHeight - tableRoot.value.getBoundingClientRect().top - 80)
  updateColumnShadow()
}
function handleScroll(): void {
  updateColumnShadow()
  scrollActive.value = true
  clearTimeout(scrollIdleTimer)
  scrollIdleTimer = setTimeout(() => { scrollActive.value = false }, 700)
}
onMounted(() => {
  if (typeof ResizeObserver !== 'undefined') {
    resizeObserver = new ResizeObserver(updateTableViewport)
    if (tableRoot.value) resizeObserver.observe(tableRoot.value)
    if (tableRoot.value?.parentElement) resizeObserver.observe(tableRoot.value.parentElement)
    const form = tableRoot.value?.closest('.platform-query')?.querySelector('.platform-query-form')
    if (form) resizeObserver.observe(form)
    const table = tableRoot.value?.querySelector('.arco-table-element')
    if (table) resizeObserver.observe(table)
  }
  window.addEventListener('resize', updateTableViewport)
  updateTableViewport()
})
onUnmounted(() => {
  resizeObserver?.disconnect()
  window.removeEventListener('resize', updateTableViewport)
  clearTimeout(scrollIdleTimer)
})
watch(() => [props.rows, props.columns], async () => {
  await nextTick()
  updateColumnShadow()
}, { flush: 'post' })
const selectedRow = ref<Record<string, unknown> | null>(null)
const detailsOpen = ref(false)
const selectedRecordNumber = ref(0)
interface EntityDetail extends QueryEntityReference {
  node?: GraphNode
  loading: boolean
  error: string
}
const entityDetails = ref<EntityDetail[]>([])
const entityReferenceCount = ref(0)
const entitiesLoading = computed(() => entityDetails.value.some((entity) => entity.loading))
let detailVersion = 0
watch(() => [props.rows, props.space, props.queryStatement, props.jobId, props.algorithmName], () => {
  detailsOpen.value = false
  detailVersion += 1
})
watch(detailsOpen, (open) => { if (!open) detailVersion += 1 })
onUnmounted(() => { detailVersion += 1 })

async function loadEntityDetail(entity: EntityDetail, version = detailVersion): Promise<void> {
  if (!props.space) return
  const space = props.space
  entity.loading = true
  entity.error = ''
  try {
    // The HTTP interceptor already unwraps Axios's response into the API envelope.
    const response = await getGraphNode(entity.vid, space) as unknown as ApiResponse<GraphNode>
    const node = unwrapApiResponse(response)
    if (String(node?.id) !== entity.vid || !Array.isArray(node.labels) || !node.properties || typeof node.properties !== 'object' || Array.isArray(node.properties)) {
      throw new Error('实体详情返回的数据不完整或 VID 不匹配')
    }
    if (version !== detailVersion || !detailsOpen.value) return
    entity.node = node
  } catch (error) {
    if (version !== detailVersion || !detailsOpen.value) return
    entity.error = getErrorMessage(error, '实体详情加载失败')
  } finally {
    if (version === detailVersion && detailsOpen.value) entity.loading = false
  }
}

async function loadEntityDetails(version: number): Promise<void> {
  // Fetch only on demand, at most two nodes concurrently; table rendering makes no node requests.
  const entities = entityDetails.value
  for (let index = 0; index < entities.length; index += 2) {
    if (version !== detailVersion || !detailsOpen.value) return
    await Promise.all(entities.slice(index, index + 2).map((entity) => loadEntityDetail(entity, version)))
  }
}

function formatCell(value: unknown): string {
  if (value === null || value === undefined) return 'NULL'
  return typeof value === 'object' ? JSON.stringify(value, null, 2) : String(value)
}
function isNumeric(column: string): boolean {
  return ['pagerank', 'rank', 'score', 'degree', 'out_degree', 'in_degree', 'count'].includes(column)
    || (props.rows.length > 0 && props.rows.every((row) => typeof row[column] === 'number' || row[column] == null))
}
const tableColumns = computed<TableColumnData[]>(() => [
  { title: '序号', dataIndex: '__index', width: 76, align: 'center' },
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
  { title: '操作', dataIndex: '__action', width: 84, fixed: 'right', slotName: 'details', align: 'left' },
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
function showDetails(row: Record<string, unknown>, index: number): void {
  const version = ++detailVersion
  selectedRow.value = row
  selectedRecordNumber.value = index
  const references = collectQueryEntityReferences(row)
  entityReferenceCount.value = references.length
  entityDetails.value = references.slice(0, 8).map((reference) => ({
    ...reference, node: reference.embeddedNode, loading: !!props.space, error: '',
  }))
  detailsOpen.value = true
  if (props.space) void loadEntityDetails(version)
}
</script>

<template>
  <div ref="tableRoot" class="query-result-table" :class="{ 'query-result-table--hidden-columns': hasHiddenColumns, 'query-result-table--scroll-active': scrollActive }" @scroll.capture="handleScroll">
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
      :scroll="{ x: tableWidth, maxHeight: `${viewportHeight}px` }"
      :scrollbar="false"
      @sorter-change="handleSort"
    >
      <template #details="{ record }">
        <button class="query-details-button" type="button" @click="showDetails(record.__raw, record.__index)">详情</button>
      </template>
    </ATable>
    <AModal v-model:visible="detailsOpen" modal-class="query-record-modal" title="记录详情" title-align="start" :width="640" :unmount-on-close="true">
      <div class="query-record-details">
        <section class="query-record-section">
          <h3>{{ algorithmName ? '作业信息' : '查询信息' }}</h3>
          <dl class="query-record-fields">
            <div v-if="space"><dt>图空间</dt><dd>{{ space }}</dd></div>
            <div><dt>结果序号</dt><dd>{{ selectedRecordNumber }}</dd></div>
            <div v-if="queryStatement"><dt>执行语句</dt><dd><pre>{{ queryStatement }}</pre></dd></div>
            <div v-if="algorithmName"><dt>算法</dt><dd>{{ algorithmName }}</dd></div>
            <div v-if="jobId"><dt>作业 ID</dt><dd><pre>{{ jobId }}</pre></dd></div>
          </dl>
        </section>
        <section class="query-record-section query-record-entities">
          <h3>实体信息</h3>
          <p v-if="entitiesLoading" class="query-record-hint" role="status">正在获取实体完整属性…</p>
          <p v-if="!entityReferenceCount" class="query-record-hint">当前记录未包含可识别的图 VID，暂无可补充的实体信息。</p>
          <p v-else-if="!space" class="query-record-hint">未选择图空间，仅展示查询返回的实体信息。</p>
          <article v-for="entity in entityDetails" :key="entity.vid" class="query-record-entity">
            <dl class="query-record-fields">
              <div><dt>图 VID</dt><dd><pre>{{ entity.vid }}</pre></dd></div>
              <template v-if="entity.node">
                <div><dt>实体名称</dt><dd>{{ queryEntityName(entity.node) ?? '未提供实体名称' }}</dd></div>
                <div><dt>实体类型</dt><dd>{{ entity.node.labels.join('、') || '未提供实体类型' }}</dd></div>
              </template>
            </dl>
            <p v-if="entity.error" class="query-record-error" role="alert">
              {{ entity.error }}<template v-if="entity.embeddedNode">；保留查询返回的实体属性。</template>
              <button type="button" class="query-record-retry" :disabled="entity.loading" @click="loadEntityDetail(entity)">重试</button>
            </p>
            <template v-if="entity.node">
              <h4>实体属性</h4>
              <dl v-if="Object.keys(entity.node.properties).length" class="query-record-fields">
                <div v-for="(value, key) in entity.node.properties" :key="key"><dt>{{ key }}</dt><dd><pre>{{ formatCell(value) }}</pre></dd></div>
              </dl>
              <p v-else class="query-record-hint">该实体未返回属性。</p>
            </template>
          </article>
          <p v-if="entityReferenceCount > entityDetails.length" class="query-record-hint">本条记录包含 {{ entityReferenceCount }} 个实体，当前展示前 {{ entityDetails.length }} 个。</p>
        </section>
        <section class="query-record-section">
          <h3>原始查询结果</h3>
          <dl class="query-record-fields">
            <div v-for="column in columns" :key="column"><dt>{{ labels[column] ?? column }}</dt><dd><pre>{{ formatCell(selectedRow?.[column]) }}</pre></dd></div>
          </dl>
        </section>
      </div>
      <template #footer>
        <button type="button" class="query-record-cancel" @click="detailsOpen = false">取消</button>
      </template>
    </AModal>
  </div>
</template>

<style scoped>
.query-result-table{min-width:0;overflow:hidden}
/* A single viewport contains the header and rows, so the vertical scrollbar
   starts at the field-name row. Sticky cells preserve the header on scroll. */
.query-result-table :deep(.arco-table-content){overflow:auto}
.query-result-table :deep(thead .arco-table-th){position:sticky;top:0;z-index:11}
.query-result-table :deep(thead .arco-table-col-fixed-right){z-index:12}
.query-details-button{height:auto;padding:0;border:0;background:transparent;color:#165dff;font-size:14px;line-height:22px;font-weight:400;white-space:nowrap;cursor:pointer}
.query-details-button:hover,.query-details-button:active{background:transparent;color:#4080ff}
/* Horizontal overflow is indicated by the fixed action column only. */
.query-result-table :deep(.arco-table-container::before){display:none;box-shadow:none}
/* The fixed action column only signals data still hidden to its left. */
.query-result-table:not(.query-result-table--hidden-columns) :deep(.arco-table-col-fixed-right-first::after){box-shadow:none}
.query-result-table :deep(.arco-table-content),.query-record-details{scrollbar-width:thin;scrollbar-color:transparent transparent}
.query-result-table:hover :deep(.arco-table-content),.query-result-table--scroll-active :deep(.arco-table-content),.query-result-table :deep(.arco-table-content.kg-is-scrolling),.query-record-details:hover,.query-record-details.kg-is-scrolling{scrollbar-color:rgba(78,89,105,.55) transparent}
.query-result-table :deep(.arco-table-content::-webkit-scrollbar),.query-record-details::-webkit-scrollbar{width:8px;height:8px}
.query-result-table :deep(.arco-table-content::-webkit-scrollbar-track),.query-record-details::-webkit-scrollbar-track{background:transparent}
.query-result-table :deep(.arco-table-content::-webkit-scrollbar-thumb),.query-record-details::-webkit-scrollbar-thumb{border:2px solid transparent;border-radius:999px;background-color:transparent;background-clip:padding-box}
.query-result-table:hover :deep(.arco-table-content::-webkit-scrollbar-thumb),.query-result-table--scroll-active :deep(.arco-table-content::-webkit-scrollbar-thumb),.query-result-table :deep(.arco-table-content.kg-is-scrolling::-webkit-scrollbar-thumb),.query-record-details:hover::-webkit-scrollbar-thumb,.query-record-details.kg-is-scrolling::-webkit-scrollbar-thumb{background-color:rgba(78,89,105,.55)}
.query-result-table :deep(.arco-table-content::-webkit-scrollbar-thumb:hover),.query-record-details::-webkit-scrollbar-thumb:hover{background-color:rgba(78,89,105,.8)}
.query-result-table :deep(.arco-table){color:var(--color-text-1)}
.query-result-table :deep(.arco-table-container){border:0;border-radius:0}
.query-result-table :deep(.arco-table-th){background:#f7f8fa;color:var(--color-text-1);font-weight:500}
.query-result-table :deep(.arco-table-th),.query-result-table :deep(.arco-table-td){height:40px!important;padding:0!important;border-color:var(--color-border-2)!important;font-size:14px;line-height:22px}
.query-result-table :deep(.arco-table-td){color:var(--color-text-2);background:var(--color-bg-2)}
.query-result-table :deep(.arco-table-tr:hover .arco-table-td){background:var(--color-fill-1)}
.query-result-table :deep(.query-cell-number){font-variant-numeric:tabular-nums;font-family:ui-monospace,SFMono-Regular,Consolas,monospace}
.query-result-table :deep(.arco-table-cell){box-sizing:border-box;height:39px;white-space:nowrap;padding:0 16px!important}
.query-record-details{margin:0;max-height:65vh;overflow:auto;text-align:left}
.query-record-fields{margin:0}
.query-record-fields>div{display:grid;grid-template-columns:140px minmax(0,1fr);gap:16px;padding:8px 0}
.query-record-section+.query-record-section{margin-top:20px;padding-top:16px;border-top:1px solid var(--color-border-2)}
.query-record-section h3{margin:0 0 8px;color:var(--color-text-1);font-size:14px;line-height:22px;font-weight:500}
.query-record-entity+.query-record-entity{margin-top:12px;padding-top:12px;border-top:1px dashed var(--color-border-2)}
.query-record-entity h4{margin:8px 0;color:var(--color-text-2);font-size:13px;line-height:20px;font-weight:500}
.query-record-hint{margin:8px 0;color:var(--color-text-3);font-size:13px;line-height:20px}
.query-record-error{margin:8px 0;color:#cb272d;font-size:13px;line-height:20px;overflow-wrap:anywhere}
.query-record-retry{margin-left:8px;padding:0;border:0;background:transparent;color:#165dff;cursor:pointer}
.query-record-retry:disabled{color:var(--color-text-4);cursor:not-allowed}
.query-record-details dt{color:var(--color-text-3);overflow-wrap:anywhere}
.query-record-details dd{margin:0;min-width:0}
.query-record-details pre{margin:0;color:var(--color-text-1);font:13px/1.6 ui-monospace,SFMono-Regular,Consolas,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
@media(max-width:600px){.query-record-fields>div{grid-template-columns:1fr;gap:8px}}
</style>
<style>
.query-record-modal{border-radius:8px}
.query-record-modal .arco-modal-header{box-sizing:border-box;height:56px;padding:0 24px}
.query-record-modal .arco-modal-title{justify-content:flex-start;text-align:left;font-size:16px;line-height:24px;font-weight:600}
.query-record-modal .arco-modal-body{padding:24px}
.query-record-modal .arco-modal-footer{box-sizing:border-box;min-height:64px;padding:16px 24px;border-top:1px solid #e5e6eb}
.query-record-modal .query-record-cancel{height:32px;padding:0 16px;border:1px solid #c9cdd4;border-radius:4px;background:#fff;color:#4e5969;font-size:14px;line-height:22px;cursor:pointer}
</style>
