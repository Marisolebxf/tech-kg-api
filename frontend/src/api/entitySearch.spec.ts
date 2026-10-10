import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browseEntities, searchEntities, searchEntityList, countEntityList } from './entitySearch'
import { http } from './http'

vi.mock('./http', () => ({ http: { get: vi.fn(), post: vi.fn() } }))

const success = { code: 200, success: true, msg: 'success', data: {
  items: [], total: 0, offset: 0, limit: 10, entityType: null, mode: 'keyword',
} }

beforeEach(() => {
  vi.resetAllMocks()
  vi.mocked(http.get).mockResolvedValue(success)
  vi.mocked(http.post).mockResolvedValue(success)
})

describe('实体检索 API 路由', () => {
  it('实体列表文字搜索使用 keyword 接口，保留当前图空间及分页', async () => {
    const scope = { space: 'dev2', entityType: 'Paper', keyword: '世界生命科学格局中的中国', limit: 10, offset: 10 }
    await searchEntityList(scope)
    expect(http.get).toHaveBeenCalledWith('/v1/entity-search/keyword', { params: scope })
    expect(http.post).not.toHaveBeenCalled()
  })

  it('总数使用独立接口并传递版本、匹配模式和取消信号', async () => {
    const signal = new AbortController().signal
    const scope = { keyword: '生命科学', space: 'dev2', generation: 'g'.repeat(32), matchMode: 'contains' as const }
    await countEntityList(scope, signal)
    expect(http.get).toHaveBeenCalledWith('/v1/entity-search/keyword/count', { params: scope, signal, timeout: 0 })
  })

  it('浏览和搜索使用同一 preview 接口，不向全图搜索发送请求', async () => {
    const scope = { space: 'dev2', entityType: 'Expert', limit: 10, offset: 0 }
    await browseEntities({ ...scope, previewOnly: true })
    await searchEntities({ ...scope, keyword: '张三', previewOnly: true })
    expect(http.get).toHaveBeenNthCalledWith(1, '/v1/entity-search/preview', { params: scope })
    expect(http.get).toHaveBeenNthCalledWith(2, '/v1/entity-search/preview', { params: { ...scope, keyword: '张三' } })
    expect(http.post).not.toHaveBeenCalled()
  })

  it('其他调用方仍可显式使用原有浏览和混合搜索接口', async () => {
    await browseEntities({ space: 'dev2' })
    await searchEntities({ space: 'dev2', keyword: '张三' })
    expect(http.get).toHaveBeenCalledWith('/v1/entity-search/entities', { params: { space: 'dev2' } })
    expect(http.post).toHaveBeenCalledWith('/v1/entity-search/search', { space: 'dev2', keyword: '张三' })
  })
})
