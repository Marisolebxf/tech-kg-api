import type { ApiResponse } from './schemaManagement'
import { http } from './http'
import { currentUserId } from './llmConfig'

export interface MilvusConfig {
  id: string
  name: string
  description: string
  uri: string
  defaultDb: string
  owner: string
  isDefault: boolean
  status: string
  hasToken: boolean
  tokenMasked: string
  createdAt: string
  updatedAt: string
}

export interface MilvusConfigInput {
  name: string
  description?: string
  uri?: string
  token?: string
  defaultDb?: string
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface MilvusConfigUpdateInput {
  name?: string
  description?: string
  uri?: string
  token?: string
  defaultDb?: string
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface TestConnectionResult {
  ok: boolean
  latencyMs: number | null
  error: string | null
}

const PREFIX = '/v1/milvus-configs'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.code !== 200) {
    throw new Error(response.msg || `Milvus 配置接口请求失败：${response.code}`)
  }
  return response.data
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

export async function listMilvusConfigs(userId = currentUserId()): Promise<MilvusConfig[]> {
  return unwrap(await asApiPromise<MilvusConfig[]>(http.get(PREFIX, { headers: headers(userId) })))
}

export async function getMilvusConfig(id: string, userId = currentUserId()): Promise<MilvusConfig> {
  return unwrap(await asApiPromise<MilvusConfig>(http.get(`${PREFIX}/${id}`, { headers: headers(userId) })))
}

export async function createMilvusConfig(
  payload: MilvusConfigInput,
  userId = currentUserId(),
): Promise<MilvusConfig> {
  return unwrap(
    await asApiPromise<MilvusConfig>(http.post(PREFIX, payload, { headers: headers(userId) })),
  )
}

export async function updateMilvusConfig(
  id: string,
  payload: MilvusConfigUpdateInput,
  userId = currentUserId(),
): Promise<MilvusConfig> {
  return unwrap(
    await asApiPromise<MilvusConfig>(http.put(`${PREFIX}/${id}`, payload, { headers: headers(userId) })),
  )
}

export async function deleteMilvusConfig(id: string, userId = currentUserId()): Promise<void> {
  await unwrap(
    await asApiPromise<{ deleted: boolean }>(http.delete(`${PREFIX}/${id}`, { headers: headers(userId) })),
  )
}

export async function setDefaultMilvusConfig(id: string, userId = currentUserId()): Promise<MilvusConfig> {
  return unwrap(
    await asApiPromise<MilvusConfig>(
      http.post(`${PREFIX}/${id}/set-default`, {}, { headers: headers(userId) }),
    ),
  )
}

export async function testMilvusConfig(id: string, userId = currentUserId()): Promise<TestConnectionResult> {
  return unwrap(
    await asApiPromise<TestConnectionResult>(
      http.post(`${PREFIX}/${id}/test`, {}, { headers: headers(userId) }),
    ),
  )
}

export async function listMilvusDatabases(id: string, userId = currentUserId()): Promise<string[]> {
  return unwrap(
    await asApiPromise<{ items: string[] }>(http.get(`${PREFIX}/${id}/databases`, { headers: headers(userId) })),
  ).items
}
