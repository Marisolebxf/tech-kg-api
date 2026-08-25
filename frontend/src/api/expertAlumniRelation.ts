/**
 * 科技专家校友关系 API。
 * 后端：/api/v1/kg-construction/expert-alumni-relations
 */

import { http } from './http'

export interface ApiResponse<T> {
  code: number
  success: boolean
  data: T
  msg: string
}

export interface AlumniInteraction {
  coauthorEdge: boolean
  paperCount: number
  patentCount: number
  projectCount: number
  summary: string
}

export interface AlumniItem {
  alumniId: string
  name: string
  sharedInstitutions: string[]
  dimensions: string[]
  educations: unknown[]
  interactions: AlumniInteraction
}

export interface AlumniSummaryRow {
  label: string
  value: string
}

export interface AlumniResultRow extends AlumniSummaryRow {
  tone?: string
}

export interface AlumniRule {
  name: string
  type: string
  target: string
  trigger: string
  logic: string
  output: string
  threshold: string
  audit: string
}

export interface AlumniEntity {
  id: string
  label: string
  entityType: string
  nodeType?: string
  confidence: number
  relations: string
  evidence: string[]
  x?: number
  y?: number
}

export interface AlumniRelation {
  id: string
  from: string
  to: string
  fromName?: string
  toName?: string
  label: string
  category: string
  dimensions?: string[]
  sharedInstitutions?: string[]
  interactions?: AlumniInteraction
}

export interface AlumniProvenanceEvidence {
  title: string
  businessTable: string
  technicalTable: string
  recordId: string
  fieldIdentifier: string
  sourceField?: string
  graphVid?: string
  summary: string
}

export interface AlumniProvenance {
  sourceDatabase: string
  summary?: string
  evidences: AlumniProvenanceEvidence[]
}

export interface AlumniQueryResult {
  expert: { id: string; name: string; educations: unknown[] }
  mode: 'pair' | 'list'
  total: number
  items: AlumniItem[]
  dimensionsCatalog: string[]
  sourceMeta: { space?: string; graph?: string; truncated?: boolean }
  /** 前端结果详情 Tab 对齐字段 */
  summaryRows?: AlumniSummaryRow[]
  resultRows?: AlumniResultRow[]
  evidence?: string[]
  rules?: AlumniRule[]
  entities?: AlumniEntity[]
  relations?: AlumniRelation[]
  graph?: { nodes: AlumniEntity[]; edges: Array<{ id: string; from: string; to: string; label: string; category: string }> }
  provenance?: AlumniProvenance
}

export type AlumniQueryRequest = {
  expertId: string
  targetExpertId?: string
  school?: string
  educationStage?: string
  limit?: number
}

export function describeExpertAlumniRelation() {
  return http.get<Record<string, unknown>>('/v1/kg-construction/expert-alumni-relations')
}

export function queryExpertAlumniRelation(body: AlumniQueryRequest) {
  return http.post<ApiResponse<AlumniQueryResult>>(
    '/v1/kg-construction/expert-alumni-relations/query',
    body,
    { timeout: 60_000 },
  )
}
