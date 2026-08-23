"""企业名实体消歧：包含匹配（简称/实验室归属）+ rapidfuzz 模糊匹配。"""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

MATCH_THRESHOLD = 85.0
MIN_NAME_LEN = 3  # 剥后缀后最短有效名长，过滤"科技有限公司"等后缀碎片

# 公司通用后缀：匹配前剥离，避免"股份有限公司/有限公司"等共有后缀在 partial_ratio
# 中虚高打分，把不相关的公司误匹配（如"菲鹏生物股份有限公司"误中"上海微创…股份有限公司"）。
_COMPANY_SUFFIXES = ("股份有限公司", "有限责任公司", "有限公司", "集团", "公司", "厂")

# 非主体企业关键词（研究院/医院/高校等），包含匹配时降权
_NON_MAIN_KW = ("研究院", "研究所", "医院", "大学", "学院", "学校", "学会", "基金会")
# 主体企业行业关键词（技术/科技/集团等），包含匹配时优先
_MAIN_KW = (
    "技术",
    "科技",
    "计算机",
    "集团",
    "股份",
    "电子",
    "通信",
    "工业",
    "制造",
    "工程",
    "医药",
    "生物",
    "能源",
    "汽车",
    "智能",
    "信息",
)

_LEADING_CN = re.compile(r"[一-龥]+")


def _strip_suffix(name: str) -> tuple[str, bool]:
    """剥离公司通用后缀（仅剥最外层一个）。返回 (剥离后, 是否剥过后缀)。"""
    n = (name or "").strip()
    for suf in _COMPANY_SUFFIXES:
        if n.endswith(suf) and len(n) > len(suf):
            return n[: -len(suf)].strip(), True
    return n, False


def _leading_chinese(s: str) -> str:
    """取字符串开头的连续中文片段（用于"腾讯Jarvis实验室"→"腾讯"）。"""
    m = _LEADING_CN.match(s or "")
    return m.group(0) if m else ""


def _has_any(s: str, kws: tuple[str, ...]) -> bool:
    return any(k in s for k in kws)


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

    两阶段：
    1) 包含匹配——抽取名的开头中文片段（lead）是某候选剥后缀名的子串时命中。
       处理简称（腾讯→深圳市腾讯计算机系统有限公司）与实验室/部门归属
       （腾讯Jarvis实验室→腾讯）。多个命中时优先主体企业（lead 在开头、有行业词、
       无研究院等非主体词、名字较短）。
    2) 模糊匹配——rapidfuzz max(token_set_ratio, partial_ratio)，阈值 85。

    Args:
        name: LLM 抽取的企业名（可能为简称/含实验室）。
        candidates: [(org_id, name_cn), ...] 候选集。

    Returns:
        {"org_id", "name_cn", "score"} 或 None（低于阈值）。
    """
    if not candidates:
        return None
    query, had_suffix = _strip_suffix(name)
    # 后缀碎片（"科技有限公司"→"科技"）：剥后缀后过短且确有后缀被剥，拒绝
    if had_suffix and len(query) < MIN_NAME_LEN:
        return None
    # 预剥离候选，过滤垃圾名，保留原始索引
    valid: list[tuple[int, str]] = []
    for i, (_oid, nc) in enumerate(candidates):
        s, _ = _strip_suffix(nc)
        if len(s) >= MIN_NAME_LEN:
            valid.append((i, s))
    if not valid:
        return None

    lead = _leading_chinese(query)
    # 阶段1：包含匹配（lead≥2 是候选子串）
    if len(lead) >= 2:
        cont = [(i, s) for i, s in valid if lead in s]
        if cont:
            # 优先主体企业：lead 在开头 > 无非主体词 > 有行业词 > 名字短
            cont.sort(
                key=lambda x: (
                    not x[1].startswith(lead),
                    _has_any(x[1], _NON_MAIN_KW),
                    not _has_any(x[1], _MAIN_KW),
                    len(x[1]),
                )
            )
            best_idx = cont[0][0]
            return {
                "org_id": candidates[best_idx][0],
                "name_cn": candidates[best_idx][1],
                "score": 100.0,
            }

    # 阶段2：模糊匹配
    names = [s for _, s in valid]
    match = process.extractOne(query, names, scorer=_combined_score, score_cutoff=MATCH_THRESHOLD)
    if match is None:
        return None
    _matched, score, vi = match
    orig_idx = valid[vi][0]
    return {
        "org_id": candidates[orig_idx][0],
        "name_cn": candidates[orig_idx][1],
        "score": round(float(score), 1),
    }


def merge_matches(matches: list[dict]) -> list[dict]:
    """同一 org_id 的多条命中合并：取最高分，relation_type 去重并集。"""
    by_org: dict[str, dict] = {}
    for m in matches:
        oid = m["org_id"]
        if oid not in by_org:
            by_org[oid] = {
                "org_id": oid,
                "name_cn": m["name_cn"],
                "extracted_name": m.get("enterprise_name", "") or m.get("extracted_name", ""),
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
