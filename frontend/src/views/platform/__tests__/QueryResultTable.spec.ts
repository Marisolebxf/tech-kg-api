import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import QueryResultTable from '../QueryResultTable.vue'

let wrapper: VueWrapper | undefined

afterEach(() => {
  wrapper?.unmount()
  vi.unstubAllGlobals()
})

describe('Query result action column shadow', () => {
  it('tracks remaining overflow on scrolling, resizing and changing columns', async () => {
    let onResize = () => {}
    const disconnect = vi.fn()
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { onResize = callback }
      observe() {}
      disconnect = disconnect
    })
    wrapper = mount(QueryResultTable, {
      props: { rows: [{ name: 'node' }], columns: ['name'], page: 1, pageSize: 20 },
    })
    const scroller = wrapper.get('.arco-table-content')
    let width = 500
    let contentWidth = 500
    Object.defineProperties(scroller.element, {
      clientWidth: { get: () => width },
      scrollWidth: { get: () => contentWidth },
    })
    onResize()
    await nextTick()
    expect(wrapper.classes()).not.toContain('query-result-table--hidden-columns')

    contentWidth = 900
    onResize()
    await nextTick()
    expect(wrapper.classes()).toContain('query-result-table--hidden-columns')
    scroller.element.scrollLeft = 400
    await scroller.trigger('scroll')
    expect(wrapper.classes()).not.toContain('query-result-table--hidden-columns')
    scroller.element.scrollLeft = 100
    await scroller.trigger('scroll')
    expect(wrapper.classes()).toContain('query-result-table--hidden-columns')

    width = 1000
    onResize()
    await nextTick()
    expect(wrapper.classes()).not.toContain('query-result-table--hidden-columns')
    width = 500
    scroller.element.scrollLeft = 0
    await wrapper.setProps({ columns: ['name', 'extra'] })
    await flushPromises()
    expect(wrapper.classes()).toContain('query-result-table--hidden-columns')
    wrapper.unmount()
    wrapper = undefined
    expect(disconnect).toHaveBeenCalledOnce()
  })
})
