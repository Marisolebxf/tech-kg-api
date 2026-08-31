import { describe, expect, it } from 'vitest'

import type { ServiceField } from '../service-modules'
import { buildRequestPayload } from './request-payload'

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
