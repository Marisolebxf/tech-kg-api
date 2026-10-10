import { http } from './http'
import { unwrapApiResponse, type ApiResponse } from './graphSearch'

export interface BusinessMember {
  userId: string
  displayName?: string
  username?: string
  role: 'user' | 'developer' | 'admin'
  clientId?: string | null
  clientIds: string[]
}
export interface BusinessAccessState {
  businesses: { clientId: string; name: string; enabled: boolean }[]
  members: BusinessMember[]
  spaces: { name: string; clientId: string | null; isSharedProduction: boolean }[]
}
async function unwrap<T>(request: unknown): Promise<T> {
  return unwrapApiResponse(await (request as Promise<ApiResponse<T>>), '业务权限请求失败')
}
export const getBusinessAccessState = () => unwrap<BusinessAccessState>(http.get('/v1/business-access/state'))
export const saveBusinessMember = (member: BusinessMember) => unwrap(http.put(
  `/v1/business-access/members/${encodeURIComponent(member.userId)}`,
  { role: member.role, clientIds: member.role === 'developer' ? member.clientIds : [] },
))
export const saveBusinessSpace = (name: string, clientId: string | null, isSharedProduction: boolean) => unwrap(http.put(
  `/v1/business-access/spaces/${encodeURIComponent(name)}`, { clientId, isSharedProduction },
))
