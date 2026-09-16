import { http } from './http'

export interface IndirectProvenanceEvidence {
  title: string
  sourceTable: string
  sourceField: string
  graphVid: string
  businessTable?: string
  technicalTable?: string
  recordId?: string
  fieldIdentifier?: string
  summary?: string
}

export interface IndirectProvenance {
  sourceDatabase: string
  summary: string
  evidences: IndirectProvenanceEvidence[]
}

export interface IndirectNode {
  id: string
  name: string
  entityType: string
  labels: string[]
  properties: Record<string, unknown>
}

export interface IndirectEdge {
  id: string
  type: string
  source: string
  target: string
  properties: Record<string, unknown>
}

export interface IndirectRelationPath {
  pathId: string
  depth: number
  relationType: string
  strength: number
  pathText: string
  targetNode: IndirectNode
  nodes: IndirectNode[]
  edges: IndirectEdge[]
}

export interface ExpertIndirectRelationResult {
  coreNode: IndirectNode
  pathDepth: number
  defaultPathDepth: number
  minStrength: number
  directNodeCount: number
  indirectNodeCount: number
  pathCount: number
  relationTypeCount: Record<string, number>
  averageStrength: number
  maxStrength: number
  directNodes: IndirectNode[]
  indirectNodes: IndirectNode[]
  paths: IndirectRelationPath[]
}

export interface ExpertIndirectRelationResponse {
  structuredResult: ExpertIndirectRelationResult
  provenance: IndirectProvenance
  rules: Array<Record<string, any>>
}

export interface ExpertIndirectRelationRequest {
  core_node_id: string
  relation_types: string[]
  path_depth: number
  min_strength: number
}

const ENDPOINT = '/v1/kg-construction/expert-indirect-relations/demo/structured-result'
const ANNOTATION_ENDPOINT = '/v1/kg-construction/expert-indirect-relations/annotations'

export const analyzeExpertIndirectRelation = (
  payload: ExpertIndirectRelationRequest,
) => http.post<ExpertIndirectRelationResponse>(ENDPOINT, payload) as unknown as Promise<ExpertIndirectRelationResponse>

export interface IndirectRelationAnnotationItem {
  sourceVid: string
  targetVid: string
  annotation: string
  updateTime?: string | null
}

interface AnnotationApiEnvelope {
  code: number
  success: boolean
  msg?: string
}

/** 边主键：两端 VID 按字典序归一后拼接，与后端 kg_indirect_relation_annotation 复合主键一致。 */
export const indirectRelationEdgeKey = (vidA: string, vidB: string): string => {
  const [source, target] = [vidA, vidB].sort()
  return `${source}:${target}`
}

function ensureAnnotationSuccess(resp: AnnotationApiEnvelope | undefined): void {
  if (!resp || resp.success === false || (resp.code !== undefined && resp.code !== 200)) {
    throw new Error(resp?.msg || '关系标注接口返回失败')
  }
}

/** 批量查询边主键对应的关系标注；查不到的边即无标注（不出现在返回 map 中，展示为空）。 */
export async function fetchIndirectRelationAnnotations(
  edgeKeys: string[],
): Promise<Record<string, string>> {
  if (!edgeKeys.length) return {}
  const resp = (await http.get(ANNOTATION_ENDPOINT, {
    params: { edges: edgeKeys.join(',') },
  })) as unknown as AnnotationApiEnvelope & {
    data?: { items?: IndirectRelationAnnotationItem[] }
  }
  ensureAnnotationSuccess(resp)
  const annotations: Record<string, string> = {}
  for (const item of resp.data?.items ?? []) {
    annotations[indirectRelationEdgeKey(item.sourceVid, item.targetVid)] =
      item.annotation || ''
  }
  return annotations
}

/** 保存（upsert）一条关系标注到业务库；annotation 传空串表示清除标注。 */
export async function upsertIndirectRelationAnnotation(
  sourceVid: string,
  targetVid: string,
  annotation: string,
): Promise<IndirectRelationAnnotationItem> {
  const resp = (await http.post(ANNOTATION_ENDPOINT, {
    sourceVid,
    targetVid,
    annotation,
  })) as unknown as AnnotationApiEnvelope & {
    data: IndirectRelationAnnotationItem
  }
  ensureAnnotationSuccess(resp)
  return resp.data
}
