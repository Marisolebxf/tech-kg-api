/**
 * 搜索框超长输入的统一防护。
 *
 * 上限与后端 schema-management 的 keyword 查询参数
 * `Query(max_length=128)` 对齐（backend/biz/handler/schema_management.py）。
 */
export const SEARCH_KEYWORD_MAX_LENGTH = 128

/** 关键字超长时的统一提示文案。 */
export function searchKeywordTooLongMessage(max = SEARCH_KEYWORD_MAX_LENGTH): string {
  return `搜索关键字过长，请不超过 ${max} 个字符`
}

/** 校验搜索关键字：超长返回提示文案，否则返回 null。 */
export function searchKeywordError(value: string, max = SEARCH_KEYWORD_MAX_LENGTH): string | null {
  if (value.length > max) return searchKeywordTooLongMessage(max)
  return null
}

/** 安全截断搜索关键字（用于路由参数等程序化赋值场景）。 */
export function clampSearchKeyword(value: string, max = SEARCH_KEYWORD_MAX_LENGTH): string {
  return value.length > max ? value.slice(0, max) : value
}
