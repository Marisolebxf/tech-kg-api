import { http } from './http'
import {
  unwrapApiResponse,
  type ApiResponse,
} from './graphSearch'

export type AssetOverviewKey = 'entity' | 'relation' | 'property'

export interface AssetOverviewGroup {
  key: AssetOverviewKey
  title: string
  total: string
  totalLabel: string
  added: string
  addedLabel: string
}

export interface AssetChangeRow {
  type: string
  object: string
  change: string
  source: string
  time: string
}

export interface LatestChange {
  time: string
  type: string
  domain: string
  title: string
  detail: string
  impact: string
  to: string
}

export interface ManagementRisk {
  title: string
  detail: string
  detailTo: string
  reviewTo: string
}

export interface StructureItem {
  label: string
  schema: string
  count: string
  ratio: number
  tone: string
}

export interface PlatformOverviewData {
  platformStatus: string
  pendingBatchCount: number
  updatedAt: string
  assetOverviewGroups: AssetOverviewGroup[]
  assetChangeRows: Record<AssetOverviewKey, AssetChangeRow[]>
  latestChanges: LatestChange[]
  managementRisks: ManagementRisk[]
  entityStructure: StructureItem[]
  relationStructure: StructureItem[]
  dataMode: 'live' | 'partial' | 'mock'
  dataSources: Record<string, string>
  warnings: string[]
}

const PLATFORM_OVERVIEW_ENDPOINT = '/v1/platform/overview'

export async function getPlatformOverview(): Promise<PlatformOverviewData> {
  const response = await http.get<
    ApiResponse<PlatformOverviewData>,
    ApiResponse<PlatformOverviewData>
  >(PLATFORM_OVERVIEW_ENDPOINT)

  return unwrapApiResponse(response)
}

export async function getPlatformOverviewRisks(): Promise<ManagementRisk[]> {
  const response = await http.get<
    ApiResponse<{ items: ManagementRisk[]; dataSource: string }>,
    ApiResponse<{ items: ManagementRisk[]; dataSource: string }>
  >(`${PLATFORM_OVERVIEW_ENDPOINT}/risks`)

  return unwrapApiResponse(response).items
}
