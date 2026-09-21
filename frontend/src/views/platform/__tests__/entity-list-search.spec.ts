import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import EntityListView from '../EntityListView.vue'
import { browseEntities, searchEntities } from '../../../api/entitySearch'

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
    await wrapper.findAll('button').find(button => button.text() === '下一页')!.trigger('click')
    await flushPromises()
    expect(searchEntities).toHaveBeenLastCalledWith(expect.objectContaining({ offset: 10, space: 'dev2', keyword: '目标实体' }))
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
