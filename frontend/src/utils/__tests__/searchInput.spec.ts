import { describe, it, expect } from 'vitest'
import {
  SEARCH_KEYWORD_MAX_LENGTH,
  clampSearchKeyword,
  searchKeywordError,
  searchKeywordTooLongMessage,
} from '../searchInput'

// 搜索框超长输入防护：与后端 schema-management keyword Query(max_length=128) 同口径
describe('searchInput', () => {
  it('上限与后端约束对齐（128）', () => {
    expect(SEARCH_KEYWORD_MAX_LENGTH).toBe(128)
  })

  it('合法长度：searchKeywordError 返回 null', () => {
    expect(searchKeywordError('')).toBeNull()
    expect(searchKeywordError('专家')).toBeNull()
    expect(searchKeywordError('a'.repeat(SEARCH_KEYWORD_MAX_LENGTH))).toBeNull()
  })

  it('超长：返回可识别的参数过长提示', () => {
    const message = searchKeywordError('a'.repeat(SEARCH_KEYWORD_MAX_LENGTH + 1))
    expect(message).toBe(searchKeywordTooLongMessage())
    expect(message).toContain('搜索关键字过长')
    expect(message).toContain(String(SEARCH_KEYWORD_MAX_LENGTH))
  })

  it('clampSearchKeyword 安全截断到上限', () => {
    const long = '张'.repeat(SEARCH_KEYWORD_MAX_LENGTH + 100)
    expect(clampSearchKeyword(long)).toHaveLength(SEARCH_KEYWORD_MAX_LENGTH)
    expect(clampSearchKeyword(long)).toBe(long.slice(0, SEARCH_KEYWORD_MAX_LENGTH))
  })

  it('clampSearchKeyword 不改动合法值', () => {
    expect(clampSearchKeyword('')).toBe('')
    expect(clampSearchKeyword('实体名称')).toBe('实体名称')
    expect(clampSearchKeyword('a'.repeat(SEARCH_KEYWORD_MAX_LENGTH))).toHaveLength(SEARCH_KEYWORD_MAX_LENGTH)
  })

  it('自定义上限生效', () => {
    expect(searchKeywordError('abc', 2)).toContain('不超过 2 个字符')
    expect(clampSearchKeyword('abc', 2)).toBe('ab')
  })
})
