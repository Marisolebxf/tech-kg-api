/**
 * 科技两点合作成果 API。
 * 后端：/api/v1/kg-construction/expert-cooperation-achievements
 */

import { http } from './http'

export interface ApiResponse<T> {
  code: number
  success: boolean
  data: T
  msg: string
}

export interface CooperationItem {
  type: 'paper' | 'patent' | 'project' | (string & {})
  id: string
  title: string
  time?: string | null
  fields?: string[]
  awards?: unknown[]
  evaluation?: string | null
}

export interface CooperationSummaryRow {
  label: string
  value: string
}

export interface CooperationResultRow extends CooperationSummaryRow {
  tone?: string
}

export interface CooperationRule {
  name: string
  type: string
  target: string
  trigger: string
  logic: string
  output: string
  threshold: string
  audit: string
}

export interface CooperationEntity {
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

export interface CooperationRelation {
  id: string
  from: string
  to: string
  fromName?: string
  toName?: string
  label: string
  category: string
  summary?: string
}

export interface CooperationProvenance {
  sourceDatabase: string
  summary?: string
  evidences: Array<{
    title: string
    businessTable: string
    technicalTable: string
    recordId: string
    fieldIdentifier: string
    sourceField?: string
    graphVid?: string
    summary: string
  }>
}

export interface CooperationQueryResult {
  source: { id: string; name: string }
  target: { id: string; name: string }
  summary: { papers: number; patents: number; projects: number; awards: number }
  items: CooperationItem[]
  coreContribution: string
  cooperationMode: string
  sourceMeta: { space?: string; graph?: string; truncated?: boolean }
  summaryRows?: CooperationSummaryRow[]
  resultRows?: CooperationResultRow[]
  evidence?: string[]
  rules?: CooperationRule[]
  entities?: CooperationEntity[]
  relations?: CooperationRelation[]
  graph?: {
    nodes: CooperationEntity[]
    edges: Array<{ id: string; from: string; to: string; label: string; category: string }>
  }
  provenance?: CooperationProvenance
}

export type CooperationQueryRequest = {
  sourceExpertId: string
  targetExpertId: string
  achievementTypes?: Array<'paper' | 'patent' | 'project'>
  timeRangeStart?: string
  timeRangeEnd?: string
  limitPerType?: number
}

export function describeExpertCooperationAchievement() {
  return http.get<Record<string, unknown>>('/v1/kg-construction/expert-cooperation-achievements')
}

export function queryExpertCooperationAchievement(body: CooperationQueryRequest) {
  return http.post<ApiResponse<CooperationQueryResult>>(
    '/v1/kg-construction/expert-cooperation-achievements/query',
    body,
    // 与校友/同事一致；所属领域 LLM 已默认异步，图结果应远快于 60s
    { timeout: 60_000 },
  )
}
