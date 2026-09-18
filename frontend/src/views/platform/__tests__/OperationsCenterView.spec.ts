import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsCenterView from '../OperationsCenterView.vue'

const mocks = vi.hoisted(() => ({
  getProductionReviews: vi.fn(),
  rerunExtractFailures: vi.fn(),
  getProductionReview: vi.fn(),
  deleteProductionReview: vi.fn(),
  getExecution: vi.fn(),
  getTask: vi.fn(),
  TRIGGER_SOURCE_LABEL: { MANUAL: '手动触发', SCHEDULE: '定期触发', RERUN: '重新执行' },
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
        ASelect: { name: 'ASelect', props: ['modelValue', 'options'], setup: () => () => null },
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
  mocks.getProductionReview.mockReset()
  mocks.deleteProductionReview.mockReset()
  mocks.getExecution.mockReset()
  mocks.getTask.mockReset()
})

afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
})

describe('审核队列 C 类（抽取失败重跑）', () => {
  it('入库决策 Tab（A 类）只筛 T_LINK：请求带 templateId=T_LINK；C 类不传', async () => {
    const wrapper = renderReview()
    await flushPromises()
    // A 类默认加载即带 T_LINK 过滤（T_DIRECT 详情走工作台总览/实例详情直达）
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: 'A', templateId: 'T_LINK' }),
    )

    await switchToCategoryC(wrapper)
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: 'C', templateId: undefined }),
    )
  })

  it('C 类状态筛选只有 全部/待处理/已处理/重跑中——「重跑失败」是幽灵状态（无代码写入），已移除', async () => {
    const wrapper = renderReview()
    await flushPromises()
    // 状态下拉是筛选行第一个 a-select
    expect(wrapper.findAllComponents({ name: 'ASelect' })[0].props('options'))
      .toEqual(['全部', '待处理', '已处理'])

    await switchToCategoryC(wrapper)
    expect(wrapper.findAllComponents({ name: 'ASelect' })[0].props('options'))
      .toEqual(['全部', '待处理', '已处理', '重跑中'])
  })

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

  it('批量重跑部分 schema 被跳过：反馈条转黄并展示跳过明细', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    mocks.rerunExtractFailures.mockResolvedValueOnce({
      executions: [{ executionId: 'EXEC-R1', schemaId: 'schema-paper', records: 2, cases: 2 }],
      cases: 2,
      skipped: [
        { schemaId: 'schema-patent', schemaKey: 'patent', cases: 1, reason: 'Schema 不存在: schema-patent' },
      ],
    })

    const header = headerCheckbox(wrapper)
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')
    await batchButton(wrapper).trigger('click')
    await flushPromises()

    const bar = wrapper.get('.rerun-feedback')
    expect(bar.classes()).toContain('is-warning')
    expect(bar.text()).toContain('已下发重跑：2 条失败记录')
    expect(bar.text()).toContain('跳过 1 条')
    expect(bar.text()).toContain('patent×1')
  })

  it('批量重跑无跳过：反馈条保持绿色 success', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    const header = headerCheckbox(wrapper)
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')
    await batchButton(wrapper).trigger('click')
    await flushPromises()

    const bar = wrapper.get('.rerun-feedback')
    expect(bar.classes()).toContain('is-success')
    expect(bar.classes()).not.toContain('is-warning')
  })

  it('更新时间表头三态排序：默认 → 新→旧 → 旧→新 → 默认，请求带对应 sort 参数', async () => {
    const wrapper = renderReview()
    await flushPromises()
    const th = wrapper.get('.th-time-sort')
    expect(th.text()).toContain('更新时间')

    await th.trigger('click')
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'updated_desc' }))
    await th.trigger('click')
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ sort: 'updated_asc' }))
    await th.trigger('click')
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ sort: undefined }))
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
})

describe('来源记录跳图谱构建任务详情', () => {
  it('统一 job 维度：有 jobId 跳 /graph-build/jobs；无 jobId 不再回落执行详情，显示占位符', async () => {
    mocks.getProductionReviews.mockReset().mockResolvedValue({
      items: [
        { ...caseRow('MR-1', 'OPEN'), jobId: 'job-abc123def456' },
        caseRow('MR-2', 'OPEN'),
      ],
      total: 2, page: 1, pageSize: 10,
    })

    const wrapper = renderReview()
    await flushPromises()

    // 来源记录单元格（区别于首列处理实例 ID 单元格：后者无链接）；
    // RouterLink stub 不渲染插槽，标签文本断言从单元格取
    const sourceLinks = wrapper.findAll('tbody tr td.review-id-cell router-link-stub')
    expect(sourceLinks).toHaveLength(1)
    expect(sourceLinks[0].attributes('to')).toBe('/graph-build/jobs/job-abc123def456')

    // 存量 case 无 jobId：不回落 EXEC 执行链接，显示占位符
    const secondSourceCell = wrapper.findAll('tbody tr td.review-id-cell')[2 + 1]
    expect(secondSourceCell.find('router-link-stub').exists()).toBe(false)
    expect(secondSourceCell.text()).toBe('—')
  })
})
