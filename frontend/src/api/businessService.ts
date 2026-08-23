import { http } from './http'

export interface BusinessOptionItem {
  value: string
  label: string
}

export interface BusinessServiceOptions {
  scholars: Array<{ scholarId: string; name: string }>
  enterprises: Array<{ enterpriseId: string; name: string }>
  edges: Array<{ relationId: string; scholarId: string; enterpriseId: string }>
  relationTypes: BusinessOptionItem[]
  roles: BusinessOptionItem[]
  dimensions: BusinessOptionItem[]
  techFields: string[]
  cpcCodes: string[]
}

export interface BusinessApiResponse<T = Record<string, unknown>> {
  code: number
  success: boolean
  data: T
  msg: string
}

function apiPath(endpoint: string) {
  return endpoint.replace(/^\/api(?=\/)/, '')
}

export function getBusinessServiceOptions() {
  return http.get<BusinessServiceOptions>('/v1/kg-construction/options')
}

export function describeBusinessService(endpoint: string) {
  return http.get<Record<string, unknown>>(apiPath(endpoint.replace(/\/query$/, '').replace(/\/mine$/, '')))
}

export function queryBusinessService<T = Record<string, unknown>>(
  endpoint: string,
  body: Record<string, unknown>,
) {
  return http.post<BusinessApiResponse<T>>(apiPath(endpoint), body)
}
