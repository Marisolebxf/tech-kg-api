import type { AxiosError } from 'axios'

import { fetchEventSource } from '@microsoft/fetch-event-source'

import { apiBase } from '../config'
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
  category: 'core' | 'dynamic' | 'required' | 'provenance'
  locked?: boolean
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
  capturedRevision: number
  lastRunStatus: 'none' | 'ok' | 'failed'
  lastRunError: string | null
  /** 最近一次抽取收尾时间：null = 从未运行；早于 uploadedAt = 脚本已更新待重跑 */
  lastRunAt: string | null
  stale: boolean
  staleBehind: number
  /** 脚本对象在对象存储真实存在（系统 Schema 种子行只是目录占位，available=false） */
  available?: boolean
  /** 脚本上传后从未跑过、或上传时间晚于最近一次收尾（变更尚未应用到图数据） */
  needsRun: boolean
  downloadUrl: string
}

export interface SchemaDefinition {
  id: string
  key: string
  kind: 'entity' | 'relation'
  kindLabel: '实体' | '关系'
  graphSpace?: string
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
  canManageProperties?: boolean
  propertyRevision?: number
  properties: SchemaProperty[]
  sources?: SchemaSource[]
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
  category?: 'core' | 'dynamic' | 'required' | 'provenance'
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
  graphSpace?: string
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
  graphSpace?: string
}

const PREFIX = '/v1/schema-management'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

interface ValidationErrorItem {
  loc?: unknown[]
  msg?: string
}

function formatValidationErrors(items: ValidationErrorItem[]): string {
  return items
    .map((item) => {
      const field = Array.isArray(item.loc)
        ? item.loc.filter((part) => part !== 'body').join('.')
        : ''
      const message = item.msg || '校验失败'
      return field ? `${field}: ${message}` : message
    })
    .filter(Boolean)
    .join('；')
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success || response.code !== 200) {
    if (response.code === 422 && Array.isArray(response.data)) {
      const fieldErrors = formatValidationErrors(response.data as ValidationErrorItem[])
      const base = response.msg || '请求参数校验失败'
      throw new Error(fieldErrors ? `${base}：${fieldErrors}` : base)
    }
    throw new Error(response.msg || `Schema 接口请求失败：${response.code}`)
  }
  return response.data
}

function asApiPromise<T>(request: unknown): Promise<ApiResponse<T>> {
  return request as Promise<ApiResponse<T>>
}

export async function getSchemaOverview(graphSpace?: string): Promise<SchemaOverview> {
  return unwrap(
    await asApiPromise<SchemaOverview>(
      http.get(`${PREFIX}/overview`, { params: graphSpace ? { graphSpace } : undefined }),
    ),
  )
}

export interface SchemaTopology {
  nodes: SchemaDefinition[]
  edges: Array<SchemaDefinition & { sourceSchemaId: string | null; targetSchemaId: string | null }>
}

export async function getSchemaTopology(graphSpace?: string): Promise<SchemaTopology> {
  return unwrap(
    await asApiPromise<SchemaTopology>(
      http.get(`${PREFIX}/schemas/topology`, {
        params: graphSpace ? { graphSpace } : undefined,
      }),
    ),
  )
}

export interface SchemaPageQuery {
  kind?: 'entity' | 'relation'
  keyword?: string
  page?: number
  pageSize?: number
  includeDetails?: boolean
  graphSpace?: string
}

async function requestSchemaPage(
  userId: string,
  query: SchemaPageQuery = {},
): Promise<SchemaListData> {
  const {
    kind,
    keyword,
    page = 1,
    pageSize = 10,
    includeDetails = true,
    graphSpace,
  } = query
  return unwrap(
    await asApiPromise<SchemaListData>(
      http.get(`${PREFIX}/schemas`, {
        params: {
          kind,
          keyword: keyword?.trim() || undefined,
          page,
          pageSize,
          includeDetails,
          graphSpace,
        },
        headers: headers(userId),
      }),
    ),
  )
}

/** 服务端分页拉取 Schema 列表（列表页用，避免一次性拉全量导致开屏慢） */
export function listSchemasPaged(
  userId: string,
  query: SchemaPageQuery = {},
): Promise<SchemaListData> {
  return requestSchemaPage(userId, query)
}

/** 轻量拉取全部实体（不带属性/来源/脚本明细），供关系新建弹窗的起点/终点下拉 */
export async function listEntityOptions(
  userId: string,
  graphSpace?: string,
): Promise<SchemaDefinition[]> {
  const fetchPage = (page: number) =>
    requestSchemaPage(userId, {
      kind: 'entity',
      page,
      pageSize: 100,
      includeDetails: false,
      graphSpace,
    })
  const first = await fetchPage(1)
  if (first.total <= first.items.length) return first.items

  const pageCount = Math.ceil(first.total / first.pageSize)
  const remaining = await Promise.all(
    Array.from({ length: pageCount - 1 }, (_, index) => index + 2).map(
      async (page) => (await fetchPage(page)).items,
    ),
  )
  return [...first.items, ...remaining.flat()]
}

export async function listAllSchemas(
  userId: string,
  graphSpace?: string,
): Promise<SchemaDefinition[]> {
  const fetchPage = (page: number) =>
    requestSchemaPage(userId, { page, pageSize: 100, includeDetails: true, graphSpace })
  const first = await fetchPage(1)
  if (first.total <= first.items.length) return first.items

  const pageCount = Math.ceil(first.total / first.pageSize)
  const remaining = await Promise.all(
    Array.from({ length: pageCount - 1 }, (_, index) => index + 2).map(
      async (page) => (await fetchPage(page)).items,
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

export interface SchemaDeleteResult {
  id: string
  deleted: boolean
  scriptCleanupSucceeded?: boolean
  /** 图数据删除统计（真删：该类型全部点/边 + DROP TAG/EDGE） */
  graphData?: {
    status: 'succeeded' | 'failed'
    error: string | null
    typeExisted: boolean
    verticesDeleted: number
    edgesDeleted: number
    dropStatement: string | null
  }
}

/** 删除影响预览：实体返回仍引用它的关系清单（删除确认弹窗展示） */
export interface SchemaDeleteImpact {
  id: string
  kind: 'entity' | 'relation'
  kindLabel: '实体' | '关系'
  graphSpace: string
  name: string
  label: string
  isSystem: boolean
  canDelete: boolean
  referencingRelations: Array<{ id: string; name: string; label: string }>
}

export async function getSchemaDeleteImpact(
  schemaId: string,
  userId: string,
): Promise<SchemaDeleteImpact> {
  return unwrap(
    await asApiPromise<SchemaDeleteImpact>(
      http.get(`${PREFIX}/schemas/${schemaId}/delete-impact`, { headers: headers(userId) }),
    ),
  )
}

export interface SchemaSource {
  id: string
  datasourceId: string
  databaseName: string
  tableName: string
  pkColumn: string
  timeColumn: string
  /** 复杂 SQL 绑定（非空时分批读该查询而非整表） */
  querySql?: string | null
  position: number
}

export interface SchemaSourceInput {
  datasourceId: string
  databaseName: string
  tableName: string
  pkColumn: string
  timeColumn: string
}

export interface SchemaSourcesReplaceResult {
  sources: SchemaSource[]
}

export interface SchemaPropertyAddResult {
  property: SchemaProperty
  ddlStatement: string
  ddlStatus: 'succeeded' | 'failed'
  ddlError: string | null
}

export interface SchemaPropertyDeleteResult {
  deleted: boolean
  propertyName: string
  warnings: string[]
  ddlStatement: string | null
  ddlStatus: 'succeeded' | 'skipped' | 'failed'
  ddlError: string | null
}

export async function getSchemaDetail(
  schemaId: string,
  userId: string,
): Promise<SchemaDefinition> {
  return unwrap(
    await asApiPromise<SchemaDefinition>(
      http.get(`${PREFIX}/schemas/${schemaId}`, { headers: headers(userId) }),
    ),
  )
}

export async function addSchemaProperty(
  schemaId: string,
  payload: SchemaPropertyInput,
  userId: string,
): Promise<SchemaPropertyAddResult> {
  return unwrap(
    await asApiPromise<SchemaPropertyAddResult>(
      http.post(`${PREFIX}/schemas/${schemaId}/properties`, payload, {
        headers: headers(userId),
      }),
    ),
  )
}

export async function deleteSchemaProperty(
  schemaId: string,
  propertyName: string,
  userId: string,
): Promise<SchemaPropertyDeleteResult> {
  return unwrap(
    await asApiPromise<SchemaPropertyDeleteResult>(
      http.delete(`${PREFIX}/schemas/${schemaId}/properties/${encodeURIComponent(propertyName)}`, {
        headers: headers(userId),
      }),
    ),
  )
}

export async function replaceSchemaSources(
  schemaId: string,
  sources: SchemaSourceInput[],
  userId: string,
): Promise<SchemaSourcesReplaceResult> {
  return unwrap(
    await asApiPromise<SchemaSourcesReplaceResult>(
      http.put(`${PREFIX}/schemas/${schemaId}/sources`, { sources }, { headers: headers(userId) }),
    ),
  )
}

export interface SchemaExtractTriggerResult {
  executionId: string
  workflowId: string
  status: string
  staleScript?: boolean
  staleBehind?: number
}

export interface SchemaBackfillResult extends SchemaExtractTriggerResult {
  watermarksCleared: number
  forced: boolean
}

export async function backfillSchemaHistory(
  schemaId: string,
  userId: string,
  options?: { force?: boolean; graphSpace?: string; batchSize?: number },
): Promise<SchemaBackfillResult> {
  const body: Record<string, unknown> = {}
  if (options?.force) body.force = true
  if (options?.graphSpace) body.graphSpace = options.graphSpace
  if (options?.batchSize) body.batchSize = options.batchSize
  return unwrap(
    await asApiPromise<SchemaBackfillResult>(
      http.post(`${PREFIX}/schemas/${schemaId}/backfill`, body, { headers: headers(userId) }),
    ),
  )
}

export async function triggerSchemaExtraction(
  schemaId: string,
  userId: string,
  options?: { graphSpace?: string; batchSize?: number },
): Promise<SchemaExtractTriggerResult> {
  return unwrap(
    await asApiPromise<SchemaExtractTriggerResult>(
      http.post(
        `${PREFIX}/schemas/${schemaId}/extract`,
        options?.graphSpace || options?.batchSize
          ? { graphSpace: options.graphSpace, batchSize: options.batchSize }
          : {},
        { headers: headers(userId) },
      ),
    ),
  )
}

export async function deleteSchema(
  schemaId: string,
  userId: string,
): Promise<SchemaDeleteResult> {
  return unwrap(
    await asApiPromise<SchemaDeleteResult>(
      http.delete(`${PREFIX}/schemas/${schemaId}`, { headers: headers(userId) }),
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
  const baseUrl = apiBase
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
