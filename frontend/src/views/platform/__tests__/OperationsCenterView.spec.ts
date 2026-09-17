import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsCenterView from '../OperationsCenterView.vue'

const mocks = vi.hoisted(() => ({
  getProductionReviews: vi.fn(),
  rerunExtractFailures: vi.fn(),
  getProductionReview: vi.fn(),
  deleteProductionReviewCases: vi.fn(),
  getExecution: vi.fn(),
  getTask: vi.fn(),
  TRIGGER_SOURCE_LABEL: { MANUAL: '手动触发', SCHEDULE: '定期触发', RERUN: '重新执行' },
}))
vi.mock('../../../api/workflowOperations', () => ({ ...mocks }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({
  IconSearch: { name: 'IconSearch', setup: () => () => null },
}))

/** C 类所有行可勾选删除，只有 OPEN/RERUN_FAILED 可下发重跑。 */
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
        // 弹窗 stub 直渲染默认插槽，让日志弹窗内容可被断言
        AModal: { name: 'AModal', setup: (_props: Record<string, unknown>, { slots }: { slots: { default?: () => unknown } }) => () => h('div', slots.default?.()) },
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
  mocks.deleteProductionReviewCases.mockReset().mockResolvedValue({ deleted: 4, skipped: 0 })
  mocks.getProductionReview.mockReset()
  mocks.getExecution.mockReset()
  mocks.getTask.mockReset()
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

  it('表头全选全部行用于删除，批量重跑只包含 OPEN/RERUN_FAILED', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    expect(batchButton(wrapper).attributes()).toHaveProperty('disabled')

    const header = headerCheckbox(wrapper)
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')

    const checked = rowCheckboxes(wrapper).map((input) => (input.element as HTMLInputElement).checked)
    expect(checked).toEqual([true, true, true, true])
    expect(wrapper.get('.rerun-batch-action.is-danger').text()).toBe('批量删除（4）')
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

  it('更新时间排序循环传递服务端参数，切回 A 类恢复默认排序', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)
    for (const order of ['desc', 'asc', undefined]) {
      await wrapper.get('.th-sort').trigger('click')
      await flushPromises()
      expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({
        category: 'C', sort: order ? 'updatedAt' : undefined, order, page: 1,
      }))
    }
    await wrapper.get('.th-sort').trigger('click')
    await wrapper.findAll('.review-tabs nav button')[0].trigger('click')
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({
      category: 'A', sort: undefined, order: undefined,
    }))
    expect(wrapper.find('.th-status-filter').exists()).toBe(false)
  })

  it('C 类表头筛选重跑失败，切回 A 类清除不兼容状态', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)
    wrapper.get('.th-status-filter').findComponent({ name: 'ASelect' }).vm.$emit('update:modelValue', '重跑失败')
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ status: 'RERUN_FAILED' }))
    await wrapper.findAll('.review-tabs nav button')[0].trigger('click')
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'A', status: undefined }))
  })

  it('「时间」过滤下拉切换后请求带 updatedWithin 参数', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)
    const timeField = wrapper.findAll('.review-filter-field').find((field) => field.text().includes('时间'))!
    timeField.findComponent({ name: 'ASelect' }).vm.$emit('update:modelValue', '近24小时')
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ updatedWithin: '24h', page: 1 }))
  })

  it('批量删除需确认，成功后清空选择', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)
    const header = headerCheckbox(wrapper)
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')
    await wrapper.get('.rerun-batch-action.is-danger').trigger('click')
    expect(mocks.deleteProductionReviewCases).not.toHaveBeenCalled()
    const modal = wrapper.findAllComponents({ name: 'AModal' }).at(-1)!
    modal.vm.$emit('ok')
    await flushPromises()
    expect(mocks.deleteProductionReviewCases).toHaveBeenCalledWith(['MR-1', 'MR-2', 'MR-3', 'MR-4'])
    expect(wrapper.get('.rerun-batch-action.is-danger').text()).toBe('批量删除（0）')
  })

  it('「日志」弹窗展示关联工作流执行日志（重跑执行优先，概要/阶段/任务日志）', async () => {
    mocks.getProductionReview.mockResolvedValue({
      ...caseRow('MR-1', 'RERUN_FAILED'),
      data: { input: { executionId: 'EXEC-ORIG-1', rerunExecutionId: 'EXEC-RERUN-9', attempt: 2 } },
    })
    mocks.getExecution.mockResolvedValue({
      id: 'EXEC-RERUN-9', definitionId: 'schema:paper', workflowId: 'wf-1', status: 'COMPLETED',
      startedAt: '2026-09-17 10:00:00', completedAt: '2026-09-17 10:02:00', triggerSource: 'RERUN',
      taskId: 'PI-1', message: '执行完成', output: { sources: [{ written: 120, failed: 1 }], failures: { count: 1 } },
    })
    mocks.getTask.mockResolvedValue({
      id: 'PI-1', logs: ['2026-09-17 10:00:00 执行启动', '阶段回写：1 个 stage'],
      steps: [{ id: 's1', phase: '数据处理', name: '抽取', status: '成功', count: '120', abnormal: '0', duration: '2m', description: '' }],
    })

    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)
    // 操作列第一个按钮是「日志」
    await wrapper.findAll('tbody .rerun-link')[0].trigger('click')
    await flushPromises()

    // 重跑执行优先展示，且不拉旧的审计日志
    expect(mocks.getExecution).toHaveBeenCalledWith('EXEC-RERUN-9')
    expect(mocks.getTask).toHaveBeenCalledWith('PI-1')
    expect(wrapper.text()).toContain('执行概要')
    expect(wrapper.text()).toContain('重新执行')
    expect(wrapper.text()).toContain('写入 120 · 失败 1')
    expect(wrapper.text()).toContain('阶段回写：1 个 stage')
    expect(wrapper.text()).not.toContain('处理时间线')
  })

  it('「日志」弹窗在 case 未关联执行 ID 时展示未找到兜底', async () => {
    mocks.getProductionReview.mockResolvedValue(C_ROWS[0])
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)
    await wrapper.findAll('tbody .rerun-link')[0].trigger('click')
    await flushPromises()
    expect(mocks.getProductionReview).toHaveBeenCalledWith('MR-1')
    // 无 data.input.executionId → 不拉执行详情，展示未找到兜底
    expect(mocks.getExecution).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('未找到关联的工作流执行记录')
  })
})
