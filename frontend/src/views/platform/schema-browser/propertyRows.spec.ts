import { describe, expect, it } from 'vitest'

import {
  buildRequiredPropertyRows,
  emptyPropertyRow,
  ENTITY_REQUIRED_PROPERTY_NAMES,
  RELATION_REQUIRED_PROPERTY_NAMES,
} from './propertyRows'

describe('buildRequiredPropertyRows', () => {
  it('实体返回 5 个锁定公共属性', () => {
    const rows = buildRequiredPropertyRows('entity')
    expect(rows.map((row) => row.name)).toEqual(ENTITY_REQUIRED_PROPERTY_NAMES)
    expect(rows.map((row) => row.name)).toEqual([
      'id',
      'name',
      'create_time',
      'update_time',
      'source_table',
    ])
    for (const row of rows) {
      expect(row.locked).toBe(true)
      expect(row.required).toBe(true)
      expect(row.dataType).toBe('string')
    }
  })

  it('关系返回 3 个锁定公共属性', () => {
    const rows = buildRequiredPropertyRows('relation')
    expect(rows.map((row) => row.name)).toEqual(RELATION_REQUIRED_PROPERTY_NAMES)
    for (const row of rows) {
      expect(row.locked).toBe(true)
      expect(row.required).toBe(true)
    }
  })

  it('每次调用返回全新对象，互不影响', () => {
    const first = buildRequiredPropertyRows('entity')
    first[0].name = 'changed'
    const second = buildRequiredPropertyRows('entity')
    expect(second[0].name).toBe('id')
  })

  it('emptyPropertyRow 生成非锁定的空行', () => {
    const row = emptyPropertyRow()
    expect(row.locked).toBeUndefined()
    expect(row.required).toBe(false)
    expect(row.name).toBe('')
    expect(row.dataType).toBe('string')
  })
})
