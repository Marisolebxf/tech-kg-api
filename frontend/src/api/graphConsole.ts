import type { ApiResponse } from './schemaManagement'
import { http } from './http'

const PREFIX = '/v1/graph-console'

export interface GraphConsoleResult {
  records: Array<Record<string, unknown>>
  columns: string[]
  summary: Record<string, unknown>
  kind: 'read' | 'write'
}

export async function runNgql(space: string, statement: string): Promise<GraphConsoleResult> {
  const response = await http.post<ApiResponse<GraphConsoleResult>>(`${PREFIX}/query`, {
    space,
    statement,
  })
  const body = response.data
  if (!body.success || body.code !== 200) {
    throw new Error(body.msg || 'nGQL 执行失败')
  }
  return body.data
}
