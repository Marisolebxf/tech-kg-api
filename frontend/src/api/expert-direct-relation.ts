import { http } from './http'

import type {
  DirectRelationQueryRequest,
  DirectRelationQueryResponse,
} from '../views/reasoning-placeholder/expert-direct-types'

export async function fetchExpertDirectRelation(
  payload: DirectRelationQueryRequest,
): Promise<DirectRelationQueryResponse> {
  return http.post(
    '/v1/kg-construction/expert-direct-relations/query',
    payload,
  ) as Promise<DirectRelationQueryResponse>
}
