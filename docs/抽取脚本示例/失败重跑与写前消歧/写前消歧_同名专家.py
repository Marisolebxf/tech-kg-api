"""写前消歧示例脚本（@step 多步版）：Expert（专家）← 模拟来源表 demo_disambig_expert。

演示实体**写入图数据库前**的消歧阶段（消歧 v2，backend/service/
entity_disambiguation.py + temporal_workflows.resolve_entity_batch）：

- 脚本只负责出实体点（纯转换，不连图不写库）；平台在写图前对每条实体
  做**同名召回 + 加权评分**：score = 0.6×名称相似 + 0.4×属性一致率
  （只比双方都非空的业务属性；全空给中性 0.5），阈值 0.85 / 0.65 / 0.08；
- ≥0.85（单候选免分差）→ 自动并入已有实体（改写 vid，upsert 即合并）；
- [0.65, 0.85) → **扣留不写图**，建 T_LINK 人工裁决 case（审核队列 A 类，
  exception_code=KG_ENTITY_DISAMBIGUATION_GRAY），人在审核工作台裁决
  merge/create 后才落图；
- <0.65 → 新实体直接写图。

**两轮数据**（配套 demo_数据.sql 的 A2 段，第二轮 INSERT 默认注释着，
跑完第一轮抽取后再放开执行）——同名专家按属性重合度精确落三个分支：

| 第二轮行 | 与图内同名实体属性一致 | 得分 | 平台判定 |
|---|---|---|---|
| E2001 王伟（单位同、简介同） | 2/2 = 1.0 | 1.00 | merge 自动并入 E1001 |
| E2002 李娜（单位同、简介异） | 1/2 = 0.5 | 0.80 | **灰区 → T_LINK 扣留** |
| E2003 张敏（单位异、简介异） | 0/2 = 0.0 | 0.60 | new 直接新建 |
| E2004 刘洋（无单位、只有简介；图内同名者无简介） | 无可比属性 → 0.5 | 0.80 | **灰区 → T_LINK 扣留** |

vid 公式 ``expert_{expert_id}``（业务主键派生，不用姓名派生——同名不同人
必须不同 vid，消歧才有意义）；关系脚本 关系挂起_任职边.py 引用专家端点
必须用同一公式。E2002 被扣留期间，指向 expert_E2002 的边会被平台
park_or_rewrite_edges 停靠到 case 里，裁决后补写。

failures 语义与 失败重跑_产品实体.py 相同（毒行隔离 → T_EXTRACT_FAIL
→ 可点重跑）。

模拟来源表 demo_disambig_expert 的列：
    id, expert_id, name_zh, organization_name_zh, bio_zh, update_time
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from kg_sdk import step


def _clean(value: Any) -> str:
    """strip + 折叠空白，空白返回空串。"""
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def expert_vid(expert_id: Any) -> str:
    """专家稳定 vid：expert_{expert_id}（业务主键派生）。

    与 关系挂起_任职边.py 内联的同名函数必须保持一致，否则边端点对不上。
    """
    raw = _clean(expert_id)
    if not raw:
        raise ValueError("missing expert_id")
    vid = f"expert_{raw}"
    if len(vid.encode("utf-8")) <= 64:
        return vid
    return vid[:31] + "_" + hashlib.md5(vid.encode(), usedforsecurity=False).hexdigest()


def _record_id(row: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    """行溯源 id：优先源表主键（重跑按它回读），缺主键退化整行摘要。"""
    pk = (payload.get("source") or {}).get("pkColumn") or "id"
    if row.get(pk) is not None:
        return str(row[pk])
    digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"row:{digest[:16]}"


@step
def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """第 1 步：行清洗。expert_id/name_zh 缺失 → failures（T_EXTRACT_FAIL 可重跑）。"""
    from kg_sdk import current_context

    rows = payload.get("rows") or []
    failures: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        record_id = _record_id(row, payload)
        name = _clean(row.get("name_zh"))
        if not _clean(row.get("expert_id")) or not name:
            failures.append(
                {
                    "recordId": record_id,
                    "error": f"expert_id 或 name_zh 缺失（id={record_id}）",
                }
            )
            continue
        cleaned.append(
            {
                **row,
                "expert_id": _clean(row["expert_id"]),
                "name_zh": name,
                # organization_name_zh 允许为空：演示「无可比属性 → 中性 0.5 → 灰区」
                "organization_name_zh": _clean(row.get("organization_name_zh")),
                "bio_zh": _clean(row.get("bio_zh")),
            }
        )
    # SDK：ctx.config 读来源级增量游标（只读；本地直跑 ctx 为 None，判空降级）
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
def emit(payload: dict[str, Any]) -> dict[str, Any]:
    """第 2 步：出实体点 ``{"id": vid, "props": {...}}``。

    同名消歧（召回/评分/扣留建 T_LINK）全部由平台在写图前负责——脚本侧
    无感知；props 里 organization_name_zh / bio_zh 是消歧评分的可比属性，
    没有的宁可不输出（空值不参与评分，与图内实体「无可比属性」走中性 0.5）。
    """
    cleaned = payload["input"].get("cleaned") or []
    entities: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in cleaned:
        try:
            vid = expert_vid(row["expert_id"])
            props: dict[str, Any] = {
                "id": row["expert_id"],
                # name 列：schema 管理建的标准列（未注册时平台自动剔除，无害）
                "name": row["name_zh"],
                "name_zh": row["name_zh"],
            }
            if row.get("organization_name_zh"):
                props["organization_name_zh"] = row["organization_name_zh"]
            if row.get("bio_zh"):
                props["bio_zh"] = row["bio_zh"]
            entities.append({"id": vid, "props": props})
        except Exception as exc:  # noqa: BLE001 —— 毒行隔离，只进 failures
            failures.append(
                {
                    "recordId": _record_id(row, payload),
                    "error": f"{type(exc).__name__}: {exc}"[:1000],
                }
            )
    return {
        "entities": entities,
        "failures": failures,
        "stats": {"entities": len(entities), "failed": len(failures)},
    }
