import { flushPromises, mount } from '@vue/test-utils'
import { h } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import OperationsCenterView from '../OperationsCenterView.vue'
import ListPagination from '../../../components/list-pagination.vue'

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
// 路由 query 可按用例覆写（?category=C 深链直达抽取失败重跑子页）
const routeState = vi.hoisted(() => ({ query: {} as Record<string, string> }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: routeState.query }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({
  IconSearch: { name: 'IconSearch', setup: () => () => null },
}))
// 全局图空间 store：reactive 包装（Vue 对同一 target 缓存同一代理），
// 用例经 graphSpaceMock.state 改 current 才能触发组件的切空间重拉 watch
const graphSpaceMock = vi.hoisted(() => {
  const raw = { current: 'dev' }
  return { raw, state: null as { current: string } | null }
})
vi.mock('../../../stores/graphSpace', async () => {
  const { reactive } = await import('vue')
  graphSpaceMock.state = reactive(graphSpaceMock.raw)
  return { useGraphSpaceStore: () => graphSpaceMock.state }
})

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
        // 分页已迁移到共享 ListPagination（真组件渲染，翻页直接对它 emit）
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
  // 清队列视图状态快照，避免上一用例写入的页码/筛选串扰本用例的默认加载断言
  sessionStorage.removeItem('techkg.manual-review-queue.v1')
  routeState.query = {}
  // 图空间复位默认 dev（经 raw 写：组件未挂载，无需触发响应式）
  graphSpaceMock.raw.current = 'dev'
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
  it('沿用顶栏空间过滤审核队列，公共空间403不会保留旧记录或勾选', async () => {
    // 初始空间 business(挂载前写 raw 即可);原 kgetl 版经真 pinia store 设置,本文件 stores/graphSpace 已被 vi.mock
    graphSpaceMock.raw.current = 'business'
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)
    await rowCheckboxes(wrapper)[0].setValue(true)
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ graphSpace: 'business' }))
    mocks.getProductionReviews.mockRejectedValueOnce(new Error('无权查看公共审核'))
    graphSpaceMock.state!.current = 'public'
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ graphSpace: 'public' }))
    expect(wrapper.text()).not.toContain('对象MR-1')
    expect(wrapper.text()).toContain('无权查看公共审核')
    expect(rowCheckboxes(wrapper)).toHaveLength(0)
  })

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

  it('?category=C 深链直达抽取失败重跑子页：首次加载即按 C 类请求且 Tab 高亮；带 keyword 时填入搜索定位该实例', async () => {
    routeState.query = { category: 'C' }
    const wrapper = renderReview()
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: 'C', templateId: undefined }),
    )
    expect(wrapper.findAll('.review-tabs nav button')[1].classes()).toContain('active')
    expect(wrapper.find('.rerun-batch-action').exists()).toBe(true)

    // 工作台总览「抽取失败重跑」卡片跳转携带对象名：首次加载即按关键字过滤
    routeState.query = { category: 'C', keyword: 'MR-1' }
    const keywordWrapper = renderReview()
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ category: 'C', templateId: undefined, keyword: 'MR-1' }),
    )
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

  it('不可重跑行（重跑中/已完成）的重跑、删除按钮置灰禁用而非隐藏', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    // C_ROWS：MR-1 OPEN、MR-2 RERUN_FAILED 可操作；MR-3 RERUNNING、MR-4 RESOLVED 置灰
    const rows = wrapper.findAll('tbody tr')
    const openRow = rows[0].findAll('.review-action-btn')
    expect(openRow).toHaveLength(3)
    expect(openRow[1].attributes('disabled')).toBeUndefined()
    expect(openRow[2].attributes('disabled')).toBeUndefined()

    const rerunningRow = rows[2].findAll('.review-action-btn')
    expect(rerunningRow).toHaveLength(3)
    expect(rerunningRow[1].attributes('disabled')).toBeDefined()
    expect(rerunningRow[2].attributes('disabled')).toBeDefined()
    expect(rerunningRow[1].attributes('title')).toBe('重跑中：等待本次重跑完成后再操作')

    const resolvedRow = rows[3].findAll('.review-action-btn')
    expect(resolvedRow).toHaveLength(3)
    expect(resolvedRow[1].attributes('disabled')).toBeDefined()
    expect(resolvedRow[2].attributes('disabled')).toBeDefined()
    expect(resolvedRow[2].attributes('title')).toBe('已处理：仅「待处理 / 重跑失败」的记录可重跑或删除')
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

  it('批量重跑无跳过：反馈条保持绿色 success，执行信息纯文本不跳转', async () => {
    const wrapper = renderReview()
    await flushPromises()
    await switchToCategoryC(wrapper)

    mocks.rerunExtractFailures.mockResolvedValueOnce({
      executions: [{ executionId: 'EXEC-R2', schemaId: 'schema-paper', records: 2, cases: 2 }],
      cases: 2,
    })

    const header = headerCheckbox(wrapper)
    ;(header.element as HTMLInputElement).checked = true
    await header.trigger('change')
    await batchButton(wrapper).trigger('click')
    await flushPromises()

    const bar = wrapper.get('.rerun-feedback')
    expect(bar.classes()).toContain('is-success')
    expect(bar.classes()).not.toContain('is-warning')
    // 执行信息是纯文本，不再提供跳执行详情的链接
    expect(bar.findAll('router-link-stub')).toHaveLength(0)
    expect(bar.text()).toContain('schema-paper · 2 条')
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
    await wrapper.findAll('tbody .review-action-btn')[0].trigger('click')
    await flushPromises()

    // 重跑执行优先展示，且不拉旧的审计日志
    expect(mocks.getExecution).toHaveBeenCalledWith('EXEC-RERUN-9')
    expect(mocks.getTask).toHaveBeenCalledWith('PI-1')
    expect(wrapper.text()).toContain('执行概要')
    expect(wrapper.text()).toContain('重新执行')
    expect(wrapper.text()).toContain('写入 120 · 失败 1')
    expect(wrapper.text()).toContain('阶段回写：1 个 stage')
    expect(wrapper.text()).not.toContain('处理时间线')
    // 执行 ID 纯文本展示，不再跳执行详情页
    expect(wrapper.text()).toContain('EXEC-RERUN-9')
    expect(wrapper.find('.case-log-dl router-link-stub').exists()).toBe(false)
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

describe('分页统计与页数收缩收敛（FUNC-00781）/ 处理实例 ID 纯文本（FUNC-00775）', () => {
  /** 按 statusGroup 区分筛选前后：全部 41 条（3 页）；待处理 5 条（1 页）。 */
  const mockPaged = () => mocks.getProductionReviews.mockImplementation(
    async (params: { page?: number; statusGroup?: string }) => {
      if (params.statusGroup === 'pending') {
        return params.page && params.page > 1
          ? { items: [], total: 5, page: params.page, pageSize: 20 }
          : { items: C_ROWS.slice(0, 5), total: 5, page: 1, pageSize: 20 }
      }
      return { items: C_ROWS, total: 41, page: params.page ?? 1, pageSize: 20 }
    },
  )

  it('筛选后总页数收缩：当前页自动收敛到最后有效页并重新加载，不出现空页', async () => {
    mockPaged()
    const wrapper = renderReview()
    await flushPromises()
    expect(wrapper.get('.review-pagination > span').text()).toBe('共 41 条 · 第 1 / 3 页')

    // 翻至第 3 页
    wrapper.findComponent(ListPagination).vm.$emit('change', 3)
    await flushPromises()
    expect(wrapper.get('.review-pagination > span').text()).toBe('共 41 条 · 第 3 / 3 页')

    // 增加筛选（状态=待处理）使结果只剩 1 页：先按第 3 页请求 → 收敛到第 1 页重拉
    wrapper.findAllComponents({ name: 'ASelect' })[0].vm.$emit('update:modelValue', '待处理')
    await flushPromises()
    await flushPromises()

    const pages = mocks.getProductionReviews.mock.calls.map((call) => call[0]?.page)
    expect(pages).toEqual([1, 3, 3, 1])
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ page: 1, statusGroup: 'pending' }))
    // 统计文案与实际数据一致，且无空页（收敛后立即有数据行）
    expect(wrapper.get('.review-pagination > span').text()).toBe('共 5 条 · 第 1 / 1 页')
    expect(wrapper.findAll('tbody tr td.review-id-cell').length).toBeGreaterThan(0)
  })

  it('筛选后当前页仍有效：保留当前页重新加载，不回第 1 页', async () => {
    mocks.getProductionReviews.mockImplementation(
      async (params: { page?: number }) => ({ items: C_ROWS, total: 61, page: params.page ?? 1, pageSize: 20 }),
    )
    const wrapper = renderReview()
    await flushPromises()

    wrapper.findComponent(ListPagination).vm.$emit('change', 3)
    await flushPromises()

    wrapper.findAllComponents({ name: 'ASelect' })[0].vm.$emit('update:modelValue', '待处理')
    await flushPromises()
    await flushPromises()

    // 61 条 = 4 页，第 3 页仍有效：筛选后停在原页
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({ page: 3, statusGroup: 'pending' }))
    expect(wrapper.get('.review-pagination > span').text()).toBe('共 61 条 · 第 3 / 4 页')
  })

  it('跳详情返回后恢复页码/页大小/分类/筛选（sessionStorage 快照），不回第 1 页', async () => {
    // 模拟上一会话留下的队列状态：C 类第 3 页、每页 50、待处理 + 实体 + 近7天 + 新→旧 + 关键字
    sessionStorage.setItem('techkg.manual-review-queue.v1', JSON.stringify({
      category: 'C', page: 3, pageSize: 50, status: '待处理', kind: '实体',
      time: '近7天', sort: 'desc', keyword: '论文',
    }))
    mocks.getProductionReviews.mockResolvedValue({ items: C_ROWS, total: 120, page: 3, pageSize: 50 })

    const wrapper = renderReview()
    await flushPromises()

    // 重挂载后首次加载即按快照状态请求，且 C 类 Tab 高亮
    expect(mocks.getProductionReviews).toHaveBeenCalledWith(expect.objectContaining({
      category: 'C', page: 3, pageSize: 50, statusGroup: 'pending', kind: 'entity',
      updatedWithin: '7d', sort: 'updated_desc', keyword: '论文',
    }))
    expect(wrapper.get('.review-pagination > span').text()).toBe('共 120 条 · 第 3 / 3 页')
    expect(wrapper.findAll('.review-tabs nav button')[1].classes()).toContain('active')
  })

  it('深链 query 优先于快照：?category=A 覆盖快照分类，A 类下快照的「重跑中」收敛回「全部」', async () => {
    routeState.query = { category: 'A' }
    sessionStorage.setItem('techkg.manual-review-queue.v1', JSON.stringify({ category: 'C', page: 5, status: '重跑中' }))

    renderReview()
    await flushPromises()

    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(expect.objectContaining({
      category: 'A', templateId: 'T_LINK', statusGroup: undefined, status: undefined,
    }))
  })

  it('处理实例 ID 为纯文本（中性色 code，非链接），title 悬停提供全称', async () => {
    const wrapper = renderReview()
    await flushPromises()

    // 首列处理实例 ID 单元格：纯 code 文本，不带链接，悬停 title 可看全称
    const idCell = wrapper.findAll('tbody tr td.review-id-cell')[0]
    const code = idCell.get('code.review-id-plain')
    expect(code.attributes('title')).toBe('MR-1')
    expect(code.text()).toBe('MR-1')
    expect(idCell.find('router-link-stub').exists()).toBe(false)
    expect(idCell.find('a').exists()).toBe(false)
  })
})

describe('队列跟随图空间切换', () => {
  it('请求带当前空间；切空间后按新空间重拉且页码归 1（空间是全局态，不进快照）', async () => {
    // 60 条 = 每页 20 共 3 页，允许翻到第 3 页后再切空间
    mocks.getProductionReviews.mockImplementation(
      async (params: { page?: number }) => ({ items: C_ROWS, total: 60, page: params?.page ?? 1, pageSize: 20 }),
    )
    const wrapper = renderReview()
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ graphSpace: 'dev' }),
    )

    wrapper.findComponent(ListPagination).vm.$emit('change', 3)
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ graphSpace: 'dev', page: 3 }),
    )

    // 切到 dev2：整份数据更换，页码归 1 并带新空间参数
    graphSpaceMock.state!.current = 'dev2'
    await flushPromises()
    expect(mocks.getProductionReviews).toHaveBeenLastCalledWith(
      expect.objectContaining({ graphSpace: 'dev2', page: 1 }),
    )
  })
})
