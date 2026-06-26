export interface ExpertProfile {
  id: string
  name: string
  title: string
  organization: string
  field: string
  location: string
  paperCount: number
  patentCount: number
  colleagueCount: number
}

export interface ColleagueRelation {
  id: string
  name: string
  organization: string
  department: string
  relationType: string
  evidence: string
  cooperationYears: string
  strength: number
}

export interface RelationNode {
  id: string
  name: string
  role: 'center' | 'colleague' | 'organization'
}

export interface RelationLink {
  source: string
  target: string
  label: string
}

export interface ColleagueInferenceResult {
  featureName: string
  endpoint: string
  method: 'POST'
  lastTestTime: string
  expertA: {
    id: string
    name: string
    title: string
  }
  expertB: {
    id: string
    name: string
    title: string
  }
  relationType: string
  organization: string
  overlapPeriod: string
  researchDirections: string[]
  collaborations: {
    paper: number
    patent: number
    project: number
  }
  requestParams: Array<{
    field: string
    type: string
    required: '是' | '否'
    description: string
  }>
  responseFields: Array<{
    field: string
    type: string
    description: string
  }>
}
