export type PropertyDataType =
  | 'string'
  | 'int64'
  | 'double'
  | 'bool'
  | 'date'
  | 'datetime'
  | 'geo'
  | 'fixed_string'

export interface PropertyRow {
  name: string
  dataType: PropertyDataType
  length: number
  required: boolean
  locked?: boolean
}

export const PROPERTY_TYPES: PropertyDataType[] = [
  'string',
  'int64',
  'double',
  'bool',
  'date',
  'datetime',
  'geo',
  'fixed_string',
]

export const ENTITY_REQUIRED_PROPERTY_NAMES = ['id', 'name', 'create_time', 'update_time', 'source_table']
export const RELATION_REQUIRED_PROPERTY_NAMES = ['create_time', 'update_time', 'source_table']

export function buildRequiredPropertyRows(kind: 'entity' | 'relation'): PropertyRow[] {
  const names = kind === 'relation' ? RELATION_REQUIRED_PROPERTY_NAMES : ENTITY_REQUIRED_PROPERTY_NAMES
  return names.map((name) => ({
    name,
    dataType: 'string' as const,
    length: 64,
    required: true,
    locked: true,
  }))
}

export function emptyPropertyRow(): PropertyRow {
  return { name: '', dataType: 'string', length: 64, required: false }
}
