import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import SourceBindingRow from '../sourceBindingRow.vue'

vi.mock('../../../../api/mysqlDatasource', () => ({
  listMysqlDatabases: vi.fn(async () => []),
  listMysqlTables: vi.fn(async () => []),
  listMysqlTableColumns: vi.fn(async () => []),
}))
vi.mock('../../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))
const SelectStub = defineComponent({
  props: ['modelValue', 'allowClear'], emits: ['change'], template: '<div><slot /></div>',
})

describe('source binding dropdown clearing', () => {
  it.each([0, 1, 2])('clears downstream fields with parent selection %s', async (index) => {
    const row = { datasourceId: 'ds', databaseName: 'db', tableName: 'papers', pkColumn: 'paper_id', timeColumn: 'modified_at' }
    const view = mount(SourceBindingRow, {
      props: { modelValue: row, datasources: [], removable: false },
      global: { stubs: { 'a-select': SelectStub, 'a-option': true } },
    })
    await flushPromises()
    const selects = view.findAllComponents(SelectStub)
    expect(selects.every(select => select.props('allowClear') !== undefined)).toBe(true)
    selects[index]!.vm.$emit('change', undefined)
    await flushPromises()
    expect(view.emitted('update:modelValue')?.at(-1)?.[0]).toEqual({
      datasourceId: index === 0 ? '' : 'ds',
      databaseName: index <= 1 ? '' : 'db',
      tableName: '', pkColumn: '', timeColumn: '',
    })
    view.unmount()
  })
})
