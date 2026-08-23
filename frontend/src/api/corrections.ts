import { http } from './http'
import { unwrapApiResponse, type ApiResponse } from './graphSearch'

export type CorrectionTargetType = 'expert' | 'organization' | 'relation'
export type CorrectionOperation = 'create' | 'update' | 'delete'

export interface CorrectionSync {
  id: string
  status: string
  mysqlStatus: string
  graphStatus: string
  attempts: number
  maxAttempts: number
  nextRetryAt: string | null
  lastError: string
}

export interface CorrectionHistory {
  id: string
  action: string
  actorId: string
  actorName: string
  note: string
  createdAt: string
}

export interface CorrectionRecord {
  id: string
  targetType: CorrectionTargetType
  operation: CorrectionOperation
  targetId: string
  title: string
  reason: string
  beforeData: Record<string, unknown>
  afterData: Record<string, unknown>
  status: string
  submitterId: string
  submitterName: string
  reviewerId: string | null
  reviewerName: string | null
  decisionNote: string
  version: number
  submittedAt: string
  reviewedAt: string | null
  completedAt: string | null
  updatedAt: string
  sync: CorrectionSync | null
  history?: CorrectionHistory[]
}

export interface CorrectionPayload {
  target_type: CorrectionTargetType
  operation: CorrectionOperation
  target_id: string
  title: string
  reason: string
  before_data: Record<string, unknown>
  after_data: Record<string, unknown>
}

export interface PlatformMember {
  userId: string
  username: string
  nickname: string
  email: string
  isAdmin: boolean
  lastSeenAt: string | null
}

const unwrap = <T>(response: ApiResponse<T>) => unwrapApiResponse(response)

export async function listCorrections(params: Record<string, unknown> = {}) {
  return unwrap(
    await http.get<ApiResponse<{ items: CorrectionRecord[]; total: number; page: number; pageSize: number; statusCounts: Record<string, number> }>, ApiResponse<{ items: CorrectionRecord[]; total: number; page: number; pageSize: number; statusCounts: Record<string, number> }>>('/v1/corrections', { params, timeout: 3_000 }),
  )
}

export async function getCorrection(id: string) {
  return unwrap(await http.get<ApiResponse<CorrectionRecord>, ApiResponse<CorrectionRecord>>(`/v1/corrections/${id}`))
}

export async function createCorrection(payload: CorrectionPayload) {
  return unwrap(await http.post<ApiResponse<CorrectionRecord>, ApiResponse<CorrectionRecord>>('/v1/corrections', payload))
}

export async function updateCorrection(id: string, payload: Partial<Omit<CorrectionPayload, 'target_type' | 'operation' | 'target_id'>>) {
  return unwrap(await http.patch<ApiResponse<CorrectionRecord>, ApiResponse<CorrectionRecord>>(`/v1/corrections/${id}`, payload))
}

export async function cancelCorrection(id: string) {
  return unwrap(await http.delete<ApiResponse<CorrectionRecord>, ApiResponse<CorrectionRecord>>(`/v1/corrections/${id}`))
}

export async function reviewCorrection(id: string, decision: 'approve' | 'reject', note: string) {
  return unwrap(await http.post<ApiResponse<CorrectionRecord>, ApiResponse<CorrectionRecord>>(`/v1/corrections/${id}/review`, { decision, note }))
}

export async function retryCorrection(id: string, note = '') {
  return unwrap(await http.post<ApiResponse<CorrectionRecord>, ApiResponse<CorrectionRecord>>(`/v1/corrections/${id}/retry`, { note }))
}

export async function listPlatformMembers() {
  return unwrap(await http.get<ApiResponse<{ items: PlatformMember[]; total: number }>, ApiResponse<{ items: PlatformMember[]; total: number }>>('/v1/admin/members', { timeout: 3_000 }))
}

export async function setMemberAdmin(userId: string, isAdmin: boolean) {
  return unwrap(await http.put<ApiResponse<{ userId: string; isAdmin: boolean }>, ApiResponse<{ userId: string; isAdmin: boolean }>>(`/v1/admin/members/${encodeURIComponent(userId)}/admin`, { is_admin: isAdmin }))
}
