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
  industry?: string | null
  anchorId?: string | null
  depth?: number
  topK?: number
  /** 关系筛选：只保留这些边类型（如 COAUTHOR_WITH），留空表示不筛选。 */
  relationTypes?: string[]
  /** true 时忽略服务端缓存，强制重新组装分层与子图（页面「刷新图谱」用）。 */
  refresh?: boolean
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
 * 查询超时（ms）。
 *
 * 该接口要拉 4 个分层再拼子图，冷缓存或大产业下耗时明显高于普通查询；
 * 后端 graph_api_client / trs-graph 侧超时均为 30s，前端若沿用 axios 默认的
 * 20s 会先于后端掐断请求，浏览器只能看到一个没有响应体的失败请求。
 * 故与校友 / 同事 / 两点合作等同类查图接口保持一致，放宽到 60s。
 */
const PANORAMA_QUERY_TIMEOUT_MS = 60_000


/**
 * 触发产业链全景图查询。
 *
 * @param request 查询参数。
 * @param signal 可选的取消信号，用于自动更新与手动刷新并发时丢弃旧请求。
 */
export function queryIndustryChainPanorama(
  request: IndustryChainPanoramaQueryRequest,
  signal?: AbortSignal,
) {
  return http.post<
    IndustryChainPanoramaQueryResponse,
    IndustryChainPanoramaQueryResponse
  >(PANORAMA_QUERY_ENDPOINT, request, {
    timeout: PANORAMA_QUERY_TIMEOUT_MS,
    signal,
  })
}
