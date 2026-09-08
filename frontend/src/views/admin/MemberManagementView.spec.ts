import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { PlatformMember } from '../../api/corrections'
import MemberManagementView from './MemberManagementView.vue'

const mocks = vi.hoisted(() => ({
  authDisabled: false,
  adminExampleFallback: true,
  listPlatformMembers: vi.fn(),
  setMemberAdmin: vi.fn(),
  getExampleMembers: vi.fn(),
  success: vi.fn(),
  error: vi.fn(),
}))
vi.mock('../../config', () => ({
  get authDisabled() { return mocks.authDisabled },
  get adminExampleFallback() { return mocks.adminExampleFallback },
}))
vi.mock('../../api/corrections', () => ({ listPlatformMembers: mocks.listPlatformMembers, setMemberAdmin: mocks.setMemberAdmin }))
vi.mock('../../api/http', () => ({ getErrorMessage: (error: Error) => error.message }))
vi.mock('../../data/adminGovernanceExamples', () => ({ getExampleMembers: mocks.getExampleMembers }))
vi.mock('../../stores/auth', () => ({ useAuthStore: () => ({ profile: { user: { id: 'current-admin' } } }) }))
vi.mock('@arco-design/web-vue', () => ({ Message: { success: mocks.success, error: mocks.error } }))

const member = (isAdmin = true): PlatformMember => ({
  userId: 'member-1', username: 'member', nickname: '真实成员', email: 'member@example.test',
  isAdmin, lastSeenAt: '2026-09-07T00:00:00',
})
const wrappers: ReturnType<typeof mount>[] = []
const renderMembers = () => {
  const wrapper = mount(MemberManagementView, {
    global: { stubs: { AButton: { template: '<button><slot /></button>' } } },
  })
  wrappers.push(wrapper)
  return wrapper
}

beforeEach(() => {
  mocks.authDisabled = false
  mocks.adminExampleFallback = true
  mocks.listPlatformMembers.mockReset().mockResolvedValue({ items: [member()], total: 1 })
  mocks.setMemberAdmin.mockReset()
  mocks.getExampleMembers.mockReset().mockReturnValue([member()])
  mocks.success.mockReset()
  mocks.error.mockReset()
  vi.spyOn(window, 'confirm').mockReturnValue(true)
})
afterEach(() => {
  wrappers.splice(0).forEach((wrapper) => wrapper.unmount())
  vi.restoreAllMocks()
})

describe('真实成员授权数据', () => {
  it('认证开启时空列表保持为空，即使配置允许示例兜底', async () => {
    mocks.listPlatformMembers.mockResolvedValue({ items: [], total: 0 })
    const wrapper = renderMembers()
    await flushPromises()
    expect(mocks.getExampleMembers).not.toHaveBeenCalled()
    expect(wrapper.findAll('.member-action')).toHaveLength(0)
    expect(wrapper.text()).toContain('暂无成员记录；用户首次登录后会自动出现在这里。')
  })

  it('认证开启时接口失败不制造示例成员或假授权', async () => {
    mocks.listPlatformMembers.mockRejectedValue(new Error('成员服务暂时不可用'))
    const wrapper = renderMembers()
    await flushPromises()
    expect(mocks.getExampleMembers).not.toHaveBeenCalled()
    expect(wrapper.findAll('.member-action')).toHaveLength(0)
    expect(mocks.error).toHaveBeenCalledWith('成员服务暂时不可用')
  })

  it('取消本地授权后仍为门户管理员时保留后端有效身份并刷新列表', async () => {
    mocks.setMemberAdmin.mockResolvedValue({ userId: 'member-1', isAdmin: true })
    mocks.listPlatformMembers
      .mockResolvedValueOnce({ items: [member()], total: 1 })
      .mockResolvedValueOnce({ items: [{ ...member(), nickname: '刷新后的真实成员' }], total: 1 })
    const wrapper = renderMembers()
    await flushPromises()
    await wrapper.get('.member-action').trigger('click')
    await flushPromises()
    expect(mocks.setMemberAdmin).toHaveBeenCalledWith('member-1', false)
    expect(mocks.listPlatformMembers).toHaveBeenCalledTimes(2)
    expect(wrapper.get('.role').text()).toBe('全局管理员')
    expect(wrapper.text()).toContain('刷新后的真实成员')
  })

  it('授权后列表刷新失败也不把门户管理员乐观降级为普通用户', async () => {
    mocks.setMemberAdmin.mockResolvedValue({ userId: 'member-1', isAdmin: true })
    mocks.listPlatformMembers
      .mockResolvedValueOnce({ items: [member()], total: 1 })
      .mockRejectedValueOnce(new Error('列表刷新失败'))
    const wrapper = renderMembers()
    await flushPromises()
    await wrapper.get('.member-action').trigger('click')
    await flushPromises()
    expect(wrapper.get('.role').text()).toBe('全局管理员')
    expect(mocks.error).toHaveBeenCalledWith('列表刷新失败')
    expect(mocks.getExampleMembers).not.toHaveBeenCalled()
  })

  it('仅本地管理员撤权后读取服务器的普通用户结果', async () => {
    mocks.setMemberAdmin.mockResolvedValue({ userId: 'member-1', isAdmin: false })
    mocks.listPlatformMembers
      .mockResolvedValueOnce({ items: [member()], total: 1 })
      .mockResolvedValueOnce({ items: [member(false)], total: 1 })
    const wrapper = renderMembers()
    await flushPromises()
    await wrapper.get('.member-action').trigger('click')
    await flushPromises()
    expect(wrapper.get('.role').text()).toBe('普通用户')
    expect(wrapper.get('.member-action').text()).toBe('设为管理员')
  })

  it('现有按钮授予本地管理员后读取服务器的有效身份', async () => {
    mocks.setMemberAdmin.mockResolvedValue({ userId: 'member-1', isAdmin: true })
    mocks.listPlatformMembers
      .mockResolvedValueOnce({ items: [member(false)], total: 1 })
      .mockResolvedValueOnce({ items: [member()], total: 1 })
    const wrapper = renderMembers()
    await flushPromises()
    await wrapper.get('.member-action').trigger('click')
    await flushPromises()
    expect(mocks.setMemberAdmin).toHaveBeenCalledWith('member-1', true)
    expect(wrapper.get('.role').text()).toBe('全局管理员')
    expect(wrapper.get('.member-action').text()).toBe('取消管理员')
  })

  it('门户独有管理员撤权被后端拒绝时显示既有错误提示并保留身份', async () => {
    mocks.setMemberAdmin.mockRejectedValue(new Error('请在统一门户撤销管理员权限'))
    const wrapper = renderMembers()
    await flushPromises()
    await wrapper.get('.member-action').trigger('click')
    await flushPromises()
    expect(wrapper.get('.role').text()).toBe('全局管理员')
    expect(mocks.error).toHaveBeenCalledWith('请在统一门户撤销管理员权限')
    expect(mocks.success).not.toHaveBeenCalled()
  })

  it('显式免登录开发模式继续允许既有示例行为', async () => {
    mocks.authDisabled = true
    mocks.listPlatformMembers.mockResolvedValue({ items: [], total: 0 })
    const wrapper = renderMembers()
    await flushPromises()
    expect(mocks.getExampleMembers).toHaveBeenCalled()
    await wrapper.get('.member-action:not(:disabled)').trigger('click')
    await flushPromises()
    expect(mocks.setMemberAdmin).not.toHaveBeenCalled()
    expect(mocks.success).toHaveBeenCalledWith('示例成员权限已更新')
  })
})
