import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsCenterView from '../OperationsCenterView.vue'

const mocks = vi.hoisted(() => ({
  getProductionReviews: vi.fn(),
  rerunExtractFailures: vi.fn(),
  getProductionReview: vi.fn(),
  getProductionReviewAuditLogs: vi.fn(),
  deleteProductionReview: vi.fn(),
}))
vi.mock('../../../api/workflowOperations', () => ({ ...mocks }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({
  IconSearch: { name: 'IconSearch', setup: () => () => null },
}))

/** C 类队列行：OPEN/RERUN_FAILED 可勾选，RERUNNING/RESOLVED 不可。 */
const caseRow = (id: string, status: string) => ({
  id, sourceTaskId: `task-${id}`, batchId: 'B-1', nodeId: 'extract', objectId: id,
  objectType: 'entity', objectName: `对象${id}`, executionId: `EXEC-${id}`,
  errorType: '逐行抽取失败', category: 'C', templateId: 'T_EXTRACT_FAIL', domain: '论文',
  phase: '图谱构建', riskLevel: 'P1', scope: 'OBJECT', status, version: 1,
  slaClaimAt: '', slaResolveAt: '', diagnosis: 'boom', sourceTable: 't_paper',
  sourceRecordId: `R-${id}`, createdAt: '2026-09-17 09:00:00', updatedAt: '2026-09-17 10:00:00',
})

const C_ROWS = [caseRow('MR-1', 'OPEN'), caseRow('MR-2', 'RERUN_FAILED'), caseRow('MR-3', 'RERUNNING'), caseRow('MR-4', 'RESOLVED')]

const wrappers: Array<ReturnType<typeof mount>> = []
const renderReview = () => {
  const wrapper = mount(OperationsCenterView, {
    props: { mode: 'review' },
    global: {
      components: {
        ASelect: { name: 'ASelect', setup: () => () => null },
        AInput: { name: 'AInput', setup: () => () => null },
        AModal: { name: 'AModal', setup: () => () => null },
        APagination: { name: 'APagination', setup: () => () => null },
      },
      stubs: { RouterLink: true },
    },
  })
  wrappers.push(wrapper)
  return wrapper
}

/** 切到 C 类（抽取失败重跑）并等待队列加载完成。 */
const switchToCategoryC = async (wrapper: ReturnType<typeof mount>) => {
  await wrapper.findAll('.review-tabs nav button')[1].trigger('click')
  await flushPromises()
}

const headerCheckbox = (wrapper: ReturnType<typeof mount>) =>
  wrapper.get('thead .pick-col input[type="checkbox"]')
const rowCheckboxes = (wrapper: ReturnType<typeof mount>) =>
  wrapper.findAll('tbody tr td.pick-col input[type="checkbox"]')
const batchButton = (wrapper: ReturnType<typeof mount>) => wrapper.get('.rerun-batch-action')

beforeEach(() => {
  mocks.getProductionReviews.mockReset().mockResolvedValue({ items: C_ROWS, total: 4, page: 1, pageSize: 10 })
  mocks.rerunExtractFailures.mockReset().mockResolvedValue({ executions: [], cases: 2 })
})

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
})

describe('审核队列 C 类（抽取失败重跑）', () => {
  it('A 类不渲染批量重跑按钮与勾选列；C 类才渲染', async () => {
    const wrapper = renderReview()
    await flushPromises()
    expect(wrapper.find('.rerun-batch-action').exists()).toBe(false)
    expect(wrapper.find('thead .pick-col').exists()).toBe(false)

    await switchToCategoryC(wrapper)
    expect(wrapper.find('.rerun-batch-action').exists()).toBe(true)
    // 批量重跑按钮单独一行右对齐，不挤在筛选栏里
    expect(wrapper.find('.review-toolbar-actions .rerun-batch-action').exists()).toBe(false)
    expect(wrapper.find('.rerun-batch-row .rerun-batch-action').exists()).toBe(true)
    expect(wrapper.find('thead .pick-col').exists()).toBe(true)
  })

  it('表头全选只勾选当前页可重跑行（OPEN/RERUN_FAILED），批量重跑按钮随之点亮', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    expect(batchButton(wrapper).attributes()).toHaveProperty('disabled')

    const header = headerCheckbox(wrapper)
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')

    const checked = rowCheckboxes(wrapper).map((input) => (input.element as HTMLInputElement).checked)
    expect(checked).toEqual([true, true, false, false])
    // 不可重跑行保持禁用
    expect((rowCheckboxes(wrapper)[2].element as HTMLInputElement).disabled).toBe(true)
    expect((rowCheckboxes(wrapper)[3].element as HTMLInputElement).disabled).toBe(true)
    // 批量按钮点亮并显示勾选数
    expect(batchButton(wrapper).attributes().disabled).toBeUndefined()
    expect(batchButton(wrapper).text()).toBe('批量重跑（2）')
  })

  it('再点表头全选取消当前页勾选，批量按钮回到禁用', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    const header = headerCheckbox(wrapper)
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')
    ;(header.element as HTMLInputElement).checked = false
    await header.trigger('change')

    const checked = rowCheckboxes(wrapper).map((input) => (input.element as HTMLInputElement).checked)
    expect(checked).toEqual([false, false, false, false])
    expect(batchButton(wrapper).attributes()).toHaveProperty('disabled')
  })

  it('部分勾选时表头呈半选态；点批量重跑按勾选集合下发', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    const firstRow = rowCheckboxes(wrapper)[0]
    ;(firstRow.element as HTMLInputElement).checked = true
    await firstRow.trigger('change')

    const header = headerCheckbox(wrapper)
    expect((header.element as HTMLInputElement).indeterminate).toBe(true)

    // 表头再全选补齐剩余可重跑行后下发
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')
    await batchButton(wrapper).trigger('click')

    expect(mocks.rerunExtractFailures).toHaveBeenCalledWith({ caseIds: ['MR-1', 'MR-2'] })
  })
})
