import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import OperationsCenterView from '../OperationsCenterView.vue'
import ListPagination from '../../../components/list-pagination.vue'

const mocks = vi.hoisted(() => ({ getProductionReviews: vi.fn() }))
vi.mock('../../../api/workflowOperations', () => ({
  ...mocks, deleteProductionReview: vi.fn(), getExecution: vi.fn(),
  getProductionReview: vi.fn(), getTask: vi.fn(), rerunExtractFailures: vi.fn(),
  TRIGGER_SOURCE_LABEL: {},
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconSearch: { template: '<span />' } }))
// 队列页消费全局图空间 store（请求带 graphSpace、watch 切空间重拉）：此处只需静态当前空间
vi.mock('../../../stores/graphSpace', () => ({ useGraphSpaceStore: () => ({ current: 'dev' }) }))

function pending() {
  let resolve!: (value: { items: unknown[]; total: number }) => void
  let reject!: (reason: Error) => void
  const promise = new Promise<{ items: unknown[]; total: number }>((yes, no) => {
    resolve = yes
    reject = no
  })
  return { promise, resolve, reject }
}
const result = (name: string) => ({ items: [{ id: name, objectName: name, status: 'OPEN' }], total: 1 })
const wrappers: ReturnType<typeof mount>[] = []
function render() {
  const wrapper = mount(OperationsCenterView, {
    props: { mode: 'review' },
    global: { stubs: { ASelect: true, AInput: true, AModal: true, RouterLink: true } },
  })
  wrappers.push(wrapper)
  return wrapper
}
beforeEach(() => {
  mocks.getProductionReviews.mockReset()
  // 清队列视图状态快照，保证每次挂载都从默认第 1 页/默认筛选加载
  sessionStorage.removeItem('techkg.manual-review-queue.v1')
})
afterEach(() => {
  wrappers.splice(0).forEach(wrapper => wrapper.unmount())
  vi.useRealTimers()
})

describe('人工审核队列读取状态', () => {
  it('首次请求显示加载状态，失败可手动重试，不把失败显示成空队列', async () => {
    const first = pending()
    mocks.getProductionReviews.mockReturnValueOnce(first.promise).mockResolvedValueOnce(result('重试记录'))
    const wrapper = render()
    expect(wrapper.get('[role="status"]').text()).toContain('正在加载')
    expect(wrapper.text()).not.toContain('暂无人工处理记录')
    first.reject(new Error('服务暂时不可用'))
    await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('服务暂时不可用')
    expect(wrapper.find('.review-pagination').exists()).toBe(false)
    expect(mocks.getProductionReviews).toHaveBeenCalledTimes(1)
    await wrapper.get('[role="alert"] button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('重试记录')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper.get('.review-pagination').text()).toContain('共 1 条')
  })

  it.each(['success', 'failure'])('快速切换分类后忽略旧请求的 %s', async (outcome) => {
    const old = pending()
    const latest = pending()
    mocks.getProductionReviews.mockReturnValueOnce(old.promise).mockReturnValueOnce(latest.promise)
    const wrapper = render()
    await wrapper.findAll('.review-tabs nav button')[1].trigger('click')
    latest.resolve(result('最新分类记录'))
    await flushPromises()
    if (outcome === 'success') old.resolve(result('旧分类记录'))
    else old.reject(new Error('旧请求错误'))
    await flushPromises()
    expect(wrapper.text()).toContain('最新分类记录')
    expect(wrapper.text()).not.toContain('旧分类记录')
    expect(wrapper.text()).not.toContain('旧请求错误')
    expect(wrapper.find('[role="alert"]').exists()).toBe(false)
  })

  it('已加载记录后筛选失败时清除旧记录，显示错误及重试入口', async () => {
    mocks.getProductionReviews.mockResolvedValueOnce(result('旧记录')).mockRejectedValueOnce(new Error('筛选加载失败'))
    const wrapper = render()
    await flushPromises()
    await wrapper.findAll('.review-tabs nav button')[1].trigger('click')
    await flushPromises()
    expect(wrapper.text()).not.toContain('旧记录')
    expect(wrapper.get('[role="alert"]').text()).toContain('筛选加载失败')
  })

  it('卸载时清理防抖，晚返回的请求不触发分页补查', async () => {
    vi.useFakeTimers()
    const first = pending()
    mocks.getProductionReviews.mockResolvedValueOnce({ items: [], total: 100 }).mockReturnValueOnce(first.promise)
    const wrapper = render()
    await flushPromises()
    wrapper.findComponent(ListPagination).vm.$emit('change', 3)
    await flushPromises()
    wrapper.findComponent({ name: 'AInput' }).vm.$emit('update:modelValue', '待搜索')
    await wrapper.vm.$nextTick()
    wrapper.unmount()
    wrappers.splice(wrappers.indexOf(wrapper), 1)
    first.resolve({ items: [], total: 0 })
    await flushPromises()
    await vi.advanceTimersByTimeAsync(300)
    expect(mocks.getProductionReviews).toHaveBeenCalledTimes(2)
  })
})
