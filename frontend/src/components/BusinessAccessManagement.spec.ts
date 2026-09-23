import { flushPromises, mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useAuthStore } from '../stores/auth'
import type { AuthProfile } from '../api/auth'
import BusinessAccessManagement from './BusinessAccessManagement.vue'
import { getBusinessAccessState, requestBusinessSpace, retryBusinessSpace } from '../api/businessAccess'

vi.mock('../api/businessAccess', () => ({
  getBusinessAccessState: vi.fn(), saveBusiness: vi.fn(), saveBusinessMember: vi.fn(), saveBusinessSpace: vi.fn(),
  requestBusinessSpace: vi.fn(), decideBusinessSpace: vi.fn(), retryBusinessSpace: vi.fn(),
}))
vi.mock('../stores/graphSpace', () => ({ useGraphSpaceStore: () => ({ ensureLoaded: vi.fn() }) }))
const state = { businesses: [{ clientId: 'a', name: '业务 A', enabled: true }], members: [], spaces: [], requests: [], currentBusinessId: 'a' }
beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  vi.mocked(getBusinessAccessState).mockResolvedValue(structuredClone(state))
})

describe('业务权限配置管理', () => {
  it('开发维护只能查看空间并提交申请，不能修改业务成员归属', async () => {
    useAuthStore().profile = { businessRbacEnabled: true, canDevelop: true, isAdmin: false } as AuthProfile
    const wrapper = mount(BusinessAccessManagement)
    await flushPromises()
    expect(wrapper.text()).not.toContain('保存账号绑定')
    expect(wrapper.text()).not.toContain('保存空间归属')
    const form = wrapper.find('form')
    await form.find('input').setValue('business_a_space')
    await form.trigger('submit')
    await flushPromises()
    expect(requestBusinessSpace).toHaveBeenCalledWith({ spaceName: 'business_a_space', reason: '' })
  })
  it('管理员可以管理归属并重试创建失败的申请', async () => {
    useAuthStore().profile = { businessRbacEnabled: true, isAdmin: true } as AuthProfile
    vi.mocked(getBusinessAccessState).mockResolvedValue({ ...state, requests: [{ id: 'req-1', clientId: 'a', spaceName: 's', status: 'failed', reason: '', requestedBy: 'u', reviewedBy: 'admin', reviewNote: '', lastError: '创建失败', createdAt: '' }] })
    const wrapper = mount(BusinessAccessManagement)
    await flushPromises()
    expect(wrapper.text()).toContain('保存账号绑定')
    expect(wrapper.text()).toContain('保存空间归属')
    await wrapper.findAll('button').find(button => button.text() === '重试创建')!.trigger('click')
    await flushPromises()
    expect(retryBusinessSpace).toHaveBeenCalledWith('req-1')
  })
})

it('未绑定业务的管理员可以为指定业务申请新空间', async () => {
  useAuthStore().profile = { businessRbacEnabled: true, isAdmin: true } as AuthProfile
  vi.mocked(getBusinessAccessState).mockResolvedValue({ ...state, currentBusinessId: '' })
  const wrapper = mount(BusinessAccessManagement)
  await flushPromises()
  const form = wrapper.findAll('form').at(-1)!
  await form.find('select').setValue('a')
  await form.find('input').setValue('new_business_space')
  await form.trigger('submit')
  await flushPromises()
  expect(requestBusinessSpace).toHaveBeenCalledWith({ clientId: 'a', spaceName: 'new_business_space', reason: '' })
})

it('服务端标记超时创建可重试时展示恢复入口', async () => {
  useAuthStore().profile = { businessRbacEnabled: true, isAdmin: true } as AuthProfile
  vi.mocked(getBusinessAccessState).mockResolvedValue({ ...state, requests: [{ id: 'stuck', clientId: 'a', spaceName: 's', status: 'creating', canRetry: true, reason: '', requestedBy: 'u', reviewedBy: 'admin', reviewNote: '', lastError: '', createdAt: '' }] })
  const wrapper = mount(BusinessAccessManagement)
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text() === '重试创建')!.trigger('click')
  await flushPromises()
  expect(retryBusinessSpace).toHaveBeenCalledWith('stuck')
})
