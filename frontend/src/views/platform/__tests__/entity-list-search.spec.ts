import { flushPromises, mount } from '@vue/test-utils'
import { Popover } from '@arco-design/web-vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EntityListView from '../EntityListView.vue'
import { browseEntities, searchEntities } from '../../../api/entitySearch'
import ListPagination from '../../../components/list-pagination.vue'

vi.mock('../../../api/entitySearch', () => ({
  browseEntities: vi.fn(), searchEntities: vi.fn(),
  entitySearchErrorMessage: (error: Error) => error.message,
  getEntityIndexStatus: async () => null,
  getEntitySearchTypes: async () => [],
}))
vi.mock('../../../api/currentGraphSpace', () => ({ currentGraphSpace: () => 'dev2' }))
vi.mock('../../../stores/graphSpace', () => ({ useGraphSpaceStore: () => ({ current: 'dev2' }) }))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

const row = { vid: 'entity-1', entityId: 'entity-1', name: '目标实体', entityType: 'DataSource', properties: {}, score: null }
beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(browseEntities).mockResolvedValue({ items: [row], total: 1, offset: 0, limit: 10, entityType: null, mode: 'browse' })
})

async function setup() {
  const wrapper = mount(EntityListView, { global: { stubs: {
    'a-input': { props: ['modelValue'], emits: ['update:modelValue'], template: '<input :value="modelValue" @input="$emit(\'update:modelValue\', $event.target.value)" />' },
    'a-select': { template: '<select><slot /></select>' },
    'a-option': { template: '<option><slot /></option>' },
    Popover: { props: ['trigger', 'position', 'contentClass'], template: '<div class="popover-stub"><slot /><div class="popover-content"><slot name="content" /></div></div>' },
  } } })
  await flushPromises()
  await wrapper.get('input').setValue('目标实体')
  return wrapper
}

describe('实体搜索结果', () => {
  it('精确结果按服务端总数分页，并显示精确匹配模式', async () => {
    vi.mocked(searchEntities).mockResolvedValue({ items: [row], total: 21, offset: 0, limit: 10, entityType: null, mode: 'graph-exact' })
    const wrapper = await setup()
    await wrapper.findAll('button').find(button => button.text() === '搜索')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('第 1 / 3 页')
    expect(wrapper.text()).toContain('精确匹配')
    wrapper.findComponent(ListPagination).vm.$emit('change', 2)
    await flushPromises()
    expect(searchEntities).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 10, space: 'dev2', keyword: '目标实体' }))
    wrapper.unmount()
  })

  it('浏览模式左侧先显示实体总数，右侧使用统一分页导航', async () => {
    vi.mocked(browseEntities).mockResolvedValue({ items: [row], total: 527336, offset: 0, limit: 10, entityType: null, mode: 'browse' })
    const wrapper = await setup()
    await wrapper.get('input').setValue('')
    await wrapper.findAll('button').find(button => button.text() === '搜索')!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('共 527336 个实体 · 第 1 / 52734 页 · 检索模式：浏览（图直查）')
    expect(wrapper.findComponent(ListPagination).exists()).toBe(true)
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
    await wrapper.findAll('button').find(button => button.text() === '搜索')!.trigger('click')
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
