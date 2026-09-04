export const INDIRECT_CORE_NODE_ID_MAX_LENGTH = 64;
export const INDIRECT_CORE_NODE_ID_ERROR =
  "不能包含空格或 !@#￥%& 等异常字符";
export const INDIRECT_PATH_DEPTH_ERROR = "路径分析深度只能填写 2 或 3";
export const INDIRECT_MIN_STRENGTH_ERROR = "最小关联强度必须在 0-1 范围内";

const indirectCoreNodeIdPattern = /^[\w\u4e00-\u9fff·.-]+$/u;

export interface ExpertIndirectFormValues {
  core_node_id?: string;
  relation_types?: string;
  path_depth?: string;
  min_strength?: string;
  [key: string]: string | undefined;
}

export interface ExpertIndirectPayload {
  core_node_id: string;
  relation_types: string[];
  path_depth: number;
  min_strength: number;
}

export interface ExpertIndirectValidationResult {
  errors: Record<string, string>;
  hasMissingRequired: boolean;
  payload: ExpertIndirectPayload | null;
}

export function indirectCoreNodeIdError(value: string): string | null {
  if (value.length > INDIRECT_CORE_NODE_ID_MAX_LENGTH) {
    return `输入长度不能超过 ${INDIRECT_CORE_NODE_ID_MAX_LENGTH} 个字符`;
  }
  if (value && !indirectCoreNodeIdPattern.test(value)) {
    return INDIRECT_CORE_NODE_ID_ERROR;
  }
  return null;
}

export function indirectPathDepthError(value: string): string | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const depth = Number(normalized);
  return Number.isInteger(depth) && (depth === 2 || depth === 3)
    ? null
    : INDIRECT_PATH_DEPTH_ERROR;
}

export function indirectMinStrengthError(value: string): string | null {
  const normalized = value.trim();
  if (!normalized) return null;
  const strength = Number(normalized);
  return Number.isFinite(strength) && strength >= 0 && strength <= 1
    ? null
    : INDIRECT_MIN_STRENGTH_ERROR;
}

export function validateExpertIndirectParameters(
  values: ExpertIndirectFormValues,
): ExpertIndirectValidationResult {
  const errors: Record<string, string> = {};
  const coreNodeIdRaw = values.core_node_id ?? "";
  const coreNodeId = coreNodeIdRaw.trim();
  const relationType = (values.relation_types ?? "").trim();

  if (!coreNodeId) {
    errors.core_node_id = "请输入核心专家或人才节点 ID";
  } else {
    const error = indirectCoreNodeIdError(coreNodeIdRaw);
    if (error) errors.core_node_id = error;
  }
  if (!relationType) errors.relation_types = "请选择间接关系类型";

  const pathDepthRaw = values.path_depth ?? "";
  const pathDepthError = indirectPathDepthError(pathDepthRaw);
  if (pathDepthError) errors.path_depth = pathDepthError;

  const minStrengthRaw = values.min_strength ?? "";
  const minStrengthError = indirectMinStrengthError(minStrengthRaw);
  if (minStrengthError) errors.min_strength = minStrengthError;

  const hasMissingRequired = !coreNodeId || !relationType;
  if (Object.keys(errors).length) {
    return { errors, hasMissingRequired, payload: null };
  }

  return {
    errors,
    hasMissingRequired,
    payload: {
      core_node_id: coreNodeId,
      relation_types: [relationType],
      path_depth: pathDepthRaw.trim() === "" ? 2 : Number(pathDepthRaw),
      min_strength:
        minStrengthRaw.trim() === "" ? 0.65 : Number(minStrengthRaw),
    },
  };
}
