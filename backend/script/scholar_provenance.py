"""学者领域入图的置信度与溯源字段约定。

四个学者域脚本（实体、关系、机构对齐、消歧）共用同一套规则，避免各写一份阈值。
字段命名沿用专利域 / 项目域已有约定，方便跨域统一查询：

- ``confidence``：double，0~1
- ``match_method``：判定方式，便于事后按方式聚合统计
- ``match_evidence``：判定依据的自然语言描述，人工复核时直接看这个字段
- ``organization_base`` / ``organization_id``：机构溯源表名与该表内的机构 ID

置信度分档：

- ``1.00`` 源表主键 / 稳定标识符直取，无歧义
- ``0.90`` 跨域标识符匹配，且两端顶点在图中均已存在
- 向量或模糊匹配：取实际相似度分值，不做人为抬高
- ``0.60`` 仅按机构名 md5 生成的桩机构，等正式 Organization 落地后对齐

低于 :data:`REVIEW_THRESHOLD` 的关系视为「待人工复核 / 待对齐」，不应直接当作
可信结论对外提供。
"""

from __future__ import annotations

from typing import Any

# 源表主键直取，无歧义
CONFIDENCE_SOURCE_PRIMARY_KEY = 1.0
# 跨域标识符匹配（如 dwd_scholar_paper_relation 的 paper_id 命中论文域顶点）
CONFIDENCE_CROSS_DOMAIN_ID = 0.9
# 仅按机构名 md5 生成的桩机构
CONFIDENCE_PLACEHOLDER_ORG = 0.6
# 低于该值即需要人工复核或等待对齐
REVIEW_THRESHOLD = 0.75

# 机构溯源缺失时的占位值，便于按该值反查未对齐的数据
ORGANIZATION_BASE_UNKNOWN = ""


def confidence_props(confidence: float, method: str, evidence: str) -> dict[str, Any]:
    """构造置信度三件套属性。

    Args:
        confidence: 置信度，0~1；越界值会被裁剪。
        method: 判定方式标识，如 ``source_primary_key``。
        evidence: 判定依据描述，供人工复核阅读。

    Returns:
        含 ``confidence`` / ``match_method`` / ``match_evidence`` 的属性字典。
    """
    bounded = max(0.0, min(1.0, float(confidence)))
    return {
        "confidence": round(bounded, 4),
        "match_method": method,
        "match_evidence": evidence,
    }


def organization_provenance(
    organization_base: Any | None,
    organization_id: Any | None,
) -> dict[str, str]:
    """构造机构溯源属性。

    Args:
        organization_base: 机构数据所在的源表名；未知时传 ``None``。
        organization_id: 机构在该源表内的 ID；未知时传 ``None``。

    Returns:
        含 ``organization_base`` / ``organization_id`` 的属性字典，缺失项为空串。
    """
    return {
        "organization_base": str(organization_base or ORGANIZATION_BASE_UNKNOWN).strip(),
        "organization_id": str(organization_id or "").strip(),
    }


def needs_review(confidence: float) -> bool:
    """置信度是否低到需要人工复核。"""
    return float(confidence) < REVIEW_THRESHOLD
