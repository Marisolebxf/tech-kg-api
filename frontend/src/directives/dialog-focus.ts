import { nextTick, type ObjectDirective } from 'vue'

interface DialogOptions { close: () => void; busy?: boolean }
interface DialogState {
  element: HTMLElement
  options: DialogOptions
  opener: HTMLElement | null
  keydown: (event: KeyboardEvent) => void
  focusin: (event: FocusEvent) => void
}
const stack: DialogState[] = []
const states = new WeakMap<HTMLElement, DialogState>()
const focusable = 'button:not(:disabled),a[href],input:not(:disabled):not([type="hidden"]),select:not(:disabled),textarea:not(:disabled),[tabindex]:not([tabindex="-1"])'
function controls(element: HTMLElement) {
  return [...element.querySelectorAll<HTMLElement>(focusable)].filter(node =>
    node.tabIndex >= 0 && !node.closest('[hidden],[inert],[aria-hidden="true"]') &&
    getComputedStyle(node).display !== 'none' && getComputedStyle(node).visibility !== 'hidden')
}
function focusFirst(element: HTMLElement) { (controls(element)[0] ?? element).focus() }

/** Focus belongs to the topmost custom dialog, including its Arco popup controls. */
export const vDialogFocus: ObjectDirective<HTMLElement, DialogOptions> = {
  mounted(element, binding) {
    const state: DialogState = {
      element, options: binding.value,
      opener: document.activeElement instanceof HTMLElement ? document.activeElement : null,
      keydown(event) {
        if (stack.at(-1) !== state) return
        if (document.activeElement instanceof Element && document.activeElement.closest('.arco-modal,.arco-drawer')) return
        if (event.key === 'Escape') {
          // A select/date popup handles its own first Escape before the dialog closes.
          if (document.querySelector('.arco-trigger-popup:not([style*="display: none"]),.el-popper:not([aria-hidden="true"])')) return
          event.preventDefault()
          if (!state.options.busy) state.options.close()
        }
        if (event.key !== 'Tab') return
        const items = controls(element)
        const first = items[0] ?? element
        const last = items.at(-1) ?? element
        if (event.shiftKey ? document.activeElement === first : document.activeElement === last) {
          event.preventDefault()
          ;(event.shiftKey ? last : first).focus()
        } else if (!element.contains(document.activeElement)) {
          event.preventDefault()
          first.focus()
        }
      },
      focusin(event) {
        if (stack.at(-1) !== state || !(event.target instanceof Element)) return
        if (!element.contains(event.target) && !event.target.closest('.arco-trigger-popup,.el-popper,.arco-modal,.arco-drawer')) focusFirst(element)
      },
    }
    element.setAttribute('role', 'dialog')
    element.setAttribute('aria-modal', 'true')
    element.tabIndex = -1
    if (!element.hasAttribute('aria-label') && !element.hasAttribute('aria-labelledby')) {
      element.setAttribute('aria-label', element.querySelector('h1,h2,h3')?.textContent?.trim() || '对话框')
    }
    // Existing symbol-only close buttons need an accessible name and tooltip.
    for (const button of element.querySelectorAll('header button')) {
      if (button.textContent?.trim() === '×' && !button.hasAttribute('aria-label')) {
        button.setAttribute('aria-label', '关闭弹窗')
        button.setAttribute('title', '关闭弹窗')
      }
    }
    states.set(element, state)
    stack.push(state)
    document.addEventListener('keydown', state.keydown)
    document.addEventListener('focusin', state.focusin)
    void nextTick(() => { if (stack.at(-1) === state) focusFirst(element) })
  },
  updated(element, binding) { const state = states.get(element); if (state) state.options = binding.value },
  beforeUnmount(element) {
    const state = states.get(element)
    if (!state) return
    const wasTop = stack.at(-1) === state
    stack.splice(stack.indexOf(state), 1)
    document.removeEventListener('keydown', state.keydown)
    document.removeEventListener('focusin', state.focusin)
    states.delete(element)
    if (wasTop) void nextTick(() => {
      if (state.opener?.isConnected) state.opener.focus()
      else if (stack.at(-1)) focusFirst(stack.at(-1)!.element)
    })
  },
}
