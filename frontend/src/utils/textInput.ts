/**
 * 自由文本输入的统一校验：超长检测 + 异常字符检测（+ 可选字符集）。
 * 上限与后端 Pydantic 约束对齐（biz/schemas/workflow_operations.py、schema_management.py）。
 */

/**
 * 异常字符：控制字符（保留 Tab/换行/回车给正常输入）
 * 加零宽空格、双向排版控制等不可见字符（防视觉欺骗 / 破坏下游 SQL 与 nGQL）。
 */
const ABNORMAL_CHARS = /[\u0000-\u0008\u000B\u000C\u000E-\u001F\u007F\u200B-\u200F\u2028\u2029\u202A-\u202E\u2060\uFEFF]/

export function hasAbnormalChars(value: string): boolean {
  return ABNORMAL_CHARS.test(value)
}

export interface TextRule {
  /** 最大字符数（与后端 max_length 对齐） */
  max: number
  /** 可选字符集白名单（对 trim 后的值校验；空值跳过） */
  pattern?: RegExp
  /** 违反字符集时的提示 */
  patternHint?: string
}

/** 校验单项文本：返回错误文案，合法返回 null。value 为空时只跳过字符集检查（必填由表单管）。 */
export function validateText(label: string, value: string, rule: TextRule): string | null {
  if (value.length > rule.max) {
    return `${label}过长：已输入 ${value.length} 字符，上限 ${rule.max}`
  }
  if (hasAbnormalChars(value)) {
    return `${label}包含控制字符或不可见字符（如零宽空格），请删除后重试`
  }
  if (rule.pattern && value.trim() && !rule.pattern.test(value.trim())) {
    return rule.patternHint || `${label}含不支持的字符`
  }
  return null
}

// ---- 预设规则（命名与后端字段对应）----

/** 任务/作业名称：JobCreateRequest.name max_length=128 */
export const JOB_NAME_RULE: TextRule = { max: 128 }

/** MySQL 库名：MySQL 标识符上限 64，仅字母/数字/下划线 */
export const MYSQL_DB_RULE: TextRule = {
  max: 64,
  pattern: /^[A-Za-z0-9_]+$/,
  patternHint: '数据库只能是字母、数字、下划线（如 gkx_element）',
}

/** 增量游标 since：日期或日期时间 */
export const SINCE_RULE: TextRule = {
  max: 32,
  pattern: /^\d{4}-\d{2}-\d{2}([ T]\d{2}:\d{2}(:\d{2})?)?$/,
  patternHint: '增量游标需为时间，如 2026-08-01 或 2026-08-01 00:00:00',
}

/** 实体名：PascalCase（schema_key 由其派生，name max_length=128） */
export const SCHEMA_ENTITY_NAME_RULE: TextRule = {
  max: 128,
  pattern: /^[A-Z][A-Za-z0-9]*$/,
  patternHint: '实体名需为 PascalCase 英文（首字母大写，如 Gadget）',
}

/** 关系英文名：UPPER_SNAKE_CASE（nGQL EDGE 类型名） */
export const SCHEMA_RELATION_NAME_RULE: TextRule = {
  max: 128,
  pattern: /^[A-Z][A-Z0-9_]*$/,
  patternHint: '关系英文名需为大写下划线（如 USES_TECHNOLOGY）',
}

/** Schema 中文名：label max_length=128 */
export const SCHEMA_LABEL_RULE: TextRule = { max: 128 }

/** Schema 说明：description max_length=4000 */
export const SCHEMA_DESC_RULE: TextRule = { max: 4000 }

/** 属性名：nGQL 属性列标识符，SchemaPropertyInput.name max_length=128 */
export const PROP_NAME_RULE: TextRule = {
  max: 128,
  pattern: /^[A-Za-z_][A-Za-z0-9_]*$/,
  patternHint: '属性名只能是字母、数字、下划线，且以字母或下划线开头',
}
