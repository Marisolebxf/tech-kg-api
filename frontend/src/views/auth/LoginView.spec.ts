import { createPinia, setActivePinia } from 'pinia'
import { mount, flushPromises, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { getCurrentProfile, type AuthProfile } from '../../api/auth'
import { useAuthStore } from '../../stores/auth'
import LoginView from './LoginView.vue'

vi.mock('../../api/auth', () => ({
  getCurrentProfile: vi.fn(), getLoginUrl: vi.fn(),
  logoutCurrentSession: vi.fn(), refreshCurrentSession: vi.fn(),
}))

const profile = { user: { id: 1 }, isAdmin: false, permissions: [] } as AuthProfile
const unauthorized = { response: { status: 401 } }
let wrapper: VueWrapper | undefined

async function setup(initialProfile: AuthProfile | null = null) {
  const pinia = createPinia()
  setActivePinia(pinia)
  if (initialProfile) vi.mocked(getCurrentProfile).mockResolvedValue(initialProfile)
  else vi.mocked(getCurrentProfile).mockRejectedValue(unauthorized)
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/login', name: 'login', component: LoginView },
      { path: '/overview', name: 'overview', component: {} },
    ],
  })
  await router.push('/login')
  wrapper = mount(LoginView, { global: { plugins: [pinia, router] } })
  await flushPromises()
  const store = useAuthStore()
  const startLogin = vi.spyOn(store, 'startLogin').mockResolvedValue()
  return { router, store, startLogin, button: wrapper.find('button') }
}

beforeEach(() => vi.resetAllMocks())
afterEach(() => { wrapper?.unmount(); wrapper = undefined })

describe('login navigation recovery', () => {
  it('checks the server at click time instead of trusting the mounted profile', async () => {
    const { button, startLogin } = await setup(profile)
    vi.mocked(getCurrentProfile).mockRejectedValueOnce(unauthorized)
    await button.trigger('click')
    await flushPromises()
    expect(getCurrentProfile).toHaveBeenCalledTimes(2)
    expect(startLogin).toHaveBeenCalledExactlyOnceWith('/overview')
    expect(button.attributes('disabled')).toBeUndefined()
    expect(button.text()).toContain('进入 →')
  })

  it('restores the buttons when authenticated navigation is cancelled', async () => {
    const { router, button, startLogin } = await setup(profile)
    router.beforeEach((to) => to.name === 'overview' ? false : true)
    await button.trigger('click')
    await flushPromises()
    expect(router.currentRoute.value.name).toBe('login')
    expect(startLogin).not.toHaveBeenCalled()
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('starts explicit OAuth if a navigation check returns to login with an expired identity', async () => {
    const { router, store, button, startLogin } = await setup(profile)
    router.beforeEach((to) => {
      if (to.name !== 'overview') return true
      store.invalidate()
      return { path: '/login', query: { error: '登录状态已失效或已超时，请重新登录' } }
    })
    await button.trigger('click')
    await flushPromises()
    expect(startLogin).toHaveBeenCalledExactlyOnceWith('/overview')
    expect(button.attributes('disabled')).toBeUndefined()
  })

  it('restores the buttons and existing error feedback when OAuth navigation fails', async () => {
    const { button, startLogin } = await setup()
    startLogin.mockRejectedValue(new Error('offline'))
    await button.trigger('click')
    await flushPromises()
    expect(button.attributes('disabled')).toBeUndefined()
    expect(wrapper?.find('[role="alert"]').exists()).toBe(true)
  })

  it('restores the buttons on browser pageshow while a navigation is pending', async () => {
    const { button, startLogin } = await setup()
    let finish!: () => void
    startLogin.mockReturnValue(new Promise<void>((resolve) => { finish = resolve }))
    await button.trigger('click')
    await flushPromises()
    expect(button.text()).toContain('跳转中')
    window.dispatchEvent(new Event('pageshow'))
    await flushPromises()
    expect(button.attributes('disabled')).toBeUndefined()
    finish()
    await flushPromises()
  })

  it('does not silently restore an old login after local logout', async () => {
    const { store, button, startLogin } = await setup(profile)
    await store.logout()
    await button.trigger('click')
    await flushPromises()
    expect(getCurrentProfile).toHaveBeenCalledTimes(1)
    expect(startLogin).toHaveBeenCalledExactlyOnceWith('/overview')
  })
})
