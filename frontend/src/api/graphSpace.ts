import type { ApiResponse } from './schemaManagement'
import { http } from './http'
import { currentUserId } from './currentUser'

const PREFIX = '/v1/graph-spaces'

export interface GraphSpaceItem {
  name: string
  bound: boolean
  mine: boolean
}

export interface BoundGraphSpace {
  name: string
  createdAt: string
}

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

/** 列出图空间：管理员返回全量（带 bound/mine 标记），普通用户仅返回自己绑定的。 */
export async function listGraphSpaces(userId = currentUserId()): Promise<string[]> {
  const items = await listGraphSpaceItems(userId)
  return items.map((item) => item.name)
}

/** 列出图空间（完整 item 结构）。 */
export async function listGraphSpaceItems(userId = currentUserId()): Promise<GraphSpaceItem[]> {
  return unwrap(
    await asApiPromise<{ items: GraphSpaceItem[] }>(http.get(PREFIX, { headers: headers(userId) })),
  ).items
}

/** 新建图空间（真实 CREATE SPACE，创建后自动绑定到当前用户）。 */
export async function createGraphSpace(name: string, userId = currentUserId()): Promise<GraphSpaceItem> {
  return unwrap(
    await asApiPromise<GraphSpaceItem>(http.post(PREFIX, { name }, { headers: headers(userId) })),
  )
}

/** 绑定已有图空间。 */
export async function bindGraphSpace(name: string, userId = currentUserId()): Promise<GraphSpaceItem> {
  return unwrap(
    await asApiPromise<GraphSpaceItem>(
      http.post(`${PREFIX}/${encodeURIComponent(name)}/bind`, {}, { headers: headers(userId) }),
    ),
  )
}

/** 解除绑定（仅删绑定关系，不删除图空间数据）。 */
export async function unbindGraphSpace(name: string, userId = currentUserId()): Promise<void> {
  await unwrap(
    await asApiPromise<{ unbound: boolean }>(
      http.delete(`${PREFIX}/${encodeURIComponent(name)}`, { headers: headers(userId) }),
    ),
  )
}
