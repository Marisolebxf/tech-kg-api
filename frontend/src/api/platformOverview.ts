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
  /** 该写入块（执行×来源）的对象数：控制库 written 精确计数。 */
  count: number
  source: string
  time: string
  /** 工作流控制库中的真实任务 ID；兼容没有任务关联的历史记录。 */
  taskId?: string | null
  /** 同一条执行所属的图谱构建任务（job-xxx）；与 taskId 同源。 */
  jobId?: string | null
  /** 该写入块归属的执行 ID（EXEC-xxx）：跳任务详情时直达那一次执行——
   *  任务可多次运行，任务页默认展示最新执行，不带它数字会对不上。 */
  execId?: string | null
  /** 图对象唯一 ID；聚合格式下写入块行不再携带（保留字段兼容）。 */
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
  /** 昨日新增对象数合计（控制库 written 精确计数），抽屉左下角「共 N 条变化」同源。 */
  assetChangeTotals?: Partial<Record<AssetOverviewKey, number>>
  assetChangeErrors?: Partial<Record<AssetOverviewKey, string>>
  entityStructure: StructureItem[]
  relationStructure: StructureItem[]
  dataMode: 'partial' | 'mock'
  dataSources: Record<string, string>
  warnings: string[]
}

const PLATFORM_OVERVIEW_ENDPOINT = '/v1/platform/overview'

/** 图资产统计随 space（全局图空间选择器当前空间）查询；缺省由后端回落 env 默认空间。
 * day（YYYY-MM-DD）指定统计日回看历史「昨日新增」（验收核对）；缺省=昨天。 */
export async function getPlatformOverview(
  space?: string,
  day?: string,
): Promise<PlatformOverviewData> {
  const params: Record<string, string> = {}
  if (space) params.space = space
  if (day) params.day = day
  const response = await http.get<
    ApiResponse<PlatformOverviewData>,
    ApiResponse<PlatformOverviewData>
  >(PLATFORM_OVERVIEW_ENDPOINT, { params: Object.keys(params).length ? params : undefined })

  return unwrapApiResponse(response)
}
