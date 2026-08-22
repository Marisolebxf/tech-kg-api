/**
 * 科技专家直接关系 API。
 * 后端：/api/v1/kg-construction/expert-direct-relations
 */

import { http } from './http'

export interface DirectRelationExpert {
  expertId: string
  name: string
  organization?: string | null
  title: string
  paperCount: number
  citationCount: number
  hIndex: number
}

export interface DirectRelationItem {
  key: string
  relationType: string
  expertA: DirectRelationExpert
  expertB: DirectRelationExpert
  institution?: string | null
  coPaperCount: number
  relationStrength: number
  reasonTags: string[]
  relationSummary: string
  lastUpdatedAt?: string | null
  detailRows: Array<[string, unknown]>
}

export interface DirectRelationGraphNode {
  id: string
  type: string
  label: string
  subtitle?: string | null
  data: Record<string, unknown>
}

export interface DirectRelationGraphEdge {
  source: string
  target: string
  label: string
  data: Record<string, unknown>
}

export interface DirectRelationQueryResult {
  taskName: string
  input: Record<string, unknown>
  total: number
  items: DirectRelationItem[]
  graph: {
    nodes: DirectRelationGraphNode[]
    edges: DirectRelationGraphEdge[]
  }
  source: Record<string, unknown>
  apiResultExample: Record<string, unknown>
}

export interface DirectRelationQueryRequest {
  dataSource?: 'all'
  expertAId?: string
  expertBId?: string
  institution?: string
  startTime?: string
  endTime?: string
  limit?: number
}

export function describeExpertDirectRelation() {
  return http.get<Record<string, unknown>>('/v1/kg-construction/expert-direct-relations')
}

export function queryExpertDirectRelation(body: DirectRelationQueryRequest) {
  return http.post<DirectRelationQueryResult>(
    '/v1/kg-construction/expert-direct-relations/query',
    body,
  )
}
