import { http } from './http'

import type { GraphEdgeData, GraphNodeData, GraphNodeType, LiveEntityProvenance } from '../data/graph-presets'

/**
 * 业务关系服务（/api/v1/kg-service/*）的统一客户端。
 *
 * backend/biz/handler 下的各关系模块返回统一 ApiResponse：
 * { code, success, data, msg }。http.ts 的响应拦截器已拆包返回 body。
 */

export interface KgServiceGraphNode {
  id: string
  type?: string
  label?: string
  data?: Record<string, unknown>
}

export interface KgServiceGraphEdge {
  id?: string
  source: string
  target: string
  label?: string
  type?: string
  data?: Record<string, unknown>
}

export interface KgServiceGraphData {
  nodes: KgServiceGraphNode[]
  edges: KgServiceGraphEdge[]
}

export interface KgServiceResponse {
  [key: string]: unknown
  expert?: { id?: string; name?: string }
  colleagues?: Array<Record<string, unknown>>
  total?: number
  summary?: Record<string, unknown>
  graph?: KgServiceGraphData
  apiCalls?: Array<Record<string, unknown>>
}

export interface KgServiceResult {
  data: KgServiceResponse | null
  error: string | null
}

const NODE_TYPE_MAP: Record<string, GraphNodeType> = {
  main: 'main',
  expert: 'expert',
  person: 'expert',
  scholar: 'expert',
  org: 'org',
  organization: 'org',
  affiliation: 'org',
  company: 'company',
  enterprise: 'company',
  paper: 'paper',
  project: 'project',
  patent: 'paper',
  report: 'paper',
  award: 'project',
  achievement: 'paper',
  event: 'event',
  topic: 'topic',
}

const ENTITY_TYPE_LABEL: Record<string, string> = {
  main: '核心专家',
  expert: '科技专家',
  org: '机构',
  company: '企业',
  paper: '论文',
  project: '项目',
  event: '事件',
  topic: '主题',
}

/**
 * 调用一个业务关系服务。endpoint 取自 service-modules.ts 的 moduleInfo.endpoint。
 * 返回 { data, error }：成功时 data 为 ApiResponse.data，失败时 error 为可展示信息。
 */
export async function runKgService(
  endpoint: string,
  payload: Record<string, unknown>,
): Promise<KgServiceResult> {
  try {
    const body = (await http.post(endpoint, payload)) as {
      code?: number
      success?: boolean
      data?: KgServiceResponse
      msg?: string
    }

    if (body && (body.success === true || body.code === 200 || body.code === 0) && body.data) {
      return { data: body.data, error: null }
    }

    if (body && body.code === 404) {
      return { data: null, error: body.msg || '未查询到相关实体' }
    }

    return { data: null, error: body?.msg || `服务返回未成功（code=${body?.code ?? 'unknown'}）` }
  } catch (err) {
    const anyErr = err as {
      response?: { status?: number; data?: { msg?: string; detail?: string } }
      message?: string
    }
    if (anyErr.response?.status === 404) {
      return { data: null, error: '该服务后端尚未实现（404 Not Found）' }
    }
    const msg = anyErr.response?.data?.msg || anyErr.response?.data?.detail || anyErr.message || String(err)
    return { data: null, error: msg }
  }
}

function edgeCategory(label: string): string {
  if (label.includes('同事')) return '同事'
  if (label.includes('论文')) return '论文合作'
  if (label.includes('校友')) return '校友'
  if (label.includes('企业')) return '企业关联'
  if (label.includes('产业') || label.includes('事件')) return '产业事件'
  if (label.includes('直接')) return '直接关系'
  if (label.includes('间接')) return '间接关系'
  return label || '关系'
}

/**
 * 把后端返回的 graph（{nodes, edges}）转成画布需要的 GraphNodeData/GraphEdgeData，
 * 并按中心节点 + 环形布局生成坐标。
 */
export function convertServiceGraph(
  graph: KgServiceGraphData | undefined,
  centerId?: string,
): { nodes: GraphNodeData[]; edges: GraphEdgeData[] } {
  if (!graph || !graph.nodes?.length) return { nodes: [], edges: [] }

  const center = centerId ?? String(graph.nodes[0]?.id ?? '')
  const total = graph.nodes.length
  const cx = 380
  const cy = 215
  const radius = total > 1 ? 160 : 0

  const nodes: GraphNodeData[] = graph.nodes.map((node, index) => {
    const id = String(node.id)
    const isCenter = id === center
    const rawType = (node.type || '').toLowerCase()
    const nodeType = NODE_TYPE_MAP[rawType] ?? 'expert'
    const data = node.data ?? {}
    const angle = (index / total) * Math.PI * 2
    const confidence = typeof data.confidence === 'number'
      ? (data.confidence as number)
      : (isCenter ? 1 : 0.8)
    return {
      id,
      label: node.label || String(data.name ?? data.title ?? id),
      nodeType: isCenter ? 'main' : nodeType,
      entityType: ENTITY_TYPE_LABEL[nodeType] ?? '实体',
      confidence,
      relations: typeof data.relations === 'string' ? (data.relations as string) : '',
      evidence: Array.isArray(data.evidence) ? (data.evidence as string[]) : [],
      details: typeof data.details === 'object' && data.details !== null ? data.details as Record<string, unknown> : data,
      provenance: typeof data.provenance === 'object' && data.provenance !== null ? data.provenance as LiveEntityProvenance : undefined,
      x: isCenter ? cx : cx + Math.cos(angle) * radius,
      y: isCenter ? cy : cy + Math.sin(angle) * radius,
      level: isCenter ? 0 : 1,
    }
  })

  const nodeIds = new Set(nodes.map((node) => node.id))
  const edges: GraphEdgeData[] = (graph.edges || [])
    .filter((edge) => nodeIds.has(String(edge.source)) && nodeIds.has(String(edge.target)))
    .map((edge, index) => {
      const label = edge.label || edge.type || '关系'
      return {
        id: edge.id || `${edge.source}:${edge.target}:${index}`,
        from: String(edge.source),
        to: String(edge.target),
        label,
        category: edgeCategory(label),
        confidence: typeof edge.data?.confidence === 'number' ? edge.data.confidence as number : undefined,
        evidence: Array.isArray(edge.data?.evidence) ? edge.data.evidence as string[] : [],
        ruleName: typeof edge.data?.ruleName === 'string' ? edge.data.ruleName as string : undefined,
        details: edge.data ?? {},
      }
    })

  return { nodes, edges }
}
