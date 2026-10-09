import type { ApiResponse } from './schemaManagement'
import { unwrapApiResponse } from './graphSearch'
import { http } from './http'

export interface LlmConfig {
  id: string
  name: string
  description: string
  baseUrl: string
  model: string
  owner: string
  isDefault: boolean
  status: string
  hasApiKey: boolean
  apiKeyMasked: string
  createdAt: string
  updatedAt: string
}

export interface LlmConfigInput {
  name: string
  description?: string
  baseUrl: string
  apiKey?: string
  model: string
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface LlmConfigUpdateInput {
  name?: string
  description?: string
  baseUrl?: string
  apiKey?: string
  model?: string
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface TestConnectionResult {
  ok: boolean
  latencyMs: number | null
  error: string | null
}

const PREFIX = '/v1/llm-config'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

function unwrap<T>(response: ApiResponse<T>): T {
  // 422 字段级明细走共享解包（graphSearch.unwrapApiResponse），本文件只留兜底文案
  return unwrapApiResponse(response, 'LLM 配置接口请求失败')
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

export async function listLlmConfigs(userId: string): Promise<LlmConfig[]> {
  return unwrap(
    await asApiPromise<LlmConfig[]>(http.get(`${PREFIX}/llm-configs`, {
      headers: headers(userId),
    })),
  )
}

export async function createLlmConfig(
  payload: LlmConfigInput,
  userId: string,
): Promise<LlmConfig> {
  return unwrap(
    await asApiPromise<LlmConfig>(
      http.post(`${PREFIX}/llm-configs`, payload, { headers: headers(userId) }),
    ),
  )
}

export async function updateLlmConfig(
  id: string,
  payload: LlmConfigUpdateInput,
  userId: string,
): Promise<LlmConfig> {
  return unwrap(
    await asApiPromise<LlmConfig>(
      http.put(`${PREFIX}/llm-configs/${id}`, payload, { headers: headers(userId) }),
    ),
  )
}

export async function deleteLlmConfig(id: string, userId: string): Promise<void> {
  unwrap(
    await asApiPromise<{ deleted: boolean }>(
      http.delete(`${PREFIX}/llm-configs/${id}`, { headers: headers(userId) }),
    ),
  )
}

export async function setDefaultLlmConfig(
  id: string,
  userId: string,
): Promise<LlmConfig> {
  return unwrap(
    await asApiPromise<LlmConfig>(
      http.post(`${PREFIX}/llm-configs/${id}/set-default`, {}, { headers: headers(userId) }),
    ),
  )
}

export async function testLlmConfig(
  id: string,
  userId: string,
): Promise<TestConnectionResult> {
  return unwrap(
    await asApiPromise<TestConnectionResult>(
      http.post(`${PREFIX}/llm-configs/${id}/test`, {}, { headers: headers(userId) }),
    ),
  )
}

export async function verifyLlmConfig(
  payload: { baseUrl: string; model: string; apiKey: string },
  userId: string,
): Promise<TestConnectionResult> {
  return unwrap(
    await asApiPromise<TestConnectionResult>(
      http.post(`${PREFIX}/llm-configs/verify`, payload, { headers: headers(userId) }),
    ),
  )
}

export { currentUserId } from './currentUser'
