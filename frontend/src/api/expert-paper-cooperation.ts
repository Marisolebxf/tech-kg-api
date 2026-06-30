import { http } from './http'

import type {
  ExpertPaperCooperationDemoRequest,
  ExpertPaperCooperationStructuredResultOnlyResponse,
} from '../views/expert-paper-cooperation/types'

export async function fetchExpertPaperCooperationStructuredResult(
  payload: ExpertPaperCooperationDemoRequest,
): Promise<ExpertPaperCooperationStructuredResultOnlyResponse> {
  return http.post(
    '/v1/kg-construction/expert-paper-cooperation-relations/demo/structured-result',
    payload,
  ) as Promise<ExpertPaperCooperationStructuredResultOnlyResponse>
}
