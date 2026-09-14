/**
 * 图谱搜索 API。
 *
 * 后端接口前缀：
 * /api/v1/graph-search
 *
 * frontend/src/api/http.ts 已设置 baseURL: '/api'，
 * 所以本文件只需要使用 /v1/graph-search。
 */

import { http } from './http'


/**
 * 后端统一响应结构。
 */
export interface ApiResponse<T> {
  code: number
  success: boolean
  data: T
  msg: string
}


/**
 * 图节点属性。
 *
 * 不同类型的节点具有不同属性，因此使用通用对象结构。
 */
export type GraphProperties = Record<string, unknown>


/**
 * 后端返回的图节点。
 */
export interface GraphNode {
  id: string
  labels: string[]
  properties: GraphProperties
}


/**
 * 后端返回的图关系边。
 */
export interface GraphEdge {
  id: string
  type: string
  source: string
  target: string
  properties: GraphProperties
}


/**
 * 标准图数据。
 */
export interface GraphData {
  nodes: GraphNode[]
  edges: GraphEdge[]
}


/**
 * 节点列表或属性搜索结果。
 */
export interface GraphNodeListData {
  items: GraphNode[]
  total: number
}


/**
 * 图空间列表。
 */
export interface GraphSpaceListData {
  spaces: string[]
}


/**
 * 图关系查询方向。
 */
export type GraphDirection = 'out' | 'in' | 'both'


/**
 * 子图查询深度。
 *
 * 后端当前限制为 1～3 跳。
 */
export type GraphDepth = 1 | 2 | 3


/**
 * 按属性搜索节点的查询参数。
 *
 * 具体属性条件通过 POST 请求体传递。
 */
export interface SearchGraphNodesParams {
  label: string
  limit?: number
  space?: string
}


/**
 * 子图查询参数。
 */
export interface GetSubgraphParams {
  depth?: GraphDepth
  limit?: number
  edge_type?: string
  direction?: GraphDirection
  space?: string
}


/**
 * Axios 实例已经配置了 baseURL: '/api'。
 *
 * 最终请求地址为：
 * /api/v1/graph-search/...
 */
const GRAPH_SEARCH_PREFIX = '/v1/graph-search'


/**
 * 处理后端统一响应。
 *
 * 后端即使发生参数校验错误，也可能返回 HTTP 200，
 * 因此前端必须继续检查 code 和 success。
 */
export function unwrapApiResponse<T>(
  response: ApiResponse<T>,
): T {
  if (!response.success || response.code !== 200) {
    throw new Error(
      response.msg || `图谱接口请求失败，错误码：${response.code}`,
    )
  }

  return response.data
}


/**
 * 获取全部图空间。
 *
 * 对应后端：
 * GET /api/v1/graph-search/spaces
 */
export function listGraphSpaces() {
  return http.get<ApiResponse<GraphSpaceListData>>(
    `${GRAPH_SEARCH_PREFIX}/spaces`,
  )
}


/**
 * 按节点属性搜索节点。
 *
 * 查询参数：
 * - label
 * - limit
 * - space
 *
 * 请求体示例：
 * {
 *   name_zh: '吴边'
 * }
 *
 * 对应后端：
 * POST /api/v1/graph-search/nodes/search
 */
export function searchGraphNodes(
  params: SearchGraphNodesParams,
  properties: GraphProperties,
) {
  return http.post<ApiResponse<GraphNodeListData>>(
    `${GRAPH_SEARCH_PREFIX}/nodes/search`,
    properties,
    {
      params,
    },
  )
}


/**
 * 根据节点 ID 查询节点详情。
 *
 * 对应后端：
 * GET /api/v1/graph-search/nodes/{node_id}
 */
export function getGraphNode(
  nodeId: string,
  space?: string,
) {
  return http.get<ApiResponse<GraphNode>>(
    `${GRAPH_SEARCH_PREFIX}/nodes/${encodeURIComponent(nodeId)}`,
    {
      params: {
        space,
      },
    },
  )
}


/**
 * 查询指定节点的多跳子图。
 *
 * 对应后端：
 * GET /api/v1/graph-search/subgraph/{node_id}
 */
export function getSubgraph(
  nodeId: string,
  params: GetSubgraphParams = {},
) {
  return http.get<ApiResponse<GraphData>>(
    `${GRAPH_SEARCH_PREFIX}/subgraph/${encodeURIComponent(nodeId)}`,
    {
      params,
    },
  )
}