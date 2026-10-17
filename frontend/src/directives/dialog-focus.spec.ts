import { mount } from '@vue/test-utils'
import { defineComponent, nextTick, ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { vDialogFocus } from './dialog-focus'

function fixture() {
  const close = vi.fn()
  const wrapper = mount(defineComponent({
    directives: { dialogFocus: vDialogFocus },
    setup: () => ({ open: ref(false), nested: ref(false), busy: ref(false), close }),
    template: `<div><button class="opener" @click="open = true">打开</button>
      <aside v-if="open" v-dialog-focus="{ close, busy }"><header><h2>编辑配置</h2><button @click="open = false">×</button></header>
        <input aria-label="名称"><button class="last" @click="nested = true">子弹窗</button>
        <aside v-if="nested" v-dialog-focus="{ close: () => nested = false }"><h2>确认</h2><button @click="nested = false">取消</button></aside>
      </aside></div>`,
  }), { attachTo: document.body })
  return { wrapper, close }
}

describe('custom dialog keyboard contract', () => {
  it('names the dialog, moves focus, wraps Tab, and restores its opener', async () => {
    const { wrapper } = fixture()
    const opener = wrapper.get<HTMLButtonElement>('.opener')
    opener.element.focus()
    await opener.trigger('click'); await nextTick()
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.attributes('aria-label')).toBe('编辑配置')
    expect(dialog.attributes('aria-modal')).toBe('true')
    const first = dialog.get<HTMLButtonElement>('header button')
    expect(first.attributes('aria-label')).toBe('关闭弹窗')
    expect(document.activeElement).toBe(first.element)
    await first.trigger('keydown', { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(wrapper.get('.last').element)
    await wrapper.get('.last').trigger('keydown', { key: 'Tab' })
    expect(document.activeElement).toBe(first.element)
    await first.trigger('click'); await nextTick()
    expect(document.activeElement).toBe(opener.element)
    wrapper.unmount()
  })
  it('only the top dialog handles Escape and busy dialogs cannot be dismissed', async () => {
    const { wrapper, close } = fixture()
    await wrapper.get('.opener').trigger('click'); await nextTick()
    const childOpener = wrapper.get<HTMLButtonElement>('.last')
    childOpener.element.focus()
    await childOpener.trigger('click'); await nextTick()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await nextTick(); await nextTick()
    expect(wrapper.findAll('[role="dialog"]')).toHaveLength(1)
    expect(document.activeElement).toBe(childOpener.element)
    expect(close).not.toHaveBeenCalled()
    wrapper.vm.busy = true; await nextTick()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(close).not.toHaveBeenCalled()
    wrapper.vm.busy = false; await nextTick()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    expect(close).toHaveBeenCalledOnce()
    wrapper.unmount()
  })
})
