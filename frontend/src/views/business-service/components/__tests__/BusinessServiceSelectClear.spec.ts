import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import ElSelect from 'element-plus/es/components/select/index'
import BusinessServiceAlgorithmPanel from '../BusinessServiceAlgorithmPanel.vue'
import { getServiceModule } from '../../service-modules'
import { analyzeExpertIndirectRelation } from '../../../../api/expertIndirectRelation'

vi.mock('element-plus/es/components/select/style/css', () => ({}))
vi.mock('../../../../api/expertIndirectRelation', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../../api/expertIndirectRelation')>()),
  analyzeExpertIndirectRelation: vi.fn(),
}))

vi.mock('../../../../composables/use-space-permissions', () => ({
  useSpacePermissions: () => ({ canWrite: ref(true), spaces: { contextKey: 'test', current: 'dev' } }),
}))
vi.mock('../../../../composables/use-toast', () => ({ useToast: () => ({ showToast: vi.fn() }) }))

const cases = [
  ['expert-direct', 'dataSource', 'all'],
  ['node-indirect', 'relation_types', '学术关联'],
  ['enterprise-relation', 'key_tech_enterprise_only', 'false'],
  ['industry-chain-panorama', 'depth', '3'],
] as const
let view: VueWrapper | undefined

afterEach(() => { view?.unmount(); view = undefined })

function mountPanel(moduleKey: string) {
  const errors = vi.fn()
  view = mount(BusinessServiceAlgorithmPanel, {
    props: { moduleInfo: getServiceModule(moduleKey), responseJson: '{}' },
    attachTo: document.body,
    global: { stubs: { KgGraphCanvas: true, ListPagination: true }, config: { errorHandler: errors } },
  })
  return { view, errors }
}

function fieldSelect(wrapper: VueWrapper, fieldName: string) {
  return wrapper.get(`[data-field="${fieldName}"]`).getComponent(ElSelect)
}

function expectPlaceholder(wrapper: VueWrapper, fieldName: string) {
  const select = fieldSelect(wrapper, fieldName)
  expect(select.props('modelValue')).toBeUndefined()
  const placeholder = select.get('.el-select__placeholder')
  expect(placeholder.text()).toBe('请选择')
  expect(placeholder.classes()).toContain('is-transparent')
  expect(select.find('.el-select__clear').exists()).toBe(false)
}

describe('business service single-select clear', () => {
  it.each(cases)('%s / %s clears through the real × control and can be selected again', async (moduleKey, name, choice) => {
    const { view, errors } = mountPanel(moduleKey)
    await flushPromises()
    fieldSelect(view, name).vm.$emit('update:modelValue', choice)
    await flushPromises()
    const select = fieldSelect(view, name)
    expect(select.props('modelValue')).toBe(choice)
    await select.trigger('mouseenter')
    await select.get('.el-select__clear').trigger('click')
    await flushPromises()
    expect(errors).not.toHaveBeenCalled()
    expectPlaceholder(view, name)
    fieldSelect(view, name).vm.$emit('update:modelValue', choice)
    await flushPromises()
    expect(fieldSelect(view, name).props('modelValue')).toBe(choice)
    expect(errors).not.toHaveBeenCalled()
  })

  it.each(cases)('%s / %s also tolerates the library default undefined and null clear values', async (moduleKey, name, choice) => {
    const { view, errors } = mountPanel(moduleKey)
    await flushPromises()
    for (const empty of [undefined, null, '']) {
      fieldSelect(view, name).vm.$emit('update:modelValue', choice)
      await flushPromises()
      fieldSelect(view, name).vm.$emit('update:modelValue', empty)
      await flushPromises()
      expect(errors).not.toHaveBeenCalled()
      expectPlaceholder(view, name)
    }
  })

  it('keeps a cleared required relation type empty and blocks the query until it is selected again', async () => {
    const { view, errors } = mountPanel('node-indirect')
    await flushPromises()
    await view.get('[data-field="core_node_id"] input').setValue('person_123')
    fieldSelect(view, 'relation_types').vm.$emit('update:modelValue', '学术关联')
    await flushPromises()
    const select = fieldSelect(view, 'relation_types')
    await select.trigger('mouseenter')
    await select.get('.el-select__clear').trigger('click')
    await flushPromises()
    await view.get('.service-console__actions .kg-button').trigger('click')
    await flushPromises()
    expect(analyzeExpertIndirectRelation).not.toHaveBeenCalled()
    expect(view.get('[data-field="relation_types"] .service-console__field-error').text()).toBe('请选择间接关系类型')
    expectPlaceholder(view, 'relation_types')
    expect(errors).not.toHaveBeenCalled()
  })

})
