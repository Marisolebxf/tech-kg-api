import { describe, expect, it } from 'vitest'
import { nextTick, ref } from 'vue'

import { useClientPagination } from '../use-client-pagination'

function range(n: number) {
  return Array.from({ length: n }, (_, i) => i + 1)
}

describe('useClientPagination', () => {
  it('按页大小切片，末页不满页', () => {
    const source = ref(range(25))
    const { pagedItems, total, totalPages } = useClientPagination(source, 10)
    expect(total.value).toBe(25)
    expect(totalPages.value).toBe(3)
    expect(pagedItems.value).toEqual(range(10))
  })

  it('changePage 翻页后切片随之变化', () => {
    const source = ref(range(25))
    const { pagedItems, changePage } = useClientPagination(source, 10)
    changePage(3)
    expect(pagedItems.value).toEqual([21, 22, 23, 24, 25])
  })

  it('源数组收缩导致页码越界时自动回退到最后有效页', async () => {
    const source = ref(range(25))
    const { page, pagedItems, changePage } = useClientPagination(source, 10)
    changePage(3)
    // 末页 5 条全删（模拟删除/过滤收缩）
    source.value = range(20)
    await nextTick()
    expect(page.value).toBe(2)
    expect(pagedItems.value).toEqual(range(20).slice(10))
  })

  it('源数组清空后回到第 1 页（空态）', async () => {
    const source = ref(range(25))
    const { page, totalPages, changePage } = useClientPagination(source, 10)
    changePage(2)
    source.value = []
    await nextTick()
    expect(page.value).toBe(1)
    expect(totalPages.value).toBe(1)
  })

  it('resetPage 回到第 1 页', () => {
    const source = ref(range(25))
    const { page, changePage, resetPage } = useClientPagination(source, 10)
    changePage(2)
    resetPage()
    expect(page.value).toBe(1)
  })

  it('changePageSize 生效并重置回第 1 页；相同值 no-op', () => {
    const source = ref(range(25))
    const { page, pageSize, pagedItems, changePage, changePageSize } = useClientPagination(source, 10)
    changePage(2)
    changePageSize(50)
    expect(pageSize.value).toBe(50)
    expect(page.value).toBe(1)
    expect(pagedItems.value).toEqual(range(25))
    changePage(2)
    changePageSize(50)
    expect(page.value).toBe(2)
    changePageSize(Number.NaN)
    expect(pageSize.value).toBe(50)
  })
})
