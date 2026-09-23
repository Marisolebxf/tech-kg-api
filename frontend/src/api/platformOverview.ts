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

export interface StructureMember {
  name: string
  count: number
}

export interface StructureItem {
  label: string
  schema: string
  /** 桶内全部非零成员（按计数降序），悬停中文标签的浮窗展示；降级演示数据无此字段 */
  members?: StructureMember[]
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
  /** 环形图中心数 = 各分段之和（Σ标签/Σ边类型计数），与分段自洽；资产卡 total 仍是去重口径 */
  entityStructureTotal?: string
  relationStructureTotal?: string
  dataMode: 'live' | 'partial' | 'mock'
  dataSources: Record<string, string>
  warnings: string[]
}

const PLATFORM_OVERVIEW_ENDPOINT = '/v1/platform/overview'

/** 图资产统计随 space（全局图空间选择器当前空间）查询；缺省由后端回落 env 默认空间。 */
export async function getPlatformOverview(space?: string): Promise<PlatformOverviewData> {
  const response = await http.get<
    ApiResponse<PlatformOverviewData>,
    ApiResponse<PlatformOverviewData>
  >(PLATFORM_OVERVIEW_ENDPOINT, { params: space ? { space } : undefined })

  return unwrapApiResponse(response)
}
