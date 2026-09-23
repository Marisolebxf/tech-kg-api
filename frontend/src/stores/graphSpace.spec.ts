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

function storeRecord(userId: string, space: string): string {
  return JSON.stringify({ u: userId, s: space })
}

beforeEach(() => {
  setActivePinia(createPinia())
  vi.resetAllMocks()
  localStorage.clear()
})

describe('全局图空间 store', () => {
  it('bindUser 采纳本人持久化记录，不采纳他人/旧版裸字符串', () => {
    const store = useGraphSpaceStore()
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, storeRecord('101', 'dev2'))
    store.bindUser('101')
    expect(store.current).toBe('dev2')

    // 换账号登录：上一用户选中的空间（即使本人列表里也有）不被带过来
    store.bindUser('202')
    expect(store.current).toBe('cfg-space')
    expect(localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)).toBe(storeRecord('202', 'cfg-space'))

    // 旧版裸字符串（跨账号共享时代的遗留）同样不采纳
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, 'gaoxing_test')
    useGraphSpaceStore().bindUser('303')
    expect(useGraphSpaceStore().current).toBe('cfg-space')
  })

  it('列表到位后按 本人持久化 > 构建默认 > 列表第一个 归一当前值并持久化', async () => {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, storeRecord('101', 'dev2'))
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'dev2'] } } as never)
    const store = useGraphSpaceStore()
    store.bindUser('101')
    await store.ensureLoaded()
    expect(store.spaces).toEqual(['dev', 'dev2'])
    expect(store.current).toBe('dev2')
    expect(localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)).toBe(storeRecord('101', 'dev2'))
  })

  it('持久化值不在列表时回退构建默认（VITE_GRAPH_SPACE）', async () => {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, storeRecord('101', 'gone-space'))
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev', 'cfg-space'] } } as never)
    const store = useGraphSpaceStore()
    store.bindUser('101')
    await store.ensureLoaded()
    expect(store.current).toBe('cfg-space')
  })

  it('两级默认都未命中时取列表第一个；空列表回退构建默认', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['only-one'] } } as never)
    const store = useGraphSpaceStore()
    store.bindUser('101')
    await store.ensureLoaded()
    expect(store.current).toBe('only-one')

    // 列表暂空（如另一处清空）：无本地取值时回退构建默认 cfg-space
    localStorage.removeItem(GRAPH_SPACE_STORAGE_KEY)
    store.spaces = []
    store.current = ''
    store._normalizeCurrent()
    expect(store.current).toBe('cfg-space')
  })

  it('setCurrent 仅接受列表内取值并按本人持久化', () => {
    const store = useGraphSpaceStore()
    store.bindUser('101')
    store.spaces = ['dev', 'dev2']
    store.setCurrent('dev2')
    expect(store.current).toBe('dev2')
    expect(localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)).toBe(storeRecord('101', 'dev2'))

    store.setCurrent('not-in-list')
    expect(store.current).toBe('dev2')
    store.setCurrent('')
    expect(store.current).toBe('dev2')
  })

  it('列表加载失败置 loadError 且保留既有当前值（不抛出）', async () => {
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, storeRecord('101', 'dev2'))
    vi.mocked(listGraphSpaces).mockRejectedValue(new Error('boom'))
    const store = useGraphSpaceStore()
    store.bindUser('101')
    await expect(store.ensureLoaded()).resolves.toBeUndefined()
    expect(store.loadError).toBe(true)
    expect(store.initialized).toBe(false)
    expect(store.current).toBe('dev2')
  })

  it('已初始化时重复 ensureLoaded 不再请求，force 可强制重拉', async () => {
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: ['dev'] } } as never)
    const store = useGraphSpaceStore()
    store.bindUser('101')
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
    localStorage.setItem(GRAPH_SPACE_STORAGE_KEY, storeRecord('101', 'private-other-business'))
    useAuthStore().profile = { businessRbacEnabled: true } as AuthProfile
    vi.mocked(listGraphSpaces).mockResolvedValue({ data: { spaces: [] } } as never)
    const store = useGraphSpaceStore()
    store.bindUser('101')
    await store.ensureLoaded()
    expect(store.current).toBe('')
    expect(localStorage.getItem(GRAPH_SPACE_STORAGE_KEY)).toBe(storeRecord('101', ''))
    store.setCurrent('private-other-business')
    expect(store.current).toBe('')
  })
})
