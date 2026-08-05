import { http } from './http'

export interface CooperationTimeRange {
  startYear: number
  endYear: number
  displayText: string
}

export interface ExpertPaperCooperationResult {
  authorList: string[]
  authorUnits: string[]
  cooperationTimeRange: CooperationTimeRange
  paperTopics: string[]
  cooperationPaperCount: number
  journalLevelCount: Record<string, number>
  conferenceLevelCount: Record<string, number>
  citation: {
    total: number
    max: number
  }
  cooperationFrequency: number
  academicImpactScore: number
  stableTeamMembers: string[]
  coreCollaborators: string[]
  sharedContribution: string[]
}

export interface ExpertPaperCooperationResponse {
  structuredResult: ExpertPaperCooperationResult
}

export interface ExpertPaperCooperationRequest {
  dataSource: 'knowledge_graph'
  expertAId: string
  expertBId: string
  startTime?: string
  endTime?: string
}

const ENDPOINT = '/v1/kg-construction/expert-paper-cooperation-relations/demo/structured-result'

export const analyzeExpertPaperCooperation = (
  payload: ExpertPaperCooperationRequest,
) => http.post<ExpertPaperCooperationResponse>(ENDPOINT, payload) as unknown as Promise<ExpertPaperCooperationResponse>

