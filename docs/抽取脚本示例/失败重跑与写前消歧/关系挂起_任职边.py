"""关系挂起示例脚本（@step 多步版）：WORKS_AT（Expert → Organization）
← 模拟来源表 demo_works_at_relation。

演示关系写入前的**消歧挂起**：源行只有机构**名称**没有机构 ID，脚本按
别名表解析端点——

- 机构名唯一命中 → 出 WORKS_AT 边（平台 nGQL INSERT EDGE）；
- 未命中 / 命中多个 → 不自动建边，产出 ``pendingReview`` 项入人工审核
  队列（默认模板 T_DIRECT：accept 后由审核侧直接写图；统一写前消歧方案
  落地后并入 T_LINK「消歧裁决」，见 docs/T_DIRECT统一写前消歧方案.md），
  管线不暂停；
- 专家端点指向**灰区扣留中实体**（如 写前消歧_同名专家.py 第二轮的
  expert_E2002）时，平台 write_records 会把边停靠进该实体的 T_LINK case
  （``_pendingRelations``），人裁 merge/create 后自动补写——脚本无感知。

机构别名表**内联**（演示用；真实脚本用 ``ctx.mysql`` 查机构字典表，见
sample_produces_relation_extract.py 的 _org_index）。查找表每步现载（每步
一个子进程，跨批不驻留），口径与仓库内 registered 抽取脚本一致。

failures 语义同前两个脚本（毒行隔离 → T_EXTRACT_FAIL → 可点重跑）。
pendingReview 项字段口径见 script/extract_transform_common.py 的
pending_review_items（平台 create_direct_case 逐字段 .get，缺省安全）。

数据配套：``demo_数据.sql`` 的 A3 段（表 demo_works_at_relation：2 条可
解析、1 条多义、1 条未命中、2 条毒行）。本地零库验证：``python 本地验证.py``。

模拟来源表 demo_works_at_relation 的列：
    id, expert_id, expert_name, org_name, position, start_date, update_time
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from kg_sdk import step

# 演示用机构别名表：归一化机构名 → org_id 候选集合（真实脚本查字典表）
_ORG_ALIASES: dict[str, list[str]] = {
    "浙江大学": ["org_zju"],
    "浙大": ["org_zju"],
    "中国科学院": ["org_cas"],
    "中科院": ["org_cas"],
    # 「华科」多义：两个候选 → 演示 pendingReview（命中多个）
    "华科": ["org_hust", "org_scut"],
    # 「未来科技大学」不在表中 → 演示 pendingReview（未命中）
}


def _clean(value: Any) -> str:
    """strip + 折叠空白，空白返回空串。"""
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _normalize_name(value: Any) -> str:
    """机构名归一化键：NFKC + 空白折叠 + casefold（与别名表两侧同公式）。"""
    return unicodedata.normalize("NFKC", _clean(value)).casefold()


def expert_vid(expert_id: Any) -> str:
    """专家稳定 vid：expert_{expert_id}。

    与 写前消歧_同名专家.py 的同款公式必须保持一致，否则边端点对不上
    实体点（端点停靠/裁决补写也按 vid 匹配）。
    """
    raw = _clean(expert_id)
    if not raw:
        raise ValueError("missing expert_id")
    vid = f"expert_{raw}"
    if len(vid.encode("utf-8")) <= 64:
        return vid
    return vid[:31] + "_" + hashlib.md5(vid.encode(), usedforsecurity=False).hexdigest()


def org_vid(org_id: str) -> str:
    """机构端点 vid：org_{org_id}（别名表候选即 org_id）。"""
    return f"org_{org_id}"


def _row_id(row: Mapping[str, Any]) -> str:
    """行溯源 id：优先源表主键，缺主键退化整行 JSON 摘要。"""
    if row.get("id") is not None:
        return str(row["id"])
    digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"row:{digest[:16]}"


def _review_item(
    *,
    reason: str,
    expert_name: str,
    expert_id: str,
    candidates: list[dict[str, Any]],
    record_id: str,
    confidence: float | None,
    source_table: str,
) -> dict[str, Any]:
    """歧义/未命中候选 → pendingReview 项（字段口径同
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
        "objectName": expert_name,
        "edgeType": "WORKS_AT",
        # toId 留空：机构端点尚未定案，裁决通过后由审核侧补齐
        "fromId": expert_vid(expert_id),
        "reason": reason,
        "confidence": confidence,
        "evidence": [f"专家：{expert_name}（{expert_id}）", f"来源行：{source_table}#{record_id}"],
        "sourceTable": source_table,
        "sourceRecordId": record_id,
    }


@step
def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """第 1 步：行清洗。expert_id/org_name 缺失 → failures（T_EXTRACT_FAIL 可重跑）。"""
    from kg_sdk import current_context

    rows = payload.get("rows") or []
    failures: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        expert_id = _clean(row.get("expert_id"))
        org_name = _clean(row.get("org_name"))
        if not expert_id or not org_name:
            failures.append(
                {
                    "recordId": _row_id(row),
                    "error": f"expert_id/org_name 缺失（id={_row_id(row)}）",
                }
            )
            continue
        cleaned.append(
            {
                **row,
                "expert_id": expert_id,
                "expert_name": _clean(row.get("expert_name")),
                "org_name": org_name,
                "position": _clean(row.get("position")),
                "start_date": _clean(row.get("start_date")),
            }
        )
    ctx = current_context()
    stats: dict[str, Any] = {
        "rows": len(rows),
        "cleaned": len(cleaned),
        "failed": len(failures),
    }
    if ctx is not None:
        stats["watermark"] = ctx.config.watermark
    return {"cleaned": cleaned, "failures": failures, "stats": stats}


@step
def resolve(payload: dict[str, Any]) -> dict[str, Any]:
    """第 2 步：机构名 → org vid 解析（演示用内联别名表）。

    唯一命中 → ``resolved``（含端点 vid 与匹配置信度）；未命中/多义 →
    ``pendingReview``（人工裁决，不阻塞管线）。
    """
    source_table = str(payload.get("source_table") or "")
    resolved: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for row in payload["input"]["cleaned"]:
        record_id = _row_id(row)
        org_ids = _ORG_ALIASES.get(_normalize_name(row["org_name"]), [])
        if len(org_ids) == 1:
            resolved.append(
                {
                    **row,
                    "org_vid": org_vid(org_ids[0]),
                    "match_evidence": f"机构名精确且唯一命中别名表#{org_ids[0]}",
                }
            )
            continue
        # 未命中 / 多义：不自动建边，交人工裁决
        reason = (
            f"机构名命中 {len(org_ids)} 个候选，无法唯一定位"
            if org_ids
            else "机构名未在别名表中命中"
        )
        pending.append(
            _review_item(
                reason=reason,
                expert_name=row.get("expert_name") or row["expert_id"],
                expert_id=row["expert_id"],
                candidates=[{"name": row["org_name"], "orgId": oid} for oid in org_ids[:5]],
                record_id=record_id,
                # 多义给 0.50（倾向有人同名歧义）；未命中不给置信度
                confidence=0.50 if org_ids else None,
                source_table=source_table,
            )
        )
    return {
        "resolved": resolved,
        "pendingReview": pending,
        "stats": {"resolved": len(resolved), "pending": len(pending)},
    }


@step
def emit(payload: dict[str, Any]) -> dict[str, Any]:
    """第 3 步：出边（平台负责 nGQL INSERT EDGE 写图 + 端点停靠/补写）。"""
    edges = [
        {
            "fromId": expert_vid(row["expert_id"]),
            "toId": row["org_vid"],
            "props": {
                "source_record_id": _row_id(row),
                "confidence": 0.90,
                "match_method": "exact_alias",
                "match_evidence": row["match_evidence"],
                "position": row.get("position") or "",
                "start_date": row.get("start_date") or "",
            },
        }
        for row in payload["input"]["resolved"]
    ]
    return {"edges": edges, "stats": {"edges": len(edges)}}
