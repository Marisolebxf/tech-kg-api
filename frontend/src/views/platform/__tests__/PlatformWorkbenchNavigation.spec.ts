import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { defineComponent } from 'vue'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { cancelAlgorithmJob, submitAlgorithmJob } from '../../../api/graphAlgorithm'
import { useGraphSpaceStore } from '../../../stores/graphSpace'
import PlatformWorkbenchView from '../PlatformWorkbenchView.vue'

vi.mock('../../../api/graphConsole', () => ({ runNgql: vi.fn() }))
vi.mock('../../../api/schemaManagement', () => ({ getSchemaTopology: vi.fn().mockResolvedValue({ nodes: [], edges: [] }) }))
vi.mock('../../../api/platformOverview', () => ({ getPlatformOverview: vi.fn().mockResolvedValue({
  platformStatus: '正常', pendingBatchCount: 0, updatedAt: '--', dataMode: 'partial', warnings: [],
  assetOverviewGroups: [], assetChangeRows: { entity: [], relation: [] },
  entityStructure: [], relationStructure: [], dataSources: {},
}) }))
vi.mock('../../../api/workflowOperations', () => ({
  listJobs: vi.fn().mockResolvedValue([]), getProductionReviews: vi.fn().mockResolvedValue([]),
  countJobUnifiedStatuses: vi.fn().mockReturnValue({}), deriveJobUnifiedStatus: vi.fn(),
  jobGraphSpace: vi.fn(), JOB_STATUS_TONE: {},
}))
vi.mock('../../../api/graphAlgorithm', () => ({
  cancelAlgorithmJob: vi.fn(), submitAlgorithmJob: vi.fn(), getAlgorithmJob: vi.fn(),
  getAlgorithmJobResult: vi.fn(), fetchGraphAlgorithmEngine: vi.fn(),
  fetchGraphAlgorithmMetadata: vi.fn().mockResolvedValue({ edgeTypes: ['ACQUIRES'], engine: { status: 'UP' } }),
}))
vi.mock('../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

const SelectStub = defineComponent({
  props: ['modelValue', 'multiple'], emits: ['update:modelValue'],
  template: `<select multiple :value="modelValue" @change="$emit('update:modelValue', Array.from($event.target.selectedOptions, o => o.value))"><slot /></select>`,
})
const OptionStub = defineComponent({ props: ['value'], template: '<option :value="value"><slot /></option>' })
let wrapper: VueWrapper
let router: ReturnType<typeof createRouter>
const pinia = createPinia()

beforeEach(async () => {
  localStorage.clear()
  vi.clearAllMocks()
  vi.stubGlobal('matchMedia', () => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() }))
  vi.mocked(submitAlgorithmJob).mockResolvedValue({ jobId: 'navigation-job', status: 'running' })
  vi.mocked(cancelAlgorithmJob).mockResolvedValue({ jobId: 'navigation-job', status: 'cancelled' })
  setActivePinia(pinia)
  const store = useGraphSpaceStore()
  store.$reset()
  store.spaces = ['dev2']
  store.setCurrent('dev2')
  router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/graph-query', component: PlatformWorkbenchView, props: { initialTab: 'query' } },
    { path: '/overview', component: PlatformWorkbenchView, props: { initialTab: 'overview' } },
    { path: '/other', component: { template: '<p>Other page</p>' } },
  ] })
  await router.push('/graph-query')
  await router.isReady()
  wrapper = mount(defineComponent({ components: { RouterView }, template: '<RouterView />' }), {
    global: { plugins: [pinia, router], stubs: { 'a-select': SelectStub, 'a-option': OptionStub } },
  })
  const click = async (label: string) => {
    const button = wrapper.findAll('button').find(b => b.text() === label)
    expect(button).toBeDefined()
    await button!.trigger('click')
    await flushPromises()
  }
  await click('图算法')
  await wrapper.get('.platform-query-algo__labels select').setValue(['ACQUIRES'])
  await click('提交算法作业')
  expect(submitAlgorithmJob).toHaveBeenCalledTimes(1)
})

afterEach(async () => {
  wrapper.unmount()
  await flushPromises()
  vi.unstubAllGlobals()
})

it.each(['/other', '/overview'])('actual router waits for termination before navigating to %s', async destination => {
  let finish!: (value: { jobId: string; status: 'cancelled' }) => void
  vi.mocked(cancelAlgorithmJob).mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  const navigation = router.push(destination)
  await flushPromises()
  expect(router.currentRoute.value.path).toBe('/graph-query')
  expect(cancelAlgorithmJob).toHaveBeenCalledWith('dev2', 'navigation-job')
  finish({ jobId: 'navigation-job', status: 'cancelled' })
  await navigation
  await flushPromises()
  expect(router.currentRoute.value.path).toBe(destination)
  expect(cancelAlgorithmJob).toHaveBeenCalledTimes(1)
})

it('actual router keeps the job page when termination fails and allows retry', async () => {
  expect(wrapper.get('.platform-query-algo__job').text()).toContain('navigation-job')
  vi.mocked(cancelAlgorithmJob).mockRejectedValueOnce(new Error('Spark unavailable'))
  await router.push('/other')
  expect(cancelAlgorithmJob).toHaveBeenCalledTimes(1)
  expect(router.currentRoute.value.path).toBe('/graph-query')
  expect(wrapper.get('.platform-query-algo__job').text()).toContain('navigation-job')
  await router.push('/other')
  expect(router.currentRoute.value.path).toBe('/other')
  expect(cancelAlgorithmJob).toHaveBeenCalledTimes(2)
})
