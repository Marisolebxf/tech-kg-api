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
  return { jobId: 'job-a', sink: 'csv', rows: [{ vertex: value, pagerank: '0.5' }] }
}

let wrapper: VueWrapper
let store: ReturnType<typeof useGraphSpaceStore>

beforeEach(() => {
  vi.resetAllMocks()
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
    expect(wrapper.get('table[aria-label="nGQL 查询结果"]').text()).toContain('result-a')

    await switchSpace()
    expect(wrapper.find('table[aria-label="nGQL 查询结果"]').exists()).toBe(false)
    await clickButton('执行 nGQL')
    await flushPromises()
    expect(runNgql).toHaveBeenLastCalledWith('space-b', 'MATCH (v) RETURN v')
    expect(wrapper.get('table[aria-label="nGQL 查询结果"]').text()).toContain('result-b')
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
    expect(wrapper.get('table').text()).toContain('fresh-result')
  })

  it('renders common nGQL result columns as Chinese-only headers', async () => {
    vi.mocked(runNgql).mockResolvedValueOnce({
      columns: ['rel', 'src', 'custom_col'],
      records: [{ rel: 'HAS_KEYWORD', src: 'patent-a', custom_col: 'x' }],
      summary: {},
      kind: 'read',
    })
    await wrapper.get('textarea').setValue('MATCH (v:Patent)-[e:HAS_KEYWORD]->() RETURN type(e) AS rel, id(v) AS src LIMIT 3')
    await clickButton('执行 nGQL')
    await flushPromises()
    const headers = wrapper.get('table[aria-label="nGQL 查询结果"]').findAll('th')
    // 命中映射：只显示中文名，不再附带英文原列名（原始列名仅保留在 title 悬停提示）
    expect(headers[0].text()).toBe('边类型')
    expect(headers[0].attributes('title')).toContain('rel')
    expect(headers[1].text()).toBe('起点ID')
    // 未收录的列名原样展示
    expect(headers[2].text()).toBe('custom_col')
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
    expect(wrapper.get('table[aria-label="图算法执行结果"]').text()).toContain('current-result')
    await switchSpace('space-c')
    expect(wrapper.find('.platform-query-algo__job').exists()).toBe(false)
    expect(wrapper.find('table[aria-label="图算法执行结果"]').exists()).toBe(false)
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

  it('renders algorithm-specific advanced params per tab and hides them for degree', async () => {
    await enterAlgorithms()
    expect(wrapper.text()).toContain('最大迭代次数')
    expect(wrapper.text()).toContain('重置概率')
    await clickButton('Louvain算法')
    expect(wrapper.text()).toContain('内部迭代')
    expect(wrapper.text()).not.toContain('重置概率')
    await clickButton('Degree算法')
    expect(wrapper.text()).toContain('当前算法无可调参数')
    expect(wrapper.find('.platform-query-algo__input').exists()).toBe(false)
    await clickButton('PageRank算法')
    await clickButton('收起高级参数')
    expect(wrapper.text()).not.toContain('最大迭代次数')
    await clickButton('高级参数（2 个）')
    expect(wrapper.text()).toContain('最大迭代次数')
  })

  it('marks the submit button as running and shows the running panel while a job is in progress', async () => {
    await enterAlgorithms()
    await submitAlgorithm()
    const button = wrapper.get('.platform-query-algo__actions button')
    expect(button.text()).toContain('作业运行中')
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
    expect(wrapper.find('.platform-query-algo-result').exists()).toBe(false)
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
    expect(wrapper.get('table[aria-label="图算法执行结果"]').text()).toContain('current-result')
    expect(fetchGraphAlgorithmMetadata).toHaveBeenCalledTimes(1)
  })
})
