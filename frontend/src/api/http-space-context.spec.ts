import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'
import { AxiosError, AxiosHeaders, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { http } from './http'
import { useGraphSpaceStore } from '../stores/graphSpace'

beforeEach(() => {
  setActivePinia(createPinia())
  useGraphSpaceStore().$patch({ userId: 'u', current: 'a', spaces: ['a', 'b'], items: [
    {name: 'a', bound: true, mine: true, groupKind: 'business', clientId: 'business-a'},
    {name: 'b', bound: true, mine: true, groupKind: 'business', clientId: 'business-b'},
  ] })
})

describe('请求空间隔离', () => {
  it('九大请求携带空间与所属业务，不触发机器认证', async () => {
    let sent!: InternalAxiosRequestConfig
    await http.post('/v1/kg-construction/expert-direct-relations/query', {}, { adapter: async config => {
      sent = config
      return { data: {}, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
    } })
    expect(sent.headers.get('X-Graph-Space')).toBe('a')
    expect(sent.headers.get('X-Business-Id')).toBe('business-a')
    expect(sent.headers.has('X-Client-Id')).toBe(false)
  })
  it('切空间后丢弃旧空间迟到结果', async () => {
    let finish!: () => void
    let started!: () => void
    const entered = new Promise<void>(resolve => { started = resolve })
    const pending = http.get('/v1/kg-service/key-enterprise-relation', { adapter: config => new Promise<AxiosResponse>(resolve => {
      finish = () => resolve({ data: { secret: 'a' }, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config })
      started()
    }) })
    const rejected = expect(pending).rejects.toMatchObject({ code: 'ERR_CANCELED' })
    await entered
    useGraphSpaceStore().setCurrent('b')
    finish()
    await rejected
  })
  it('授权目录加载不依赖旧空间或业务上下文', async () => {
    await http.get('/v1/graph-search/spaces', { adapter: async config => {
      expect(config.headers.has('X-Graph-Space')).toBe(false)
      expect(config.headers.has('X-Business-Id')).toBe(false)
      return { data: {}, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
    } })
  })
  it('切回原空间也不接受切换前的响应', async () => {
    await expect(http.get('/v1/kg-service/key-enterprise-relation', { adapter: async config => {
      useGraphSpaceStore().setCurrent('b')
      useGraphSpaceStore().setCurrent('a')
      return { data: { old: true }, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
    } })).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  })
  it('旧空间失败响应同样丢弃', async () => {
    await expect(http.get('/v1/kg-service/key-enterprise-relation', { adapter: async config => {
      useGraphSpaceStore().setCurrent('b')
      throw new AxiosError('forbidden', 'ERR_BAD_REQUEST', config, undefined, {
        data: { detail: '旧空间不可访问' }, status: 403, statusText: 'Forbidden', headers: new AxiosHeaders(), config,
      })
    } })).rejects.toMatchObject({ code: 'ERR_CANCELED' })
  })
  it('profile 刷新可跨越空间切换完成', async () => {
    const result = await http.get('/v1/auth/me', { adapter: async config => {
      expect(config.headers.has('X-Graph-Space')).toBe(false)
      useGraphSpaceStore().setCurrent('b')
      return { data: { userId: 'u' }, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
    } })
    expect(result).toEqual({ userId: 'u' })
  })
  it('同空间保存后刷新不丢弃响应', async () => {
    const adapter = async (config: InternalAxiosRequestConfig) => ({ data: { ok: true }, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config })
    await expect(http.put('/v1/configurations/llms/one', {}, { adapter })).resolves.toEqual({ ok: true })
    // 保存后重新确认相同空间并刷新列表，不构成上下文切换。
    useGraphSpaceStore().setCurrent('a')
    await expect(http.get('/v1/configurations/llms', { adapter })).resolves.toEqual({ ok: true })
  })
})
