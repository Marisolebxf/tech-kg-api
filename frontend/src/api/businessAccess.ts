import { http } from './http'
import type { ApiResponse } from './schemaManagement'

const PREFIX = '/v1/business-access'
export type BusinessRole = 'user' | 'developer' | 'admin'
export interface BusinessAccessState {
  businesses: { clientId: string; name: string; enabled: boolean }[]
  members: { userId: string; username: string; nickname: string; clientId: string | null; role: BusinessRole }[]
  spaces: { name: string; clientId: string | null; isSharedProduction: boolean }[]
  requests: { id: string; clientId: string; spaceName: string; reason: string; status: string; requestedBy: string; reviewedBy: string; reviewNote: string; lastError: string; createdAt: string; canRetry?: boolean }[]
  currentBusinessId: string
}
async function unwrap<T>(request: unknown): Promise<T> {
  const response = await (request as Promise<ApiResponse<T>>)
  if (!response.success || response.code !== 200) throw new Error(response.msg || '业务权限操作失败')
  return response.data
}
export const getBusinessAccessState = () => unwrap<BusinessAccessState>(http.get(`${PREFIX}/state`))
export const saveBusiness = (id: string, body: { name: string; enabled: boolean }) => unwrap(http.put(`${PREFIX}/businesses/${encodeURIComponent(id)}`, body))
export const saveBusinessMember = (id: string, body: { clientId: string | null; role: BusinessRole }) => unwrap(http.put(`${PREFIX}/members/${encodeURIComponent(id)}`, body))
export const saveBusinessSpace = (name: string, body: { clientId: string | null; isSharedProduction: boolean }) => unwrap(http.put(`${PREFIX}/spaces/${encodeURIComponent(name)}`, body))
export const requestBusinessSpace = (body: { spaceName: string; reason: string; clientId?: string }) => unwrap(http.post(`${PREFIX}/requests`, body))
export const decideBusinessSpace = (id: string, approve: boolean, note: string) => unwrap(http.post(`${PREFIX}/requests/${encodeURIComponent(id)}/decision`, { approve, note }))
export const retryBusinessSpace = (id: string) => unwrap(http.post(`${PREFIX}/requests/${encodeURIComponent(id)}/retry`))
