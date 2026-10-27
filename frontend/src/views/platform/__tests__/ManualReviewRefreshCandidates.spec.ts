/**
 * MR-CAND B：T_LINK 受控刷新未决候选——按钮只出现在可编辑 T_LINK；刷新后
 * 候选列表更新、版本随响应推进；选中目标被剔除时清空选择并提示；真 no-op
 * 不宣称变更；终态不出刷新入口。
 */
import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useGraphSpaceStore } from '../../../stores/graphSpace'
import ManualReviewWorkspaceView from '../ManualReviewWorkspaceView.vue'

const api = vi.hoisted(() => ({
  getProductionReview: vi.fn(), heartbeatProductionReview: vi.fn(), rerunExtractFailures: vi.fn(),
  directDecideProductionReview: vi.fn(), submitProductionReview: vi.fn(),
  refreshProductionReviewCandidates: vi.fn(),
}))
vi.mock('../../../api/workflowOperations', () => api)
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { instanceId: 'case-1' } }),
  RouterLink: { template: '<a><slot /></a>' },
}))

const ARadioGroupStub = {
  props: ['modelValue'],
  emits: ['update:modelValue'],
  template: '<select data-test="verdict" :value="modelValue" @change="$emit(\'update:modelValue\', $event.target.value)"><slot /></select>',
}
const ARadioStub = { props: ['value'], template: '<option :value="value"><slot /></option>' }

function mountView() {
  return mount(ManualReviewWorkspaceView, {
    global: {
      stubs: {
        AForm: { template: '<div><slot /></div>', methods: { validate: () => undefined } },
        AFormItem: { template: '<div><slot /></div>' },
        RouterLink: true,
        'a-radio-group': ARadioGroupStub,
        'a-radio': ARadioStub,
      },
    },
  })
}

const baseLinkCase = {
  id: 'case-1', templateId: 'T_LINK', canOperate: true,
  phase: '图谱构建', nodeId: 'align', errorType: '同名实体冲突', objectName: '张三',
  objectId: 'new-1', objectType: 'entity', domain: '人才', riskLevel: 'P1', scope: 'OBJECT',
  sourceTable: 'dwd_person', sourceRecordId: 'r-1', version: 3,
  input: {}, evidence: [],
  template: { id: 'T_LINK', allowedActions: ['entity-confirm', 'reject-candidate'] },
}
const snapshotWithCandidates = {
  existingCandidates: [{ vid: 'old-1', name: '张三', score: 0.8 }],
  _incoming: { vid: 'new-1', name: '张三', props: { org: '中国科学院' } },
  _nodeLabel: 'Expert',
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useGraphSpaceStore().$patch({
    current: 'dev', spaces: ['dev'],
    items: [{ name: 'dev', bound: false, mine: false, writeAllowed: true, reviewAllowed: true }],
  })
})

describe('MR-CAND B 刷新候选', () => {
  it('可编辑 T_LINK 出现刷新按钮；点击带当前版本调用，列表按响应更新', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined, candidate: snapshotWithCandidates,
    })
    api.refreshProductionReviewCandidates.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', version: 4,
      candidate: {
        ...snapshotWithCandidates,
        existingCandidates: [
          { vid: 'old-1', name: '张三', score: 0.8 },
          { vid: 'fresh-2', name: '张三丰', score: 0.9 },
        ],
        _candidateRefresh: { addedVids: ['fresh-2'], removedVids: [] },
      },
    })
    const wrapper = mountView()
    await flushPromises()
    const button = wrapper.find('.link-refresh button')
    expect(button.exists()).toBe(true)
    expect(wrapper.text()).not.toContain('张三丰')
    await button.trigger('click')
    await flushPromises()
    expect(api.refreshProductionReviewCandidates).toHaveBeenCalledWith('case-1', 3)
    expect(wrapper.text()).toContain('张三丰')
    expect(wrapper.find('.rw-feedback').text()).toContain('新增 1 个、剔除 0 个（版本已更新）')
    wrapper.unmount()
  })

  it('选中目标被剔除：清空选择并提示重选（merge 白名单只认刷新后候选集）', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined, candidate: snapshotWithCandidates,
    })
    api.refreshProductionReviewCandidates.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', version: 4,
      candidate: {
        ...snapshotWithCandidates,
        existingCandidates: [],
        _candidateRefresh: { addedVids: [], removedVids: ['old-1'] },
      },
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('input[name="link-target"]').setValue('old-1')
    await wrapper.find('.link-refresh button').trigger('click')
    await flushPromises()
    const feedback = wrapper.find('.rw-feedback').text()
    expect(feedback).toContain('剔除 1 个')
    expect(feedback).toContain('原选中目标已被剔除，请重选')
    // 候选集已空：选择目标随之消失（选中状态不可能残留）
    expect(wrapper.findAll('input[name="link-target"]')).toHaveLength(0)
    wrapper.unmount()
  })

  it('真 no-op（响应无 _candidateRefresh）：提示无变化，不宣称变更', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined, candidate: snapshotWithCandidates,
    })
    api.refreshProductionReviewCandidates.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', version: 3, candidate: snapshotWithCandidates,
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.link-refresh button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.rw-feedback').text()).toContain('图库暂无变化')
    wrapper.unmount()
  })

  it('刷新失败（如 409 版本冲突）：错误反馈原样透出', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined, candidate: snapshotWithCandidates,
    })
    api.refreshProductionReviewCandidates.mockRejectedValue(new Error('状态或版本冲突'))
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('.link-refresh button').trigger('click')
    await flushPromises()
    expect(wrapper.find('.rw-feedback').text()).toContain('状态或版本冲突')
    wrapper.unmount()
  })

  it('终态（RESOLVED）不出刷新入口', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'RESOLVED', candidate: snapshotWithCandidates,
      decision: { actionId: 'entity-confirm', result: { entityVerdict: 'create' } },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.find('.link-refresh').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('刷新候选')
    wrapper.unmount()
  })
})
