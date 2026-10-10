import { Cascader } from '@arco-design/web-vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listGraphSpaces } from '../../api/graphSearch'
import { useGraphSpaceStore } from '../../stores/graphSpace'
import GraphSpaceSelector from '../GraphSpaceSelector.vue'

vi.mock('../../api/graphSearch', () => ({ listGraphSpaces: vi.fn() }))
beforeEach(() => { setActivePinia(createPinia()); vi.resetAllMocks(); localStorage.clear() })
const mountSelector = () => mount(GraphSpaceSelector, { global: { components: { ACascader: Cascader } } })

describe('两级图空间选择', () => {
  it('公共目录置顶、只选择叶子空间，切换后保留全局当前空间', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: {
      spaces: ['private-a', 'dev', 'dev2'],
      items: [
        { name: 'private-a', groupKind: 'business', clientId: 'a', businessName: '业务 A' },
        { name: 'dev', groupKind: 'public' }, { name: 'dev2', groupKind: 'public' },
      ],
    } } as never)
    const wrapper = mountSelector()
    await flushPromises()
    const cascader = wrapper.getComponent(Cascader)
    expect(cascader.props('options')).toEqual([
      { value: 'public', label: '公共图空间', kind: 'public', children: [{value: 'dev', label: 'dev'}, {value: 'dev2', label: 'dev2'}] },
      { value: 'business:a', label: '业务 A', kind: 'business', children: [{value: 'private-a', label: 'private-a'}] },
    ])
    cascader.vm.$emit('change', 'public')
    expect(useGraphSpaceStore().current).toBe('private-a')
    cascader.vm.$emit('change', 'dev2')
    expect(useGraphSpaceStore().current).toBe('dev2')
    await nextTick()
    // 触发栏 200px 装不下长名时省略号截断，完整名靠包裹层悬停 title 兜底；
    // 弹层封顶宽 CSS 依赖 triggerProps contentClass 打标，一并守住
    expect(wrapper.find('.app-space-select').attributes('title')).toBe('切换当前工作图空间：dev2')
    expect(cascader.props('triggerProps')).toEqual({ contentClass: 'app-space-select-popup' })
    wrapper.unmount()
  })
  it('空授权集显示空状态且不选择默认空间', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: [], items: [] } } as never)
    const wrapper = mountSelector()
    await flushPromises()
    expect(wrapper.getComponent(Cascader).props('placeholder')).toBe('暂无可用图空间')
    expect(useGraphSpaceStore().current).toBe('')
    wrapper.unmount()
  })
})
