import type { AxiosError } from 'axios'

import { fetchEventSource } from '@microsoft/fetch-event-source'

import { http } from './http'

export interface ApiResponse<T> {
  code: number
  success: boolean
  data: T
  msg: string
}

export interface SchemaOverview {
  currentVersion: string
  environment: string
  releasedAt: string
  entityTypes: number
  coreEntityTypes: number
  relationTypes: number
  factRelationTypes: number
  inferredRelationTypes: number
  propertyFields: number
  requiredFields: number
  constraintRules: number
  sourceMappings: number
}

export interface SchemaProperty {
  name: string
  dataType: string
  required: boolean
  rule: string
  category: 'core' | 'dynamic'
}

export interface SchemaScript {
  filename: string
  contentType: string
  sizeBytes: number
  etag: string | null
  sha256: string
  uploadedBy: string
  uploadedAt: string | null
  workflowDefinitionId: string | null
  workflowFunctionName: string | null
  downloadUrl: string
}

export interface SchemaDefinition {
  id: string
  key: string
  kind: 'entity' | 'relation'
  kindLabel: '实体' | '关系'
  name: string
  label: string
  description: string
  identityKey: string
  attributeIdentityKey: string
  attributeSource: string
  instanceCount: number
  version: string
  isCore: boolean
  relationCategory: 'fact' | 'inferred' | null
  isSystem: boolean
  createdBy: string | null
  createdAt: string | null
  updatedAt: string | null
  sourceSchemaId: string | null
  sourceSchemaName: string | null
  targetSchemaId: string | null
  targetSchemaName: string | null
  mappings: string[]
  canDelete: boolean
  properties: SchemaProperty[]
  script: SchemaScript | null
  llmConfigId: string | null
  ddlStatement: string | null
  ddlStatus: 'pending' | 'succeeded' | 'failed' | 'skipped'
  ddlError: string | null
  ddlExecutedAt: string | null
}

export interface SchemaListData {
  items: SchemaDefinition[]
  total: number
  page: number
  pageSize: number
}

export interface SchemaPropertyInput {
  name: string
  dataType: string
  required: boolean
  rule?: string
  category?: 'core' | 'dynamic'
}

export interface EntitySchemaCreatePayload {
  schemaKey: string
  name: string
  label: string
  description: string
  identityKey: string
  properties: SchemaPropertyInput[]
  mappings?: string[]
  isCore?: boolean
  version?: string
  llmConfigId?: string | null
}

export interface RelationSchemaCreatePayload {
  schemaKey: string
  name: string
  label: string
  description: string
  sourceSchemaId: string
  targetSchemaId: string
  sourceExpression: string
  targetExpression: string
  relationCategory: 'fact' | 'inferred'
  properties: SchemaPropertyInput[]
  mappings?: string[]
  version?: string
  llmConfigId?: string | null
}

const PREFIX = '/v1/schema-management'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.code !== 200) {
    throw new Error(response.msg || `Schema 接口请求失败：${response.code}`)
  }
  return response.data
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

export async function getSchemaOverview(): Promise<SchemaOverview> {
  return unwrap(
    await asApiPromise<SchemaOverview>(http.get(`${PREFIX}/overview`)),
  )
}

export interface SchemaTopology {
  nodes: SchemaDefinition[]
  edges: Array<SchemaDefinition & { sourceSchemaId: string | null; targetSchemaId: string | null }>
}

export async function getSchemaTopology(): Promise<SchemaTopology> {
  return unwrap(
    await asApiPromise<SchemaTopology>(http.get(`${PREFIX}/schemas/topology`)),
  )
}

export async function listAllSchemas(userId: string): Promise<SchemaDefinition[]> {
  const first = unwrap(
    await asApiPromise<SchemaListData>(
      http.get(`${PREFIX}/schemas`, {
        params: { page: 1, pageSize: 100, includeDetails: true },
        headers: headers(userId),
      }),
    ),
  )
  if (first.total <= first.items.length) return first.items

  const pageCount = Math.ceil(first.total / first.pageSize)
  const remaining = await Promise.all(
    Array.from({ length: pageCount - 1 }, (_, index) => index + 2).map(
      async (page) =>
        unwrap(
          await asApiPromise<SchemaListData>(
            http.get(`${PREFIX}/schemas`, {
              params: { page, pageSize: 100, includeDetails: true },
              headers: headers(userId),
            }),
          ),
        ).items,
    ),
  )
  return [...first.items, ...remaining.flat()]
}

async function createSchema<T extends object>(
  path: string,
  payload: T,
  userId: string,
): Promise<SchemaDefinition> {
  return unwrap(
    await asApiPromise<SchemaDefinition>(
      http.post(`${PREFIX}${path}`, payload, { headers: headers(userId) }),
    ),
  )
}

export function createEntitySchema(
  payload: EntitySchemaCreatePayload,
  userId: string,
) {
  return createSchema('/schemas/entities', payload, userId)
}

export function createRelationSchema(
  payload: RelationSchemaCreatePayload,
  userId: string,
) {
  return createSchema('/schemas/relations', payload, userId)
}

export async function replaceSchemaScript(
  schemaId: string,
  script: File,
  userId: string,
): Promise<SchemaDefinition> {
  const body = new FormData()
  body.append('script', script)
  return unwrap(
    await asApiPromise<SchemaDefinition>(
      http.put(`${PREFIX}/schemas/${schemaId}/script`, body, {
        headers: headers(userId),
      }),
    ),
  )
}

export function schemaErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<{ detail?: string | Array<{ msg?: string }> }>
  const detail = axiosError.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).filter(Boolean).join('；')
  }
  return error instanceof Error ? error.message : 'Schema 服务请求失败'
}

export interface ScriptContent {
  filename: string
  content: string
  contentType: string
  sizeBytes: number
  sha256: string
  uploadedAt: string | null
}

export async function getScriptContent(
  schemaId: string,
  userId: string,
): Promise<ScriptContent> {
  return unwrap(
    await asApiPromise<ScriptContent>(
      http.get(`${PREFIX}/schemas/${schemaId}/script/content`, {
        headers: headers(userId),
      }),
    ),
  )
}

export interface VerifyScriptInfo {
  scriptId: string | null
  filename: string
  sha256: string | null
  sizeBytes: number
  uploadedAt: string | null
}

export interface VerifyScriptHandlers {
  onProgress?: (stage: string, message: string) => void
  onSuccess?: (script: VerifyScriptInfo) => void
  onError?: (message: string, issues: string[], stage: string) => void
}

/**
 * 上传脚本 → LLM 安全校验 → 保存，以 SSE 流式回传进度。
 * 走 fetchEventSource（支持 POST + 自定义头 + 流式），不能用 axios（其响应拦截器会解包且不支持流）。
 */
export async function verifyAndSaveScript(
  schemaId: string,
  file: File,
  userId: string,
  handlers: VerifyScriptHandlers,
): Promise<void> {
  const baseUrl = import.meta.env.VITE_API_BASE || '/api'
  const url = `${baseUrl}${PREFIX}/schemas/${schemaId}/script/verify`
  const body = new FormData()
  body.append('script', file)
  await fetchEventSource(url, {
    method: 'POST',
    headers: { 'X-User-Id': userId },
    body,
    openWhenHidden: true,
    async onopen(response: Response): Promise<void> {
      if (response.ok) return
      let detail = `校验请求失败：${response.status}`
      try {
        const data = (await response.json()) as { detail?: unknown }
        if (typeof data.detail === 'string') detail = data.detail
        else if (Array.isArray(data.detail)) {
          detail = data.detail
            .map((item) => (item as { msg?: string }).msg)
            .filter(Boolean)
            .join('；')
        }
      } catch {
        // ignore JSON parse error
      }
      throw new Error(detail)
    },
    onmessage(ev) {
      if (!ev.data) return
      let payload: {
        type: string
        stage?: string
        message?: string
        issues?: string[]
        script?: VerifyScriptInfo
      }
      try {
        payload = JSON.parse(ev.data)
      } catch {
        return
      }
      if (payload.type === 'progress') {
        handlers.onProgress?.(payload.stage || '', payload.message || '')
      } else if (payload.type === 'success') {
        handlers.onSuccess?.(payload.script as VerifyScriptInfo)
      } else if (payload.type === 'error') {
        handlers.onError?.(
          payload.message || '校验失败',
          payload.issues || [],
          payload.stage || '',
        )
      }
    },
    onerror(err) {
      throw err
    },
  })
}
