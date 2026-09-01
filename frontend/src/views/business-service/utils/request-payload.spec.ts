import { describe, expect, it } from 'vitest'

import type { ServiceField } from '../service-modules'
import {
  buildRequestPayload,
  integerRangeError,
  limitPerTypeError,
  numericInputRangeError,
} from './request-payload'

const fields: ServiceField[] = [
  { name: 'achievementTypes', type: 'multi-select', description: '' },
  { name: 'educationStage', type: 'string', description: '' },
  { name: 'limitPerType', type: 'number', description: '' },
  { name: 'includeIndirect', type: 'boolean', description: '' },
  { name: 'timeRangeStart', type: 'month', description: '' },
]

describe('buildRequestPayload', () => {
  it('serializes multi-select values as trimmed JSON arrays', () => {
    expect(
      buildRequestPayload(fields, {
        achievementTypes: 'paper, patent,project',
        educationStage: '本科,硕士',
        limitPerType: '20',
        includeIndirect: 'true',
        timeRangeStart: '',
      }),
    ).toEqual({
      achievementTypes: ['paper', 'patent', 'project'],
      educationStage: '本科,硕士',
      limitPerType: 20,
      includeIndirect: true,
    })
  })

  it('omits empty multi-select values instead of sending an empty array', () => {
    expect(
      buildRequestPayload(fields, {
        achievementTypes: '',
        educationStage: '',
        limitPerType: '',
        includeIndirect: '',
        timeRangeStart: '',
      }),
    ).toEqual({})
  })

  it('drops empty items produced by repeated commas', () => {
    expect(
      buildRequestPayload(fields, {
        achievementTypes: 'paper, ,project,',
        educationStage: '',
        limitPerType: '',
        includeIndirect: 'false',
        timeRangeStart: '',
      }),
    ).toEqual({
      achievementTypes: ['paper', 'project'],
      includeIndirect: false,
    })
  })
})

describe('limitPerTypeError', () => {
  it.each(['', '1', '20', '50'])('accepts %j', (value) => {
    expect(limitPerTypeError(value)).toBeNull()
  })

  it.each(['0', '51'])('rejects out-of-range value %j', (value) => {
    expect(limitPerTypeError(value)).toBe('请输入 1-50 之间的整数')
  })

  it.each(['-1', '1.5', 'abc', 'true', '1e2', '!'])('rejects non-digit value %j', (value) => {
    expect(limitPerTypeError(value)).toBe('只能输入数字')
  })
})

describe('numericInputRangeError', () => {
  it.each(['', '1', '20', '50'])('accepts alumni limit %j', (value) => {
    expect(numericInputRangeError(value, 1, 50)).toBeNull()
  })

  it.each(['0', '51', '9'.repeat(65)])('rejects out-of-range alumni limit %j', (value) => {
    expect(numericInputRangeError(value, 1, 50)).toBe('请输入 1-50 之间的整数')
  })

  it.each(['-1', '1.5', 'abc', 'true', '1e2', '!'])('rejects non-digit alumni limit %j', (value) => {
    expect(numericInputRangeError(value, 1, 50)).toBe('只能输入数字')
  })
})

describe('integerRangeError', () => {
  it.each(['', '1', '10', '100'])('accepts direct-relation limit %j', (value) => {
    expect(integerRangeError(value, 1, 100)).toBeNull()
  })

  it.each(['0', '101', '-1', '2.5', 'abc', 'true'])(
    'rejects direct-relation limit %j',
    (value) => {
      expect(integerRangeError(value, 1, 100)).toBe('请输入 1-100 之间的整数')
    },
  )

  it.each(['', '1', '20', '50'])('accepts max_orgs %j', (value) => {
    expect(integerRangeError(value, 1, 50)).toBeNull()
  })

  it.each(['0', '51', '-1', '1.5', 'abc', 'true'])('rejects max_orgs %j', (value) => {
    expect(integerRangeError(value, 1, 50)).toBe('请输入 1-50 之间的整数')
  })

  it('rejects a 65-digit alumni limit without throwing', () => {
    expect(integerRangeError('9'.repeat(65), 1, 50)).toBe('请输入 1-50 之间的整数')
  })
})
