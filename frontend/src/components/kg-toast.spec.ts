import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import { useToast } from '../composables/use-toast'
import KgToast from './kg-toast.vue'

/** useToast 的 toasts 是模块级单例：每个用例先清空，避免跨用例串扰。 */
function resetToasts() {
  const { toasts, dismissToast } = useToast()
  for (const item of [...toasts.value]) dismissToast(item.id)
}

describe('全局提示（kg-toast）：四态划分与提示符', () => {
  it('info/success/warning/error 各渲染对应状态类与前置提示符图标', () => {
    resetToasts()
    const { showToast } = useToast()
    for (const tone of ['success', 'info', 'warning', 'error'] as const) {
      showToast(`测试提示-${tone}`, tone)
    }
    const wrapper = mount(KgToast)
    const items = wrapper.findAll('.kg-toast')
    expect(items).toHaveLength(4)
    expect(
      items.map((node) => node.classes().filter((c) => c.startsWith('kg-toast--'))),
    ).toEqual([['kg-toast--success'], ['kg-toast--info'], ['kg-toast--warning'], ['kg-toast--error']])
    // 每条提示都带与状态同色的提示符（填充圆形图标）
    for (const item of items) {
      expect(item.find('.kg-toast__icon svg').exists()).toBe(true)
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
