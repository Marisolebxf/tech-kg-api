import { unwrapApiResponse, type ApiResponse } from './graphSearch'
import { http } from './http'

const PREFIX = '/v1/graph-algorithms'

/** 算法作业状态快照（提交/轮询共用）。 */
export interface AlgorithmJobSnapshot {
  jobId: string
  status: 'running' | 'succeeded' | 'failed'
  createdAt?: string | null
  startedAt?: string | null
  finishedAt?: string | null
  submissionId?: string | null
  driverState?: string | null
  error?: string | null
  logTail?: string | null
}

/** csv 结果：rows 为 header→cell 字符串字典列表。 */
export interface AlgorithmResultPayload {
  jobId: string
  sink: 'csv'
  rows: Array<Record<string, string>>
  count?: number
  truncated?: boolean
}

/** Spark 运行器健康状态；探测失败降级为 DOWN（带中文原因）。 */
export interface GraphAlgorithmEngineStatus {
  status: 'UP' | 'DOWN'
  activeJobs?: number | null
  message?: string | null
}

/** 图算法面板元数据（进入面板时加载一次）。 */
export interface GraphAlgorithmMetadata {
  edgeTypes: string[]
  engine: GraphAlgorithmEngineStatus
}

/** 提交算法作业请求；params 键为算法专有参数（camelCase，如 maxIter），
 *  页面不暴露调优参数时可省略，由服务端默认值兜底。 */
export interface AlgorithmJobSubmitPayload {
  space: string
  algorithm: string
  labels: string[]
  params?: Record<string, number | string | boolean>
  hasWeight: boolean
  weightCols: string[] | null
  encodeId: boolean
  partitionNum: number
}

export async function fetchGraphAlgorithmMetadata(space: string): Promise<GraphAlgorithmMetadata> {
  const body = (await http.get(`${PREFIX}/metadata`, {
    params: { space },
  })) as ApiResponse<GraphAlgorithmMetadata>
  return unwrapApiResponse(body)
}

export async function fetchGraphAlgorithmEngine(space: string): Promise<GraphAlgorithmEngineStatus> {
  const body = (await http.get(`${PREFIX}/engine`, {
    params: { space },
  })) as ApiResponse<GraphAlgorithmEngineStatus>
  return unwrapApiResponse(body)
}

export async function submitAlgorithmJob(
  payload: AlgorithmJobSubmitPayload,
): Promise<AlgorithmJobSnapshot> {
  const body = (await http.post(`${PREFIX}/jobs`, payload)) as ApiResponse<AlgorithmJobSnapshot>
  return unwrapApiResponse(body)
}

export async function getAlgorithmJob(space: string, jobId: string): Promise<AlgorithmJobSnapshot> {
  const body = (await http.get(`${PREFIX}/jobs/${jobId}`, {
    params: { space },
  })) as ApiResponse<AlgorithmJobSnapshot>
  return unwrapApiResponse(body)
}

export async function getAlgorithmJobResult(
  space: string,
  jobId: string,
): Promise<AlgorithmResultPayload> {
  const body = (await http.get(`${PREFIX}/jobs/${jobId}/result`, {
    params: { space },
  })) as ApiResponse<AlgorithmResultPayload>
  return unwrapApiResponse(body)
}
