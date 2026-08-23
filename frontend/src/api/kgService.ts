import { http } from './http'

/**
 * 调用九大业务服务端点。
 * @param endpoint 形如 /api/v1/kg-service/key-enterprise-relation（service-modules.ts 里定义）
 * @param params 请求参数
 * @param timeout 超时（ms），业务编排可能多跳查图，默认 60s
 *
 * baseURL 已为 /api，dev 由 vite 代理到 VITE_API_TARGET，生产由 nginx 代理到后端。
 */
export async function invokeKgService(
  endpoint: string,
  params: Record<string, unknown>,
  timeout = 60000,
): Promise<Record<string, any>> {
  const path = endpoint.replace(/^\/api/, '') // 去掉 /api 前缀，由 baseURL 补
  const res = await http.post(path, params, { timeout })
  return res as Record<string, any>
}
