import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import SourceBindingRowVue from '../sourceBindingRow.vue'
const { toast } = vi.hoisted(() => ({ toast: vi.fn() }))
vi.mock('../../../../composables/use-toast', () => ({ useToast: () => ({ showToast: toast }) }))
import SourceBindings from '../sourceBindings.vue'
import { emptySourceBindingRow } from '../sourceBindingRows'
vi.mock('../../../../api/mysqlDatasource', () => ({ listMysqlDatasources: vi.fn().mockResolvedValue([]) }))
const mountBindings = (rows = [emptySourceBindingRow()]) => mount(SourceBindings, {
  props: { modelValue: rows }, global: { stubs: { SourceBindingRowVue: true } },
})
describe('source binding append validation', () => {
  it('blocks incomplete rows and clears the prompt once required fields are complete', async () => {
    const w = mountBindings()
    await w.get('button').trigger('click')
    expect(w.emitted('update:modelValue')).toBeUndefined()
    expect(w.get('[role="alert"]').text()).toContain('必填信息')
    await w.setProps({ modelValue: [{ ...emptySourceBindingRow(), datasourceId: 'ds', databaseName: 'db', tableName: 'table' }] })
    expect(w.find('[role="alert"]').exists()).toBe(false)
    await w.get('button').trigger('click')
    const rows = w.emitted('update:modelValue')![0]![0] as ReturnType<typeof emptySourceBindingRow>[]
    expect(rows).toHaveLength(2)
    await w.setProps({ modelValue: rows })
    await w.get('button').trigger('click')
    expect(w.emitted('update:modelValue')).toHaveLength(1)
    expect(w.find('[role="alert"]').exists()).toBe(true)
    w.unmount()
  })
  it('allows the first row when no binding exists', async () => {
    const w = mountBindings([])
    await w.get('button').trigger('click')
    expect(w.emitted('update:modelValue')![0]![0]).toEqual([emptySourceBindingRow()])
    w.unmount()
  })
})

it('coalesces identical errors across rows but permits a later retry message', () => {
  toast.mockClear()
  const w = mountBindings([emptySourceBindingRow(), emptySourceBindingRow()])
  const clock = vi.spyOn(Date, 'now').mockReturnValue(10000)
  try {
    const rows = w.findAllComponents(SourceBindingRowVue)
    rows[0]!.props('reportLoadError')!('加载失败')
    rows[1]!.props('reportLoadError')!('加载失败')
    expect(toast).toHaveBeenCalledTimes(1)
    clock.mockReturnValue(13000)
    rows[1]!.props('reportLoadError')!('加载失败')
    expect(toast).toHaveBeenCalledTimes(2)
  } finally { clock.mockRestore(); w.unmount() }
})