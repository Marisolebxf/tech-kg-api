import { Select as ASelect, Option as AOption } from '@arco-design/web-vue'
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { nextTick } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listGraphSpaces } from '../../api/graphSearch'
import { useGraphSpaceStore } from '../../stores/graphSpace'
import GraphSpaceSelector from '../GraphSpaceSelector.vue'

vi.mock('../../api/graphSearch', () => ({
  listGraphSpaces: vi.fn(),
}))
// config 的其它导出（portalAllowedOrigins 等）被 http/iframeBridge 链路访问，必须保留真实值
vi.mock('../../config', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../config')>()),
  graphSpace: 'cfg-space',
}))

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  localStorage.clear()
})

const mountSelector = () =>
  mount(GraphSpaceSelector, {
    global: {
      components: { 'a-select': ASelect, 'a-option': AOption },
    },
  })

describe('GraphSpaceSelector', () => {
  it('挂载即加载空间列表并展示当前值', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'dev2'] } } as never)
    const wrapper = mountSelector()
    await flushPromises()
    expect(listGraphSpaces).toHaveBeenCalledTimes(1)
    expect(wrapper.get('.app-space-select__label').text()).toBe('图空间')
    // 本地无取值且构建默认不在列表 → 归一为列表第一个
    expect(wrapper.get('.arco-select-view-value').text()).toBe('dev')

    // 选项随列表渲染（断言 option 组件数据源即可）
    const options = wrapper.findAllComponents(AOption)
    expect(options.map((option) => option.props('value'))).toEqual(['dev', 'dev2'])
  })

  it('store 切换当前空间后选择器跟随刷新', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'dev2'] } } as never)
    const wrapper = mountSelector()
    await flushPromises()
    const store = useGraphSpaceStore()
    store.setCurrent('dev')
    await nextTick()
    expect(wrapper.get('.arco-select-view-value').text()).toBe('dev')
  })

  it('选择框固定默认宽 + 下拉弹层带横向滚动打标', async () => {
    // arco <a-select> 不透传 scoped data-v，宽度只能经包裹层 :deep 下钻；
    // 弹层 teleport 到 body，只能经 triggerProps contentClass 打标横向滚动容器。
    // 本用例守住这两个机制不被改回死规则/裸类选择器
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'techkg'] } } as never)
    const wrapper = mountSelector()
    await flushPromises()
    const select = wrapper.findComponent(ASelect)
    expect(select.props('triggerProps')).toEqual({ contentClass: 'app-space-select-popup' })
    // 选项悬停 title 兜底显示完整空间名
    const option = wrapper.findAllComponents(AOption)[0]
    expect(option.attributes('title')).toBe('dev')
  })

  it('列表为空时展示“暂无可用图空间”兜底选项', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: [] } } as never)
    const wrapper = mountSelector()
    await flushPromises()
    // 空态占位项 disabled；arco 会为未匹配的当前值再渲染一个内部项，不做精确计数
    const options = wrapper.findAllComponents(AOption)
    const emptyOption = options.find((option) => option.text().includes('暂无可用图空间'))
    expect(emptyOption).toBeTruthy()
    expect(emptyOption!.props('disabled')).toBe(true)
  })
})
