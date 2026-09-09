import { describe, expect, it } from 'vitest'

import { isFutureMonth, monthRangePairErrors, monthRangeToApiDates } from './month-range'

describe('monthRangePairErrors', () => {
  it('allows both months to be empty or both to be filled', () => {
    expect(monthRangePairErrors(undefined, undefined)).toEqual({})
    expect(monthRangePairErrors('2024-01', '2024-02')).toEqual({})
  })

  it('requires the missing month when only one is filled', () => {
    expect(monthRangePairErrors('2024-01', undefined)).toEqual({
      timeRangeEnd: '开始月份和结束月份必须同时填写',
    })
    expect(monthRangePairErrors(undefined, '2024-02')).toEqual({
      timeRangeStart: '开始月份和结束月份必须同时填写',
    })
  })
})

describe('monthRangeToApiDates', () => {
  it('converts a start month to its first day', () => {
    expect(monthRangeToApiDates('2024-03', undefined)).toEqual({ start: '2024-03-01' })
  })

  it('converts an end month to its last day', () => {
    expect(monthRangeToApiDates(undefined, '2024-05')).toEqual({ end: '2024-05-31' })
  })

  it('handles leap years and a complete range', () => {
    expect(monthRangeToApiDates('2024-01', '2024-02')).toEqual({
      start: '2024-01-01',
      end: '2024-02-29',
    })
  })

  it('omits empty or invalid values', () => {
    expect(monthRangeToApiDates(undefined, undefined)).toEqual({})
    expect(monthRangeToApiDates('2024-13', 'invalid')).toEqual({})
  })
})

describe('isFutureMonth', () => {
  const now = new Date(2026, 7, 25)

  it('rejects future months', () => {
    expect(isFutureMonth('2026-09', now)).toBe(true)
    expect(isFutureMonth('2027-01', now)).toBe(true)
  })

  it('allows current, past, and malformed months', () => {
    expect(isFutureMonth('2026-08', now)).toBe(false)
    expect(isFutureMonth('2025-12', now)).toBe(false)
    expect(isFutureMonth('invalid', now)).toBe(false)
  })
})
