import { describe, expect, it, vi, beforeEach } from 'vitest'

import { http } from './http'
import { getSchemaOverview } from './schemaManagement'

vi.mock('./http', () => ({
  http: { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() },
}))

describe('unwrap 422 字段级错误透出', () => {
  beforeEach(() => {
    vi.mocked(http.get).mockReset()
  })

  it('code=422 时拼接 data 里的 loc/msg 抛出', async () => {
    vi.mocked(http.get).mockResolvedValue({
      code: 422,
      success: false,
      msg: '请求参数校验失败',
      data: [
        { loc: ['body', 'name'], msg: '实体 Schema 名称必须使用 PascalCase', type: 'value_error' },
      ],
    })
    await expect(getSchemaOverview()).rejects.toThrow(
      '请求参数校验失败：name: 实体 Schema 名称必须使用 PascalCase',
    )
  })

  it('多个字段错误用「；」连接并过滤 body 前缀', async () => {
    vi.mocked(http.get).mockResolvedValue({
      code: 422,
      success: false,
      msg: '请求参数校验失败',
      data: [
        { loc: ['body', 'properties', 0, 'name'], msg: '属性名只能包含字母、数字和下划线', type: 'value_error' },
        { loc: ['body', 'schemaKey'], msg: 'schemaKey 必须以小写字母开头', type: 'value_error' },
      ],
    })
    await expect(getSchemaOverview()).rejects.toThrow(
      '请求参数校验失败：properties.0.name: 属性名只能包含字母、数字和下划线；schemaKey: schemaKey 必须以小写字母开头',
    )
  })

  it('code=422 且 data 非数组时回退到 msg', async () => {
    vi.mocked(http.get).mockResolvedValue({
      code: 422,
      success: false,
      msg: '请求参数校验失败',
      data: null,
    })
    await expect(getSchemaOverview()).rejects.toThrow('请求参数校验失败')
  })

  it('正常 200 返回 data', async () => {
    vi.mocked(http.get).mockResolvedValue({
      code: 200,
      success: true,
      msg: 'ok',
      data: { currentVersion: 'v1.8' },
    })
    await expect(getSchemaOverview()).resolves.toEqual({ currentVersion: 'v1.8' })
  })

  it('其它非 200 code 仍走原 msg 逻辑', async () => {
    vi.mocked(http.get).mockResolvedValue({
      code: 409,
      success: false,
      msg: 'schemaKey 或 Schema 名称已存在',
      data: null,
    })
    await expect(getSchemaOverview()).rejects.toThrow('schemaKey 或 Schema 名称已存在')
  })
})
