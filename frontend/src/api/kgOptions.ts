import { http } from './http'

/** 目录型选项计数（工作台数据服务卡展示用）。 */
export interface KgOptionCounts {
  relationTypes: number
  roles: number
  dimensions: number
  techFields: number
}

const EMPTY_COUNTS: KgOptionCounts = {
  relationTypes: 0,
  roles: 0,
  dimensions: 0,
  techFields: 0,
}

/** 拉取目录型选项计数；后端对任一数据源异常已兜底空列表，此处失败整体兜 0。 */
export async function getKgOptionCounts(): Promise<KgOptionCounts> {
  try {
    const data = await http.get<Record<string, unknown[]>, Record<string, unknown[]>>(
      '/v1/kg-construction/options',
    )
    const count = (key: string): number => (Array.isArray(data[key]) ? data[key].length : 0)
    return {
      relationTypes: count('relationTypes'),
      roles: count('roles'),
      dimensions: count('dimensions'),
      techFields: count('techFields'),
    }
  } catch {
    return { ...EMPTY_COUNTS }
  }
}
