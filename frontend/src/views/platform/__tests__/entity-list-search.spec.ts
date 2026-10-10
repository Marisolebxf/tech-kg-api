import { flushPromises, mount } from '@vue/test-utils'
import { Popover } from '@arco-design/web-vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EntityListView from '../EntityListView.vue'
import { browseEntities, exportEntitiesCsv, searchEntities, getEntitySearchTypes } from '../../../api/entitySearch'
import ListPagination from '../../../components/list-pagination.vue'

vi.mock('../../../api/entitySearch', () => ({
  browseEntities: vi.fn(), searchEntities: vi.fn(),
  exportEntitiesCsv: vi.fn(),
  entitySearchErrorMessage: (error: Error) => error.message,
  getEntitySearchTypes: vi.fn(),
}))
vi.mock('../../../api/currentGraphSpace', () => ({ currentGraphSpace: () => 'dev2' }))
vi.mock('../../../stores/graphSpace', () => ({ useGraphSpaceStore: () => ({ current: 'dev2' }) }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

const row = { vid: 'entity-1', entityId: 'entity-1', name: '目标实体', entityType: 'DataSource', properties: {}, score: null }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(getEntitySearchTypes).mockResolvedValue([])
  vi.mocked(browseEntities).mockResolvedValue({ items: [row], total: 1, offset: 0, limit: 10, entityType: null, mode: 'browse' })
})

async function setup() {
  const wrapper = mount(EntityListView, { global: { stubs: {
    'a-input': { props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
    'a-select': { props: ['modelValue'], emits: ['update:modelValue', 'change'], template: '<select :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value); $emit(\'change\')"><slot /></select>' },
    'a-option': { props: ['value'], template: '<option :value="value"><slot /></option>' },
    Popover: { props: ['trigger', 'position', 'contentClass'], template: '<div class="popover-stub"><slot /><div class="popover-content"><slot name="content" /></div></div>' },
  } } })
  await flushPromises()
  await wrapper.get('input').setValue('目标实体')
  return wrapper
}

describe('实体搜索结果', () => {
  it('类型筛选默认显示全部，并通过原生 title 展示选项全称', async () => {
    const name = '非常长的实体类型名称用于完整显示测试'
    vi.mocked(getEntitySearchTypes).mockResolvedValue([{ name, count: 123 }])
    const wrapper = await setup()
    expect(wrapper.get('select').attributes('placeholder')).toBe('全部')
    expect(wrapper.get('select').attributes('aria-label')).toBe('实体类型')
    const option = wrapper.get('.entity-type-option')
    expect(option.text()).toBe(name)
    expect(option.attributes('title')).toBe(name)
    expect(wrapper.text()).not.toContain('（123）')
    wrapper.unmount()
  })

  it('搜索要求预览范围内匹配，并按实际匹配数分页', async () => {
    vi.mocked(searchEntities).mockResolvedValue({ items: [row], total: 21, offset: 0, limit: 10, entityType: null, mode: 'keyword' })
    const wrapper = await setup()
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('共 21 条')
    expect(wrapper.text()).not.toContain('第 1 / 3 页')
    expect(wrapper.findComponent(ListPagination).props()).toMatchObject({ showJumper: false, sizeAtEnd: true, total: 21 })
    wrapper.findComponent(ListPagination).vm.$emit('change', 2)
    await flushPromises()
    expect(searchEntities).toHaveBeenLastCalledWith(expect.objectContaining({ previewOnly: true, offset: 10, space: 'dev2', keyword: '目标实体' }))
    expect(wrapper.get('thead').text()).not.toContain('相关度')
    wrapper.unmount()
  })

  it('浏览最多 1000 个实体，最后一页和页数按展示范围计算，不能翻到范围外', async () => {
    vi.mocked(browseEntities).mockResolvedValue({ items: [row], total: 527336, offset: 0, limit: 10, entityType: null, mode: 'browse' })
    const wrapper = await setup()
    await wrapper.get('input').setValue('')
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('共 1000 个实体')
    expect(wrapper.text()).toContain('列表和搜索仅覆盖最多 1000 个实体')
    expect(wrapper.text()).not.toContain('第 1 / 52734 页')
    expect(wrapper.findComponent(ListPagination).props()).toMatchObject({ total: 1000, pageSize: 10, showJumper: false, sizeAtEnd: true })
    expect(wrapper.findComponent(ListPagination).exists()).toBe(true)
    wrapper.findComponent(ListPagination).vm.$emit('change', 100)
    await flushPromises()
    expect(browseEntities).toHaveBeenLastCalledWith(expect.objectContaining({ previewOnly: true, offset: 990, limit: 10 }))
    const calls = vi.mocked(browseEntities).mock.calls.length
    wrapper.findComponent(ListPagination).vm.$emit('change', 101)
    await flushPromises()
    expect(browseEntities).toHaveBeenCalledTimes(calls)
    wrapper.findComponent(ListPagination).vm.$emit('change-size', 100)
    await flushPromises()
    expect(wrapper.findComponent(ListPagination).props()).toMatchObject({ page: 1, pageSize: 100, total: 1000 })
    wrapper.unmount()
  })

  it('不足 1000 时保留实际数量，搜索无匹配时不恢复全图搜索，清空后恢复预览', async () => {
    const wrapper = await setup()
    expect(wrapper.text()).toContain('共 1 个实体')
    vi.mocked(searchEntities).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 10, entityType: null, mode: 'keyword' })
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('当前展示范围内未找到匹配')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(searchEntities).toHaveBeenLastCalledWith(expect.objectContaining({ previewOnly: true }))
    await wrapper.get('input').setValue('')
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(browseEntities).toHaveBeenLastCalledWith(expect.objectContaining({ previewOnly: true, offset: 0 }))
    expect(wrapper.text()).toContain('共 1 个实体')
    wrapper.unmount()
  })

  it('导出所选类型全部数据，不传搜索关键词和分页；全部选择不传类型过滤', async () => {
    vi.mocked(getEntitySearchTypes).mockResolvedValue([{ name: 'Expert', count: 5000 }])
    const createUrl = vi.fn(() => 'blob:csv')
    Object.defineProperty(URL, 'createObjectURL', { configurable: true, value: createUrl })
    Object.defineProperty(URL, 'revokeObjectURL', { configurable: true, value: vi.fn() })
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {})
    const blob = new Blob(['实体名称,ID\r\n张三,1'])
    vi.mocked(exportEntitiesCsv).mockResolvedValue(blob)
    const wrapper = await setup()
    const button = wrapper.findAll('button').find(item => item.text() === '导出 CSV')!
    expect(button.element.previousElementSibling?.id).toBe('entity-filter-type')
    await button.trigger('click')
    await flushPromises()
    expect(exportEntitiesCsv).toHaveBeenLastCalledWith({ space: 'dev2', entityType: null }, expect.any(AbortSignal))
    await wrapper.get('select').setValue('Expert')
    await flushPromises()
    await button.trigger('click')
    await flushPromises()
    expect(exportEntitiesCsv).toHaveBeenLastCalledWith({ space: 'dev2', entityType: 'Expert' }, expect.any(AbortSignal))
    expect(createUrl).toHaveBeenLastCalledWith(blob)
    expect(click).toHaveBeenCalledTimes(2)
    click.mockRestore()
    wrapper.unmount()
  })

  it('导出中禁止重复提交，失败后恢复按钮', async () => {
    let rejectExport!: (error: Error) => void
    vi.mocked(exportEntitiesCsv).mockReturnValue(new Promise((_resolve, reject) => { rejectExport = reject }))
    const wrapper = await setup()
    const button = wrapper.findAll('button').find(item => item.text() === '导出 CSV')!
    await button.trigger('click')
    expect(button.text()).toBe('导出中...')
    expect(button.attributes('disabled')).toBeDefined()
    rejectExport(new Error('图服务不可用'))
    await flushPromises()
    expect(button.text()).toBe('导出 CSV')
    expect(button.attributes('disabled')).toBeUndefined()
    wrapper.unmount()
  })

  it('多于四个公共属性时在悬浮或点击浮层中仅展示其余属性，不新增明细行', async () => {
    vi.mocked(browseEntities).mockResolvedValue({
      items: [{ ...row, properties: { first: '1', second: '2', third: '3', fourth: '4', fifth: '5', sixth: '6' } }],
      total: 1, offset: 0, limit: 10, entityType: null, mode: 'browse',
    })
    const wrapper = await setup()
    const more = wrapper.get('.entity-props__more')
    expect(more.text()).toBe('+2')
    expect(more.attributes('title')).toBeUndefined()
    expect(more.attributes('aria-label')).toBe('查看其余 2 个公共属性')
    const popover = wrapper.findComponent(Popover)
    expect(popover.props('trigger')).toEqual(['hover', 'click'])
    expect(popover.props('position')).toBe('bl')
    expect(wrapper.findAll('.entity-property-popover__item').map(item => item.attributes('title')))
      .toEqual(['fifth: 5', 'sixth: 6'])
    await more.trigger('click')
    expect(wrapper.find('.entity-detail-row').exists()).toBe(false)
    wrapper.unmount()
  })

  it('失败后清除旧结果，显示错误及重试，不能显示为无匹配', async () => {
    vi.mocked(searchEntities).mockRejectedValueOnce(new Error('实体检索暂不可用'))
      .mockResolvedValueOnce({ items: [row], total: 1, offset: 0, limit: 10, entityType: null, mode: 'graph-exact' })
    const wrapper = await setup()
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('实体检索暂不可用')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('未找到匹配')
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('table').text()).toContain('目标实体')
    wrapper.unmount()
  })
})
