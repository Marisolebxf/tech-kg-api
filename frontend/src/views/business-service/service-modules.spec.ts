import { describe, expect, it } from 'vitest'

import { serviceModules } from './service-modules'

describe('serviceModules', () => {
  it.each([
    ['expert-direct', ['taskName', 'input', 'total', 'items', 'graph', 'source', 'provenance', 'apiResultExample']],
    ['node-indirect', ['structuredResult', 'provenance', 'rules']],
    ['expert-alumni', ['code', 'success', 'data', 'msg']],
    ['paper-cooperation', ['structuredResult', 'provenance', 'rules']],
    ['two-point-achievement', ['code', 'success', 'data', 'msg']],
    ['enterprise-relation', ['code', 'success', 'data', 'msg']],
    ['industry-chain-event', ['code', 'success', 'data', 'msg']],
    ['industry-chain-panorama', ['taskName', 'input', 'summary', 'layers', 'graph', 'source', 'provenance', 'apiResultExample']],
  ])('shows the actual response fields for %s', (key, expectedFields) => {
    const module = serviceModules.find((item) => item.key === key)
    expect(module?.responseFields.map((field) => field.name)).toEqual(expectedFields)
  })

  it.each([
    ['industry-chain-event', ['chain_node_id', 'top_n', 'event_type', 'time_range_start', 'time_range_end', 'max_orgs']],
    ['industry-chain-panorama', ['industry', 'anchorId', 'depth', 'relationTypes', 'topK']],
  ])('keeps the visible request fields aligned for %s', (key, expectedFields) => {
    const module = serviceModules.find((item) => item.key === key)
    expect(module?.requestFields.map((field) => field.name)).toEqual(expectedFields)
  })

  it('limits the cooperation result count input to 64 characters', () => {
    const module = serviceModules.find((item) => item.key === 'two-point-achievement')
    const field = module?.requestFields.find((item) => item.name === 'limitPerType')

    expect(field?.maxLength).toBe(64)
  })

  it('limits the alumni result count input to 64 characters', () => {
    const module = serviceModules.find((item) => item.key === 'expert-alumni')
    const field = module?.requestFields.find((item) => item.name === 'limit')

    expect(field?.maxLength).toBe(64)
  })

  it('uses month calendars for paper cooperation start and end times', () => {
    const module = serviceModules.find((item) => item.key === 'paper-cooperation')
    const startTime = module?.requestFields.find((item) => item.name === 'startTime')
    const endTime = module?.requestFields.find((item) => item.name === 'endTime')

    expect(startTime?.type).toBe('month')
    expect(endTime?.type).toBe('month')
  })
})
