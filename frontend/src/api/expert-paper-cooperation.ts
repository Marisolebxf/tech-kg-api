import { http } from './http'

import type {
  ExpertPaperCooperationDemoRequest,
  ExpertPaperCooperationStructuredResultOnlyResponse,
} from '../views/expert-paper-cooperation/types'

type ApiBusinessError = {
  code?: number
  success?: boolean
  msg?: string
  data?: Array<{ msg?: string }>
}

function buildBusinessErrorMessage(response: ApiBusinessError) {
  const detail = response.data?.map((item) => item.msg).filter(Boolean).join('；')
  return detail || response.msg || '请求参数校验失败'
}

export async function fetchExpertPaperCooperationStructuredResult(
  payload: ExpertPaperCooperationDemoRequest,
): Promise<ExpertPaperCooperationStructuredResultOnlyResponse> {
  const response = (await http.post(
    '/v1/kg-construction/expert-paper-cooperation-relations/demo/structured-result',
    payload,
  )) as ExpertPaperCooperationStructuredResultOnlyResponse | ApiBusinessError

  if ('success' in response && response.success === false) {
    throw new Error(buildBusinessErrorMessage(response))
  }
  return response as ExpertPaperCooperationStructuredResultOnlyResponse
}
