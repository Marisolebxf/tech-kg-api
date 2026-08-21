import { describe, expect, it } from 'vitest'

import { monthRangeToApiDates } from './month-range'

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
