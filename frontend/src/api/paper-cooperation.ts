export interface PaperCooperationRequest {
  dataSource: string
  expertAId: string
  expertBId: string
  startTime?: string
  endTime?: string
}

export async function fetchPaperStructuredResult(payload: PaperCooperationRequest) {
  const response = await fetch('/api/v1/scholar-paper-cooperation/demo/structured-result', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null)
    throw new Error(body?.detail || `接口请求失败：${response.status}`)
  }
  return response.json()
}
