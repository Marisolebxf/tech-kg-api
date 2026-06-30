export type DataSource = 'all' | 'knowledge_graph' | 'cnki' | 'wanfang' | 'web_of_science'

export interface ExpertPaperCooperationDemoRequest {
  dataSource: DataSource
  expertAId: string
  expertBId: string
  startTime: string
  endTime: string
}

export interface StructuredResultPayload {
  authorList: string[]
  authorUnits: string[]
  paperTopics: string[]
  cooperationPaperCount: number
  journalLevelCount: Record<string, number>
  conferenceLevelCount: Record<string, number>
  cooperationFrequency: number
  academicImpactScore: number
  citation: { total: number; max: number }
  cooperationTimeRange: { startYear: number; endYear: number; displayText: string }
  stableTeamMembers?: string[]
  coreCollaborators?: string[]
  sharedContribution?: string[]
}

export interface ExpertPaperCooperationStructuredResultOnlyResponse {
  structuredResult: StructuredResultPayload
}
