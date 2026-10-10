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

  it('恢复原有搜索接口，并按接口匹配数分页', async () => {
    vi.mocked(searchEntities).mockResolvedValue({ items: [row], total: 21, offset: 0, limit: 10, entityType: null, mode: 'keyword' })
    const wrapper = await setup()
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('共 21 个实体')
    expect(wrapper.text()).not.toContain('第 1 / 3 页')
    expect(wrapper.findComponent(ListPagination).props()).toMatchObject({ showJumper: false, sizeAtEnd: true, total: 21 })
    wrapper.findComponent(ListPagination).vm.$emit('change', 2)
    await flushPromises()
    expect(searchEntities).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 10, space: 'dev2', keyword: '目标实体' }))
    expect(wrapper.get('thead').text()).not.toContain('相关度')
    wrapper.unmount()
  })

  it('浏览全部实体范围，使用实际总数并允许翻过第 100 页', async () => {
    vi.mocked(browseEntities).mockResolvedValue({ items: [row], total: 527336, offset: 0, limit: 10, entityType: null, mode: 'browse' })
    const wrapper = await setup()
    expect(wrapper.text()).toContain('共 527336 个实体')
    expect(wrapper.text()).not.toContain('1000 个实体')
    expect(wrapper.text()).not.toContain('导出')
    expect(exportEntitiesCsv).not.toHaveBeenCalled()
    expect(wrapper.findComponent(ListPagination).props()).toMatchObject({ total: 527336, pageSize: 10, showJumper: false, sizeAtEnd: true, slidingPages: true })
    expect(browseEntities).toHaveBeenLastCalledWith({ space: 'dev2', entityType: null, offset: 0, limit: 10 })
    await wrapper.get('input').setValue('')
    wrapper.findComponent(ListPagination).vm.$emit('change', 101)
    await flushPromises()
    expect(browseEntities).toHaveBeenLastCalledWith({ space: 'dev2', entityType: null, offset: 1000, limit: 10 })
    expect(wrapper.get('table').text()).toContain('目标实体')
    wrapper.findComponent(ListPagination).vm.$emit('change', 52734)
    await flushPromises()
    expect(browseEntities).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 527330 }))
    const calls = vi.mocked(browseEntities).mock.calls.length
    wrapper.findComponent(ListPagination).vm.$emit('change', 52735)
    await flushPromises()
    expect(browseEntities).toHaveBeenCalledTimes(calls)
    wrapper.findComponent(ListPagination).vm.$emit('change-size', 100)
    await flushPromises()
    expect(wrapper.findComponent(ListPagination).props()).toMatchObject({ page: 1, pageSize: 100, total: 527336 })
    wrapper.unmount()
  })

  it('小数据量显示实际数量，无匹配显示空态，清空后恢复全部范围浏览', async () => {
    const wrapper = await setup()
    expect(wrapper.text()).toContain('共 1 个实体')
    vi.mocked(searchEntities).mockResolvedValue({ items: [], total: 0, offset: 0, limit: 10, entityType: null, mode: 'keyword' })
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('未找到匹配')
    expect(wrapper.find('table').exists()).toBe(false)
    expect(searchEntities).toHaveBeenLastCalledWith({ keyword: '目标实体', space: 'dev2', entityType: null, offset: 0, limit: 10 })
    await wrapper.get('input').setValue('')
    await wrapper.findAll('button').find(button => button.text() === '查询')!.trigger('click')
    await flushPromises()
    expect(browseEntities).toHaveBeenLastCalledWith({ space: 'dev2', entityType: null, offset: 0, limit: 10 })
    expect(wrapper.text()).toContain('共 1 个实体')
    wrapper.unmount()
  })

  it('实际翻页请求加载期间保留七页窗口，点击 7 后展示 4 到 10', async () => {
    vi.mocked(getEntitySearchTypes).mockResolvedValue([{ name: 'DataSource', count: 200 }])
    vi.mocked(browseEntities).mockResolvedValue({ items: [row], total: 200, offset: 0, limit: 10, entityType: null, mode: 'browse' })
    const wrapper = await setup()
    await wrapper.get('input').setValue('')
    let resolvePage!: (value: Awaited<ReturnType<typeof browseEntities>>) => void
    vi.mocked(browseEntities).mockReturnValueOnce(new Promise(resolve => { resolvePage = resolve }))
    await wrapper.get('[aria-label="第 7 页"]').trigger('click')
    expect(wrapper.get('[aria-label="下一页"]').attributes('disabled')).toBeDefined()
    resolvePage({ items: [row], total: 200, offset: 60, limit: 10, entityType: null, mode: 'browse' })
    await flushPromises()
    const pages = () => wrapper.findAll('.list-pagination__page').map(item => item.text()).filter(text => /^\d+$/.test(text))
    expect(pages()).toEqual(['4', '5', '6', '7', '8', '9', '10'])
    await wrapper.get('[aria-label="第 8 页"]').trigger('click')
    await flushPromises()
    expect(pages()).toEqual(['4', '5', '6', '7', '8', '9', '10'])
    await wrapper.get('select').setValue('DataSource')
    await flushPromises()
    expect(pages()).toEqual(['1', '2', '3', '4', '5', '6', '7'])
    expect(browseEntities).toHaveBeenLastCalledWith(expect.objectContaining({ entityType: 'DataSource', offset: 0 }))
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
