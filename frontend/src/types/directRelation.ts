export interface RelationGraphNode {
  id: string
  kind: 'expertA' | 'expertB' | 'institution'
  x: number
  y: number
  icon?: string
  title: string
  subtitle?: string
  desc?: string
  chips?: string[]
  achievements?: Array<Record<string, string | number>>
}

export interface RelationGraphEdge {
  type: 'curve'
  from_: [number, number]
  c1?: [number, number]
  c2?: [number, number]
  to: [number, number]
  stroke: string
  marker: string
  width: number
  label: string
  label_x: number
  label_y: number
  label_color?: string
}

export interface RelationGraph {
  width: number
  height: number
  nodes: RelationGraphNode[]
  edges: RelationGraphEdge[]
}

export interface RelationScenario {
  key: string
  label: string
  last_test_time: string
  graph: RelationGraph
  detail_rows: Array<[string, unknown]>
  api_example: {
    relation_type: string
    relation_subtype: string
    expert_a: { name: string; title: string }
    expert_b: { name: string; title: string }
    institution: string
    reasons: string[]
    relation_strength: number
    relation_summary: string
    query_params?: Record<string, string>
    request_example?: Record<string, unknown>
    response_example?: Record<string, unknown>
  }
}

export interface RelationPreviewResponse {
  scenarios: RelationScenario[]
}

export interface RelationModeOption {
  key: 'two_hop' | 'three_hop'
  label: string
  path: string
  subtitle: string
}

export interface SidebarItem {
  label: string
  active?: boolean
}
