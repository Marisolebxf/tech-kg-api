import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ProcessInstanceDetailView from '../ProcessInstanceDetailView.vue'

const state = vi.hoisted(() => ({
  job: { id: 'job', name: '公共任务', graphSpace: 'public-hidden', isSharedProduction: true, writeAllowed: false },
  current: 'business-space',
  items: [] as { name: string; groupKind: string }[],
}))
vi.mock('../../../stores/graphSpace', () => ({ useGraphSpaceStore: () => ({
  get current() { return state.current }, get items() { return state.items },
  canWrite: (space: string) => space === 'business-space',
}) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { jobId: 'job' }, query: {} }), useRouter: () => ({ replace: vi.fn() }) }))
vi.mock('../../../api/workflowOperations', async (original) => ({
  ...await original<typeof import('../../../api/workflowOperations')>(),
  getJob: vi.fn(async () => ({ job: state.job, executions: [] })),
}))

describe('任务详情实际空间权限', () => {
  it('公共任务已个人隐藏且当前选择业务空间，仍显示只读提醒', async () => {
    state.job = { id: 'job', name: '公共任务', graphSpace: 'public-hidden', isSharedProduction: true, writeAllowed: false }
    state.current = 'business-space'
    state.items = []
    const wrapper = mount(ProcessInstanceDetailView, { global: { stubs: { AppAlert: { template: '<div><slot /></div>' } } } })
    await flushPromises()
    expect(wrapper.get('.space-readonly-bar').text()).toContain('操作需管理员执行')
    wrapper.unmount()
  })
  it('业务任务可写而当前选择公共空间，不误显示公共只读提醒', async () => {
    state.job = { id: 'job', name: '业务任务', graphSpace: 'business-space', isSharedProduction: false, writeAllowed: true }
    state.current = 'public-hidden'
    state.items = [{ name: 'public-hidden', groupKind: 'public' }]
    const wrapper = mount(ProcessInstanceDetailView)
    await flushPromises()
    expect(wrapper.find('.space-readonly-bar').exists()).toBe(false)
    wrapper.unmount()
  })
})
