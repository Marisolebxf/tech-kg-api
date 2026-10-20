import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

afterEach(() => { resetToasts(); vi.useRealTimers() })

import { useToast } from '../composables/use-toast'
import KgToast from './kg-toast.vue'

/** useToast 的 toasts 是模块级单例：每个用例先清空，避免跨用例串扰。 */
function resetToasts() {
  const { toasts, dismissToast } = useToast()
  for (const item of [...toasts.value]) dismissToast(item.id)
}

describe('全局提示（kg-toast）：四态划分与提示符', () => {
  it('已卸载页面的迟到请求不再向当前页面发提示', () => {
    resetToasts()
    let send!: ReturnType<typeof useToast>['showToast']
    const page = mount(defineComponent({ setup() { send = useToast().showToast; return () => null } }))
    send('当前页面提示')
    page.unmount()
    send('旧请求迟到提示', 'error')
    expect(useToast().toasts.value.map(item => item.message)).toEqual(['当前页面提示'])
  })
  it('info/success/warning/error 各渲染对应状态类与前置提示符图标', () => {
    resetToasts()
    const { showToast } = useToast()
    for (const tone of ['success', 'info', 'warning', 'error'] as const) {
      resetToasts()
      showToast(`测试提示-${tone}`, tone)
      const wrapper = mount(KgToast)
      expect(wrapper.get('.kg-toast').classes()).toContain(`kg-toast--${tone}`)
      expect(wrapper.find('.kg-toast__icon svg').exists()).toBe(true)
      wrapper.unmount()
    }
  })

  it('最多保留三条，移除最早提示且可手动关闭', () => {
    resetToasts()
    const { showToast, toasts, dismissToast } = useToast()
    for (const message of ['一', '二', '三', '四']) showToast(message)
    expect(toasts.value.map(item => item.message)).toEqual(['二', '三', '四'])
    dismissToast(toasts.value[0]!.id)
    expect(toasts.value.map(item => item.message)).toEqual(['三', '四'])
  })

  it('信息/成功停留3秒，警告/错误停留4.5秒', () => {
    vi.useFakeTimers()
    const { showToast, toasts } = useToast()
    for (const tone of ['info', 'success', 'warning', 'error'] as const) {
      resetToasts()
      showToast('定时提示', tone)
      const duration = tone === 'info' || tone === 'success' ? 3000 : 4500
      vi.advanceTimersByTime(duration - 1)
      expect(toasts.value).toHaveLength(1)
      vi.advanceTimersByTime(1)
      expect(toasts.value).toHaveLength(0)
    }
  })

  it('默认 success 态；消息文本渲染', () => {
    resetToasts()
    const { showToast } = useToast()
    showToast('来源表绑定已保存')
    const wrapper = mount(KgToast)
    const item = wrapper.get('.kg-toast')
    expect(item.classes()).toContain('kg-toast--success')
    expect(item.text()).toContain('来源表绑定已保存')
  })
})
