import { http } from "./http";

export interface ExpertColleagueRelationRequest {
  expert_a_id: string;
  expert_b_id: string;
  start_time?: string;
  end_time?: string;
  limit?: number;
  offset?: number;
}

export interface ColleagueGraphNode {
  id: string;
  type: string;
  label: string;
  data?: Record<string, any>;
}

export interface ColleagueGraphEdge {
  id?: string;
  source: string;
  target: string;
  label: string;
  data?: Record<string, any>;
}

export interface ExpertColleagueRelationData {
  expert: Record<string, any>;
  targetExpert?: Record<string, any> | null;
  colleagues: Array<Record<string, any>>;
  total: number;
  returnedCount: number;
  summary: Record<string, any>;
  graph: {
    nodes: ColleagueGraphNode[];
    edges: ColleagueGraphEdge[];
  };
  rules: Array<Record<string, any>>;
  apiCalls: Array<Record<string, any>>;
  persistence: Record<string, any>;
}

export interface ExpertColleagueRelationResponse {
  code: number;
  success: boolean;
  msg: string;
  data?: ExpertColleagueRelationData;
}

export async function queryExpertColleagueRelation(
  request: ExpertColleagueRelationRequest,
): Promise<ExpertColleagueRelationResponse> {
  return http.post("/v1/kg-service/expert-colleague-relation", request, {
    timeout: 60_000,
  });
}
