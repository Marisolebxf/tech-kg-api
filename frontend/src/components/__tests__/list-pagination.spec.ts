import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import { Pagination, Select } from '@arco-design/web-vue'

import ListPagination from '../list-pagination.vue'

const mountPager = (props: Record<string, unknown> = {}) =>
  mount(ListPagination, {
    props: { total: 12, page: 1, pageSize: 10, ...props },
  })

describe('ListPagination', () => {
  const pageNumbers = (w: ReturnType<typeof mountPager>) => w.findAll('.list-pagination__page')
    .map(button => button.text()).filter(text => /^\d+$/.test(text))

  it('七页窗口点击右侧边缘后前进，左侧边缘后返回，不固定首尾页或省略号', async () => {
    const w = mountPager({ total: 1000, slidingPages: true })
    expect(pageNumbers(w)).toEqual(['1', '2', '3', '4', '5', '6', '7'])
    expect(w.findComponent(Pagination).exists()).toBe(false)
    expect(w.get('[aria-label="上一页"]').attributes('disabled')).toBeDefined()
    await w.get('[aria-label="第 7 页"]').trigger('click')
    expect(w.emitted('change')).toEqual([[7]])
    await w.setProps({ page: 7 })
    expect(pageNumbers(w)).toEqual(['4', '5', '6', '7', '8', '9', '10'])
    expect(w.get('[aria-current="page"]').text()).toBe('7')
    await w.setProps({ page: 8 })
    expect(pageNumbers(w)).toEqual(['4', '5', '6', '7', '8', '9', '10'])
    await w.setProps({ page: 10 })
    expect(pageNumbers(w)).toEqual(['7', '8', '9', '10', '11', '12', '13'])
    await w.setProps({ page: 7 })
    expect(pageNumbers(w)).toEqual(['4', '5', '6', '7', '8', '9', '10'])
    await w.setProps({ page: 4 })
    expect(pageNumbers(w)).toEqual(['1', '2', '3', '4', '5', '6', '7'])
  })

  it('七页窗口支持首尾边界、每页条数变化和总页数缩小', async () => {
    const w = mountPager({ total: 1000, page: 100, slidingPages: true })
    expect(pageNumbers(w)).toEqual(['94', '95', '96', '97', '98', '99', '100'])
    expect(w.get('[aria-label="下一页"]').attributes('disabled')).toBeDefined()
    await w.setProps({ page: 1, pageSize: 20 })
    expect(pageNumbers(w)).toEqual(['1', '2', '3', '4', '5', '6', '7'])
    await w.setProps({ total: 81, page: 5 })
    expect(pageNumbers(w)).toEqual(['1', '2', '3', '4', '5'])
    await w.setProps({ total: 0, page: 1 })
    expect(pageNumbers(w)).toEqual(['1'])
    expect(w.get('[aria-label="下一页"]').attributes('disabled')).toBeDefined()
  })

  it('七页窗口的上下页透传页码，加载中禁止翻页', async () => {
    const w = mountPager({ total: 1000, page: 7, slidingPages: true })
    await w.get('[aria-label="上一页"]').trigger('click')
    await w.get('[aria-label="下一页"]').trigger('click')
    expect(w.emitted('change')).toEqual([[6], [8]])
    await w.setProps({ loading: true })
    expect(w.findAll('.list-pagination__page').every(button => button.attributes('disabled') !== undefined)).toBe(true)
    await w.get('[aria-label="第 8 页"]').trigger('click')
    expect(w.emitted('change')).toEqual([[6], [8]])
  })

  it('展示总数与页位，页数向上取整', () => {
    const w = mountPager()
    expect(w.text()).toContain('共 12 条 · 第 1 / 2 页')
  })

  it('total 为 0 时展示空态口径', () => {
    const w = mountPager({ total: 0 })
    expect(w.text()).toContain('共 0 条 · 第 1 / 1 页')
  })

  it('允许调用方用摘要插槽扩展列表口径', () => {
    const w = mount(ListPagination, {
      props: { total: 527336, page: 1, pageSize: 10 },
      slots: { summary: '共 527336 个实体 · 第 1 / 52734 页' },
    })
    expect(w.text()).toContain('共 527336 个实体 · 第 1 / 52734 页')
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

  it('跳页框恒显：总页数 ≤7 时默认仍透传 showJumper=true（kgetl 曾按页数阈值隐藏，已回退）', () => {
    const w = mountPager({ total: 30, pageSize: 20 })
    expect(w.findComponent(Pagination).props('showJumper')).toBe(true)
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
