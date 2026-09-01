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

export function limitPerTypeError(value: string): string | null {
  return integerRangeError(value, 1, 50)
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

    payload[field.name] =
      field.type === 'boolean'
        ? value === 'true'
        : field.type === 'number'
          ? Number(value)
          : value
  }

  return payload
}
