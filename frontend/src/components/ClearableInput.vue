<script setup lang="ts">
import { ref, useAttrs, type StyleValue } from 'vue'
import '../styles/clearable-controls.css'
import IconClose from '@arco-design/web-vue/es/icon/icon-close'

// Keep native input events and string-valued numeric fields intact. Several
// forms validate the original numeric text before converting it for submission.
defineOptions({ inheritAttrs: false })
const props = withDefaults(defineProps<{
  modelValue?: string | number | boolean | null
  modelModifiers?: { number?: boolean; trim?: boolean; lazy?: boolean }
}>(), { modelValue: undefined })
const emit = defineEmits<{
  'update:modelValue': [value: string | number]
  input: [event: Event]
  clear: []
}>()
const attrs = useAttrs()
const input = ref<HTMLInputElement>()
const value = () => props.modelValue ?? attrs.value ?? ''
const disabled = () => attrs.disabled === '' || Boolean(attrs.disabled)
const readonly = () => attrs.readonly === '' || Boolean(attrs.readonly)
const controlAttrs = () => {
  const { class: _class, style: _style, value: _value, ...rest } = attrs
  return rest
}
const composing = ref(false)

function updateModel(event: Event) {
  let next: string | number = (event.target as HTMLInputElement).value
  if (props.modelModifiers?.trim) next = next.trim()
  if (props.modelModifiers?.number || attrs.type === 'number') {
    const numeric = Number.parseFloat(next)
    if (!Number.isNaN(numeric)) next = numeric
  }
  emit('update:modelValue', next)
}

function onInput(event: Event) {
  if (!composing.value && !props.modelModifiers?.lazy) updateModel(event)
  emit('input', event)
}

function clear() {
  if (!input.value || disabled() || readonly()) return
  input.value.value = ''
  input.value.dispatchEvent(new Event('input', { bubbles: true }))
  input.value.dispatchEvent(new Event('change', { bubbles: true }))
  emit('clear')
  input.value.focus()
}
</script>

<template>
  <div
    class="clearable-input"
    :class="[attrs.class, { 'is-disabled': disabled(), 'is-invalid': attrs['aria-invalid'] === true || attrs['aria-invalid'] === 'true' }]"
    :style="attrs.style as StyleValue"
  >
    <input
      ref="input"
      v-bind="controlAttrs()"
      class="clearable-input__control"
      :class="attrs.class"
      :value="value()"
      @input="onInput"
      @change="props.modelModifiers?.lazy && updateModel($event)"
      @compositionstart="composing = true"
      @compositionend="composing = false; updateModel($event)"
    />
    <button
      v-if="String(value()) !== '' && !disabled() && !readonly()"
      class="clearable-input__clear"
      type="button"
      :aria-label="`清空${attrs['aria-label'] || attrs.placeholder || '输入内容'}`"
      title="清空"
      @mousedown.prevent
      @click.prevent.stop="clear"
    ><IconClose /></button>
  </div>
</template>

<style scoped>
.clearable-input {
  position: relative;
  display: inline-flex;
  align-items: center;
  box-sizing: border-box;
  width: 100%;
  min-width: 0;
  height: 32px;
  padding: 0 12px;
  border: 1px solid #e5e6eb;
  border-radius: 4px;
  background: #fff;
  color: #1d2129;
  font: inherit;
}
.clearable-input:hover { border-color: #4080ff; }
.clearable-input:focus-within { border-color: #165dff; box-shadow: 0 0 0 2px rgb(22 93 255 / 10%); }
.clearable-input.is-invalid { border-color: #e4322d; }
.clearable-input.is-disabled { background: #f2f3f5; color: #86909c; cursor: not-allowed; }
</style>

