import { mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import ClearableInput from '../ClearableInput.vue'
import ClearableTextarea from '../ClearableTextarea.vue'

describe('clearable controls', () => {
  it('clears the bound value, keeps focus, and does not submit the surrounding form', async () => {
    const submit = vi.fn()
    const view = mount(defineComponent({
      components: { ClearableInput },
      data: () => ({ name: '' }),
      methods: { submit },
      template: '<form @submit.prevent="submit"><ClearableInput v-model="name" aria-label="任务名称" /></form>',
    }), { attachTo: document.body })
    expect(view.find('button').exists()).toBe(false)
    await view.get('input').setValue('抽取任务')
    await view.get('button[aria-label="清空任务名称"]').trigger('click')
    expect(view.vm.name).toBe('')
    expect(view.get('input').element.value).toBe('')
    expect(view.find('button').exists()).toBe(false)
    expect(document.activeElement).toBe(view.get('input').element)
    expect(submit).not.toHaveBeenCalled()
    view.unmount()
  })

  it('preserves raw numeric strings for input-event consumers, including long values and zero', async () => {
    const view = mount(defineComponent({
      components: { ClearableInput },
      data: () => ({ port: '0' }),
      template: '<ClearableInput type="number" :value="port" @input="port = $event.target.value" />',
    }))
    expect(view.get('input').element.value).toBe('0')
    expect(view.find('button').exists()).toBe(true)
    await view.get('input').setValue('1'.repeat(65))
    expect(view.vm.port).toBe('1'.repeat(65))
    await view.get('button').trigger('click')
    expect(view.vm.port).toBe('')
    view.unmount()
  })

  it('updates value and editability when attrs change and hides clear for protected controls', async () => {
    const view = mount(ClearableInput, { attrs: { value: '旧值', disabled: true } })
    expect(view.find('button').exists()).toBe(false)
    await view.setProps({ disabled: false, value: '新值' })
    expect(view.get('input').element.value).toBe('新值')
    expect(view.find('button').exists()).toBe(true)
    await view.setProps({ readonly: true })
    expect(view.find('button').exists()).toBe(false)
    view.unmount()
  })

  it('retains number modifiers and emits an empty string on clear', async () => {
    const view = mount(ClearableInput, { props: { modelValue: 5, modelModifiers: { number: true } } })
    await view.get('input').setValue('8')
    expect(view.emitted('update:modelValue')?.at(-1)).toEqual([8])
    await view.get('button').trigger('click')
    expect(view.emitted('update:modelValue')?.at(-1)).toEqual([''])
    view.unmount()
  })

  it('clears multiline text and notifies input validation', async () => {
    const view = mount(ClearableTextarea, { props: { modelValue: 'MATCH (n) RETURN n' } })
    await view.get('button[aria-label="清空文本内容"]').trigger('click')
    expect(view.emitted('update:modelValue')).toEqual([['']])
    expect(view.emitted('input')).toEqual([['']])
    await view.setProps({ modelValue: '' })
    expect(view.find('button').exists()).toBe(false)
    view.unmount()
  })
})
