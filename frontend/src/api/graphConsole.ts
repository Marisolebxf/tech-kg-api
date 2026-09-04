import { unwrapApiResponse, type ApiResponse } from './graphSearch'
import { http } from './http'

const PREFIX = '/v1/graph-console'

export interface GraphConsoleResult {
  records: Array<Record<string, unknown>>
  columns: string[]
  summary: Record<string, unknown>
  kind: 'read' | 'write'
}

export async function runNgql(space: string, statement: string): Promise<GraphConsoleResult> {
  // http 拦截器已把 axios response 解成信封 body，这里只需解一层信封
  const body = (await http.post(`${PREFIX}/query`, {
    space,
    statement,
  })) as ApiResponse<GraphConsoleResult>
  return unwrapApiResponse(body)
}
