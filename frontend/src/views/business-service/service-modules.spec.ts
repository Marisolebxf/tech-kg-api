import { describe, expect, it } from 'vitest'

import { serviceModules } from './service-modules'

describe('serviceModules', () => {
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
})
