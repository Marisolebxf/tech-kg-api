import { useAuthStore } from './auth'
import type { AuthProfile } from '../api/auth'
import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { listGraphSpaces } from '../api/graphSearch'
import { GRAPH_SPACE_STORAGE_KEY, useGraphSpaceStore } from './graphSpace'

vi.mock('../api/graphSearch', () => ({
  listGraphSpaces: vi.fn(),
}))
vi.mock('../api/auth', () => ({ getCurrentProfile: vi.fn(), getLoginUrl: vi.fn(), logoutCurrentSession: vi.fn(), refreshCurrentSession: vi.fn() }))
vi.mock('../config', () => ({ graphSpace: 'cfg-space' }))

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  localStorage.clear()
})

describe('全局图空间 store', () => {
  it('列表到位后按 localStorage > 构建默认 > 列表第一个 归一当前值并持久化', async () => {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, 'dev2')
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'dev2'] } } as never)
    const store = useGraphSpaceStore()
    await store.ensureLoaded()
    expect(store.spaces).toEqual(['dev', 'dev2'])
    expect(store.current).toBe('dev2')
    expect(localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)).toBe('dev2')
  })

  it('localStorage 值不在列表时回退构建默认（VITE_GRAPH_SPACE）', async () => {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, 'gone-space')
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'cfg-space'] } } as never)
    const store = useGraphSpaceStore()
    await store.ensureLoaded()
    expect(store.current).toBe('cfg-space')
  })

  it('两级默认都未命中时取列表第一个；空列表回退构建默认', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['only-one'] } } as never)
    const store = useGraphSpaceStore()
    await store.ensureLoaded()
    expect(store.current).toBe('only-one')

    // 列表暂空（如另一处清空）：无本地取值时回退构建默认 cfg-space
    localStorage.removeItem(GRAPH_SPACE_STORAGE_KEY)
    store.spaces = []
    store.current = ''
    store._normalizeCurrent()
    expect(store.current).toBe('cfg-space')
  })

  it('setCurrent 仅接受列表内取值并写入 localStorage', () => {
    const store = useGraphSpaceStore()
    store.spaces = ['dev', 'dev2']
    store.setCurrent('dev2')
    expect(store.current).toBe('dev2')
    expect(localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)).toBe('dev2')

    store.setCurrent('not-in-list')
    expect(store.current).toBe('dev2')
    store.setCurrent('')
    expect(store.current).toBe('dev2')
  })

  it('列表加载失败置 loadError 且保留既有当前值（不抛出）', async () => {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, 'dev2')
    vi.mocked(listGraphSpaces).mockRejectedValue(new Error('boom'))
    const store = useGraphSpaceStore()
    await expect(store.ensureLoaded()).resolves.toBeUndefined()
    expect(store.loadError).toBe(true)
    expect(store.initialized).toBe(false)
    expect(store.current).toBe('dev2')
  })

  it('已初始化时重复 ensureLoaded 不再请求，force 可强制重拉', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev'] } } as never)
    const store = useGraphSpaceStore()
    await store.ensureLoaded()
    await store.ensureLoaded()
    expect(listGraphSpaces).toHaveBeenCalledTimes(1)

    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'dev2'] } } as never)
    await store.ensureLoaded(true)
    expect(listGraphSpaces).toHaveBeenCalledTimes(2)
    expect(store.spaces).toEqual(['dev', 'dev2'])
  })
})

describe('业务空间隔离', () => {
  it('授权空间为空时清除旧账号选中空间，不回退到默认空间', async () => {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, 'private-other-business')
    useAuthStore().profile = { businessRbacEnabled: true } as AuthProfile
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: [] } } as never)
    const store = useGraphSpaceStore()
    await store.ensureLoaded()
    expect(store.current).toBe('')
    expect(localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)).toBe('')
    store.setCurrent('private-other-business')
    expect(store.current).toBe('')
  })
})
