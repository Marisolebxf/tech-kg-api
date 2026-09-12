import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getCurrentProfile, logoutCurrentSession, refreshCurrentSession, type AuthProfile } from '../api/auth'
import { useAuthStore } from './auth'

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

describe('session state recovery', () => {
  it('rechecks a cached identity and clears it when the server rejects it', async () => {
    const store = useAuthStore()
    vi.mocked(getCurrentProfile).mockResolvedValueOnce(profile).mockRejectedValueOnce(unauthorized)
    expect(await store.loadCurrentUser(true)).toEqual(profile)
    expect(await store.loadCurrentUser(true)).toBeNull()
    expect(store.isAuthenticated).toBe(false)
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
