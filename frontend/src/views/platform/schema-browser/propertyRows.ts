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
  // fixed_string 长度以字符串承载：避免 number 输入把非法字符静默转默认值、
  // 超长数字转科学计数法（FUNC-00426/00427）。提交前用 validateFixedLength 校验。
  length: string
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

/** 输入框字符数上限（FUNC-00426：65 位截断） */
export const FIXED_STRING_MAX_INPUT_CHARS = 64
/** Nebula FIXED_STRING 有效长度范围（FUNC-00421/00429） */
export const FIXED_STRING_MIN = 1
export const FIXED_STRING_MAX = 1024

/** 输入即净化：只留数字、最多 64 字符 */
export function sanitizeLengthInput(raw: string): string {
  return raw.replace(/\D/g, '').slice(0, FIXED_STRING_MAX_INPUT_CHARS)
}

/** 返回校验错误文案；合法返回 null */
export function validateFixedLength(raw: string): string | null {
  if (!raw || !/^\d+$/.test(raw)) {
    return 'fixed_string 长度必须是纯数字'
  }
  const value = Number(raw)
  if (!Number.isFinite(value) || value < FIXED_STRING_MIN || value > FIXED_STRING_MAX) {
    return `fixed_string 长度必须在 ${FIXED_STRING_MIN}～${FIXED_STRING_MAX} 之间`
  }
  return null
}

export const ENTITY_REQUIRED_PROPERTY_NAMES = ['id', 'name', 'create_time', 'update_time', 'source_table']
export const RELATION_REQUIRED_PROPERTY_NAMES = ['create_time', 'update_time', 'source_table']

export function buildRequiredPropertyRows(kind: 'entity' | 'relation'): PropertyRow[] {
  const names = kind === 'relation' ? RELATION_REQUIRED_PROPERTY_NAMES : ENTITY_REQUIRED_PROPERTY_NAMES
  return names.map((name) => ({
    name,
    dataType: 'string' as const,
    length: '64',
    required: true,
    locked: true,
  }))
}

export function emptyPropertyRow(): PropertyRow {
  return { name: '', dataType: 'string', length: '64', required: false }
}
