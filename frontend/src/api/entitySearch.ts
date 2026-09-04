/**
 * 实体检索 API（Milvus 混合搜索：m3e 语义 + BM25 关键词 + 图直查浏览）。
 *
 * 后端接口前缀：/api/v1/entity-search
 */

import { http } from './http'
import { currentUserId, currentUserIsAdmin } from './currentUser'

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
  mode: 'browse' | 'hybrid' | 'dense' | 'sparse'
}

export interface EntityIndexStatus {
  indexed: boolean
  entityCount: number
  typeCounts: Record<string, number>
  types: EntityTypeCount[]
  graphSpace: string | null
  embeddingModel: string | null
  updatedAt: string | null
  collectionExists: boolean
  bm25Ready: boolean
  reindexing: boolean
}

export interface EntityReindexResult {
  entityCount: number
  typeCounts: Record<string, number>
  graphSpace: string
  embeddingModel: string
  durationSeconds: number
}

const PREFIX = '/v1/entity-search'

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.code !== 200) {
    throw new Error(response.msg || `实体检索接口请求失败：${response.code}`)
  }
  return response.data
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

export async function browseEntities(payload: {
  space?: string | null
  entityType?: string | null
  limit?: number
  offset?: number
}): Promise<EntityListResult> {
  return unwrap(
    await asApiPromise<EntityListResult>(
      http.get(`${PREFIX}/entities`, { params: payload }),
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
}): Promise<EntityListResult> {
  return unwrap(
    await asApiPromise<EntityListResult>(http.post(`${PREFIX}/search`, payload)),
  )
}

export async function reindexEntities(options?: {
  space?: string
  entityTypes?: string[]
}): Promise<EntityReindexResult> {
  return unwrap(
    await asApiPromise<EntityReindexResult>(
      http.post(`${PREFIX}/reindex`, options ?? {}, {
        headers: { 'X-User-Id': currentUserId() },
        // 全量重建是长操作（千级实体含 embedding 约 1 分钟），默认 20s 超时
        // 会在完成前中断请求——用户只看到失败提示，后台仍在重建
        timeout: 600_000,
      }),
    ),
  )
}

export function canReindexEntityIndex(): boolean {
  return currentUserIsAdmin()
}
