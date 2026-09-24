import { mount } from '@vue/test-utils'
import { Popover } from '@arco-design/web-vue'
import { describe, expect, it } from 'vitest'

import type { SchemaDefinition, SchemaProperty } from '../../../api/schemaManagement'
import SchemaPropertyCell from './SchemaPropertyCell.vue'

const property = (name: string, dataType: string): SchemaProperty => ({
  name,
  dataType,
  required: false,
  rule: '',
  category: 'core',
  locked: false,
})

function mountCell(properties: SchemaProperty[]) {
  return mount(SchemaPropertyCell, {
    props: {
      schema: { properties } as SchemaDefinition,
    },
    global: {
      stubs: {
        Popover: {
          props: ['trigger', 'position', 'contentClass'],
          template: '<div class="popover-stub"><slot /><div class="popover-content"><slot name="content" /></div></div>',
        },
      },
    },
  })
}

describe('Schema 属性单元格', () => {
  it('前四个属性以方框展示，其余属性使用 +N 浮层', async () => {
    const wrapper = mountCell([
      property('first', 'string'),
      property('second', 'int'),
      property('third', 'boolean'),
      property('fourth', 'datetime'),
      property('fifth', 'float'),
      property('sixth', 'string'),
    ])

    expect(wrapper.findAll('.schema-properties__chip')).toHaveLength(4)
    expect(wrapper.findAll('.schema-properties__chip').map(item => item.attributes('title')))
      .toEqual(['first: string', 'second: int', 'third: boolean', 'fourth: datetime'])

    const more = wrapper.get('.schema-properties__more')
    expect(more.text()).toBe('+2')
    expect(more.attributes('aria-label')).toBe('查看其余 2 个属性')

    const popover = wrapper.findComponent(Popover)
    expect(popover.props('trigger')).toEqual(['hover', 'click'])
    expect(popover.props('position')).toBe('bl')
    expect(wrapper.findAll('.schema-property-popover__item').map(item => item.attributes('title')))
      .toEqual(['fifth: float', 'sixth: string'])

    await more.trigger('click')
    expect(wrapper.find('.schema-prop-detail-row').exists()).toBe(false)
  })

  it('无属性时显示空状态', () => {
    const wrapper = mountCell([])
    expect(wrapper.get('.schema-properties__empty').text()).toBe('—')
  })
})
