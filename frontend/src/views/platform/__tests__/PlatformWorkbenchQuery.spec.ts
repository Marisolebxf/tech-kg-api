import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent, nextTick } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { runNgql, type GraphConsoleResult } from '../../../api/graphConsole'
import {
  fetchGraphAlgorithmMetadata,
  getAlgorithmJob,
  getAlgorithmJobResult,
  submitAlgorithmJob,
  type AlgorithmJobSnapshot,
  type AlgorithmResultPayload,
  type GraphAlgorithmMetadata,
} from '../../../api/graphAlgorithm'
import { useGraphSpaceStore } from '../../../stores/graphSpace'
import PlatformWorkbenchView from '../PlatformWorkbenchView.vue'

vi.mock('vue-router', () => ({ useRouter: () => ({ push: vi.fn() }) }))
vi.mock('../../../api/graphConsole', () => ({ runNgql: vi.fn() }))
vi.mock('../../../api/graphAlgorithm', () => ({
  fetchGraphAlgorithmMetadata: vi.fn(),
  fetchGraphAlgorithmEngine: vi.fn(),
  getAlgorithmJob: vi.fn(),
  getAlgorithmJobResult: vi.fn(),
  submitAlgorithmJob: vi.fn(),
}))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
vi.mock('@arco-design/web-vue/es/icon', () => ({ IconInfoCircle: { template: '<i />' } }))

// Preserve v-model and user selection without depending on Arco's popup layout.
const SelectStub = defineComponent({
  props: ['modelValue', 'multiple'],
  emits: ['update:modelValue'],
  template: `<select :multiple="multiple !== undefined" :value="modelValue"
    @change="$emit('update:modelValue', Array.from($event.target.selectedOptions, option => option.value))"><slot /></select>`,
})
const OptionStub = defineComponent({
  props: ['value'],
  template: '<option :value="value"><slot /></option>',
})

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function queryResult(value: string): GraphConsoleResult {
  return { columns: ['name'], records: [{ name: value }], summary: {}, kind: 'read' }
}

function algorithmResult(value: string): AlgorithmResultPayload {
  return { jobId: 'job-a', sink: 'csv', rows: [{ vid: value, pagerank: '0.5' }] }
}

let wrapper: VueWrapper
let store: ReturnType<typeof useGraphSpaceStore>

beforeEach(() => {
  vi.resetAllMocks()
  vi.stubGlobal('matchMedia', (query: string) => ({
    matches: false, media: query, onchange: null,
    addListener: vi.fn(), removeListener: vi.fn(),
    addEventListener: vi.fn(), removeEventListener: vi.fn(), dispatchEvent: vi.fn(),
  }))
  vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'] })
  localStorage.clear()
  const pinia = createPinia()
  setActivePinia(pinia)
  store = useGraphSpaceStore()
  store.setCurrent('space-a')
  vi.mocked(fetchGraphAlgorithmMetadata).mockImplementation(async (space) => ({
    edgeTypes: [`${space}-edge`], engine: { status: 'UP' },
  }))
  vi.mocked(submitAlgorithmJob).mockResolvedValue({ jobId: 'job-a', status: 'running' })
  vi.mocked(getAlgorithmJob).mockResolvedValue({ jobId: 'job-a', status: 'running' })
  vi.mocked(getAlgorithmJobResult).mockResolvedValue(algorithmResult('current-result'))
  wrapper = mount(PlatformWorkbenchView, {
    props: { initialTab: 'query' },
    global: {
      plugins: [pinia],
      stubs: { 'a-select': SelectStub, 'a-option': OptionStub, ListPagination: true },
    },
  })
})

afterEach(() => {
  wrapper.unmount()
  vi.useRealTimers()
})

async function clickButton(label: string) {
  const button = wrapper.findAll('button').find((item) => item.text() === label)
  expect(button, `Missing button: ${label}`).toBeDefined()
  await button!.trigger('click')
}

async function enterAlgorithms() {
  await clickButton('图算法')
  await flushPromises()
}

async function submitAlgorithm() {
  await wrapper.get('.platform-query-algo__labels select').setValue([`${store.current}-edge`])
  await clickButton('提交算法作业')
  await flushPromises()
}

async function switchSpace(space = 'space-b') {
  store.setCurrent(space)
  await nextTick()
  await flushPromises()
}

describe('PlatformWorkbench query graph-space context', () => {
  it('executes nGQL in the global space and clears completed results when that space changes', async () => {
    vi.mocked(runNgql).mockResolvedValueOnce(queryResult('result-a')).mockResolvedValueOnce(queryResult('result-b'))
    await wrapper.get('textarea').setValue('  MATCH (v) RETURN v  ')
    await clickButton('执行 nGQL')
    await flushPromises()
    expect(runNgql).toHaveBeenLastCalledWith('space-a', 'MATCH (v) RETURN v')
    expect(wrapper.get('.query-result-table[aria-label="nGQL 查询结果"]').text()).toContain('result-a')

    await switchSpace()
    expect(wrapper.find('.query-result-table[aria-label="nGQL 查询结果"]').exists()).toBe(false)
    await clickButton('执行 nGQL')
    await flushPromises()
    expect(runNgql).toHaveBeenLastCalledWith('space-b', 'MATCH (v) RETURN v')
    expect(wrapper.get('.query-result-table[aria-label="nGQL 查询结果"]').text()).toContain('result-b')
  })

  it('ignores an old nGQL response while the new space request remains in progress', async () => {
    const oldRequest = deferred<GraphConsoleResult>()
    const newRequest = deferred<GraphConsoleResult>()
    vi.mocked(runNgql).mockReturnValueOnce(oldRequest.promise).mockReturnValueOnce(newRequest.promise)
    await wrapper.get('textarea').setValue('SHOW TAGS')
    await clickButton('执行 nGQL')
    await switchSpace()
    await clickButton('执行 nGQL')
    oldRequest.resolve(queryResult('stale-result'))
    await flushPromises()
    expect(wrapper.text()).not.toContain('stale-result')
    expect(wrapper.get('.platform-ngql-header-actions button').attributes('disabled')).toBeDefined()
    newRequest.resolve(queryResult('fresh-result'))
    await flushPromises()
    expect(wrapper.get('.query-result-table').text()).toContain('fresh-result')
  })

  it('uses the current space for metadata, submission, polling and result retrieval', async () => {
    await switchSpace()
    await enterAlgorithms()
    expect(fetchGraphAlgorithmMetadata).toHaveBeenLastCalledWith('space-b')
    await submitAlgorithm()
    expect(submitAlgorithmJob).toHaveBeenCalledWith(expect.objectContaining({
      space: 'space-b', labels: ['space-b-edge'], algorithm: 'pagerank',
    }))
    vi.mocked(getAlgorithmJob).mockResolvedValueOnce({ jobId: 'job-a', status: 'succeeded' })
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(getAlgorithmJob).toHaveBeenLastCalledWith('space-b', 'job-a')
    expect(getAlgorithmJobResult).toHaveBeenLastCalledWith('space-b', 'job-a')
    expect(wrapper.get('.query-result-table[aria-label="图算法执行结果"]').text()).toContain('current-result')
    await switchSpace('space-c')
    expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)
    expect(wrapper.find('.query-result-table[aria-label="图算法执行结果"]').exists()).toBe(false)
  })

  it('clears labels and cancels a running job when the global space changes', async () => {
    await enterAlgorithms()
    await submitAlgorithm()
    expect(wrapper.get('.platform-query-algo__job').text()).toContain('job-a')
    await switchSpace()
    expect(fetchGraphAlgorithmMetadata).toHaveBeenLastCalledWith('space-b')
    expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)
    const select = wrapper.get('.platform-query-algo__labels select').element as HTMLSelectElement
    expect(Array.from(select.selectedOptions)).toHaveLength(0)
    expect(wrapper.get('.platform-query-algo__labels').text()).toContain('space-b-edge')
    await clickButton('提交算法作业')
    expect(submitAlgorithmJob).toHaveBeenCalledTimes(1)
    await vi.advanceTimersByTimeAsync(6000)
    expect(getAlgorithmJob).not.toHaveBeenCalled()
  })

  it('blocks submission when more than 20 edge types are selected', async () => {
    const manyEdges = Array.from({ length: 21 }, (_, index) => `edge-${index + 1}`)
    vi.mocked(fetchGraphAlgorithmMetadata).mockResolvedValueOnce({
      edgeTypes: manyEdges,
      engine: { status: 'UP' },
    })
    await enterAlgorithms()
    await wrapper.get('.platform-query-algo__labels select').setValue(manyEdges)
    await clickButton('提交算法作业')
    expect(submitAlgorithmJob).not.toHaveBeenCalled()
    expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)

    await wrapper.get('.platform-query-algo__labels select').setValue(manyEdges.slice(0, 20))
    await clickButton('提交算法作业')
    await flushPromises()
    expect(submitAlgorithmJob).toHaveBeenCalledTimes(1)
  })

  it('removes advanced controls from all three algorithm tabs', async () => {
    await enterAlgorithms()
    for (const label of ['PageRank算法', 'Louvain算法', 'Degree算法']) {
      await clickButton(label)
      expect(wrapper.text()).not.toContain('高级参数')
      expect(wrapper.find('.platform-query-algo__input').exists()).toBe(false)
      expect(wrapper.find('.platform-query-algo__labels').exists()).toBe(true)
    }
  })

  it('keeps completed results and relation selections separate for each algorithm', async () => {
    await enterAlgorithms()
    for (const [index, label] of ['Degree算法', 'Louvain算法', 'PageRank算法'].entries()) {
      await clickButton(label)
      expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)
      expect(wrapper.find('.query-result-table[aria-label="图算法执行结果"]').exists()).toBe(false)
      const select = wrapper.get('.platform-query-algo__labels select').element as HTMLSelectElement
      expect(select.selectedOptions).toHaveLength(0)
      vi.mocked(submitAlgorithmJob).mockResolvedValueOnce({ jobId: `job-${index}`, status: 'succeeded' })
      vi.mocked(getAlgorithmJobResult).mockResolvedValueOnce(algorithmResult(`result-${index}`))
      await submitAlgorithm()
      expect(wrapper.get('.query-result-table[aria-label="图算法执行结果"]').text()).toContain(`result-${index}`)
    }
    for (const [index, label] of ['Degree算法', 'Louvain算法', 'PageRank算法'].entries()) {
      await clickButton(label)
      expect(wrapper.get('.platform-query-algo__job').text()).toContain(`job-${index}`)
      expect(wrapper.get('.query-result-table[aria-label="图算法执行结果"]').text()).toContain(`result-${index}`)
    }
  })

  it('stores a late submission in its original tab and resumes polling on return', async () => {
    const request = deferred<AlgorithmJobSnapshot>()
    vi.mocked(submitAlgorithmJob).mockReturnValueOnce(request.promise)
    await enterAlgorithms()
    await submitAlgorithm()
    await clickButton('Degree算法')
    expect(wrapper.get('.platform-query-algo__actions button').attributes('disabled')).toBeUndefined()
    request.resolve({ jobId: 'pagerank-job', status: 'running' })
    await flushPromises()
    expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)
    await vi.advanceTimersByTimeAsync(3000)
    expect(getAlgorithmJob).not.toHaveBeenCalled()
    await clickButton('PageRank算法')
    expect(wrapper.get('.platform-query-algo__job').text()).toContain('pagerank-job')
    await vi.advanceTimersByTimeAsync(3000)
    expect(getAlgorithmJob).toHaveBeenCalledWith('space-a', 'pagerank-job')
  })

  it('keeps an in-flight result in its original algorithm tab', async () => {
    const request = deferred<AlgorithmResultPayload>()
    vi.mocked(submitAlgorithmJob).mockResolvedValueOnce({ jobId: 'job-a', status: 'succeeded' })
    vi.mocked(getAlgorithmJobResult).mockReturnValueOnce(request.promise)
    await enterAlgorithms()
    await submitAlgorithm()
    await clickButton('Louvain算法')
    request.resolve(algorithmResult('pagerank-only-result'))
    await flushPromises()
    expect(wrapper.find('.query-result-table[aria-label="图算法执行结果"]').exists()).toBe(false)
    await clickButton('PageRank算法')
    expect(wrapper.get('.query-result-table').text()).toContain('pagerank-only-result')
  })

  it('marks the submit button as running and shows the running panel while a job is in progress', async () => {
    await enterAlgorithms()
    await submitAlgorithm()
    const button = wrapper.get('.platform-query-algo__actions button')
    expect(button.text()).toBe('提交算法作业')
    expect(button.attributes('disabled')).toBeDefined()
    expect(wrapper.get('.platform-query-algo__job-running').text()).toContain('算法作业运行中')
  })

  it('does not restore metadata from a space whose request completed late', async () => {
    const oldRequest = deferred<GraphAlgorithmMetadata>()
    vi.mocked(fetchGraphAlgorithmMetadata).mockReturnValueOnce(oldRequest.promise)
    await enterAlgorithms()
    await switchSpace()
    oldRequest.resolve({ edgeTypes: ['stale-edge'], engine: { status: 'DOWN', message: 'old-engine' } })
    await flushPromises()
    expect(wrapper.get('.platform-query-algo__labels').text()).toContain('space-b-edge')
    expect(wrapper.text()).not.toContain('stale-edge')
    expect(wrapper.text()).not.toContain('old-engine')
    expect(wrapper.get('.platform-query-algo__engine').text()).toContain('算法引擎正常')
  })

  it('ignores a late submission response after switching spaces', async () => {
    const oldRequest = deferred<AlgorithmJobSnapshot>()
    vi.mocked(submitAlgorithmJob).mockReturnValueOnce(oldRequest.promise)
    await enterAlgorithms()
    await submitAlgorithm()
    await switchSpace()
    oldRequest.resolve({ jobId: 'stale-job', status: 'running' })
    await flushPromises()
    expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)
    expect(wrapper.get('.platform-query-algo__actions button').attributes('disabled')).toBeUndefined()
    await vi.advanceTimersByTimeAsync(6000)
    expect(getAlgorithmJob).not.toHaveBeenCalled()
  })

  it('ignores a late poll response and does not fetch its results in the new space', async () => {
    const oldPoll = deferred<AlgorithmJobSnapshot>()
    vi.mocked(getAlgorithmJob).mockReturnValueOnce(oldPoll.promise)
    await enterAlgorithms()
    await submitAlgorithm()
    await vi.advanceTimersByTimeAsync(3000)
    expect(getAlgorithmJob).toHaveBeenCalledWith('space-a', 'job-a')
    await switchSpace()
    oldPoll.resolve({ jobId: 'job-a', status: 'succeeded' })
    await flushPromises()
    expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)
    expect(getAlgorithmJobResult).not.toHaveBeenCalled()
  })

  it('ignores an in-flight result response after switching spaces', async () => {
    const oldResult = deferred<AlgorithmResultPayload>()
    vi.mocked(getAlgorithmJob).mockResolvedValueOnce({ jobId: 'job-a', status: 'succeeded' })
    vi.mocked(getAlgorithmJobResult).mockReturnValueOnce(oldResult.promise)
    await enterAlgorithms()
    await submitAlgorithm()
    await vi.advanceTimersByTimeAsync(3000)
    expect(getAlgorithmJobResult).toHaveBeenCalledWith('space-a', 'job-a')
    await switchSpace()
    oldResult.resolve(algorithmResult('stale-algorithm-result'))
    await flushPromises()
    expect(wrapper.find('.query-result-table[aria-label="图算法执行结果"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('stale-algorithm-result')
  })

  it.each(['mode', 'page'] as const)('resumes polling a running job after returning from another %s', async (destination) => {
    await enterAlgorithms()
    await submitAlgorithm()
    if (destination === 'mode') await clickButton('nGQL 模式')
    else await wrapper.setProps({ initialTab: 'service' })
    await vi.advanceTimersByTimeAsync(6000)
    expect(getAlgorithmJob).not.toHaveBeenCalled()

    if (destination === 'mode') await clickButton('图算法')
    else await wrapper.setProps({ initialTab: 'query' })
    vi.mocked(getAlgorithmJob).mockResolvedValueOnce({ jobId: 'job-a', status: 'succeeded' })
    await vi.advanceTimersByTimeAsync(3000)
    await flushPromises()
    expect(getAlgorithmJob).toHaveBeenCalledTimes(1)
    expect(getAlgorithmJob).toHaveBeenCalledWith('space-a', 'job-a')
    expect(wrapper.get('.query-result-table[aria-label="图算法执行结果"]').text()).toContain('current-result')
    expect(fetchGraphAlgorithmMetadata).toHaveBeenCalledTimes(1)
  })
})


describe('Algorithm result lists', () => {
  it('shows the shared vertical marker on nGQL and every algorithm result title', async () => {
    const assertMarkedTitle = (title: string) => {
      const heading = wrapper.get('.platform-query-result__title')
      expect(heading.text()).toBe(title)
      expect(heading.get('.platform-query-result__title-marker').attributes('aria-hidden')).toBe('true')
    }

    assertMarkedTitle('nGQL 执行结果')
    await enterAlgorithms()
    for (const algorithm of ['PageRank算法', 'Louvain算法', 'Degree算法']) {
      await clickButton(algorithm)
      assertMarkedTitle(`${algorithm}执行结果`)
    }
  })

  it('fills the remaining height with unexecuted result panels so the workspace keeps its 16px inset', async () => {
    const ngqlResult = wrapper.get('.platform-query-result')
    expect(ngqlResult.classes()).toContain('platform-query-result--fill')
    expect(ngqlResult.text()).toContain('暂无数据，执行 nGQL 语句后在此查看结果')
    await enterAlgorithms()
    const algorithmResult = wrapper.get('.platform-query-algo-result')
    expect(algorithmResult.classes()).toContain('platform-query-result--fill')
    expect(algorithmResult.text()).toContain('暂无数据，提交算法作业后在此查看结果')
  })

  it('keeps the query page scrollable without showing its scrollbar in either mode', async () => {
    expect(wrapper.get('.platform-query').classes()).toContain('platform-query--scrollbar-suppressed')
    await enterAlgorithms()
    expect(wrapper.get('.platform-query').classes()).toContain('platform-query--scrollbar-suppressed')
  })

  it('does not show the verbose server-truncation alert', async () => {
    vi.mocked(submitAlgorithmJob).mockResolvedValueOnce({ jobId: 'job-a', status: 'succeeded' })
    vi.mocked(getAlgorithmJobResult).mockResolvedValueOnce({
      jobId: 'job-a', sink: 'csv', truncated: true, rows: [{ vid: 'limited-node', degree: '1' }],
    })
    await enterAlgorithms()
    await clickButton('Degree算法')
    await submitAlgorithm()
    expect(wrapper.find('.platform-query-algo__truncated').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('本次结果预览已被服务端截断')
  })

  it('shows progress below the unchanged submit button before the submit response', async () => {
    const request = deferred<AlgorithmJobSnapshot>()
    vi.mocked(submitAlgorithmJob).mockReturnValueOnce(request.promise)
    await enterAlgorithms()
    await clickButton('Degree算法')
    await submitAlgorithm()
    expect(wrapper.get('.platform-query-algo__actions button').text()).toBe('提交算法作业')
    expect(wrapper.get('.platform-query-algo__job-running').text()).toContain('正在提交')
    request.resolve({ jobId: 'degree-job', status: 'running' })
    await flushPromises()
    expect(wrapper.get('.platform-query-algo__job-running').text()).toContain('运行中')
  })

  it('paginates, searches and numerically sorts a large result without graph panels', async () => {
    vi.mocked(submitAlgorithmJob).mockResolvedValueOnce({ jobId: 'job-a', status: 'succeeded' })
    vi.mocked(getAlgorithmJobResult).mockResolvedValueOnce({
      jobId: 'job-a', sink: 'csv', truncated: true,
      rows: Array.from({ length: 10000 }, (_, index) => ({ vid: `node-${index}`, degree: String(index) })),
    })
    await enterAlgorithms()
    await clickButton('Degree算法')
    await submitAlgorithm()
    expect(wrapper.findAll('tbody tr')).toHaveLength(20)
    expect(wrapper.findAll('tbody tr')[0]!.text()).toContain('node-9999')
    expect(wrapper.text()).not.toContain('已返回 10000 条（非全部结果）')
    expect(wrapper.text()).not.toContain('匹配 10000 条 · 搜索和排序仅针对已返回结果')
    expect(wrapper.find('aside').exists()).toBe(false)
    await wrapper.get('input[aria-label="搜索图 VID"]').setValue('node-1234')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
    expect(wrapper.get('tbody').text()).toContain('node-1234')
    await wrapper.get('input[aria-label="搜索图 VID"]').setValue('missing-node')
    expect(wrapper.text()).toContain('没有匹配')
  })

  it('places the nGQL toolbar below the shared mode header', async () => {
    const header = wrapper.get('.platform-query-form .kg-panel__header')
    expect(header.text()).toContain('图算法')
    expect(header.text()).not.toContain('执行 nGQL')
    expect(wrapper.get('.platform-ngql-toolbar').text()).toContain('执行 nGQL')
  })
})


describe('Query page concise controls and graph VIDs', () => {
  it.each(['vid', '_id', 'id'])('shows and filters original graph VID from %s without matching algorithm values', async (key) => {
    vi.mocked(submitAlgorithmJob).mockResolvedValueOnce({ jobId: 'job-a', status: 'succeeded' })
    vi.mocked(getAlgorithmJobResult).mockResolvedValueOnce({
      jobId: 'job-a', sink: 'csv', rows: [
        { [key]: 'person_AbC', pagerank: '0.123', community: 'community-77' },
        { [key]: 'paper_XyZ', pagerank: '0.456', community: 'community-88' },
      ],
    })
    await enterAlgorithms()
    await submitAlgorithm()
    expect(wrapper.get('.query-result-table').text()).toContain('图 VID')
    const input = wrapper.get('input[aria-label="搜索图 VID"]')
    await input.setValue('person_AbC')
    expect(wrapper.findAll('.query-result-table tbody tr')).toHaveLength(1)
    expect(wrapper.get('.query-result-table').text()).toContain('person_AbC')
    await input.setValue('0.123')
    expect(wrapper.find('.query-result-table').exists()).toBe(false)
    await input.setValue('community-77')
    expect(wrapper.find('.query-result-table').exists()).toBe(false)
    await input.setValue('person_abc')
    expect(wrapper.find('.query-result-table').exists()).toBe(false)
  })

  it('removes the redundant parameter notice and keeps relation help next to its label', async () => {
    await enterAlgorithms()
    expect(wrapper.text()).not.toContain('当前算法无可调参数')
    expect(wrapper.find('.arco-form-item-extra').exists()).toBe(false)
    expect(wrapper.get('.arco-form-item-label').text()).toContain('可多选，最多 20 个')
    expect(wrapper.find('.platform-query-algo__desc').exists()).toBe(false)
    expect(wrapper.find('button[aria-label="查看算法说明"]').exists()).toBe(true)
  })

  it('uses the same primary button style in both modes and validates an empty query on click', async () => {
    expect(wrapper.get('.platform-ngql-header-actions button').classes()).toContain('arco-btn-primary')
    expect(wrapper.get('.platform-ngql-header-actions button').attributes('disabled')).toBeUndefined()
    await clickButton('执行 nGQL')
    expect(runNgql).not.toHaveBeenCalled()
    await enterAlgorithms()
    expect(wrapper.get('.platform-query-algo__actions button').classes()).toContain('arco-btn-primary')
  })
})
