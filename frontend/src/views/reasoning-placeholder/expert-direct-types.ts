export type DirectRelationDataSource = 'all'

export interface DirectRelationQueryRequest {
  dataSource: DirectRelationDataSource
  expertAId: string
  expertBId: string
  institution: string
  startTime: string
  endTime: string
  limit: number
}

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
  detailRows: [string, unknown][]
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

export interface DirectRelationQueryResponse {
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

export interface DocField {
  name: string
  type: string
  required?: string
  description: string
}
