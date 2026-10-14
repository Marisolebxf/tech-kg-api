import { http } from './http'
import {
  unwrapApiResponse,
  type ApiResponse,
} from './graphSearch'

export type AssetOverviewKey = 'entity' | 'relation'

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
  /** 工作流控制库中的真实任务 ID；兼容没有任务关联的历史记录。 */
  taskId?: string | null
  /** 同一条执行所属的图谱构建任务（job-xxx）；行点击跳 /graph-build/jobs 用。 */
  jobId?: string | null
  /** 图对象唯一 ID；同名实体也各自展示一行。 */
  objectId?: string | null
  /** 写图执行终态；中断执行（TERMINATED/CANCELED/FAILED）也计入昨日新增，行内标注「已中断/失败」。 */
  execStatus?: string | null
}

export interface StructureMember {
  name: string
  count: number
}

export interface StructureItem {
  label: string
  schema: string
  /** 全部非零成员（按计数降序，展示名=Schema 目录中文名）；降级空态无成员 */
  members?: StructureMember[]
  count: string
  ratio: number
  tone: string
  /** 「其他实体/其他关系」聚合段：只有它开悬浮（浮窗列成员 Schema 清单） */
  isOther?: boolean
}

export interface PlatformOverviewData {
  platformStatus: string
  pendingBatchCount: number
  updatedAt: string
  /** 统计日（北京自然日 YYYY-MM-DD）：昨日新增实际归属的日子，页面直接展示，不自行推算「昨天」。 */
  statsDay?: string
  assetOverviewGroups: AssetOverviewGroup[]
  assetChangeRows: Record<AssetOverviewKey, AssetChangeRow[]>
  /** 昨日新增的实际逐对象记录数，与侧栏明细同源。 */
  assetChangeTotals?: Partial<Record<AssetOverviewKey, number>>
  assetChangeErrors?: Partial<Record<AssetOverviewKey, string>>
  entityStructure: StructureItem[]
  relationStructure: StructureItem[]
  dataMode: 'partial' | 'mock'
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
