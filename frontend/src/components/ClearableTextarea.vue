<script setup lang="ts">
import { ref, useAttrs } from 'vue'
import { Textarea } from '@arco-design/web-vue'
import IconClose from '@arco-design/web-vue/es/icon/icon-close'
import '../styles/clearable-controls.css'

defineOptions({ inheritAttrs: false })
const props = defineProps<{ modelValue?: string }>()
const emit = defineEmits<{
  'update:modelValue': [value: string]
  input: [value: string, event?: Event]
  clear: []
}>()
const attrs = useAttrs()
const field = ref<InstanceType<typeof Textarea>>()
const canClear = () => props.modelValue && !attrs.disabled && attrs.disabled !== '' && !attrs.readonly && attrs.readonly !== ''
function clear() {
  emit('update:modelValue', '')
  emit('input', '')
  emit('clear')
  field.value?.focus()
}
</script>

<template>
  <div class="clearable-textarea">
    <Textarea
      ref="field"
      v-bind="attrs"
      :model-value="modelValue"
      @update:model-value="emit('update:modelValue', $event)"
      @input="(value, event) => emit('input', value, event)"
    />
    <button v-if="canClear()" class="clearable-input__clear" type="button" aria-label="清空文本内容" title="清空" @mousedown.prevent @click.prevent.stop="clear"><IconClose /></button>
  </div>
</template>

<style scoped>
.clearable-textarea { position: relative; width: 100%; min-width: 0; }
.clearable-textarea :deep(textarea.arco-textarea) { padding-right: 36px !important; }
.clearable-textarea > button.clearable-input__clear { position: absolute; top: 10px; right: 12px; }
</style>
