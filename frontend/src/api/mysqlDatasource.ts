import type { ApiResponse } from './schemaManagement'
import { http } from './http'
import { currentUserId } from './llmConfig'

export interface MysqlDatasource {
  id: string
  name: string
  description: string
  host: string
  port: number
  defaultDatabase: string
  username: string
  owner: string
  isDefault: boolean
  status: string
  hasPassword: boolean
  passwordMasked: string
  createdAt: string
  updatedAt: string
}

export interface MysqlDatasourceInput {
  name: string
  description?: string
  host: string
  port?: number
  defaultDatabase?: string
  username: string
  password?: string
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface MysqlDatasourceUpdateInput {
  name?: string
  description?: string
  host?: string
  port?: number
  defaultDatabase?: string
  username?: string
  password?: string
  owner?: string
  isDefault?: boolean
  status?: string
}

export interface TestConnectionResult {
  ok: boolean
  latencyMs: number | null
  error: string | null
}

const PREFIX = '/v1/mysql-datasources'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.code !== 200) {
    throw new Error(response.msg || `MySQL 数据源接口请求失败：${response.code}`)
  }
  return response.data
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

export async function listMysqlDatasources(userId = currentUserId()): Promise<MysqlDatasource[]> {
  return unwrap(await asApiPromise<MysqlDatasource[]>(http.get(PREFIX, { headers: headers(userId) })))
}

export async function getMysqlDatasource(id: string, userId = currentUserId()): Promise<MysqlDatasource> {
  return unwrap(await asApiPromise<MysqlDatasource>(http.get(`${PREFIX}/${id}`, { headers: headers(userId) })))
}

export async function createMysqlDatasource(
  payload: MysqlDatasourceInput,
  userId = currentUserId(),
): Promise<MysqlDatasource> {
  return unwrap(
    await asApiPromise<MysqlDatasource>(http.post(PREFIX, payload, { headers: headers(userId) })),
  )
}

export async function updateMysqlDatasource(
  id: string,
  payload: MysqlDatasourceUpdateInput,
  userId = currentUserId(),
): Promise<MysqlDatasource> {
  return unwrap(
    await asApiPromise<MysqlDatasource>(http.put(`${PREFIX}/${id}`, payload, { headers: headers(userId) })),
  )
}

export async function deleteMysqlDatasource(id: string, userId = currentUserId()): Promise<void> {
  await unwrap(
    await asApiPromise<{ deleted: boolean }>(http.delete(`${PREFIX}/${id}`, { headers: headers(userId) })),
  )
}

export async function setDefaultMysqlDatasource(id: string, userId = currentUserId()): Promise<MysqlDatasource> {
  return unwrap(
    await asApiPromise<MysqlDatasource>(
      http.post(`${PREFIX}/${id}/set-default`, {}, { headers: headers(userId) }),
    ),
  )
}

export async function testMysqlDatasource(id: string, userId = currentUserId()): Promise<TestConnectionResult> {
  return unwrap(
    await asApiPromise<TestConnectionResult>(
      http.post(`${PREFIX}/${id}/test`, {}, { headers: headers(userId) }),
    ),
  )
}

export async function listMysqlDatabases(id: string, userId = currentUserId()): Promise<string[]> {
  return unwrap(
    await asApiPromise<{ items: string[] }>(http.get(`${PREFIX}/${id}/databases`, { headers: headers(userId) })),
  ).items
}
