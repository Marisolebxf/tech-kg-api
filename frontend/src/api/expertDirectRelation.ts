/**
 * 科技专家/人才直接关系 API。
 *
 * 后端接口路径：
 * POST /api/v1/kg-construction/expert-direct-relations/query
 *
 * 该接口直接返回业务结果，未使用统一 ApiResponse 包裹。
 * frontend/src/api/http.ts 已设置 baseURL 为 /api 并解包 response.data，
 * 因此本文件仅使用 /v1/kg-construction/... 路径。
 */

import { http } from './http'


/**
 * 请求参数。
 */
export interface ExpertDirectRelationQueryRequest {
  dataSource?: 'all'
  expertAId?: string | null
  expertBId?: string | null
  institution?: string | null
  startTime?: string | null
  endTime?: string | null
  limit?: number
}


/**
 * 关系两端的专家信息。
 */
export interface DirectRelationExpert {
  expertId: string
  name: string
  organization: string | null
  title: string
  paperCount: number
  citationCount: number
  hIndex: number
}


/**
 * 单条直接关系记录。
 */
export interface DirectRelationItem {
  key: string
  relationType: string
  expertA: DirectRelationExpert
  expertB: DirectRelationExpert
  institution: string | null
  coPaperCount: number
  relationStrength: number
  reasonTags: string[]
  relationSummary: string
  lastUpdatedAt: string | null
  detailRows: Array<Array<string | number | string[]>>
}


/**
 * 图谱节点：type 为业务节点类型（expert/institution 等）。
 */
export interface DirectRelationGraphNode {
  id: string
  type: string
  label: string
  subtitle: string | null
  data: Record<string, unknown>
}


/**
 * 图谱边：source/target 为节点 id，label 为业务边描述。
 */
export interface DirectRelationGraphEdge {
  source: string
  target: string
  label: string
  data: Record<string, unknown>
}


/**
 * 数据来源信息，用于区分真实图查询结果与降级样例。
 */
export interface DirectRelationSource {
  requested: string
  actual: string
  fallback: boolean
  reason?: string
}


/**
 * 接口返回结构。
 */
export interface ExpertDirectRelationQueryResponse {
  taskName: string
  input: Record<string, unknown>
  total: number
  items: DirectRelationItem[]
  graph: {
    nodes: DirectRelationGraphNode[]
    edges: DirectRelationGraphEdge[]
  }
  source: DirectRelationSource
  apiResultExample: Record<string, unknown>
}


const EXPERT_DIRECT_RELATION_ENDPOINT = '/v1/kg-construction/expert-direct-relations/query'


/**
 * 触发专家直接关系查询。
 */
export function queryExpertDirectRelation(
  request: ExpertDirectRelationQueryRequest,
) {
  return http.post<
    ExpertDirectRelationQueryResponse,
    ExpertDirectRelationQueryResponse
  >(EXPERT_DIRECT_RELATION_ENDPOINT, request)
}
