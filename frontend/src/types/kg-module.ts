export type KgModuleMode = 'live' | 'scaffold'

export interface KgModuleConfig {
  code: string
  navLabel: string
  routeName: string
  path: string
  mode: KgModuleMode
  reservedApiPath: string
  subFunctions: string[]
  schemeDescription: string
  schemeFlow: string[]
}

export interface StructuredResultPayload {
  authorList?: string[]
  authorUnits?: string[]
  paperTopics?: string[]
  cooperationPaperCount?: number
  journalLevelCount?: Record<string, number>
  conferenceLevelCount?: Record<string, number>
  cooperationFrequency?: number
  academicImpactScore?: number
  citation?: { total: number; max: number }
  cooperationTimeRange?: { displayText: string }
  stableTeamName?: string | null
  stableTeamMembers?: string[]
  coreCollaborators?: string[]
  sharedContribution?: string[]
  representativePapers?: string[]
  [key: string]: unknown
}

export interface ModuleTestResult {
  structuredResult: StructuredResultPayload
  apiExample: Record<string, unknown>
  lastTestTime: string
}

export interface DeveloperField {
  name: string
  type: string
  required?: string
  description: string
}

export interface DemoGraphNode {
  id: string
  kind: string
  title: string
  subtitle?: string
  x: number
  y: number
  w: number
  h: number
}

export interface DemoGraphLayout {
  nodes: DemoGraphNode[]
  edges: Array<{ path: string; className?: string }>
  relationPill?: { text: string; x: number; y: number }
}

export interface ScaffoldDemoPayload extends ModuleTestResult {
  apiPath: string
  httpMethod: 'GET' | 'POST'
  requestFields: DeveloperField[]
  responseFields: DeveloperField[]
  codeExamples: {
    python: string
    node: string
    curl: string
  }
  graphLayout?: DemoGraphLayout
}
