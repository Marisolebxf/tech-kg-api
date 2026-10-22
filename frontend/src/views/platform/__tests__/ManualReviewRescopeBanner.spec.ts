/**
 * MR-RESCOPE（R3，1022）：候选纠偏独立证据版本——_candidateRescope 横幅与建案
 * 时点 _resolution 并列展示，明确区分两个时点；原始证据只读不被纠偏覆盖，
 * decide=merge 只入证据不宣称自动执行。
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

function mountView() {
  return mount(ManualReviewWorkspaceView, {
    global: {
      stubs: {
        AForm: { template: '<div><slot /></div>', methods: { validate: () => undefined } },
        AFormItem: { template: '<div><slot /></div>' },
        RouterLink: true,
      },
    },
  })
}

const baseLinkCase = {
  id: 'case-1', templateId: 'T_LINK', canOperate: true,
  phase: '图谱构建', nodeId: 'align', errorType: '同名实体冲突', objectName: '张三',
  objectId: 'new-1', objectType: 'entity', domain: '人才', riskLevel: 'P1', scope: 'OBJECT',
  sourceTable: 'dwd_person', sourceRecordId: 'r-1', version: 2,
  input: {}, evidence: [],
  template: { id: 'T_LINK', allowedActions: ['entity-confirm', 'reject-candidate'] },
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useGraphSpaceStore().$patch({
    current: 'dev', spaces: ['dev'],
    items: [{ name: 'dev', bound: false, mine: false, writeAllowed: true, reviewAllowed: true }],
  })
})

describe('MR-RESCOPE 候选纠偏独立证据版本', () => {
  it('纠偏横幅：展示剔除/替换计数与纠偏判定，且原始建案证据原样并列（未被覆盖）', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined,
      candidate: {
        existingCandidates: [{ vid: 'real-1', name: '张三', score: 1.0 }],
        _resolution: { matchScore: 0.733, margin: null, scoreDecision: 'gray' },
        _candidateRescope: {
          at: '2026-10-22T10:00:00',
          deadVids: ['phantom-1'],
          stage: 'batch-gray-fix-1022',
          oldCandidates: [{ vid: 'phantom-1', name: '张三', score: 0.733 }],
          candidates: [{ vid: 'real-1', name: '张三', score: 1.0 }],
          resolution: {
            decide: 'merge', bestScore: 1.0, margin: null,
            thresholds: { merge: 0.85, grayLow: 0.65, margin: 0.08 },
            ruleVersion: 'normalized-displayname-v1',
            at: '2026-10-22T10:00:00',
          },
        },
        _incoming: { vid: 'new-1', name: '张三', props: { org: '中国科学院' } },
        _pendingRelations: [],
      },
    })
    const wrapper = mountView()
    await flushPromises()
    const text = wrapper.text()
    // 原始建案证据仍在（0.733 未被纠偏的 1.0 覆盖——两时点并列）
    expect(text).toContain('消歧得分 0.733')
    // 纠偏横幅：剔除计数、替换计数、独立判定与「不自动执行」语义
    expect(text).toContain('候选已纠偏')
    expect(text).toContain('剔除 1 个未落图候选')
    expect(text).toContain('1 个 → 1 个')
    expect(text).toContain('纠偏判定 1')
    expect(text).toContain('达到合并阈值（不自动执行，仍需人工提交）')
    expect(text).toContain('规则 normalized-displayname-v1')
    expect(text).toContain('建案时点原始证据')
    wrapper.unmount()
  })

  it('无 _candidateRescope：不渲染纠偏横幅（未纠偏案不受影响）', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined,
      candidate: {
        existingCandidates: [{ vid: 'real-1', name: '张三', score: 0.8 }],
        _resolution: { matchScore: 0.8, margin: null },
        _incoming: { vid: 'new-1', name: '张三', props: {} },
        _pendingRelations: [],
      },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('消歧得分 0.8')
    expect(wrapper.text()).not.toContain('候选已纠偏')
    wrapper.unmount()
  })

  it('decide=new（纠偏后无同名候选）：横幅给「无同名候选」建议文案', async () => {
    api.getProductionReview.mockResolvedValue({
      ...baseLinkCase, status: 'OPEN', decision: undefined,
      candidate: {
        existingCandidates: [],
        _resolution: { matchScore: 0.733, margin: null },
        _candidateRescope: {
          at: '2026-10-22T11:00:00',
          deadVids: ['phantom-1'],
          stage: 'batch-gray-fix-1022',
          oldCandidates: [{ vid: 'phantom-1', name: '张三', score: 0.733 }],
          candidates: [],
          resolution: {
            decide: 'new', bestScore: 0, margin: null,
            thresholds: { merge: 0.85, grayLow: 0.65, margin: 0.08 },
            ruleVersion: 'normalized-displayname-v1',
            at: '2026-10-22T11:00:00',
          },
        },
        _incoming: { vid: 'new-1', name: '张三', props: {} },
        _pendingRelations: [],
      },
    })
    const wrapper = mountView()
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('候选已纠偏')
    expect(text).toContain('无同名候选（建议新建或驳回）')
    wrapper.unmount()
  })
})
