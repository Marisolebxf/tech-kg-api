import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Pagination, Select } from '@arco-design/web-vue'

import ListPagination from '../list-pagination.vue'

const mountPager = (props: Record<string, unknown> = {}) =>
  mount(ListPagination, {
    props: { total: 12, page: 1, pageSize: 10, ...props },
  })

describe('ListPagination', () => {
  it('展示总数与页位，页数向上取整', () => {
    const w = mountPager()
    expect(w.text()).toContain('共 12 条 · 第 1 / 2 页')
  })

  it('total 为 0 时展示空态口径', () => {
    const w = mountPager({ total: 0 })
    expect(w.text()).toContain('共 0 条 · 第 1 / 1 页')
  })

  it('跳页框（前往）恒显：不再按 >7 页阈值隐藏，短列表页面与长列表形态一致', () => {
    const twoPages = mountPager()
    expect(twoPages.findComponent(Pagination).props('showJumper')).toBe(true)
    expect(twoPages.text()).toContain('前往')
    const singlePage = mountPager({ total: 7, pageSize: 10 })
    expect(singlePage.findComponent(Pagination).props('showJumper')).toBe(true)
  })

  it('允许调用方用摘要插槽扩展列表口径', () => {
    const w = mount(ListPagination, {
      props: { total: 527336, page: 1, pageSize: 10 },
      slots: { summary: '共 527336 个实体 · 第 1 / 52734 页 · 检索模式：浏览（图直查）' },
    })
    expect(w.text()).toContain('共 527336 个实体 · 第 1 / 52734 页 · 检索模式：浏览（图直查）')
  })

  it('a-pagination change 透传为 change 事件', () => {
    const w = mountPager()
    w.findComponent(Pagination).vm.$emit('change', 2)
    expect(w.emitted('change')).toEqual([[2]])
  })

  it('disabled 下透传给 a-pagination', () => {
    const w = mountPager({ disabled: true })
    expect(w.findComponent(Pagination).props('disabled')).toBe(true)
  })

  it('loading 同样禁用', () => {
    const w = mountPager({ loading: true })
    expect(w.findComponent(Pagination).props('disabled')).toBe(true)
  })

  it('允许调用方隐藏跳页输入框', () => {
    const w = mountPager({ total: 200, pageSize: 20, showJumper: false })
    expect(w.findComponent(Pagination).props('showJumper')).toBe(false)
  })

  it('compactPages 透传折叠参数（base=5/buffer=1，页码按钮最多 5 个且含尾页）', () => {
    const w = mountPager({ total: 200, pageSize: 20, page: 5, compactPages: true })
    expect(w.findComponent(Pagination).props('baseSize')).toBe(5)
    expect(w.findComponent(Pagination).props('bufferSize')).toBe(1)
    // 10 页触发折叠：形态 1 … 4 5 6 … 10 —— 数字页码恰 5 个且含尾页
    const numbers = w.findAll('.arco-pagination-item').map((n) => n.text()).filter((t) => /^\d+$/.test(t))
    expect(numbers).toEqual(['1', '4', '5', '6', '10'])
  })

  it('compactPages 下页数不多时仍全量展示', () => {
    const w = mountPager({ total: 55, pageSize: 10, page: 2, compactPages: true })
    // 6 页 < base(5)+buffer(1)*2=7 → 全展
    const numbers = w.findAll('.arco-pagination-item').map((n) => n.text()).filter((t) => /^\d+$/.test(t))
    expect(numbers).toEqual(['1', '2', '3', '4', '5', '6'])
  })

  it('默认不开启折叠（arco 原生形态，其他页面行为不变）', () => {
    const w = mountPager({ total: 200, pageSize: 20, page: 5 })
    // 10 页、arco 默认 base=6/buffer=2 → 折叠为 1 … 3 4 5 6 7 … 10（7 个页码）
    const numbers = w.findAll('.arco-pagination-item').map((n) => n.text()).filter((t) => /^\d+$/.test(t))
    expect(numbers).toEqual(['1', '3', '4', '5', '6', '7', '10'])
  })

  it('每页条数选择器使用默认档位并透传 change-size', () => {
    const w = mountPager()
    const select = w.findComponent(Select)
    expect(select.exists()).toBe(true)
    expect(select.props('options')).toEqual([10, 20, 50, 100])
    expect(select.props('modelValue')).toBe(10)
    // a-select @change 参数可能是宽 union，组件内 Number() 归一
    select.vm.$emit('change', '20')
    expect(w.emitted('change-size')).toEqual([[20]])
  })
})
