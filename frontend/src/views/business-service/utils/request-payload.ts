import type { ServiceField } from '../service-modules'

export function integerRangeError(value: string, min: number, max: number): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  const message = `请输入 ${min}-${max} 之间的整数`
  if (!/^\d+$/.test(trimmed)) return message

  const limit = Number(trimmed)
  if (limit < min || limit > max) return message
  return null
}

export function numericInputRangeError(value: string, min: number, max: number): string | null {
  const trimmed = value.trim()
  if (!trimmed) return null
  if (!/^\d+$/.test(trimmed)) return '只能输入数字'
  return integerRangeError(trimmed, min, max)
}

export function limitPerTypeError(value: string): string | null {
  return numericInputRangeError(value, 1, 50)
}

export function buildRequestPayload(
  fields: ServiceField[],
  values: Record<string, string>,
): Record<string, unknown> {
  const payload: Record<string, unknown> = {}

  for (const field of fields) {
    const value = values[field.name]
    if (value === undefined || value === '') continue

    if (field.type === 'multi-select') {
      const selected = value
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean)
      if (selected.length > 0) payload[field.name] = selected
      continue
    }

    if (field.type === 'boolean') {
      payload[field.name] = value === 'true'
    } else if (field.type === 'number') {
      payload[field.name] = Number(value)
    } else {
      payload[field.name] = value
    }
  }

  return payload
}
