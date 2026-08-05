import type { AxiosError } from 'axios'

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
  safetyValidationId: string | null
  safetyStatus: 'approved' | 'legacy'
  safetySummary: string
  safetyIssues: ScriptSafetyIssue[]
  safetyModel: string | null
  safetyValidatedAt: string | null
  downloadUrl: string
}

export interface ScriptSafetyIssue {
  severity: 'critical' | 'high' | 'medium' | 'low'
  category: string
  line: number | null
  message: string
  suggestion: string
}

export type ScriptValidationOperation = 'replace' | 'create_entity' | 'create_relation'
export type ScriptValidationStatus = 'queued' | 'running' | 'succeeded' | 'failed'
export type ScriptValidationStage =
  | 'queued'
  | 'static_analysis'
  | 'llm_review'
  | 'persisting'
  | 'completed'

export interface ScriptValidation {
  id: string
  operation: ScriptValidationOperation
  schemaId: string | null
  filename: string
  sizeBytes: number
  sha256: string
  status: ScriptValidationStatus
  stage: ScriptValidationStage
  progress: number
  message: string
  summary: string
  issues: ScriptSafetyIssue[]
  result: SchemaDefinition | null
  resultSchemaId: string | null
  errorCode: string | null
  createdAt: string | null
  startedAt: string | null
  completedAt: string | null
  eventsUrl: string
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
  mappings: string[]
  isCore?: boolean
  version?: string
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
}

const PREFIX = '/v1/schema-management'

function headers(userId: string) {
  return { 'X-User-Id': userId }
}

function unwrap<T>(response: ApiResponse<T>): T {
  if (!response.success) {
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
  script: File,
  userId: string,
): Promise<SchemaDefinition> {
  const body = new FormData()
  body.append('metadata', JSON.stringify(payload))
  body.append('script', script)
  return unwrap(
    await asApiPromise<SchemaDefinition>(
      http.post(`${PREFIX}${path}`, body, { headers: headers(userId) }),
    ),
  )
}

export function createEntitySchema(
  payload: EntitySchemaCreatePayload,
  script: File,
  userId: string,
) {
  return createSchema('/schemas/entities', payload, script, userId)
}

export function createRelationSchema(
  payload: RelationSchemaCreatePayload,
  script: File,
  userId: string,
) {
  return createSchema('/schemas/relations', payload, script, userId)
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

export async function startScriptValidation(
  operation: ScriptValidationOperation,
  script: File,
  userId: string,
  options: { schemaId?: string; metadata?: object } = {},
): Promise<ScriptValidation> {
  const body = new FormData()
  body.append('operation', operation)
  body.append('script', script)
  if (options.schemaId) body.append('schemaId', options.schemaId)
  if (options.metadata) body.append('metadata', JSON.stringify(options.metadata))
  return unwrap(
    await asApiPromise<ScriptValidation>(
      http.post(`${PREFIX}/script-validations`, body, { headers: headers(userId) }),
    ),
  )
}

export function watchScriptValidation(
  eventsUrl: string,
  userId: string,
  onUpdate: (validation: ScriptValidation) => void,
  onConnectionError: () => void,
): () => void {
  const separator = eventsUrl.includes('?') ? '&' : '?'
  const source = new EventSource(
    `${eventsUrl}${separator}userId=${encodeURIComponent(userId)}`,
  )
  const handle = (event: Event) => {
    const validation = JSON.parse((event as MessageEvent<string>).data) as ScriptValidation
    onUpdate(validation)
    if (validation.status === 'succeeded' || validation.status === 'failed') {
      source.close()
    }
  }
  source.addEventListener('status', handle)
  source.addEventListener('completed', handle)
  source.addEventListener('failed', handle)
  source.onerror = () => {
    if (source.readyState === EventSource.CLOSED) return
    source.close()
    onConnectionError()
  }
  return () => source.close()
}

export function schemaErrorMessage(error: unknown): string {
  const axiosError = error as AxiosError<{
    msg?: string
    detail?: string | Array<{ msg?: string }>
  }>
  if (axiosError.response?.data?.msg) return axiosError.response.data.msg
  const detail = axiosError.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map((item) => item.msg).filter(Boolean).join('；')
  }
  return error instanceof Error ? error.message : 'Schema 服务请求失败'
}
