import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import AppAlert from './AppAlert.vue'

describe('AppAlert（Arco Alert 四态提示规范）', () => {
  it('info/success/warning/error 各渲染对应状态类与前置提示符（图标）', () => {
    for (const type of ['info', 'success', 'warning', 'error'] as const) {
      const wrapper = mount(AppAlert, { props: { type } })
      expect(wrapper.classes()).toContain(`app-alert--${type}`)
      // 提示符必带：每种状态一个填充圆形图标（成功✓/警告!/错误✕/信息i）
      expect(wrapper.find('.app-alert__icon svg').exists()).toBe(true)
    }
  })

  it('默认 info 态；标题与正文分层层级渲染，role=alert', () => {
    const wrapper = mount(AppAlert, {
      props: { title: '操作成功' },
      slots: { default: '候选已写入图' },
    })
    expect(wrapper.classes()).toContain('app-alert--info')
    expect(wrapper.classes()).toContain('app-alert--with-title')
    expect(wrapper.get('.app-alert__title').text()).toBe('操作成功')
    expect(wrapper.get('.app-alert__content').text()).toBe('候选已写入图')
    expect(wrapper.attributes('role')).toBe('alert')
  })

  it('closable 时渲染关闭按钮并发出 close；默认不渲染', async () => {
    const plain = mount(AppAlert)
    expect(plain.find('.app-alert__close').exists()).toBe(false)

    const wrapper = mount(AppAlert, { props: { closable: true } })
    const close = wrapper.get('.app-alert__close')
    expect(close.attributes('aria-label')).toBe('关闭')
    await close.trigger('click')
    expect(wrapper.emitted('close')).toHaveLength(1)
  })
})
