import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import BusinessServiceAlgorithmPanel from '../BusinessServiceAlgorithmPanel.vue'
import { getServiceModule } from '../../service-modules'
import { describeExpertAlumniRelation, queryExpertAlumniRelation } from '../../../../api/expertAlumniRelation'

vi.mock('element-plus/es/components/select/style/css', () => ({}))
vi.mock('../../../../api/expertAlumniRelation', () => ({
  describeExpertAlumniRelation: vi.fn(),
  queryExpertAlumniRelation: vi.fn(),
}))
vi.mock('../../../../composables/use-space-permissions', () => ({
  useSpacePermissions: () => ({ canWrite: ref(false), spaces: { contextKey: 'test', current: 'dev' } }),
}))
vi.mock('../../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

let view: VueWrapper | undefined

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(describeExpertAlumniRelation).mockResolvedValue({} as never)
  vi.mocked(queryExpertAlumniRelation).mockResolvedValue({
    code: 200, success: true, msg: 'success',
    data: { expert: { id: 'person_9F9A0001', name: '甲', educations: [] }, mode: 'pair',
      total: 0, items: [], sourceMeta: { space: 'dev' } },
  } as never)
})

afterEach(() => {
  view?.unmount()
  view = undefined
  document.body.innerHTML = ''
})

async function panel() {
  view = mount(BusinessServiceAlgorithmPanel, {
    props: { moduleInfo: getServiceModule('expert-alumni'), responseJson: '{}' },
    attachTo: document.body,
    global: { stubs: { KgGraphCanvas: true, ListPagination: true,
      ATooltip: { template: '<div><slot /></div>' }, ElSelect: true, ElOption: true } },
  })
  await flushPromises()
  return view
}

async function execute(wrapper: VueWrapper) {
  await wrapper.get('.service-console__actions .kg-button').trigger('click')
  await flushPromises()
}

describe('校友关系必填专家', () => {
  it('在两个专家字段上都显示必填星号', async () => {
    const wrapper = await panel()
    for (const field of ['expertId', 'targetExpertId']) {
      expect(wrapper.get(`[data-field="${field}"] > span i`).text()).toBe('*')
    }
  })

  it('同时提示两个空字段且不调用查询', async () => {
    const wrapper = await panel()
    await execute(wrapper)

    expect(queryExpertAlumniRelation).not.toHaveBeenCalled()
    expect(wrapper.get('[data-field="expertId"] .service-console__field-error').text()).toBe('请输入专家唯一标识')
    expect(wrapper.get('[data-field="targetExpertId"] .service-console__field-error').text()).toBe('请输入目标专家唯一标识')
  })

  it('只填写源专家时提示目标专家必填并阻止查询', async () => {
    const wrapper = await panel()
    await wrapper.get('[data-field="expertId"] input').setValue('person_9F9A0001')
    await execute(wrapper)

    expect(queryExpertAlumniRelation).not.toHaveBeenCalled()
    expect(wrapper.get('[data-field="targetExpertId"] .service-console__field-error').text()).toBe('请输入目标专家唯一标识')
  })

  it('填齐两位专家后只提交一次双点查询', async () => {
    const wrapper = await panel()
    await wrapper.get('[data-field="expertId"] input').setValue('person_9F9A0001')
    await wrapper.get('[data-field="targetExpertId"] input').setValue('person_9F9A0004')
    await execute(wrapper)

    expect(queryExpertAlumniRelation).toHaveBeenCalledTimes(1)
    expect(queryExpertAlumniRelation).toHaveBeenCalledWith(expect.objectContaining({
      expertId: 'person_9F9A0001', targetExpertId: 'person_9F9A0004',
    }))
  })

  it('清空已填写的目标专家后重新提示必填并阻止查询', async () => {
    const wrapper = await panel()
    await wrapper.get('[data-field="expertId"] input').setValue('person_9F9A0001')
    await wrapper.get('[data-field="targetExpertId"] input').setValue('person_9F9A0004')
    await wrapper.get('[data-field="targetExpertId"] .clearable-input__clear').trigger('click')
    await execute(wrapper)

    expect(queryExpertAlumniRelation).not.toHaveBeenCalled()
    expect(wrapper.get('[data-field="targetExpertId"] .service-console__field-error').text()).toBe('请输入目标专家唯一标识')
  })
})
