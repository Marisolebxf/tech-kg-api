export interface EnterpriseBuildRequest {
  scholarId: string
  enterpriseId: string
  relationTypes: string[]
}

export async function buildExpertEnterpriseRelation(payload: EnterpriseBuildRequest) {
  const response = await fetch('/api/v1/kg-construction/expert-enterprise-relations/build', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body?.message || body?.detail || `接口请求失败：${response.status}`)
  }
  return body
}

export async function fetchKgOptions() {
  const response = await fetch('/api/v1/kg-construction/options')
  if (!response.ok) {
    return null
  }
  return response.json()
}

export async function annotateRelationDetail(payload: Record<string, unknown>) {
  const response = await fetch('/api/v1/kg-construction/relation-detail-annotations/annotate', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body?.message || body?.detail || `接口请求失败：${response.status}`)
  }
  return body
}

export async function analyzeEnterpriseBackground(payload: Record<string, unknown>) {
  const response = await fetch('/api/v1/kg-construction/enterprise-background-analyses/analyze', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  const body = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(body?.message || body?.detail || `接口请求失败：${response.status}`)
  }
  return body
}
