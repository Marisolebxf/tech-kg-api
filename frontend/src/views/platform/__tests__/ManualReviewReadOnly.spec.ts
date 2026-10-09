import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useGraphSpaceStore } from '../../../stores/graphSpace'
import ManualReviewWorkspaceView from '../ManualReviewWorkspaceView.vue'

const api = vi.hoisted(() => ({
  getProductionReview: vi.fn(), heartbeatProductionReview: vi.fn(), rerunExtractFailures: vi.fn(),
  directDecideProductionReview: vi.fn(), submitProductionReview: vi.fn(),
}))
vi.mock('../../../api/workflowOperations', () => api)
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { instanceId: 'case-1' } }) }))
beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useGraphSpaceStore().$patch({ current: 'dev', spaces: ['dev'], items: [{name: 'dev', bound: false, mine: false, writeAllowed: false, reviewAllowed: false}] })
  api.getProductionReview.mockResolvedValue({
    id: 'case-1', templateId: 'T_EXTRACT_FAIL', status: 'OPEN', canOperate: true,
    phase: '图谱构建', nodeId: 'extract', errorType: '逐行抽取失败', objectName: '失败对象',
    objectId: 'obj-1', objectType: 'entity', domain: '论文', riskLevel: 'P1', scope: 'OBJECT',
    sourceTable: 'paper', sourceRecordId: 'record-1', candidate: {}, input: {}, evidence: [],
    template: { id: 'T_EXTRACT_FAIL', actions: [] },
  })
})
afterEach(() => vi.useRealTimers())
describe('公共空间审核详情', () => {
  it('记录可查看，顶部重跑和底部确认保留并置灰', async () => {
    const wrapper = mount(ManualReviewWorkspaceView, { global: { stubs: {
      AForm: { template: '<div><slot /></div>' }, AFormItem: { template: '<div><slot /></div>' }, RouterLink: true,
    } } })
    await flushPromises()
    expect(wrapper.text()).toContain('record-1')
    const rerun = wrapper.findAll('button').find(button => button.text().includes('重跑该记录'))!
    expect(rerun.attributes()).toHaveProperty('disabled')
    expect(wrapper.get('.rw-foot__actions button').attributes()).toHaveProperty('disabled')
    await rerun.trigger('click')
    expect(api.rerunExtractFailures).not.toHaveBeenCalled()
    expect(api.heartbeatProductionReview).not.toHaveBeenCalled()
    wrapper.unmount()
  })
})
