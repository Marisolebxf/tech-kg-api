/**
 * MR-TEXT：终态详情判定树——完成态不再一律「已扣留，未写图」，按落库决议保守判定
 * 写图结果；reject-candidate 也落 RESOLVED，绝不冒认已入图；merge/create 提交成功
 * 文案必须核对回写（RESOLVED + 决议字段一致）后才宣称写入图。
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
        // AForm stub 需带 validate()（handleAction 主按钮提交前会调，缺方法会炸）
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
const snapshotWithIncoming = {
  existingCandidates: [{ vid: 'old-1', name: '张三', score: 0.8 }],
  _incoming: { vid: 'new-1', name: '张三', props: { org: '中国科学院' } },
  _pendingRelations: [{ edgeType: 'works_for', fromId: 'new-1', toId: 'org-1' }],
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useGraphSpaceStore().$patch({
    current: 'dev', spaces: ['dev'],
    items: [{ name: 'dev', bound: false, mine: false, writeAllowed: true, reviewAllowed: true }],
  })
})

describe('MR-TEXT 终态判定树', () => {
  it('非终态（OPEN）：维持扣留文案与操作提示，不出现裁决前快照', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined, candidate: snapshotWithIncoming,
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('待入库记录（已扣留，未写图）')
    expect(wrapper.text()).toContain('本裁决挂起的暂存边（1 条，未写图）')
    expect(wrapper.text()).toContain('驳回时将随挂起实体一并丢弃')
    expect(wrapper.text()).not.toContain('裁决前快照')
    expect(wrapper.text()).not.toContain('已并入图')
    wrapper.unmount()
  })

  it('RESOLVED + entity-confirm/merge + 目标：已并入图（含目标名），历史区块标裁决前快照', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'RESOLVED',
      candidate: snapshotWithIncoming,
      decision: { actionId: 'entity-confirm', result: { entityVerdict: 'merge', targetEntityId: 'old-1' }, decidedAt: '2026-10-20 10:00:00' },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('待入库记录 · 已并入图')
    expect(wrapper.text()).toContain('该记录已并入候选「张三」（old-1），案落 RESOLVED。')
    expect(wrapper.text()).toContain('裁决前快照 · 挂起的暂存边（1 条）')
    expect(wrapper.text()).toContain('这些暂存边已按并入端点补写落图。')
    expect(wrapper.text()).not.toContain('已扣留，未写图')
    wrapper.unmount()
  })

  it('RESOLVED + reject-candidate：已驳回未入图（RESOLVED 不冒认写图）', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'RESOLVED',
      candidate: snapshotWithIncoming,
      decision: { actionId: 'reject-candidate', result: { entityVerdict: 'reject' }, decidedAt: '2026-10-20 10:00:00' },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('待入库记录 · 已驳回 · 未入图')
    expect(wrapper.text()).toContain('该记录经人工裁决驳回，候选未写入图。')
    expect(wrapper.text()).toContain('这些暂存边已随挂起实体一并丢弃，未写图。')
    expect(wrapper.text()).not.toContain('已并入图')
    expect(wrapper.text()).not.toContain('已写入图')
    wrapper.unmount()
  })

  it('REJECTED：同驳回口径（未入图）', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'REJECTED', candidate: snapshotWithIncoming,
      decision: { actionId: 'reject-candidate', result: { entityVerdict: 'reject' } },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('已驳回 · 未入图')
    expect(wrapper.text()).not.toContain('已并入图')
    wrapper.unmount()
  })

  it('RESOLVED + merge 但决议缺 targetEntityId：决议不完整，不显示已入图', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'RESOLVED',
      candidate: snapshotWithIncoming,
      decision: { actionId: 'entity-confirm', result: { entityVerdict: 'merge' } },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('决议不完整')
    expect(wrapper.text()).toContain('无法确认写图结果')
    expect(wrapper.text()).not.toContain('已并入图')
    wrapper.unmount()
  })

  it('RESOLVED + create 但快照无 _incoming（存量写后案）：仅记录决议', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'RESOLVED',
      candidate: { existingCandidates: [{ vid: 'old-1', name: '张三', score: 0.8 }] },
      decision: { actionId: 'entity-confirm', result: { entityVerdict: 'create' } },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('仅记录决议')
    expect(wrapper.text()).toContain('存量写后案')
    expect(wrapper.text()).not.toContain('已新建实体')
    wrapper.unmount()
  })

  it('T_DIRECT accept（RESOLVED）：已写入图', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, templateId: 'T_DIRECT', status: 'RESOLVED', workflowType: 'kg.custom.steps',
      candidate: { _kind: 'entity', _nodeLabel: 'Expert', name: '李四', org: '清华' },
      decision: { actionId: 'accept', result: { accepted: true } },
      template: { id: 'T_DIRECT', allowedActions: ['accept', 'reject'] },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('待入库记录 · 已写入图')
    expect(wrapper.text()).toContain('该候选经人工确认已写入图，案落 RESOLVED。')
    wrapper.unmount()
  })
})

describe('MR-TEXT 提交成功文案核对回写', () => {
  async function mountOpenAndSelectTarget() {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined, candidate: snapshotWithIncoming,
    })
    const wrapper = mountView()
    await flushPromises()
    await wrapper.find('input[name="link-target"]').setValue('old-1')
    return wrapper
  }

  it('merge 回写一致（RESOLVED + 字段同）：宣称已并入图', async () => {
    api.submitProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'RESOLVED',
      candidate: snapshotWithIncoming,
      decision: { actionId: 'entity-confirm', result: { entityVerdict: 'merge', targetEntityId: 'old-1' } },
    })
    const wrapper = await mountOpenAndSelectTarget()
    await wrapper.find('.rw-foot button.primary').trigger('click')
    await flushPromises()
    expect(api.submitProductionReview).toHaveBeenCalledTimes(1)
    expect(wrapper.find('.rw-feedback').text()).toContain('已并入图（目标 old-1），案已落 RESOLVED。')
    wrapper.unmount()
  })

  it('merge 回写不一致（目标被改写）：保守降级，不宣称写入图', async () => {
    api.submitProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'RESOLVED',
      candidate: snapshotWithIncoming,
      decision: { actionId: 'entity-confirm', result: { entityVerdict: 'merge', targetEntityId: 'other-9' } },
    })
    const wrapper = await mountOpenAndSelectTarget()
    await wrapper.find('.rw-foot button.primary').trigger('click')
    await flushPromises()
    const feedback = wrapper.find('.rw-feedback').text()
    expect(feedback).toContain('回写决议与提交不一致')
    expect(feedback).toContain('写图结果待确认')
    expect(feedback).not.toContain('已并入图（目标 old-1）')
    wrapper.unmount()
  })
})
