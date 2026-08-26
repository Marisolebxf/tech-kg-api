import type { ApiResponse } from './schemaManagement'
import { http } from './http'
import { currentUserId } from './llmConfig'

const PREFIX = '/v1/graph-spaces'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.code !== 200) {
    throw new Error(response.msg || `图空间接口请求失败：${response.code}`)
  }
  return response.data
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

/** 列出 NebulaGraph 所有图空间（只读，空间在图服务侧管理）。 */
export async function listGraphSpaces(userId = currentUserId()): Promise<string[]> {
  return unwrap(
    await asApiPromise<{ items: string[] }>(http.get(PREFIX, { headers: headers(userId) })),
  ).items
}
