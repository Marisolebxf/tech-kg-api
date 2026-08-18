/**
 * 科技产业链全景图 API。
 *
 * 后端接口路径：
 * POST /api/v1/kg-construction/industry-chain-panorama/query
 *
 * 该接口直接返回全景图结果，未使用统一 ApiResponse 包裹。
 * frontend/src/api/http.ts 已设置 baseURL 为 /api 并解包 response.data，
 * 因此本文件仅使用 /v1/kg-construction/... 路径。
 */

import type { AlumniProvenance } from './expertAlumniRelation'
import { http } from './http'


/**
 * 请求参数。
 */
export interface IndustryChainPanoramaQueryRequest {
  dataSource?: 'all'
  industry?: string | null
  anchorId?: string | null
  depth?: number
  topK?: number
}


/**
 * 分层中的关键实体。
 */
export interface PanoramaKeyEntity {
  id: string
  label: string
  type: string
  subtitle: string | null
  metric: string | null
  metricValue: number | null
}


/**
 * 全景图分层：核心技术 / 领军企业 / 领军专家 / 代表成果。
 */
export type PanoramaLayerKey =
  | 'core_technology'
  | 'leading_enterprise'
  | 'leading_expert'
  | 'flagship_achievement'


export interface PanoramaLayer {
  key: PanoramaLayerKey | string
  title: string
  total: number
  items: PanoramaKeyEntity[]
}


/**
 * 图谱节点：type 为后端节点主标签（Person/Organization/Paper/...）。
 */
export interface PanoramaGraphNode {
  id: string
  type: string
  label: string
  subtitle: string | null
  data: Record<string, unknown>
}


/**
 * 图谱边：source/target 为节点 id，label 为后端边类型（如 AFFILIATED_WITH）。
 */
export interface PanoramaGraphEdge {
  source: string
  target: string
  label: string
  data: Record<string, unknown>
}


/**
 * 全景图规模摘要。
 */
export interface PanoramaSummary {
  industry: string | null
  totalNodes: number
  totalEdges: number
  nodesByLabel: Record<string, number>
  edgesByType: Record<string, number>
}


/**
 * 数据来源信息，用于区分真实图查询结果与降级样例。
 */
export interface PanoramaSource {
  requested: string
  actual: string
  fallback: boolean
  reason?: string
}


/**
 * 全景图接口返回结构。
 */
export interface IndustryChainPanoramaQueryResponse {
  taskName: string
  input: Record<string, unknown>
  summary: PanoramaSummary
  layers: PanoramaLayer[]
  graph: {
    nodes: PanoramaGraphNode[]
    edges: PanoramaGraphEdge[]
  }
  source: PanoramaSource
  provenance?: AlumniProvenance
  apiResultExample: Record<string, unknown>
}


const PANORAMA_QUERY_ENDPOINT = '/v1/kg-construction/industry-chain-panorama/query'


/**
 * 触发产业链全景图查询。
 */
export function queryIndustryChainPanorama(
  request: IndustryChainPanoramaQueryRequest,
) {
  return http.post<
    IndustryChainPanoramaQueryResponse,
    IndustryChainPanoramaQueryResponse
  >(PANORAMA_QUERY_ENDPOINT, request)
}
