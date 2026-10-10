import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getGraphNode } from '../../../api/graphSearch'
import QueryResultTable from '../QueryResultTable.vue'

vi.mock('../../../api/graphSearch', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../../api/graphSearch')>(), getGraphNode: vi.fn(),
}))
let wrapper: VueWrapper | undefined
beforeEach(() => { vi.resetAllMocks() })
afterEach(() => { wrapper?.unmount(); wrapper = undefined })
function setup(rows: Record<string, unknown>[], extra = {}) {
  wrapper = mount(QueryResultTable, {
    props: { rows, columns: Object.keys(rows[0]!), page: 2, pageSize: 20, space: 'dev2', ...extra },
    global: { stubs: { Modal: { props: ['visible'], template: '<div v-if="visible" class="modal-stub"><slot /><slot name="footer" /></div>' } } },
  })
  return wrapper
}
async function openDetails(row = 0) {
  await wrapper!.findAll('button').filter((button) => button.text() === '详情')[row]!.trigger('click')
  await flushPromises()
}

describe('Query record details without entity enrichment', () => {
  it('nGQL retains query context and the full raw result without a separate entity section or lookup', async () => {
    const vertex = { id: 'paper_10.1/example', labels: ['Paper'], properties: { title_zh: '查询返回标题' } }
    setup([{ v: vertex, missing: null }], { queryStatement: 'MATCH (v:Paper) RETURN v' })
    await openDetails()
    const sections = wrapper!.findAll('.query-record-section')
    expect(sections.map((section) => section.get('h3').text())).toEqual(['查询信息', '原始查询结果'])
    expect(sections[0]!.text()).toContain('dev2')
    expect(sections[0]!.text()).toContain('21')
    expect(sections[0]!.text()).toContain('MATCH (v:Paper) RETURN v')
    expect(sections[1]!.findAll('pre').map((field) => field.text())).toEqual([JSON.stringify(vertex, null, 2), 'NULL'])
    expect(wrapper!.find('.query-record-entities').exists()).toBe(false)
    expect(getGraphNode).not.toHaveBeenCalled()
  })

  it.each([
    { algorithmName: 'PageRank算法', column: 'pagerank', label: '重要性得分', value: '0.42' },
    { algorithmName: 'Louvain算法', column: 'community', label: '社区', value: '3' },
    { algorithmName: 'Degree算法', column: 'degree', label: '度数', value: '12' },
  ])('$algorithmName retains job information and the original algorithm values without entity lookup', async ({ algorithmName, column, label, value }) => {
    setup([{ vid: 'person-1', [column]: value }], { algorithmName, jobId: 'job-1', labels: { [column]: label } })
    await openDetails()
    const sections = wrapper!.findAll('.query-record-section')
    expect(sections.map((section) => section.get('h3').text())).toEqual(['作业信息', '原始查询结果'])
    expect(sections[0]!.text()).toContain('dev2')
    expect(sections[0]!.text()).toContain('21')
    expect(sections[0]!.text()).toContain(algorithmName)
    expect(sections[0]!.text()).toContain('job-1')
    expect(sections[1]!.text()).toContain('person-1')
    expect(sections[1]!.text()).toContain(label)
    expect(sections[1]!.text()).toContain(value)
    expect(wrapper!.find('.query-record-entities').exists()).toBe(false)
    expect(getGraphNode).not.toHaveBeenCalled()
  })

  it('switches selected records, closes when context changes, and keeps the cancel action', async () => {
    setup([{ vid: 'p1' }, { vid: 'p2' }])
    await openDetails()
    await openDetails(1)
    expect(wrapper!.get('.query-record-section:first-child').text()).toContain('22')
    expect(wrapper!.get('.query-record-section:last-child').text()).toContain('p2')
    await wrapper!.get('.query-record-cancel').trigger('click')
    expect(wrapper!.find('.modal-stub').exists()).toBe(false)
    await openDetails()
    await wrapper!.setProps({ space: 'other' })
    expect(wrapper!.find('.modal-stub').exists()).toBe(false)
    expect(getGraphNode).not.toHaveBeenCalled()
  })
})
