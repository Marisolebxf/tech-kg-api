import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getCurrentProfile, getLoginUrl, logoutCurrentSession, refreshCurrentSession, type AuthProfile } from '../api/auth'
import { useAuthStore } from './auth'
import { useToast } from '../composables/use-toast'

vi.mock('../api/auth', () => ({
  getCurrentProfile: vi.fn(), getLoginUrl: vi.fn(),
  logoutCurrentSession: vi.fn(), refreshCurrentSession: vi.fn(),
}))

const profile = { user: { id: 1, nickname: 'member' }, isAdmin: false, permissions: [] } as AuthProfile
const unauthorized = { response: { status: 401 } }

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
})

afterEach(() => {
  const { toasts, dismissToast } = useToast()
  for (const toast of [...toasts.value]) dismissToast(toast.id)
})

describe('未绑定业务登录提示', () => {
  const unbound = { ...profile, developerBusinessBindingRequired: true }

  it('首次登录提示，路由重新校验和会话刷新不重复，仍保持普通权限', async () => {
    const store = useAuthStore()
    vi.mocked(getCurrentProfile).mockResolvedValue(unbound)
    vi.mocked(refreshCurrentSession).mockResolvedValue(unbound)
    await store.loadCurrentUser(true)
    await store.loadCurrentUser(true)
    await store.refresh()
    expect(useToast().toasts.value.map(item => [item.message, item.tone])).toEqual([
      ['您已获得门户开发人员身份，但尚未绑定可开发的业务，请联系管理员为您绑定业务。', 'warning'],
    ])
    expect(store.isAuthenticated).toBe(true)
    expect(store.canDevelop).toBe(false)
    expect(store.isAdmin).toBe(false)
  })

  it('重新登录会再次提示；完成绑定后停止提示', async () => {
    const store = useAuthStore()
    vi.mocked(getCurrentProfile).mockResolvedValue(unbound)
    await store.loadCurrentUser(true)
    store.invalidate()
    await store.loadCurrentUser(true)
    expect(useToast().toasts.value).toHaveLength(2)
    vi.mocked(getCurrentProfile).mockResolvedValue({ ...profile, canDevelop: true, businessRbacEnabled: true })
    await store.loadCurrentUser(true)
    expect(useToast().toasts.value).toHaveLength(2)
    expect(store.canDevelop).toBe(true)
  })

  it.each([profile, { ...unbound, isAdmin: true }, { ...unbound, businessOnly: true }])('普通用户、管理员和受限账号不提示', async (value) => {
    vi.mocked(getCurrentProfile).mockResolvedValue(value)
    await useAuthStore().loadCurrentUser(true)
    expect(useToast().toasts.value).toEqual([])
  })

  it('不会用退出登录后才返回的旧身份弹出提示', async () => {
    const store = useAuthStore()
    const response = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValue(response.promise)
    const pending = store.loadCurrentUser(true)
    store.invalidate()
    response.resolve(unbound)
    await pending
    expect(useToast().toasts.value).toEqual([])
  })
})

describe('session state recovery', () => {
  it('treats a first unauthenticated response as login-required rather than expired', async () => {
    const store = useAuthStore()
    vi.mocked(getCurrentProfile).mockRejectedValue({ response: { status: 401, data: { detail: '尚未登录' } } })
    expect(await store.loadCurrentUser(true)).toBeNull()
    expect(store.sessionExpired).toBe(false)
  })

  it.each(['登录已过期，请重新登录', '访问令牌已过期'])('recognizes an explicit server expiry even after reload: %s', async (detail) => {
    const store = useAuthStore()
    vi.mocked(getCurrentProfile).mockRejectedValue({ response: { status: 401, data: { detail } } })
    expect(await store.loadCurrentUser(true)).toBeNull()
    expect(store.sessionExpired).toBe(true)
    vi.mocked(getCurrentProfile).mockResolvedValue(profile)
    await store.loadCurrentUser(true)
    expect(store.sessionExpired).toBe(false)
  })

  it('does not retain expiry after explicit logout', async () => {
    const store = useAuthStore()
    store.invalidate(true)
    await store.logout()
    expect(store.sessionExpired).toBe(false)
  })

  it('rechecks a cached identity and clears it when the server rejects it', async () => {
    const store = useAuthStore()
    vi.mocked(getCurrentProfile).mockResolvedValueOnce(profile).mockRejectedValueOnce(unauthorized)
    expect(await store.loadCurrentUser(true)).toEqual(profile)
    expect(await store.loadCurrentUser(true)).toBeNull()
    expect(store.isAuthenticated).toBe(false)
    expect(store.sessionExpired).toBe(true)
    expect(getCurrentProfile).toHaveBeenCalledTimes(2)
  })

  it('shares concurrent profile checks without caching later navigation checks', async () => {
    const store = useAuthStore()
    const response = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValueOnce(response.promise).mockResolvedValue(profile)
    const first = store.loadCurrentUser(true)
    const second = store.loadCurrentUser(true)
    expect(getCurrentProfile).toHaveBeenCalledTimes(1)
    response.resolve(profile)
    expect(await Promise.all([first, second])).toEqual([profile, profile])
    await store.loadCurrentUser(true)
    expect(getCurrentProfile).toHaveBeenCalledTimes(2)
  })

  it('discards a profile that arrives after business authentication expires', async () => {
    const store = useAuthStore()
    const response = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValue(response.promise)
    const pending = store.loadCurrentUser(true)
    store.invalidate()
    response.resolve(profile)
    expect(await pending).toBeNull()
    expect(store.profile).toBeNull()
    expect(store.loading).toBe(false)
  })

  it('ignores an old rejected check after a newer identity was loaded', async () => {
    const store = useAuthStore()
    const old = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValueOnce(old.promise).mockResolvedValueOnce(profile)
    const pending = store.loadCurrentUser(true)
    store.invalidate()
    await store.loadCurrentUser(true)
    old.reject(unauthorized)
    expect(await pending).toBeNull()
    expect(store.profile).toEqual(profile)
  })

  it.each([undefined, unauthorized, new Error('offline')])('finishes logout despite its API result (%s)', async (failure) => {
    const store = useAuthStore()
    store.profile = profile
    const old = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValue(old.promise)
    const pending = store.loadCurrentUser(true)
    if (failure) vi.mocked(logoutCurrentSession).mockRejectedValue(failure)
    await expect(store.logout()).resolves.toBeUndefined()
    old.resolve(profile)
    expect(await pending).toBeNull()
    expect(store.profile).toBeNull()
    expect(store.loggingOut).toBe(false)
    expect(await store.loadCurrentUser(true)).toBeNull()
    expect(getCurrentProfile).toHaveBeenCalledTimes(1)
  })

  it('discards a refresh response that arrives after logout', async () => {
    const store = useAuthStore()
    const response = deferred<AuthProfile>()
    vi.mocked(refreshCurrentSession).mockReturnValue(response.promise)
    const pending = store.refresh()
    await store.logout()
    response.resolve(profile)
    expect(await pending).toBeNull()
    expect(store.profile).toBeNull()
  })
})

describe('业务角色菜单权限', () => {
  it('开发维护不是管理员，但能进入管理功能', () => {
    const store = useAuthStore()
    store.profile = { ...profile, businessRbacEnabled: true, platformRole: 'developer', canDevelop: true }
    expect(store.isAdmin).toBe(false)
    expect(store.canDevelop).toBe(true)
    store.profile.businessOnly = true
    expect(store.canDevelop).toBe(false)
  })
  it('旧模式保持管理员门槛', () => {
    const store = useAuthStore()
    store.profile = { ...profile, businessRbacEnabled: false, canDevelop: true }
    expect(store.canDevelop).toBe(false)
  })
})

describe('explicit portal login', () => {
  it('resumes shared-cookie checks only after an explicit successful portal login request', async () => {
    const store = useAuthStore()
    await store.logout()
    vi.mocked(getCurrentProfile).mockResolvedValue(profile)
    expect(await store.loadCurrentUser(true)).toBeNull()
    vi.mocked(getLoginUrl).mockResolvedValue({ url: '/portal/', expiresIn: 0, mode: 'portal' })
    expect(await store.preparePortalLogin('/schema?view=all')).toBe('/portal/')
    expect(getLoginUrl).toHaveBeenCalledWith('/schema?view=all')
    expect(await store.loadCurrentUser(true)).toEqual(profile)
  })

  it('does not resume silent login when the entry request fails or changes mode', async () => {
    const store = useAuthStore()
    await store.logout()
    vi.mocked(getLoginUrl).mockRejectedValueOnce(new Error('offline'))
    await expect(store.preparePortalLogin()).rejects.toThrow('offline')
    expect(store.skipSilentLogin).toBe(true)
    vi.mocked(getLoginUrl).mockResolvedValue({ url: '/sso/login', expiresIn: 300, mode: 'oauth' })
    await expect(store.preparePortalLogin()).rejects.toThrow('登录方式已更新')
    expect(store.skipSilentLogin).toBe(true)
  })

  it('ignores a prepared entry that arrives after logout', async () => {
    const store = useAuthStore()
    const response = deferred<{ url: string; expiresIn: number; mode: 'portal' }>()
    vi.mocked(getLoginUrl).mockReturnValue(response.promise)
    const pending = store.preparePortalLogin()
    await store.logout()
    response.resolve({ url: '/portal/', expiresIn: 0, mode: 'portal' })
    expect(await pending).toBeNull()
    expect(store.skipSilentLogin).toBe(true)
  })
})

describe('bounded navigation profile cache', () => {
  afterEach(() => vi.restoreAllMocks())

  it('reuses a fresh profile and rechecks after the navigation window expires', async () => {
    let now = 100_000
    vi.spyOn(Date, 'now').mockImplementation(() => now)
    vi.mocked(getCurrentProfile).mockResolvedValue(profile)
    const store = useAuthStore()
    await store.loadCurrentUser(false, 15_000)
    now += 14_999
    await store.loadCurrentUser(false, 15_000)
    expect(getCurrentProfile).toHaveBeenCalledTimes(1)
    now += 1
    await store.loadCurrentUser(false, 15_000)
    expect(getCurrentProfile).toHaveBeenCalledTimes(2)
    await store.loadCurrentUser(true)
    expect(getCurrentProfile).toHaveBeenCalledTimes(3)
  })

  it('waits for an ongoing forced check instead of using the old cached role', async () => {
    vi.mocked(getCurrentProfile).mockResolvedValueOnce({ ...profile, isAdmin: true })
    const store = useAuthStore()
    await store.loadCurrentUser()
    const response = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValueOnce(response.promise)
    const forced = store.loadCurrentUser(true)
    const navigation = store.loadCurrentUser(false, 15_000)
    response.resolve(profile)
    expect(await forced).toEqual(profile)
    expect(await navigation).toEqual(profile)
    expect(getCurrentProfile).toHaveBeenCalledTimes(2)
  })

  it('invalidates freshness when a business request expires the session', async () => {
    vi.mocked(getCurrentProfile).mockResolvedValueOnce(profile).mockRejectedValueOnce(unauthorized)
    const store = useAuthStore()
    await store.loadCurrentUser(false, 15_000)
    store.invalidate(true)
    expect(store.profileLoadedAt).toBeNull()
    expect(await store.loadCurrentUser(false, 15_000)).toBeNull()
    expect(getCurrentProfile).toHaveBeenCalledTimes(2)
  })
})
