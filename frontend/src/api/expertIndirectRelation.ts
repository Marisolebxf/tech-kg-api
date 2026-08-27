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

export const analyzeExpertIndirectRelation = (
  payload: ExpertIndirectRelationRequest,
) => http.post<ExpertIndirectRelationResponse>(ENDPOINT, payload) as unknown as Promise<ExpertIndirectRelationResponse>
