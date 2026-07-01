"""企业名实体消歧：rapidfuzz 确定性匹配 gkx dwd_org_reg_info.name_cn。"""

from __future__ import annotations

from rapidfuzz import fuzz, process

MATCH_THRESHOLD = 70.0


def _combined_score(
    query: str, choice: str, score_cutoff: float | None = None, **_: object
) -> float:
    """取 token_set_ratio（token 集合重叠，容忍乱序/多余标点）与 partial_ratio（子串包含，
    适合简称→全称）的较大者。任一足够好即视为命中。

    接收 score_cutoff 仅为兼容 rapidfuzz process.extractOne 的调用约定（这里忽略，
    由 extractOne 统一在结果上过滤）。
    """
    return max(fuzz.token_set_ratio(query, choice), fuzz.partial_ratio(query, choice))


def disambiguate(name: str, candidates: list[tuple[str, str]]) -> dict | None:
    """把 LLM 抽取的企业名匹配到 gkx 真实企业。

    Args:
        name: LLM 抽取的企业名（可能为简称）。
        candidates: [(org_id, name_cn), ...] 候选集。

    Returns:
        {"org_id", "name_cn", "score"} 或 None（低于阈值）。
    """
    if not candidates:
        return None
    names = [c[1] for c in candidates]
    match = process.extractOne(name, names, scorer=_combined_score, score_cutoff=MATCH_THRESHOLD)
    if match is None:
        return None
    matched_name, score, idx = match
    return {"org_id": candidates[idx][0], "name_cn": matched_name, "score": round(float(score), 1)}


def merge_matches(matches: list[dict]) -> list[dict]:
    """同一 org_id 的多条命中合并：取最高分，relation_type 去重并集。"""
    by_org: dict[str, dict] = {}
    for m in matches:
        oid = m["org_id"]
        if oid not in by_org:
            by_org[oid] = {
                "org_id": oid,
                "name_cn": m["name_cn"],
                "score": m["score"],
                "relation_types": [],
                "role": m.get("role", "engineer"),
                "tech_field": m.get("tech_field", ""),
                "period_start": m.get("period_start", ""),
                "period_end": m.get("period_end", ""),
                "evidence": m.get("evidence", ""),
            }
        entry = by_org[oid]
        if m["score"] > entry["score"]:
            entry["score"] = m["score"]
            entry["name_cn"] = m["name_cn"]
            entry["role"] = m.get("role", entry["role"])
            entry["tech_field"] = m.get("tech_field", "") or entry["tech_field"]
            entry["evidence"] = m.get("evidence", "") or entry["evidence"]
        rt = m.get("relation_type", "")
        if rt and rt not in entry["relation_types"]:
            entry["relation_types"].append(rt)
    return list(by_org.values())
