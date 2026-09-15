"""关系抽取示例脚本（STEPS 多步版）：PRODUCES（Organization → Product）← 模拟来源表 demo_org_product。

kg.schema.extract 可上传样例（上传/绑定/触发同实体示例，见
sample_product_entity_extract.py 的说明）。与实体脚本的区别：

- **末步**返回 ``{"edges": [{"fromId", "toId", "props"}]}``（多步链里任意
  一步出了 entities/edges，平台就会在该步之后写图）；平台用 nGQL INSERT EDGE
  写边（列级 upsert）；
- 源行只有机构**名称**（org_name），没有机构 ID——端点 vid 要靠查表解析，
  这是 SDK ``ctx.mysql`` 的典型用法（resolver 查查找表；脚本仍不写库、不写图）；
- 名称唯一命中 → 出边；未命中 / 多义 → **不自动建边**，resolve 步产出
  ``pendingReview`` 项入人工审核队列（T_LINK「实体对齐裁决」），管线不暂停；
- 查找表在 resolve 步每次调用时现载（每步一个子进程，跨批不驻留），与仓库内
  invented_by 等注册脚本的口径一致。

多步形态：顶层 ``STEPS`` 清单（与 ``transform`` 互斥，二者只能取一），平台
按序执行、每步一次 Temporal activity——第 k 步失败只重试第 k 步，前序步输出
经事件历史重放。三步链：行清洗 → 机构名解析 → 出边。failures 跨步聚合，
水位仍按来源整链推进（重跑幂等，边为 upsert）。

SDK 用法（``from kg_sdk import current_context``）：

- ``ctx.mysql``：任务选择了 MySQL 数据源（或来源绑定回退注入）才有。
  resolver 类脚本缺它没法干活——按 platform_clients 约定抛 RuntimeError，
  提示建任务时选择对应配置，而不是静默产出空结果；
- ``ctx.config``：来源级增量游标（``kg_script_watermark``，``source:{绑定id}``
  为键，多步链里每一步读到的相同）——querySql 绑定的行过滤平台已按水位做完，
  脚本侧一般只作观测/排查；**只读**（脚本写回 ``_watermark`` 会被忽略），
  第 1 步演示读取；
- ``ctx.step_id`` / ``ctx.attempt``：多步时 step_id 形如
  ``source:{绑定id}#{stepId}``，用于日志/审核观测；
- ``ctx.prev_outputs``：按 stepId 读本批次已完成步输出（仅旁路观测用，
  大输出会被平台按预算截断，业务数据走 ``payload["input"]``）；
- ``ctx.graph``：本示例不需要（不做端点验存）；需要按图内现存实体过滤
  候选时可用 ``ctx.graph.execute_read(...)``。

模拟来源表 demo_org_product 的列：
    id, org_name, product_name, is_main_business, updated_time

前置依赖：Organization 实体已由机构抽取脚本写入（org vid = ``org_{org_id}``），
Product 实体已由 sample_product_entity_extract.py 写入（product vid 用同一
名称 md5 公式——本文件内联了同款 ``product_vid``，两处必须保持一致）。
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any

# 平台按清单顺序执行：第 1 步消费平台读的源表行，后续步消费上一步输出
STEPS = [
    {"id": "normalize", "fn": "step_normalize"},
    {"id": "resolve", "fn": "step_resolve"},
    {"id": "emit", "fn": "step_emit"},
]

# 机构名查找表：名称 → org_id 的候选集合。按需 UNION 更多机构表
# （dwd_org_heis_info / dwd_research_institute_base_info ...），与仓库内
# ExactOrganizationResolver 的多表口径一致；示例只演示一张表。
_ORG_LOOKUP_SQL = """
SELECT org_id, name_cn, name_en
FROM dwd_org_base_info
WHERE org_id IS NOT NULL
  AND ((name_cn IS NOT NULL AND name_cn <> '') OR (name_en IS NOT NULL AND name_en <> ''))
"""

_VID_MAX_BYTES = 64


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_name(value: Any) -> str:
    """机构名归一化键：NFKC + 空白折叠 + casefold（与查找表两侧同公式）。"""
    return unicodedata.normalize("NFKC", _clean(value)).casefold()


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


def product_vid(name: Any) -> str:
    """与实体抽取示例同源的 product vid 公式（product_{md5(规范化名称)}）。"""
    normalized = _normalize_name(name)
    if not normalized:
        raise ValueError("missing product name")
    vid = f"product_{_md5_hex(normalized)}"
    if len(vid.encode("utf-8")) <= _VID_MAX_BYTES:
        return vid
    return vid[: _VID_MAX_BYTES - 33] + "_" + _md5_hex(vid)


def _row_id(row: Mapping[str, Any]) -> str:
    """行溯源 id：优先源表主键，缺主键时退化为整行 JSON 摘要。"""
    if row.get("id") is not None:
        return str(row["id"])
    return json.dumps(
        {k: str(v) for k, v in row.items()}, ensure_ascii=False, sort_keys=True
    )[:64]


def _org_index(ctx: Any) -> dict[str, list[str]]:
    """经 SDK ctx.mysql 加载机构名查找表：归一名 → org_id 候选列表。"""
    if ctx is None or ctx.mysql is None:
        raise RuntimeError(
            "本抽取脚本需要平台注入 mysql 资源（请在触发任务时选择 MySQL 数据源，"
            "或确认来源表绑定带 datasourceId）"
        )
    from sqlalchemy import text

    index: dict[str, list[str]] = {}
    with ctx.mysql.engine.connect() as conn:
        rows = conn.execute(text(_ORG_LOOKUP_SQL)).mappings().all()
    for row in rows:
        org_id = _clean(row.get("org_id"))
        if not org_id:
            continue
        for column in ("name_cn", "name_en"):
            key = _normalize_name(row.get(column))
            if key:
                candidates = index.setdefault(key, [])
                if org_id not in candidates:
                    candidates.append(org_id)
    return index


def _review_item(
    *,
    reason: str,
    org_name: str,
    candidates: list[dict[str, Any]],
    product_name: str,
    to_id: str,
    record_id: str,
    confidence: float | None,
    source_table: str,
) -> dict[str, Any]:
    """歧义/未命中候选 → pendingReview 项（字段口径见
    script/extract_transform_common.py 的 pending_review_items；平台
    create_direct_case 逐字段 .get，缺省安全）。
    """
    return {
        "kind": "relation",
        "candidate": {
            "reason": reason,
            "confidence": confidence,
            "candidates": candidates,
            "source_record_id": record_id,
        },
        "objectId": record_id,
        "objectName": org_name,
        "edgeType": "PRODUCES",
        # fromId 留空：机构端点尚未定案，裁决通过后由审核侧补齐
        "toId": to_id,
        "reason": reason,
        "confidence": confidence,
        "evidence": [f"产品：{product_name}", f"来源行：{source_table}#{record_id}"],
        "sourceTable": source_table,
        "sourceRecordId": record_id,
    }


def step_normalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    """第 1 步：行清洗（strip/空白折叠，丢端点名称缺失行）。

    只出中转数据：额外键 ``cleaned`` 原样流向 resolve 步的 ``input``。
    """
    from kg_sdk import current_context

    rows = payload.get("rows") or []
    failures: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        org_name = _clean(row.get("org_name"))
        product_name = _clean(row.get("product_name"))
        if not org_name or not product_name:
            # 逐行失败进 failures：平台落 T_EXTRACT_FAIL 审核 case，可点重跑
            failures.append(
                {
                    "recordId": _row_id(row),
                    "error": f"org_name/product_name 缺失（id={_row_id(row)}）",
                }
            )
            continue
        cleaned.append(
            {
                **row,
                "org_name": org_name,
                "product_name": product_name,
                "is_main_business": _clean(row.get("is_main_business")),
            }
        )
    # SDK：ctx.config 读来源级增量游标（只读，写回 _watermark 会被平台忽略）；
    # 本地直跑无 KG_SCRIPT_CTX 时 ctx 为 None，判空降级
    ctx = current_context()
    stats: dict[str, Any] = {
        "rows": len(rows),
        "cleaned": len(cleaned),
        "failed": len(failures),
    }
    if ctx is not None:
        stats["watermark"] = ctx.config.watermark
        stats["pkCursor"] = (ctx.config.checkpoint or {}).get("pkCursor")
    return {"cleaned": cleaned, "failures": failures, "stats": stats}


def step_resolve(payload: Mapping[str, Any]) -> dict[str, Any]:
    """第 2 步：机构名 → org vid 解析（SDK ``ctx.mysql`` 查查找表）。

    唯一命中 → ``resolved``（含端点 vid 与匹配置信度）；未命中/多义 →
    ``pendingReview``（T_LINK 人工裁决，不阻塞管线）。
    """
    from kg_sdk import current_context

    ctx = current_context()
    org_index = _org_index(ctx)
    source_table = str(payload.get("source_table") or "")

    resolved: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for row in payload["input"]["cleaned"]:
        record_id = _row_id(row)
        org_ids = org_index.get(_normalize_name(row["org_name"]), [])
        if len(org_ids) == 1:
            resolved.append(
                {
                    **row,
                    "org_vid": f"org_{org_ids[0]}",
                    "match_evidence": f"机构名精确且唯一命中 dwd_org_base_info#{org_ids[0]}",
                }
            )
            continue
        # 未命中 / 多义：不自动建边，交人工裁决
        reason = (
            f"机构名命中 {len(org_ids)} 个候选，无法唯一定位"
            if org_ids
            else "机构名未在查找表中命中"
        )
        pending.append(
            _review_item(
                reason=reason,
                org_name=row["org_name"],
                candidates=[{"name": row["org_name"], "orgId": oid} for oid in org_ids[:5]],
                product_name=row["product_name"],
                to_id=product_vid(row["product_name"]),
                record_id=record_id,
                confidence=0.50 if len(org_ids) == 1 else None,
                source_table=source_table,
            )
        )
    return {
        "resolved": resolved,
        "pendingReview": pending,
        "stats": {"resolved": len(resolved), "pending": len(pending)},
    }


def step_emit(payload: Mapping[str, Any]) -> dict[str, Any]:
    """第 3 步：出边（平台负责 nGQL INSERT EDGE 写图）。"""
    from kg_sdk import current_context

    # SDK 演示：prev_outputs 按 stepId 读任意已完成步输出（仅旁路观测——
    # 大输出会被平台按预算截断，业务数据走 payload["input"]）
    ctx = current_context()
    resolve_stats = (
        (ctx.prev_outputs.get("resolve", {}).get("stats") if ctx else None) or {}
    )

    edges = [
        {
            "fromId": row["org_vid"],
            "toId": product_vid(row["product_name"]),
            "props": {
                "source_record_id": _row_id(row),
                "confidence": 0.90,
                "match_method": "exact_name",
                "match_evidence": row["match_evidence"],
                "is_main_business": row.get("is_main_business") or "",
            },
        }
        for row in payload["input"]["resolved"]
    ]
    return {
        "edges": edges,
        "stats": {
            "edges": len(edges),
            "resolved": resolve_stats.get("resolved", len(payload["input"]["resolved"])),
        },
    }
