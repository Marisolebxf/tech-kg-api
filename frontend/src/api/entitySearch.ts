/**
 * 实体检索 API（Milvus 混合搜索：m3e 语义 + BM25 关键词 + 图直查浏览）。
 *
 * 后端接口前缀：/api/v1/entity-search
 */

import { unwrapApiResponse } from './graphSearch'
import { http } from './http'

export interface ApiResponse<T> {
  code: number
  success: boolean
  data: T
  msg: string
}

export interface EntityTypeCount {
  name: string
  count: number
}

export interface EntitySearchItem {
  vid: string
  entityId: string | null
  name: string | null
  entityType: string | null
  properties: Record<string, string>
  score: number | null
}

export interface EntityListResult {
  items: EntitySearchItem[]
  offset: number
  limit: number
  returned?: number
  total?: number
  keyword?: string
  entityType: string | null
  graphSpace?: string | null
  mode: 'browse' | 'graph-exact' | 'hybrid' | 'dense' | 'sparse' | 'keyword'
}

export interface EntityIndexStatus {
  indexed: boolean
  typeCounts: Record<string, number>
  types: EntityTypeCount[]
  graphSpace: string | null
  embeddingModel: string | null
  collectionExists: boolean
  bm25Ready: boolean
  reindexing: boolean
  milvusReachable?: boolean
  actualDataAvailable?: boolean
  stateStale?: boolean
  recordedEntityCount?: number
  recordedTypeCounts?: Record<string, number>
}


const PREFIX = '/v1/entity-search'

function unwrap<T>(response: ApiResponse<T>): T {
  // 422 字段级明细走共享解包（graphSearch.unwrapApiResponse），本文件只留兜底文案
  return unwrapApiResponse(response, '实体检索接口请求失败')
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

function errorMessage(error: unknown): string {
  const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data
    ?.detail
  if (typeof detail === 'string') return detail
  return error instanceof Error ? error.message : '实体检索服务请求失败'
}

export { errorMessage as entitySearchErrorMessage }

export async function exportEntitiesCsv(payload: {
  space?: string | null
  entityType?: string | null
}, signal?: AbortSignal): Promise<Blob> {
  try {
    // 全量导出可能持续数分钟；用户离开页面或切换图空间时取消请求。
    return await http.get(`${PREFIX}/export`, {
      params: payload, responseType: 'blob', timeout: 0, signal,
    }) as unknown as Blob
  } catch (error) {
    // blob 请求的错误正文仍是 JSON，解包后才能展示后端权限/图查询错误。
    const response = (error as { response?: { data?: unknown } })?.response
    if (response?.data instanceof Blob) {
      try { response.data = JSON.parse(await response.data.text()) } catch { /* 保留网络错误 */ }
    }
    throw new Error(errorMessage(error))
  }
}

export async function browseEntities(payload: {
  space?: string | null
  entityType?: string | null
  limit?: number
  offset?: number
  previewOnly?: boolean
}): Promise<EntityListResult> {
  const { previewOnly, ...params } = payload
  return unwrap(
    await asApiPromise<EntityListResult>(
      http.get(`${PREFIX}/${previewOnly ? 'preview' : 'entities'}`, { params }),
    ),
  )
}

export async function getEntitySearchTypes(space?: string | null): Promise<EntityTypeCount[]> {
  return unwrap(
    await asApiPromise<{ items: EntityTypeCount[] }>(
      http.get(`${PREFIX}/types`, { params: { space } }),
    ),
  ).items
}

export async function getEntityIndexStatus(
  space?: string | null,
): Promise<EntityIndexStatus> {
  return unwrap(
    await asApiPromise<EntityIndexStatus>(
      http.get(`${PREFIX}/index-status`, { params: { space } }),
    ),
  )
}

export async function searchEntities(payload: {
  keyword: string
  space?: string | null
  entityType?: string | null
  limit?: number
  offset?: number
  previewOnly?: boolean
}): Promise<EntityListResult> {
  const { previewOnly, ...params } = payload
  return unwrap(
    await asApiPromise<EntityListResult>(
      previewOnly
        ? http.get(`${PREFIX}/preview`, { params })
        : http.post(`${PREFIX}/search`, params),
    ),
  )
}

/** 实体列表采用文字匹配；图谱可视化等调用方仍使用 searchEntities 的语义检索。 */
export async function searchEntityList(payload: {
  keyword: string
  space?: string | null
  entityType?: string | null
  limit?: number
  offset?: number
}): Promise<EntityListResult> {
  return unwrap(await asApiPromise<EntityListResult>(http.get(`${PREFIX}/keyword`, { params: payload })))
}

