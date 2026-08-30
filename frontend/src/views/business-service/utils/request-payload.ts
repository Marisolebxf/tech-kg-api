import type { ServiceField } from '../service-modules'

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

    payload[field.name] = field.type === 'number' ? Number(value) : value
  }

  return payload
}
