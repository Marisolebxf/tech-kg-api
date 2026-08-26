import type { ApiResponse } from './schemaManagement'
import { http } from './http'
import { currentUserId } from './llmConfig'

export interface EmbeddingConfig {
  id: string
  name: string
  description: string
  baseUrl: string
  model: string
  dimensions: number | null
  owner: string
  isDefault: boolean
  status: string
  hasApiKey: boolean
  apiKeyMasked: string
  createdAt: string
  updatedAt: string
}

export interface EmbeddingConfigInput {
  name: string
  description?: string
  baseUrl: string
  apiKey?: string
  model: string
  dimensions?: number | null
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface EmbeddingConfigUpdateInput {
  name?: string
  description?: string
  baseUrl?: string
  apiKey?: string
  model?: string
  dimensions?: number | null
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface TestConnectionResult {
  ok: boolean
  latencyMs: number | null
  error: string | null
}

const PREFIX = '/v1/embedding-config'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.code !== 200) {
    throw new Error(response.msg || `embedding 配置接口请求失败：${response.code}`)
  }
  return response.data
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

export async function listEmbeddingConfigs(userId = currentUserId()): Promise<EmbeddingConfig[]> {
  return unwrap(await asApiPromise<EmbeddingConfig[]>(http.get(PREFIX, { headers: headers(userId) })))
}

export async function getEmbeddingConfig(id: string, userId = currentUserId()): Promise<EmbeddingConfig> {
  return unwrap(await asApiPromise<EmbeddingConfig>(http.get(`${PREFIX}/${id}`, { headers: headers(userId) })))
}

export async function createEmbeddingConfig(
  payload: EmbeddingConfigInput,
  userId = currentUserId(),
): Promise<EmbeddingConfig> {
  return unwrap(
    await asApiPromise<EmbeddingConfig>(http.post(PREFIX, payload, { headers: headers(userId) })),
  )
}

export async function updateEmbeddingConfig(
  id: string,
  payload: EmbeddingConfigUpdateInput,
  userId = currentUserId(),
): Promise<EmbeddingConfig> {
  return unwrap(
    await asApiPromise<EmbeddingConfig>(http.put(`${PREFIX}/${id}`, payload, { headers: headers(userId) })),
  )
}

export async function deleteEmbeddingConfig(id: string, userId = currentUserId()): Promise<void> {
  await unwrap(
    await asApiPromise<{ deleted: boolean }>(http.delete(`${PREFIX}/${id}`, { headers: headers(userId) })),
  )
}

export async function setDefaultEmbeddingConfig(id: string, userId = currentUserId()): Promise<EmbeddingConfig> {
  return unwrap(
    await asApiPromise<EmbeddingConfig>(
      http.post(`${PREFIX}/${id}/set-default`, {}, { headers: headers(userId) }),
    ),
  )
}

export async function testEmbeddingConfig(id: string, userId = currentUserId()): Promise<TestConnectionResult> {
  return unwrap(
    await asApiPromise<TestConnectionResult>(
      http.post(`${PREFIX}/${id}/test`, {}, { headers: headers(userId) }),
    ),
  )
}
