<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

const props = defineProps<{
  modelValue: string
  placeholder?: string
  invalid?: boolean
  title?: string
  describedBy?: string
}>()

const emit = defineEmits<{ 'update:modelValue': [string] }>()

const MONTHS = ['1月', '2月', '3月', '4月', '5月', '6月', '7月', '8月', '9月', '10月', '11月', '12月']

const open = ref(false)
const root = ref<HTMLElement | null>(null)
const panelYear = ref(new Date().getFullYear())

/** 把 modelValue（YYYY-MM）解析成年月；非法或空值返回 null */
const selected = computed(() => {
  const matched = /^(\d{4})-(\d{2})$/.exec(props.modelValue ?? '')
  if (!matched) return null
  const month = Number(matched[2])
  if (month < 1 || month > 12) return null
  return { year: Number(matched[1]), month }
})

const displayText = computed(() => {
  if (!selected.value) return ''
  return `${selected.value.year}年${String(selected.value.month).padStart(2, '0')}月`
})

watch(
  () => props.modelValue,
  () => {
    if (selected.value) panelYear.value = selected.value.year
  },
  { immediate: true },
)

function handleDocumentPointerDown(event: MouseEvent) {
  if (root.value && !root.value.contains(event.target as Node)) close()
}

function bindOutsideClose() {
  document.addEventListener('mousedown', handleDocumentPointerDown)
}

function close() {
  if (!open.value) return
  open.value = false
  document.removeEventListener('mousedown', handleDocumentPointerDown)
}

function toggle() {
  if (open.value) {
    close()
    return
  }
  panelYear.value = selected.value?.year ?? new Date().getFullYear()
  open.value = true
  bindOutsideClose()
}

function pickMonth(month: number) {
  emit('update:modelValue', `${panelYear.value}-${String(month).padStart(2, '0')}`)
  close()
}

function clearValue() {
  emit('update:modelValue', '')
  close()
}

onBeforeUnmount(() => {
  document.removeEventListener('mousedown', handleDocumentPointerDown)
})
</script>

<template>
  <div ref="root" class="month-field">
    <button
      type="button"
      class="month-field__trigger"
      :class="{ 'is-invalid': invalid, 'is-open': open, 'is-empty': !displayText }"
      :title="title"
      :aria-invalid="invalid ? 'true' : undefined"
      :aria-describedby="describedBy"
      :aria-expanded="open"
      aria-haspopup="dialog"
      @click="toggle"
      @keydown.esc.stop="close"
    >
      <span class="month-field__text">{{ displayText || placeholder }}</span>
      <svg class="month-field__icon" viewBox="0 0 16 16" aria-hidden="true">
        <rect x="1.5" y="3" width="13" height="11.5" rx="1.5" fill="none" stroke="currentColor" />
        <path d="M1.5 6.5h13M5 1.5v3M11 1.5v3" fill="none" stroke="currentColor" />
      </svg>
    </button>

    <div v-if="open" class="month-field__panel" role="dialog" aria-label="选择年月" @keydown.esc="close">
      <div class="month-field__head">
        <button type="button" aria-label="上一年" @click="panelYear -= 1">‹</button>
        <strong>{{ panelYear }} 年</strong>
        <button type="button" aria-label="下一年" @click="panelYear += 1">›</button>
      </div>
      <div class="month-field__grid">
        <button
          v-for="(name, index) in MONTHS"
          :key="name"
          type="button"
          :class="{ 'is-active': selected?.year === panelYear && selected?.month === index + 1 }"
          @click="pickMonth(index + 1)"
        >
          {{ name }}
        </button>
      </div>
      <div class="month-field__foot">
        <button type="button" @click="clearValue">清空</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.month-field {
  position: relative;
  min-width: 0;
}

.month-field__trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: #fff;
  color: var(--text-primary);
  font-size: 15px;
  text-align: left;
  cursor: pointer;
}

.month-field__trigger.is-open {
  border-color: var(--brand-primary, #2f6bff);
}

.month-field__trigger.is-invalid {
  border-color: var(--danger);
}

.month-field__trigger.is-empty .month-field__text {
  color: var(--text-placeholder, #9aa4b8);
}

.month-field__text {
  overflow: hidden;
  white-space: nowrap;
  text-overflow: ellipsis;
}

.month-field__icon {
  flex: none;
  width: 14px;
  height: 14px;
  color: var(--text-secondary);
}

.month-field__panel {
  position: absolute;
  z-index: 30;
  top: calc(100% + 4px);
  left: 0;
  width: 232px;
  padding: 8px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  background: #fff;
  box-shadow: 0 8px 24px rgb(15 23 42 / 12%);
}

.month-field__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 2px 4px 8px;
  color: var(--text-primary);
  font-size: 14px;
}

.month-field__head button {
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-secondary);
  font-size: 16px;
  cursor: pointer;
}

.month-field__head button:hover {
  background: var(--surface-subtle);
}

.month-field__grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 4px;
}

.month-field__grid button {
  height: 30px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--text-primary);
  font-size: 14px;
  cursor: pointer;
}

.month-field__grid button:hover {
  background: var(--surface-subtle);
}

.month-field__grid button.is-active {
  border-color: var(--brand-primary, #2f6bff);
  background: var(--brand-primary, #2f6bff);
  color: #fff;
}

.month-field__foot {
  display: flex;
  justify-content: flex-end;
  padding-top: 6px;
}

.month-field__foot button {
  border: none;
  background: transparent;
  color: var(--text-secondary);
  font-size: 13px;
  cursor: pointer;
}

.month-field__foot button:hover {
  color: var(--brand-primary, #2f6bff);
}
</style>
