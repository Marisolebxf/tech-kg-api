import { beforeEach, describe, expect, it, vi } from 'vitest'

import { browseEntities, searchEntities } from './entitySearch'
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

describe('实体列表预览范围 API', () => {
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
