"""实体消歧（写前判定）纯函数：名称标准化 / 候选评分 / 三分支决策。

被 ``temporal_workflows.resolve_entity_batch`` 调用，构成消歧 v2 的判定核心：

- 得分 ≥ ``MERGE_THRESHOLD`` 且与次名候选分差 ≥ ``MARGIN`` → 并入已有实体
  （改写 vid，INSERT VERTEX 幂等 upsert 即"合并"）；
- 落入灰区 [``GRAY_LOW``, ``MERGE_THRESHOLD``) → 扣留该记录并创建 T_LINK
  人工裁决 case；
- 低于 ``GRAY_LOW`` → 新实体原样写图。

阈值与权重为 v1 初值，待人工复核样本校准（docs/实体消歧与入库对齐-落地方案
（人工审核专项）.md §5）。召回为多路：图库同名精确匹配（与消歧 v1 检测同源）
∪ Milvus 稠密近邻（``kg_entity``，见 ``recall_candidates``）——近邻路把
「名称相近但不同名」的候选也送进评分，名称相似度因此不再是常量 1.0，
``NAME_WEIGHT`` 才有真实区分作用；名称相似度用 RapidFuzz 词面比对，与
``organization_entity_alignment`` 的编码器解耦。
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Iterable
from typing import Any

from rapidfuzz import fuzz

from service.organization_entity_alignment import normalize_alignment_text

logger = logging.getLogger(__name__)

MERGE_THRESHOLD = 0.85
GRAY_LOW = 0.65
MARGIN = 0.08
NAME_WEIGHT = 0.6
PROPS_WEIGHT = 0.4
TOP_K = 5

# 显示名按序取值；平台溯源列与身份列不参与属性一致性计算。
# 中文优先：name_en 提前会把 王毅/王祎/王翊 这类同英文名的不同学者坍缩成
# 同一显示名，批内去重直接错并（2026-10-16 一2/一3 幽灵点根因）
_NAME_KEYS = ("name", "name_zh", "name_cn", "name_en")
# 平台溯源/摄取元数据列整组排除：同一源表内这些列近乎恒定（source_system、
# ingest_batch 全批同值）或与身份无关（match_method、scholar_status 是厂商
# 匹配过程标注）——参与评分会把「同名不同人」的属性一致率基线抬高到 ~0.37
# （总分 ~0.74），真实业务特征（机构/领域/学历）的分歧被稀释，灰区 case 虚高
# （2026-10-16 王祎/王翊 样本实测）。业务列不同来源命名不一，无法穷举，这里
# 只收平台与摄取管线自身的元数据列。
_META_PROP_KEYS = {
    "id",
    "vid",
    "create_time",
    "update_time",
    "source_table",
    *_NAME_KEYS,
    "source",
    "source_system",
    "source_record_id",
    "source_url",
    "source_update_time",
    "ingest_batch",
    "ingest_time",
    "match_evidence",
    "match_method",
    "scholar_status",
    "confidence",
}


def display_name(props: dict[str, Any] | None) -> str:
    for key in _NAME_KEYS:
        value = str((props or {}).get(key) or "").strip()
        if value:
            return value
    return ""


def normalize_display_name(value: Any) -> str:
    return normalize_alignment_text(value)


def name_columns_in(fields: Iterable[str]) -> list[str]:
    """从 tag 实际 schema 列里挑存在的显示名列（按 ``_NAME_KEYS`` 优先级）。

    不同来源的 tag 主名列不一：schema 管理建的是 ``name``，vendor ETL 的
    Organization 是 ``name_cn``——同名召回的 WHERE 只能引用实际存在的列，
    否则 NebulaGraph 直接 SemanticError。
    """
    return [key for key in _NAME_KEYS if key in fields]


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


# 同名召回的名字分块：单条 MATCH 的 IN 列表与名单长度成比例地撑大 graphd
# 查询内存（抽取批次 2000 时每批两条 2000 名巨查 ×4 并发，实测把共享图库
# 推过内存高水位，缺陷㉘）。分块后单查询形状有界，结果按块合并；每块各自
# LIMIT 200，召回总量相对旧的全批一条 LIMIT 200 只多不少（旧实现本就是任意
# 截断，分块反而更完整）。
_RECALL_NAME_CHUNK = 150


def recall_same_name(client: Any, tag: str, names: list[str]) -> dict[str, list[dict[str, Any]]]:
    """图库同名召回：``{显示名: [{"vid", "name", "props"}...]}``。

    ``resolve_entity_batch`` 与 pendingReview 挂实体改道共用的召回口径：
    DESCRIBE 探测 tag 实际存在的显示名列（不同来源主名列不一，引用不存在的列
    直接 SemanticError）→ MATCH 精确召回并带候选完整属性（供 score_candidate
    多证据评分）；``properties()`` 失败降级为仅名称比对（props 为空 dict，属性
    分走 0.5 中性）。tag 无显示名列时返回空 dict（调用方拿不到候选即按低分
    处理）。只依赖传入 client，同步函数，异常语义由调用方决定。
    名单按 ``_RECALL_NAME_CHUNK`` 分块查询后合并（见其注释）。

    名称列一律 tag 限定（``v.`{tag}`.`{col}```）：ETL 混入共享 tag（如
    organization_base）的顶点是多 tag 顶点，非限定属性访问会被引擎按另一 tag
    解析成 NULL——WHERE 静默不命中，同名召回凭空变空。MATCH 已按 tag 锚定，
    限定引用恒安全（单 tag 顶点同样正确）。
    """
    if not names:
        return {}
    try:
        described = client.execute_query(f"DESCRIBE TAG `{tag}`")
        fields = {
            f for f in (r.get("Field") for r in described.records or []) if isinstance(f, str)
        }
        name_cols = name_columns_in(fields)
    except Exception:  # noqa: BLE001
        logger.warning("DESCRIBE TAG %s 失败，同名召回按 name 列兜底", tag)
        name_cols = ["name"]
    if not name_cols:
        logger.info("tag %s 无显示名列（name/name_zh/name_cn/name_en），跳过同名召回", tag)
        return {}
    existing: dict[str, list[dict[str, Any]]] = {}
    for start in range(0, len(names), _RECALL_NAME_CHUNK):
        chunk = names[start : start + _RECALL_NAME_CHUNK]
        name_list = ",".join(json.dumps(n, ensure_ascii=False) for n in chunk)
        where = " OR ".join(f"v.`{tag}`.`{col}` IN [{name_list}]" for col in name_cols)
        select_names = ", ".join(
            f"v.`{tag}`.`{col}` AS `nm{idx}`" for idx, col in enumerate(name_cols)
        )
        base_match = f"MATCH (v:`{tag}`) WHERE {where} RETURN id(v) AS vid, {select_names}"
        try:
            result = client.execute_read(f"{base_match}, properties(v) AS props LIMIT 200")
            name_only = False
        except Exception:  # noqa: BLE001
            logger.warning("同名召回 properties() 失败，降级为仅名称比对")
            result = client.execute_read(f"{base_match} LIMIT 200")
            name_only = True
        for rec in result.records or []:
            vid = str(rec.get("vid") or "")
            props = {} if name_only else (rec.get("props") or {})
            if name_only:
                display = next(
                    (
                        str(rec.get(f"nm{idx}") or "")
                        for idx in range(len(name_cols))
                        if rec.get(f"nm{idx}")
                    ),
                    "",
                )
            else:
                display = display_name(props)
            if display and vid:
                existing.setdefault(display, []).append(
                    {"vid": vid, "name": display, "props": props}
                )
    return existing


# ---------------------------------------------------------------------------
# 多路召回：Milvus 稠密近邻路（fail-open，可与同名精确路独立开关）
# ---------------------------------------------------------------------------

# m3e 名称语料上无关实体的余弦相似度普遍 0.7 上下（实测「华为技术」对无关公司
# 0.69-0.76，精确同名 0.87）——最小相似度 0.75 起步偏保守，宁漏召不淹候选：
# 漏掉的仍走同名路原语义，淹没则灰区 case 暴涨。近邻路每名取 TOP_K=10，
# 与 existingCandidates 的 TOP_K=5 之间留出排序淘汰余量。
_MILVUS_RECALL_TOP_K_DEFAULT = 10
_MILVUS_RECALL_MIN_SIM_DEFAULT = 0.75
# 与 entity_search 的 EMBED_BATCH_SIZE 同口径：m3e 单批 ≤64，超限服务 422 拒整批
_MILVUS_QUERY_CHUNK = 64


def _milvus_recall_top_k() -> int:
    try:
        return max(1, int(os.getenv("ENTITY_DISAMBIGUATION_MILVUS_TOP_K", "")))
    except ValueError:
        return _MILVUS_RECALL_TOP_K_DEFAULT


def _milvus_recall_min_sim() -> float:
    try:
        value = float(os.getenv("ENTITY_DISAMBIGUATION_MILVUS_MIN_SIM", ""))
    except ValueError:
        return _MILVUS_RECALL_MIN_SIM_DEFAULT
    return min(1.0, max(0.0, value))


def _milvus_fuzzy_recall(
    tag: str,
    names: list[str],
    space: str | None,
    *,
    milvus: Any | None = None,
    embedder: Any | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """Milvus 稠密近邻召回（fail-open）：``{显示名: [{"vid","name","props","similarity"}...]}``。

    复用实体检索的 ``kg_entity`` 集合（抽取链路末尾 reindex 全量同步 + T_LINK
    裁决落图后增量 upsert 维护），按 ``graph_space`` + ``entity_type`` 过滤取
    稠密向量近邻。候选属性取集合内嵌的 ``properties``（reindex 时从图库同步的
    JSON 快照），不回图逐点取——索引滞后最多损失一点属性一致率（偏保守，落
    灰区转人工），换取消歧主通道零额外图查询。

    任何一步不可用（开关关闭 / embedding 未配置 / 集合不存在 / 空间未建索引 /
    检索异常）都返回空 dict，调用方退化为仅同名精确召回，不阻塞写图。
    """
    if not names:
        return {}
    if os.getenv("ENTITY_DISAMBIGUATION_MILVUS_RECALL", "1") == "0":
        return {}
    try:
        if embedder is None:
            from service.entity_search import _embedding_client

            embedder = _embedding_client()
        if embedder is None:
            logger.info("消歧 Milvus 召回：embedding 未配置，退化为仅同名精确召回")
            return {}
        if milvus is None:
            from infra.milvus import get_milvus_client

            milvus = get_milvus_client()
        from service.entity_search import (
            COLLECTION_NAME,
            _escape_expression,
            _milvus_space_has_rows,
        )

        assert milvus is not None  # 上一分支已赋值；仅为收窄类型
        if not milvus.has_collection(COLLECTION_NAME):
            logger.info("消歧 Milvus 召回：kg_entity 集合不存在，退化为仅同名精确召回")
            return {}
        if not space:
            from infra.graph_db.config import TRSGraphSettings

            space = TRSGraphSettings.from_env().space
        if not _milvus_space_has_rows(milvus, space):
            logger.info("消歧 Milvus 召回：图空间 %s 未建实体索引，退化为仅同名精确召回", space)
            return {}
        vectors = embedder.embed(names)
        if not vectors or len(vectors) != len(names):
            logger.info("消歧 Milvus 召回：名称 embedding 失败，退化为仅同名精确召回")
            return {}
        top_k = _milvus_recall_top_k()
        min_sim = _milvus_recall_min_sim()
        expr = (
            f'graph_space == "{_escape_expression(space)}" '
            f'and entity_type == "{_escape_expression(tag)}"'
        )
        hits_by_idx: dict[int, list[dict[str, Any]]] = {}
        for start in range(0, len(names), _MILVUS_QUERY_CHUNK):
            chunk = vectors[start : start + _MILVUS_QUERY_CHUNK]
            response = milvus.search(
                collection_name=COLLECTION_NAME,
                data=chunk,
                anns_field="dense_vector",
                search_params={"metric_type": "COSINE", "params": {"ef": max(128, top_k * 2)}},
                filter=expr,
                limit=top_k,
                output_fields=["vid", "name", "properties"],
            )
            for offset, query_hits in enumerate(response or []):
                for hit in query_hits or []:
                    if not isinstance(hit, dict):
                        continue
                    similarity = float(hit.get("distance") or 0.0)
                    if similarity < min_sim:
                        continue
                    fields = hit.get("entity") or {}
                    vid = str(fields.get("vid") or "")
                    if not vid:
                        continue
                    raw_props = fields.get("properties")
                    props: dict[str, Any] = {}
                    if isinstance(raw_props, str) and raw_props:
                        try:
                            parsed = json.loads(raw_props)
                            props = parsed if isinstance(parsed, dict) else {}
                        except ValueError:
                            props = {}
                    elif isinstance(raw_props, dict):
                        props = raw_props
                    hits_by_idx.setdefault(start + offset, []).append(
                        {
                            "vid": vid,
                            "name": str(fields.get("name") or ""),
                            "props": props,
                            "similarity": round(similarity, 4),
                        }
                    )
        return {names[idx]: cands for idx, cands in hits_by_idx.items() if 0 <= idx < len(names)}
    except Exception:  # noqa: BLE001 - 近邻路失败绝不阻塞写前消歧
        logger.warning("消歧 Milvus 召回失败，退化为仅同名精确召回", exc_info=True)
        return {}


def recall_candidates(
    client: Any, tag: str, names: list[str], *, space: str | None = None
) -> dict[str, list[dict[str, Any]]]:
    """消歧多路召回（写前判定与挂实体改道的统一入口）：

    图库同名精确（``recall_same_name``）∪ Milvus 稠密近邻（``_milvus_fuzzy_recall``），
    两路并集按 vid 去重、同名路在前（保序稳定）。近邻路 fail-open——不可用即
    退化为仅同名精确召回，行为与旧版完全一致。返回形状与 ``recall_same_name``
    一致，近邻路候选额外附 ``similarity``（稠密相似度，供排查）。
    """
    exact = recall_same_name(client, tag, names)
    fuzzy = _milvus_fuzzy_recall(tag, names, space)
    if not fuzzy:
        return exact
    merged: dict[str, list[dict[str, Any]]] = {}
    for name in names:
        cands = list(exact.get(name) or [])
        seen = {str(c.get("vid")) for c in cands}
        for cand in fuzzy.get(name) or []:
            if str(cand.get("vid")) not in seen:
                cands.append(cand)
        if cands:
            merged[name] = cands
    return merged
