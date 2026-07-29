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
 * 节点关联边查询结果。
 */
export interface GraphEdgeListData {
  edges: GraphEdge[]
  total: number
}


/**
 * 邻居节点查询结果。
 */
export interface GraphNeighbourListData {
  nodes: GraphNode[]
  total: number
}


/**
 * 最短路径查询结果。
 *
 * 部分后端结果可能额外返回 found，
 * 因此这里将其定义为可选字段。
 */
export interface GraphShortestPathData extends GraphData {
  found?: boolean
}


/**
 * 图空间列表。
 */
export interface GraphSpaceListData {
  spaces: string[]
}


/**
 * 图谱统计信息。
 */
export interface GraphStatsData {
  nodes: Record<string, number>
  edges: Record<string, number>
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
 * 按标签查询节点的参数。
 */
export interface ListGraphNodesParams {
  label: string
  limit?: number
  offset?: number
  space?: string
}


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
 * 节点边和邻居节点的查询参数。
 */
export interface GetNodeRelationsParams {
  direction?: GraphDirection
  edge_type?: string
  limit?: number
  space?: string
}


/**
 * 最短路径查询参数。
 */
export interface GetShortestPathParams {
  source: string
  target: string
  max_depth?: number
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
 * 获取指定图空间的节点和边统计。
 *
 * 对应后端：
 * GET /api/v1/graph-search/stats
 */
export function getGraphStats(
  space?: string,
) {
  return http.get<ApiResponse<GraphStatsData>>(
    `${GRAPH_SEARCH_PREFIX}/stats`,
    {
      params: {
        space,
      },
    },
  )
}


/**
 * 按节点标签分页查询节点。
 *
 * 对应后端：
 * GET /api/v1/graph-search/nodes
 */
export function listGraphNodes(
  params: ListGraphNodesParams,
) {
  return http.get<ApiResponse<GraphNodeListData>>(
    `${GRAPH_SEARCH_PREFIX}/nodes`,
    {
      params,
    },
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


/**
 * 查询指定节点的关联边。
 *
 * 对应后端：
 * GET /api/v1/graph-search/node/{node_id}/edges
 */
export function getNodeEdges(
  nodeId: string,
  params: GetNodeRelationsParams = {},
) {
  return http.get<ApiResponse<GraphEdgeListData>>(
    `${GRAPH_SEARCH_PREFIX}/node/${encodeURIComponent(nodeId)}/edges`,
    {
      params,
    },
  )
}


/**
 * 查询指定节点的邻居节点。
 *
 * 对应后端：
 * GET /api/v1/graph-search/node/{node_id}/neighbours
 */
export function getNodeNeighbours(
  nodeId: string,
  params: GetNodeRelationsParams = {},
) {
  return http.get<ApiResponse<GraphNeighbourListData>>(
    `${GRAPH_SEARCH_PREFIX}/node/${encodeURIComponent(nodeId)}/neighbours`,
    {
      params,
    },
  )
}


/**
 * 查询两个节点之间的最短路径。
 *
 * 对应后端：
 * GET /api/v1/graph-search/shortest-path
 */
export function getShortestPath(
  params: GetShortestPathParams,
) {
  return http.get<ApiResponse<GraphShortestPathData>>(
    `${GRAPH_SEARCH_PREFIX}/shortest-path`,
    {
      params,
    },
  )
}