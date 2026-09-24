<script setup lang="ts">
// 平台统一的列表分页条：共 N 条 · 第 x / y 页 + 每页条数 + 跳页。
// 客户端/服务端分页通用——total 由调用方给出（客户端传源数组长度，服务端传接口 total）。
// 跳页框（前往）恒显：不按总页数阈值隐藏，保证各页面右下角功能一致。
import { computed } from 'vue'
import { Pagination as APagination, Select as ASelect } from '@arco-design/web-vue'

import { PAGE_SIZE_OPTIONS } from '../composables/use-client-pagination'

const props = withDefaults(defineProps<{
  total: number
  page: number
  pageSize: number
  pageSizeOptions?: number[]
  disabled?: boolean
  loading?: boolean
  showJumper?: boolean
  compactPages?: boolean
}>(), {
  pageSizeOptions: () => PAGE_SIZE_OPTIONS,
  disabled: false,
  loading: false,
  showJumper: true,
  compactPages: false,
})

const emit = defineEmits<{ change: [page: number]; 'change-size': [size: number] }>()

const totalPages = computed(() =>
  props.total === 0 ? 1 : Math.ceil(props.total / props.pageSize),
)
const isDisabled = computed(() => props.disabled || props.loading)

// a-select @change 参数是宽 union，统一 Number() 容错（与 SchemaBrowserView 的写法一致）
function onSelectChange(value: unknown) {
  const next = Number(value)
  if (Number.isFinite(next) && next > 0) emit('change-size', next)
}
</script>

<template>
  <footer class="list-pagination" aria-label="列表分页">
    <slot name="summary" :total-pages="totalPages">
      <span>共 {{ total }} 条 · 第 {{ page }} / {{ totalPages }} 页</span>
    </slot>
    <span class="list-pagination__size">每页
      <a-select
        class="list-pagination__size-select"
        :model-value="pageSize"
        :options="pageSizeOptions"
        :scrollbar="false"
        :disabled="isDisabled"
        @change="onSelectChange"
      />
    </span>
    <a-pagination
      :current="page"
      :page-size="pageSize"
      :total="total"
      :show-jumper="showJumper"
      :disabled="isDisabled"
      :base-size="compactPages ? 5 : undefined"
      :buffer-size="compactPages ? 1 : undefined"
      @change="(next: number) => emit('change', next)"
    />
  </footer>
</template>

<style scoped>
.list-pagination{display:flex;flex-wrap:wrap;align-items:center;flex:0 0 auto;gap:8px 16px;min-height:56px;box-sizing:border-box;padding:12px 16px;border-top:1px solid #e5e6eb;background:#fff;color:#86909c;font-size:12px;line-height:20px}
.list-pagination :deep(.arco-pagination){max-width:100%;flex-wrap:wrap;row-gap:8px}
/* The inner page list must wrap too, or next-page controls are clipped on phones. */
.list-pagination :deep(.arco-pagination-list){display:flex;max-width:100%;flex-wrap:wrap;row-gap:8px;white-space:normal}
.list-pagination :deep(.arco-pagination-list>.arco-pagination-item){flex-shrink:0}
.list-pagination>span{white-space:nowrap}
.list-pagination .list-pagination__size{display:flex;align-items:center;gap:8px;margin-left:auto;white-space:nowrap}
.list-pagination :deep(.arco-select-view){box-sizing:border-box;width:88px;height:32px;min-height:32px;padding:0 12px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;font-size:14px;line-height:22px}
.list-pagination :deep(.list-pagination__size-select.arco-select-view:hover){border-color:#4080ff!important}
.list-pagination :deep(.list-pagination__size-select.arco-select-view:focus-within),.list-pagination :deep(.list-pagination__size-select.arco-select-view-focus){border-color:#165dff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
/* line-height 须带 !important：readability.css 对 .app-workspace 内所有 li 强刷
   line-height:22px !important，页码按钮是 <li>，不压过它数字会在 32px 按钮里偏上。 */
.list-pagination :deep(.arco-pagination-item){min-width:32px;height:32px;border-radius:4px;font-size:14px;line-height:32px!important}
.list-pagination :deep(.arco-pagination-item-active){background:#165dff;color:#fff}
/* 跳页框（前往 X 页）：全局 readability.css 会把原生 input 刷成 15px 字号，把 Arco 的
   自适应高度撑到 33.5px，比 32px 的页码按钮/每页下拉高一截；这里钉回 32px、14px 字号，
   白底描边口径与“每页”下拉一致，宽度 40→48px 容下 4 位页码。 */
.list-pagination :deep(.arco-pagination-jumper){height:32px;line-height:32px}
.list-pagination :deep(.arco-pagination-jumper-input){box-sizing:border-box;width:48px;height:32px;min-height:32px;padding:0 2px!important;border:1px solid #e5e6eb!important;border-radius:4px!important;background:#fff!important;box-shadow:none!important;font-size:14px}
.list-pagination :deep(.arco-pagination-jumper-input:hover){border-color:#4080ff!important}
.list-pagination :deep(.arco-pagination-jumper-input:focus-within),.list-pagination :deep(.arco-pagination-jumper-input.arco-input-wrapper-focus){border-color:#165dff!important;box-shadow:0 0 0 2px rgba(22,93,255,.1)!important}
.list-pagination :deep(.arco-pagination-jumper-input input){height:100%;padding:0!important;font-size:14px!important;line-height:30px!important}
</style>
