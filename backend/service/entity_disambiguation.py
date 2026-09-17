"""实体消歧（写前判定）纯函数：名称标准化 / 候选评分 / 三分支决策。

被 ``temporal_workflows.resolve_entity_batch`` 调用，构成消歧 v2 的判定核心：

- 得分 ≥ ``MERGE_THRESHOLD`` 且与次名候选分差 ≥ ``MARGIN`` → 并入已有实体
  （改写 vid，INSERT VERTEX 幂等 upsert 即"合并"）；
- 落入灰区 [``GRAY_LOW``, ``MERGE_THRESHOLD``) → 扣留该记录并创建 T_LINK
  人工裁决 case；
- 低于 ``GRAY_LOW`` → 新实体原样写图。

阈值与权重为 v1 初值，待人工复核样本校准（docs/实体消歧与入库对齐-落地方案
（人工审核专项）.md §5）。召回当前走图库同名精确匹配（与消歧 v1 检测同源），
Milvus 模糊召回为后续增强；名称相似度用 RapidFuzz 词面比对，与
``organization_entity_alignment`` 的编码器解耦。
"""

from __future__ import annotations

from typing import Any

from rapidfuzz import fuzz

from service.organization_entity_alignment import normalize_alignment_text

MERGE_THRESHOLD = 0.85
GRAY_LOW = 0.65
MARGIN = 0.08
NAME_WEIGHT = 0.6
PROPS_WEIGHT = 0.4
TOP_K = 5

# 显示名按序取值；平台溯源列与身份列不参与属性一致性计算
_NAME_KEYS = ("name", "name_cn", "name_en", "name_zh")
_META_PROP_KEYS = {"id", "vid", "create_time", "update_time", "source_table", *_NAME_KEYS}


def display_name(props: dict[str, Any] | None) -> str:
    for key in _NAME_KEYS:
        value = str((props or {}).get(key) or "").strip()
        if value:
            return value
    return ""


def normalize_display_name(value: Any) -> str:
    return normalize_alignment_text(value)


def _comparable(value: Any) -> str | None:
    if value is None:
        return None
    return normalize_alignment_text(value) or None


def score_candidate(
    incoming_name: str,
    incoming_props: dict[str, Any] | None,
    cand_name: str,
    cand_props: dict[str, Any] | None,
) -> tuple[float, dict[str, Any]]:
    """单候选加权评分：``NAME_WEIGHT``*名称相似 + ``PROPS_WEIGHT``*属性一致率。

    只比较双方都非空的业务属性（平台列/身份列/``_`` 元字段排除）；无可比属性时
    属性分记 0.5（未知中性——同名但无从比对，既不推向自动合并也不推向新建）。
    """
    name_sim = (
        fuzz.ratio(normalize_display_name(incoming_name), normalize_display_name(cand_name)) / 100.0
    )
    common: list[str] = []
    agree = 0
    for key, value in (incoming_props or {}).items():
        if key in _META_PROP_KEYS or str(key).startswith("_"):
            continue
        left = _comparable(value)
        right = _comparable((cand_props or {}).get(key))
        if left is None or right is None:
            continue
        common.append(key)
        if left == right:
            agree += 1
    props_agree = agree / len(common) if common else 0.5
    score = NAME_WEIGHT * name_sim + PROPS_WEIGHT * props_agree
    return score, {
        "nameSim": round(name_sim, 3),
        "propsAgree": round(props_agree, 3),
        "comparedProps": common,
    }


def decide(scored: list[dict[str, Any]]) -> dict[str, Any]:
    """三分支决策。``scored`` 形如 ``[{"vid", "name", "score"}...]``（调用方已
    排除自身与同批 vid）。返回 ``{"decision", "targetVid", "score", "margin"}``，
    decision ∈ merge / gray / new。

    单候选视为分差通过（仍受阈值与召回完整性约束）；双高分候选分差不足时
    强制进灰区人工裁决，不自动择一。
    """
    if not scored:
        return {"decision": "new", "targetVid": None, "score": 0.0, "margin": None}
    ranked = sorted(scored, key=lambda x: x["score"], reverse=True)
    best = ranked[0]
    second = ranked[1]["score"] if len(ranked) > 1 else None
    margin = None if second is None else round(best["score"] - second, 3)
    if best["score"] >= MERGE_THRESHOLD and (second is None or best["score"] - second >= MARGIN):
        return {
            "decision": "merge",
            "targetVid": best["vid"],
            "score": round(best["score"], 3),
            "margin": margin,
        }
    if best["score"] >= GRAY_LOW:
        return {
            "decision": "gray",
            "targetVid": best["vid"],
            "score": round(best["score"], 3),
            "margin": margin,
        }
    return {
        "decision": "new",
        "targetVid": None,
        "score": round(best["score"], 3),
        "margin": margin,
    }
