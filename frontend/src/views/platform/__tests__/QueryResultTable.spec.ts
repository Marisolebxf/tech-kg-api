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
  it.each([false, true])('uses one viewport and tracks the action shadow (sortable=%s)', async (sortable) => {
    let onResize = () => {}
    const disconnect = vi.fn()
    vi.stubGlobal('ResizeObserver', class {
      constructor(callback: () => void) { onResize = callback }
      observe() {}
      disconnect = disconnect
    })
    wrapper = mount(QueryResultTable, {
      props: { rows: [{ name: 'node' }], columns: ['name'], page: 1, pageSize: 20, sortable },
    })
    const scroller = wrapper.get('.arco-table-content')
    // maxHeight must not be passed to Arco: it creates separate header/body
    // viewports and a second scrollbar even when the outer CSS looks correct.
    expect(wrapper.find('.arco-table-header').exists()).toBe(false)
    expect(wrapper.find('.arco-table-body').exists()).toBe(false)
    expect(scroller.findAll('table')).toHaveLength(1)
    expect(scroller.find('thead').exists()).toBe(true)
    expect(scroller.find('tbody').exists()).toBe(true)
    expect(scroller.find('thead .arco-table-col-fixed-right').exists()).toBe(true)
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
