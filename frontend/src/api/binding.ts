export type BindingRelationType = 'direct' | 'two_hop' | 'three_hop'

export interface BindingQueryParams {
  dataSource?: string
  expertAId?: string
  expertBId?: string
  institution?: string
  relationType?: BindingRelationType
  startTime?: string
  endTime?: string
}

export interface BindingScenario {
  key?: string
  label?: string
  last_test_time?: string
  expert_a?: { id?: string; name?: string; title?: string }
  expert_b?: { id?: string; name?: string; title?: string }
  relation_type?: string
  institution?: string
  directions?: string[]
  api_example?: Record<string, unknown>
}

export async function fetchBindingScenarios(params: BindingQueryParams): Promise<{ scenarios: BindingScenario[] }> {
  const endpoint =
    params.relationType === 'two_hop'
      ? '/api/v1/binding/expert-direct-two-hop'
      : params.relationType === 'three_hop'
        ? '/api/v1/binding/expert-direct-three-hop'
        : '/api/v1/binding/expert-direct-relation'

  const search = new URLSearchParams()
  if (params.dataSource) search.set('dataSource', params.dataSource)
  if (params.expertAId) search.set('expertAId', params.expertAId)
  if (params.expertBId) search.set('expertBId', params.expertBId)
  if (params.institution) search.set('institution', params.institution)
  if (params.relationType && params.relationType !== 'direct') search.set('relationType', params.relationType)
  if (params.startTime) search.set('startTime', params.startTime)
  if (params.endTime) search.set('endTime', params.endTime)

  const response = await fetch(`${endpoint}?${search.toString()}`)
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || `接口请求失败：${response.status}`)
  }
  return response.json()
}
