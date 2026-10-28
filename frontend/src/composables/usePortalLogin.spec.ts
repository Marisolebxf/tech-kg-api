import { createPinia } from 'pinia'
import { defineComponent } from 'vue'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getCurrentProfile, getLoginUrl, type AuthProfile } from '../api/auth'
import { usePortalLogin } from './usePortalLogin'

vi.mock('../api/auth', () => ({
  getCurrentProfile: vi.fn(), getLoginUrl: vi.fn(),
  logoutCurrentSession: vi.fn(), refreshCurrentSession: vi.fn(),
}))

const profile = { user: { id: 1 }, permissions: [] } as unknown as AuthProfile
const unauthorized = { response: { status: 401 } }
let wrapper: VueWrapper | undefined
let login: ReturnType<typeof usePortalLogin>
let navigate: ReturnType<typeof vi.fn>
let popup: { closed: boolean; close: ReturnType<typeof vi.fn>; location: { replace: ReturnType<typeof vi.fn> } }

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(yes => { resolve = yes })
  return { resolve, promise }
}

beforeEach(() => {
  vi.useFakeTimers()
  vi.resetAllMocks()
  vi.mocked(getLoginUrl).mockResolvedValue({ url: '/portal/', mode: 'portal', expiresIn: 0 })
  vi.mocked(getCurrentProfile).mockRejectedValue(unauthorized)
  popup = { closed: false, close: vi.fn(), location: { replace: vi.fn() } }
  vi.spyOn(window, 'open').mockReturnValue(popup as unknown as Window)
  navigate = vi.fn().mockResolvedValue(true)
  wrapper = mount(defineComponent({
    setup() { login = usePortalLogin(navigate); return () => null },
  }), { global: { plugins: [createPinia()] } })
})

afterEach(() => {
  wrapper?.unmount()
  vi.useRealTimers()
  vi.restoreAllMocks()
})

describe('portal popup login', () => {
  it('opens synchronously, waits for verified identity, closes and returns to the original deep link', async () => {
    const entry = deferred<{ url: string; mode: 'portal'; expiresIn: number }>()
    vi.mocked(getLoginUrl).mockReturnValue(entry.promise)
    login.start('/schema?view=all#details')
    expect(window.open).toHaveBeenCalledOnce()
    expect(popup.location.replace).not.toHaveBeenCalled()
    expect(getCurrentProfile).not.toHaveBeenCalled()
    entry.resolve({ url: '/portal/', mode: 'portal', expiresIn: 0 })
    await flushPromises()
    expect(popup.location.replace).toHaveBeenCalledWith(new URL('/portal/', window.location.href).href)
    expect(login.waiting.value).toBe(true)
    expect(navigate).not.toHaveBeenCalled()
    vi.mocked(getCurrentProfile).mockResolvedValue(profile)
    await vi.advanceTimersByTimeAsync(2_000)
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/schema?view=all#details')
    expect(popup.close).toHaveBeenCalledOnce()
    const calls = vi.mocked(getCurrentProfile).mock.calls.length
    await vi.advanceTimersByTimeAsync(10_000)
    expect(getCurrentProfile).toHaveBeenCalledTimes(calls)
  })

  it('stays on the original page when a popup is blocked', () => {
    vi.mocked(window.open).mockReturnValue(null)
    login.start('/overview')
    expect(login.error.value).toContain('允许本站弹出窗口')
    expect(login.waiting.value).toBe(false)
    expect(getLoginUrl).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it('does not open duplicate windows or overlap slow profile checks on focus', async () => {
    const pending = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValue(pending.promise)
    login.start('/overview')
    login.start('/schema')
    await flushPromises()
    window.dispatchEvent(new Event('focus'))
    window.dispatchEvent(new Event('pageshow'))
    await vi.advanceTimersByTimeAsync(10_000)
    expect(window.open).toHaveBeenCalledOnce()
    expect(getCurrentProfile).toHaveBeenCalledOnce()
    pending.resolve(profile)
    await flushPromises()
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/overview')
  })

  it('continues checking if COOP makes the window look closed', async () => {
    popup.closed = true
    login.start('/overview')
    await flushPromises()
    expect(login.waiting.value).toBe(true)
    expect(login.status.value).toContain('已关闭或已切换')
    expect(navigate).not.toHaveBeenCalled()
    vi.mocked(getCurrentProfile).mockResolvedValue(profile)
    window.dispatchEvent(new Event('focus'))
    await flushPromises()
    expect(navigate).toHaveBeenCalledOnce()
  })

  it('cancels a pending entry without navigating the closed window', async () => {
    const entry = deferred<{ url: string; mode: 'portal'; expiresIn: number }>()
    vi.mocked(getLoginUrl).mockReturnValue(entry.promise)
    login.start('/overview')
    login.cancel()
    entry.resolve({ url: '/portal/', mode: 'portal', expiresIn: 0 })
    await flushPromises()
    expect(popup.location.replace).not.toHaveBeenCalled()
    expect(getCurrentProfile).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })

  it.each(['cancel', 'unmount'] as const)('ignores a late authenticated response after %s', async (action) => {
    const pending = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValue(pending.promise)
    login.start('/overview')
    await flushPromises()
    if (action === 'cancel') login.cancel()
    else wrapper!.unmount()
    pending.resolve(profile)
    await flushPromises()
    await vi.advanceTimersByTimeAsync(10_000)
    window.dispatchEvent(new Event('focus'))
    expect(navigate).not.toHaveBeenCalled()
    expect(getCurrentProfile).toHaveBeenCalledOnce()
    expect(login.waiting.value).toBe(false)
  })

  it('can start again while a cancelled profile check is still pending', async () => {
    const pending = deferred<AuthProfile>()
    vi.mocked(getCurrentProfile).mockReturnValue(pending.promise)
    login.start('/overview')
    await flushPromises()
    login.cancel()
    login.start('/schema')
    await flushPromises()
    pending.resolve(profile)
    await flushPromises()
    expect(navigate).toHaveBeenCalledExactlyOnceWith('/schema')
  })

  it('retries a network failure and resumes immediately on visibility return', async () => {
    vi.mocked(getCurrentProfile).mockRejectedValueOnce(new Error('offline'))
    login.start('/overview')
    await flushPromises()
    expect(login.status.value).toContain('正在重试')
    vi.mocked(getCurrentProfile).mockResolvedValue(profile)
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('visible')
    document.dispatchEvent(new Event('visibilitychange'))
    await flushPromises()
    expect(navigate).toHaveBeenCalledOnce()
  })

  it('times out and stops checking even if a request never resolves', async () => {
    vi.mocked(getCurrentProfile).mockReturnValue(new Promise(() => {}))
    login.start('/overview')
    await flushPromises()
    await vi.advanceTimersByTimeAsync(300_000)
    expect(login.waiting.value).toBe(false)
    expect(login.error.value).toContain('超时')
    expect(popup.close).toHaveBeenCalledOnce()
  })

  it('cleans up when the portal entry fails', async () => {
    vi.mocked(getLoginUrl).mockRejectedValue(new Error('offline'))
    login.start('/overview')
    await flushPromises()
    expect(login.waiting.value).toBe(false)
    expect(login.error.value).toContain('无法打开')
    expect(popup.close).toHaveBeenCalledOnce()
  })
})
