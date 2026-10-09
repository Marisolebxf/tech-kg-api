import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { getGraphNode, type GraphNode } from '../../../api/graphSearch'
import QueryResultTable from '../QueryResultTable.vue'

vi.mock('../../../api/graphSearch', async (importOriginal) => ({
  ...await importOriginal<typeof import('../../../api/graphSearch')>(), getGraphNode: vi.fn(),
}))
let wrapper: VueWrapper | undefined
beforeEach(() => { vi.resetAllMocks() })
afterEach(() => { wrapper?.unmount(); wrapper = undefined })
function apiNode(node: GraphNode) {
  return { code: 200, success: true, msg: 'ok', data: node } as unknown as Awaited<ReturnType<typeof getGraphNode>>
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}
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

describe('Query record entity enrichment', () => {
  it('loads full entity attributes only after clicking details, using the result graph space', async () => {
    vi.mocked(getGraphNode).mockResolvedValue(apiNode({ id: 'paper_10.1/example', labels: ['Paper'], properties: { title_zh: '真实论文标题', publication_year: 2025, doi: '10.1/example' } }))
    setup([{ vid: 'paper_10.1/example', pagerank: '0.42' }], { algorithmName: 'PageRank算法', jobId: 'job-1' })
    expect(getGraphNode).not.toHaveBeenCalled()
    await openDetails()
    expect(getGraphNode).toHaveBeenCalledExactlyOnceWith('paper_10.1/example', 'dev2')
    expect(wrapper!.get('.query-record-entities').text()).toContain('真实论文标题')
    expect(wrapper!.get('.query-record-entities').text()).toContain('publication_year')
    expect(wrapper!.get('.query-record-details').text()).toContain('PageRank算法')
    expect(wrapper!.get('.query-record-details').text()).toContain('job-1')
    expect(wrapper!.get('.query-record-details').text()).toContain('21')
    expect(wrapper!.get('.query-record-section:last-child').text()).toContain('0.42')
  })

  it('shows query context for schema rows without making false entity requests', async () => {
    setup([{ Field: 'title_zh', Type: 'string', Null: 'YES', Default: '__EMPTY__' }], { queryStatement: 'DESCRIBE TAG Paper' })
    await openDetails()
    expect(getGraphNode).not.toHaveBeenCalled()
    expect(wrapper!.get('.query-record-details').text()).toContain('DESCRIBE TAG Paper')
    expect(wrapper!.get('.query-record-entities').text()).toContain('未包含可识别的图 VID')
    expect(wrapper!.get('.query-record-section:last-child').text()).toContain('title_zh')
  })

  it('deduplicates vertices and fetches relation endpoints rather than the edge ID', async () => {
    vi.mocked(getGraphNode).mockImplementation(async (vid) => apiNode({ id: vid, labels: ['Person'], properties: { name_zh: vid } }))
    setup([{ vid: 'person-1', v: { id: 'person-1', labels: ['Person'], properties: {} }, e: { id: 'edge-1', type: 'COAUTHOR', sourceId: 'person-1', targetId: 'person-2', properties: {} } }])
    await openDetails()
    expect(vi.mocked(getGraphNode).mock.calls).toEqual([['person-1', 'dev2'], ['person-2', 'dev2']])
    expect(wrapper!.findAll('.query-record-entity')).toHaveLength(2)
  })

  it('retains returned vertex information on lookup failure and offers retry', async () => {
    vi.mocked(getGraphNode).mockRejectedValueOnce(new Error('服务暂不可用')).mockResolvedValueOnce(apiNode({ id: 'p1', labels: ['Person'], properties: { name_zh: '最新名称', h_index: 12 } }))
    setup([{ v: { id: 'p1', labels: ['Person'], properties: { name_zh: '查询返回名称' } } }])
    await openDetails()
    expect(wrapper!.get('[role="alert"]').text()).toContain('保留查询返回的实体属性')
    expect(wrapper!.get('.query-record-entities').text()).toContain('查询返回名称')
    await wrapper!.get('.query-record-retry').trigger('click')
    await flushPromises()
    expect(wrapper!.find('[role="alert"]').exists()).toBe(false)
    expect(wrapper!.get('.query-record-entities').text()).toContain('最新名称')
    expect(wrapper!.get('.query-record-entities').text()).toContain('h_index')
  })

  it('ignores responses for a previously selected record and after a space change', async () => {
    const pending = deferred<Awaited<ReturnType<typeof getGraphNode>>>()
    vi.mocked(getGraphNode).mockReturnValueOnce(pending.promise).mockResolvedValueOnce(apiNode({ id: 'p2', labels: ['Person'], properties: { name_zh: '第二人' } }))
    setup([{ vid: 'p1' }, { vid: 'p2' }])
    await openDetails()
    await openDetails(1)
    pending.resolve(apiNode({ id: 'p1', labels: ['Person'], properties: { name_zh: '旧响应' } }))
    await flushPromises()
    expect(wrapper!.get('.query-record-entities').text()).toContain('第二人')
    expect(wrapper!.get('.query-record-entities').text()).not.toContain('旧响应')
    await wrapper!.setProps({ space: 'other' })
    expect(wrapper!.find('.modal-stub').exists()).toBe(false)
  })
})
