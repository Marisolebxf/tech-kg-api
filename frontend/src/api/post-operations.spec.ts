import { AxiosError, AxiosHeaders, type InternalAxiosRequestConfig } from 'axios'
import { createPinia, setActivePinia } from 'pinia'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { useGraphSpaceStore } from '../stores/graphSpace'
import { saveBusinessMember, saveBusinessSpace } from './businessAccess'
import { deleteEmbeddingConfig, updateEmbeddingConfig } from './embeddingConfig'
import { unbindGraphSpace } from './graphSpace'
import { businessSpaceOverride, http } from './http'
import { deleteLlmConfig, updateLlmConfig } from './llmConfig'
import { deleteMilvusConfig, updateMilvusConfig } from './milvusConfig'
import { deleteMysqlDatasource, updateMysqlDatasource } from './mysqlDatasource'
import { deleteSchema, deleteSchemaProperty, replaceSchemaSources } from './schemaManagement'
import { deleteJob, deleteProductionReview, saveProductionReviewDraft, updateJobState } from './workflowOperations'

const originalAdapter = http.defaults.adapter
const userId = 'operator-1'
const sources = [{ datasourceId: 'source-1', databaseName: 'source_db', tableName: 'paper', pkColumn: 'id', timeColumn: 'updated_at' }]

interface Operation {
  name: string
  invoke: () => Promise<unknown>
  path: string
  body: unknown
  userHeader?: boolean
  contextFree?: boolean
  force?: boolean
}

// 调用真正的 API 导出函数，检查 Axios 最终发出的请求，而不是 mock http.post。
const operations: Operation[] = [
  { name: '更新 LLM 配置并确认解除默认引用', invoke: () => updateLlmConfig('model-1', { status: 'disabled' }, userId, true), path: '/v1/llm-config/llm-configs/model-1/update', body: { status: 'disabled' }, userHeader: true, force: true },
  { name: '删除 LLM 配置并确认解除默认引用', invoke: () => deleteLlmConfig('model-1', userId, true), path: '/v1/llm-config/llm-configs/model-1/delete', body: {}, userHeader: true, force: true },
  { name: '更新 Embedding 配置', invoke: () => updateEmbeddingConfig('embed-1', { dimensions: 1024 }, userId), path: '/v1/embedding-config/embed-1/update', body: { dimensions: 1024 }, userHeader: true },
  { name: '删除 Embedding 配置', invoke: () => deleteEmbeddingConfig('embed-1', userId), path: '/v1/embedding-config/embed-1/delete', body: {}, userHeader: true },
  { name: '更新 Milvus 配置', invoke: () => updateMilvusConfig('vector-1', { defaultDb: 'knowledge' }, userId), path: '/v1/milvus-configs/vector-1/update', body: { defaultDb: 'knowledge' }, userHeader: true },
  { name: '删除 Milvus 配置', invoke: () => deleteMilvusConfig('vector-1', userId), path: '/v1/milvus-configs/vector-1/delete', body: {}, userHeader: true },
  { name: '更新 MySQL 数据源', invoke: () => updateMysqlDatasource('source-1', { port: 3307 }, userId), path: '/v1/mysql-datasources/source-1/update', body: { port: 3307 }, userHeader: true },
  { name: '删除 MySQL 数据源', invoke: () => deleteMysqlDatasource('source-1', userId), path: '/v1/mysql-datasources/source-1/delete', body: {}, userHeader: true },
  { name: '保存成员业务归属并编码用户标识', invoke: () => saveBusinessMember({ userId: 'member+1@example.org', role: 'developer', clientIds: ['business-a'] }), path: '/v1/business-access/members/member%2B1%40example.org/update', body: { role: 'developer', clientIds: ['business-a'] }, contextFree: true },
  { name: '保存图空间业务归属', invoke: () => saveBusinessSpace('space_a', 'business-a', false), path: '/v1/business-access/spaces/space_a/update', body: { clientId: 'business-a', isSharedProduction: false }, contextFree: true },
  { name: '解绑图空间', invoke: () => unbindGraphSpace('space_a', userId), path: '/v1/graph-spaces/space_a/unbind', body: {}, userHeader: true, contextFree: true },
  { name: '删除 Schema 属性并保留路径编码', invoke: () => deleteSchemaProperty('schema-1', '属性 A', userId), path: `/v1/schema-management/schemas/schema-1/properties/${encodeURIComponent('属性 A')}/delete`, body: {}, userHeader: true },
  { name: '保存 Schema 来源绑定', invoke: () => replaceSchemaSources('schema-1', sources, userId), path: '/v1/schema-management/schemas/schema-1/sources/update', body: { sources }, userHeader: true },
  { name: '删除 Schema', invoke: () => deleteSchema('schema-1', userId), path: '/v1/schema-management/schemas/schema-1/delete', body: {}, userHeader: true },
  { name: '保存审核草稿和乐观锁版本', invoke: () => saveProductionReviewDraft('case-1', 7, { decision: 'accept' }), path: '/v1/manual-reviews/production/case-1/draft/update', body: { version: 7, payload: { decision: 'accept' } } },
  { name: '删除单条审核记录', invoke: () => deleteProductionReview('case-1'), path: '/v1/manual-reviews/production/case-1/delete', body: {} },
  { name: '停用构建任务', invoke: () => updateJobState('job-1', false), path: '/v1/workflow-system/jobs/job-1/state', body: { active: false } },
  { name: '删除构建任务', invoke: () => deleteJob('job-1'), path: '/v1/workflow-system/jobs/job-1/delete', body: {} },
]

beforeEach(() => {
  setActivePinia(createPinia())
  businessSpaceOverride.value = ''
  useGraphSpaceStore().$patch({
    userId, current: 'space_a', spaces: ['space_a'],
    items: [{ name: 'space_a', bound: true, mine: true, groupKind: 'business', clientId: 'business-a' }],
  })
})

afterEach(() => {
  http.defaults.adapter = originalAdapter
})

describe('仅允许 GET/POST 的入口网关', () => {
  it.each(operations)('$name：保留请求体、查询参数和权限上下文', async operation => {
    const requests: InternalAxiosRequestConfig[] = []
    http.defaults.adapter = async config => {
      requests.push(config)
      if (!['get', 'post'].includes(config.method || '')) throw new Error('网关禁止该 HTTP 方法')
      return { data: { code: 200, success: true, data: { id: 'result-1' } }, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
    }

    await operation.invoke()

    expect(requests).toHaveLength(1)
    const sent = requests[0]!
    expect(sent.method).toBe('post')
    expect(sent.url).toBe(operation.path)
    expect(JSON.parse(sent.data as string)).toEqual(operation.body)
    expect(sent.params).toEqual(operation.force ? { force: true } : undefined)
    expect(sent.headers.get('X-User-Id')).toBe(operation.userHeader ? userId : undefined)
    expect(sent.headers.get('X-Graph-Space')).toBe(operation.contextFree ? undefined : 'space_a')
    expect(sent.headers.get('X-Business-Id')).toBe(operation.contextFree ? undefined : 'business-a')
    expect(sent.headers.has('X-HTTP-Method-Override')).toBe(false)
    expect(sent.withCredentials).toBe(true)
  })

  it('普通删除不自动携带强制解除默认引用参数', async () => {
    http.defaults.adapter = async config => {
      expect(config.params).toBeUndefined()
      expect(JSON.parse(config.data as string)).toEqual({})
      return { data: { code: 200, success: true, data: { deleted: true } }, status: 200, statusText: 'OK', headers: new AxiosHeaders(), config }
    }
    await deleteLlmConfig('model-1', userId)
  })

  it('权限拒绝直接反馈，不重试旧 DELETE 或 GET 写操作', async () => {
    const methods: string[] = []
    http.defaults.adapter = async config => {
      methods.push(config.method || '')
      throw new AxiosError('forbidden', 'ERR_BAD_REQUEST', config, undefined, {
        data: { detail: '无权对该图空间执行此操作' }, status: 403, statusText: 'Forbidden', headers: new AxiosHeaders(), config,
      })
    }
    await expect(deleteSchema('schema-1', userId)).rejects.toThrow('无权对该图空间执行此操作')
    expect(methods).toEqual(['post'])
  })
})
