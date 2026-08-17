import { ref, unref, watch, type Ref } from 'vue'

export type ValidationRule = {
  required?: boolean | string
  pattern?: RegExp | { regex: RegExp; message: string }
  min?: number | { value: number; message: string }
  max?: number | { value: number; message: string }
  validator?: (value: unknown, allValues: Record<string, unknown>) => string | null
}

export type Rules = Record<string, ValidationRule>

function isEmpty(value: unknown): boolean {
  if (value === null || value === undefined) return true
  if (typeof value === 'string') return value.trim() === ''
  if (Array.isArray(value)) return value.length === 0
  return false
}

function resolveMinMaxMessage(rule: ValidationRule, kind: 'min' | 'max'): string {
  const field = rule[kind]
  if (field === undefined) return kind === 'min' ? '值过小' : '值过大'
  if (typeof field === 'number') return kind === 'min' ? `不能小于 ${field}` : `不能大于 ${field}`
  if (typeof field === 'object' && 'value' in field) return field.message
  return kind === 'min' ? '值过小' : '值过大'
}

function runRule(rule: ValidationRule, value: unknown, allValues: Record<string, unknown>): string | null {
  if (rule.required) {
    if (isEmpty(value)) {
      return typeof rule.required === 'string' ? rule.required : '此项必填'
    }
  }
  if (rule.pattern) {
    const regex = rule.pattern instanceof RegExp ? rule.pattern : rule.pattern.regex
    const message = rule.pattern instanceof RegExp ? '格式不正确' : rule.pattern.message
    if (!isEmpty(value) && typeof value === 'string' && !regex.test(value)) {
      return message
    }
  }
  if (rule.min !== undefined) {
    const limit = typeof rule.min === 'number' ? rule.min : rule.min.value
    const message = resolveMinMaxMessage(rule, 'min')
    const num = typeof value === 'string' ? Number(value) : value
    if (!isEmpty(value) && typeof num === 'number' && !Number.isNaN(num) && num < limit) {
      return message
    }
    if (!isEmpty(value) && typeof value === 'string' && value.length < limit) {
      return typeof rule.min === 'number' ? `至少 ${limit} 个字符` : rule.min.message ?? `至少 ${limit} 个字符`
    }
  }
  if (rule.max !== undefined) {
    const limit = typeof rule.max === 'number' ? rule.max : rule.max.value
    const message = resolveMinMaxMessage(rule, 'max')
    const num = typeof value === 'string' ? Number(value) : value
    if (!isEmpty(value) && typeof num === 'number' && !Number.isNaN(num) && num > limit) {
      return message
    }
    if (!isEmpty(value) && typeof value === 'string' && value.length > limit) {
      return typeof rule.max === 'number' ? `不能超过 ${limit} 个字符` : rule.max.message ?? `不能超过 ${limit} 个字符`
    }
  }
  if (rule.validator) {
    const result = rule.validator(value, allValues)
    if (result) return result
  }
  return null
}

export function useFormValidation<T extends Record<string, unknown>>(
  form: Ref<T>,
  rules: Rules | Ref<Rules>,
) {
  const errors = ref<Record<string, string>>({})
  const touched = ref<Record<string, boolean>>({})

  function getRules(): Rules {
    return unref(rules)
  }

  function validateField(key: string): boolean {
    const rule = getRules()[key]
    if (!rule) {
      delete errors.value[key]
      return true
    }
    const message = runRule(rule, form.value[key], form.value)
    if (message) {
      errors.value = { ...errors.value, [key]: message }
      return false
    }
    const next = { ...errors.value }
    delete next[key]
    errors.value = next
    return true
  }

  function touch(key: string) {
    if (touched.value[key]) return
    touched.value = { ...touched.value, [key]: true }
    validateField(key)
  }

  function validate(): boolean {
    const allRules = getRules()
    const nextErrors: Record<string, string> = {}
    const nextTouched: Record<string, boolean> = { ...touched.value }
    for (const key of Object.keys(allRules)) {
      nextTouched[key] = true
      const message = runRule(allRules[key], form.value[key], form.value)
      if (message) nextErrors[key] = message
    }
    errors.value = nextErrors
    touched.value = nextTouched
    return Object.keys(nextErrors).length === 0
  }

  function clearErrors() {
    errors.value = {}
    touched.value = {}
  }

  function clearField(key: string) {
    const nextErrors = { ...errors.value }
    const nextTouched = { ...touched.value }
    delete nextErrors[key]
    delete nextTouched[key]
    errors.value = nextErrors
    touched.value = nextTouched
  }

  function visibleError(key: string): string | undefined {
    if (!touched.value[key]) return undefined
    return errors.value[key]
  }

  watch(
    form,
    () => {
      const touchedKeys = Object.keys(touched.value).filter((k) => touched.value[k])
      if (touchedKeys.length === 0) return
      const nextErrors = { ...errors.value }
      for (const key of touchedKeys) {
        const rule = getRules()[key]
        if (!rule) {
          delete nextErrors[key]
          continue
        }
        const message = runRule(rule, form.value[key], form.value)
        if (message) {
          nextErrors[key] = message
        } else {
          delete nextErrors[key]
        }
      }
      errors.value = nextErrors
    },
    { deep: true },
  )

  return { errors, touched, visibleError, validate, validateField, touch, clearErrors, clearField }
}
