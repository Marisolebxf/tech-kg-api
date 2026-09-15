import { computed, ref, watch, type Ref } from 'vue'

/** 列表分页统一的每页条数档位 */
export const PAGE_SIZE_OPTIONS = [10, 20, 50, 100]

/**
 * 客户端列表分页：对本地全量数组切片展示。
 *
 * 源数组因删除/过滤收缩导致页码越界时，自动回退到最后一个有效页（停在空页的常见场景：
 * 末页最后一条被删）。筛选条件变化需要回到第一页时由调用方调 resetPage()。
 */
export function useClientPagination<T>(source: Ref<T[]>, defaultPageSize = 10) {
  const page = ref(1)
  const pageSize = ref(defaultPageSize)
  const total = computed(() => source.value.length)
  const totalPages = computed(() =>
    total.value === 0 ? 1 : Math.ceil(total.value / pageSize.value),
  )
  const pagedItems = computed(() => {
    const start = (page.value - 1) * pageSize.value
    return source.value.slice(start, start + pageSize.value)
  })

  watch(total, () => {
    if (page.value > totalPages.value) page.value = totalPages.value
  })

  function resetPage() {
    page.value = 1
  }

  function changePage(next: number) {
    page.value = next
  }

  function changePageSize(size: number) {
    if (!Number.isFinite(size) || size <= 0 || size === pageSize.value) return
    pageSize.value = size
    page.value = 1
  }

  return { page, pageSize, total, totalPages, pagedItems, resetPage, changePage, changePageSize }
}
