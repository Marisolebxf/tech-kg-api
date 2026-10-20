/**
 * 人工审核详情：加载态不闪「未找到处理实例」+ 已裁决 case 刷新后裁决单选回显。
 * （2026-10-15 修复：详情加载期间曾短暂渲染空态；T_LINK 刷新后单选回落默认「合并」。）
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
        AForm: { template: '<div><slot /></div>' },
        AFormItem: { template: '<div><slot /></div>' },
        RouterLink: true,
        'a-radio-group': ARadioGroupStub,
        'a-radio': ARadioStub,
      },
    },
  })
}

const resolvedLinkCase = {
  id: 'case-1', templateId: 'T_LINK', status: 'RESOLVED', canOperate: true,
  phase: '图谱构建', nodeId: 'align', errorType: '同名实体冲突', objectName: '张三',
  objectId: 'new-1', objectType: 'entity', domain: '人才', riskLevel: 'P1', scope: 'OBJECT',
  sourceTable: 'dwd_person', sourceRecordId: 'r-1',
  candidate: { existingCandidates: [{ vid: 'old-1', name: '张三', score: 0.8 }] },
  input: {}, evidence: [], version: 2,
  template: { id: 'T_LINK', allowedActions: ['entity-confirm', 'reject-candidate'] },
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.clearAllMocks()
  useGraphSpaceStore().$patch({
    current: 'dev', spaces: ['dev'],
    items: [{ name: 'dev', bound: false, mine: false, writeAllowed: false, reviewAllowed: false }],
  })
})

describe('人工审核详情加载态', () => {
  it('加载完成前不渲染「未找到处理实例」，完成后展示记录', async () => {
    let resolveCase: (value: typeof resolvedLinkCase) => void = () => {}
    api.getProductionReview.mockReturnValue(new Promise((resolve) => { resolveCase = resolve }))
    const wrapper = mountView()
    await flushPromises()
    // 请求在途：不闪空态
    expect(wrapper.text()).not.toContain('未找到处理实例')
    expect(wrapper.text()).toContain('加载中')

    resolveCase({ ...resolvedLinkCase, decision: undefined })
    await flushPromises()
    expect(wrapper.text()).toContain('张三')
    wrapper.unmount()
  })

  it('加载失败（如 404）才显示「未找到处理实例」，并带错误提示', async () => {
    api.getProductionReview.mockRejectedValue(new Error('处理实例不存在'))
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.text()).toContain('未找到处理实例')
    expect(wrapper.text()).toContain('处理实例不存在')
    wrapper.unmount()
  })
})

describe('已裁决 case 刷新回显', () => {
  it('T_LINK 裁决「确认为新实体」刷新后单选仍是 create（不再回落合并）', async () => {
    api.getProductionReview.mockResolvedValue({
      ...resolvedLinkCase,
      decision: { actionId: 'entity-confirm', result: { entityVerdict: 'create' }, note: '判为新实体', decidedAt: '2026-10-15 10:00:00' },
    })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.findComponent(ARadioGroupStub).props('modelValue')).toBe('create')
    wrapper.unmount()
  })

  it('无决议（未裁决 case）维持默认 merge', async () => {
    api.getProductionReview.mockResolvedValue({ ...resolvedLinkCase, status: 'OPEN', decision: undefined })
    const wrapper = mountView()
    await flushPromises()
    expect(wrapper.findComponent(ARadioGroupStub).props('modelValue')).toBe('merge')
    wrapper.unmount()
  })
})
