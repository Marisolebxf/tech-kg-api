"""多步抽取示例：行清洗 → 机构名解析（未命中进审核）→ 出边。

演示用 ``@step`` 装饰器声明多步的写法（kg.schema.extract 主通道内建多步能力，
不需要独立上传通道）。场景：源表每行含 scholar_id / raw_org_name / position /
start_date，产出 EMPLOYED_BY 边。

与单 ``transform`` 脚本同构的约定：

- 每步是单参 ``step_fn(payload)`` 纯转换，顶层函数用 ``@step`` 标注即成为一步；
  步顺序 = 函数在源码中的出现顺序，step id 默认取函数名（也可 ``@step("my-id")``
  显式指定，可含 ``-``）；不标注的函数就是普通辅助函数；
- 平台按声明顺序执行，每步一次 Temporal activity（第 k 步失败只重试第 k 步，
  前序步输出经事件历史重放）；
- 第 1 步 payload 与单步 transform 相同（``rows`` / ``source_table`` / ``kind`` /
  ``source``）；第 N>1 步 payload 为 ``{"input": 上一步完整输出, ...}``（无 rows）；
- 每步返回现有契约 ``{"entities"|"edges", "failures", "pendingReview"?, "stats"?}``，
  额外键原样流向下一步 ``input``——允许「中间步只出中转数据、末步才出记录」，
  也允许「多步都出记录」（任意一步出了 entities/edges，平台就在该步之后写图）；
- 上下文 ``from kg_sdk import current_context``：``ctx.step_id`` 形如
  ``source:{绑定id}#{stepId}``，``ctx.prev_outputs`` 是本批次已完成各步的输出。

兼容说明：旧写法是在顶层声明 ``STEPS = [{"id": ..., "fn": ...}, ...]`` 清单映射
到函数名，仍被支持（存量脚本零改动），但与 ``@step`` / ``transform`` 均互斥，
新脚本推荐用装饰器。

本示例为纯演示（机构别名表写死）；真实解析可用 ``current_context().mysql``
查机构字典表（未配置数据源时 ctx.mysql 为 None，脚本自行降级）。
"""

from typing import Any

from kg_sdk import step

# 演示用机构别名表：机构名 → 组织实体 vid
ORG_ALIASES = {
    "浙江大学": "org_zju",
    "浙大": "org_zju",
    "中国科学院": "org_cas",
}


@step
def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """第 1 步：行清洗（去空白、丢关键字段缺失行）。"""
    failures: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []
    for row in payload["rows"]:
        scholar_id = str(row.get("scholar_id") or "").strip()
        org_name = str(row.get("raw_org_name") or "").strip()
        if not scholar_id or not org_name:
            # 逐行失败进 failures：平台落 T_EXTRACT_FAIL 审核 case，可点重跑
            failures.append({"recordId": row.get("id"), "error": "缺少 scholar_id 或机构名"})
            continue
        cleaned.append({**row, "scholar_id": scholar_id, "raw_org_name": org_name})
    # 清洗步只出中转数据：额外键 cleaned 原样流向下一步 input
    return {"cleaned": cleaned, "failures": failures, "stats": {"cleaned": len(cleaned)}}


@step
def resolve(payload: dict[str, Any]) -> dict[str, Any]:
    """第 2 步：机构名解析。未命中字典的行走 pendingReview（人工裁决，不阻塞管线）。"""
    from kg_sdk import current_context

    ctx = current_context()
    if ctx is not None:
        # ctx.step_id 形如 "source:{绑定id}#resolve"；prev_outputs 可读已完成步输出
        # （这里只做演示读取，真实脚本可用 normalize 步的 stats 做分支决策）
        _normalize_stats = ctx.prev_outputs.get("normalize", {}).get("stats")

    resolved: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    for row in payload["input"]["cleaned"]:
        org_vid = ORG_ALIASES.get(row["raw_org_name"])
        if org_vid:
            resolved.append({**row, "org_vid": org_vid})
        else:
            pending.append(
                {
                    "kind": "relation",
                    "candidate": {
                        "reason": "机构名未命中字典",
                        "confidence": 0.3,
                        "raw_org_name": row["raw_org_name"],
                    },
                    "objectId": row.get("id"),
                    "objectName": row["raw_org_name"],
                    "edgeType": "EMPLOYED_BY",
                    "fromId": f"scholar_{row['scholar_id']}",
                    "reason": f"机构名未命中字典：{row['raw_org_name']}",
                    "confidence": 0.3,
                    "sourceTable": payload.get("source_table"),
                    "sourceRecordId": row.get("id"),
                }
            )
    return {
        "resolved": resolved,
        "pendingReview": pending,
        "stats": {"resolved": len(resolved), "pending": len(pending)},
    }


@step
def emit(payload: dict[str, Any]) -> dict[str, Any]:
    """第 3 步：出边。已解析行 → EMPLOYED_BY 边 JSON（平台负责 nGQL 写图）。"""
    edges = [
        {
            "fromId": f"scholar_{row['scholar_id']}",
            "toId": row["org_vid"],
            "props": {
                "position": str(row.get("position") or ""),
                "start_date": str(row.get("start_date") or ""),
                "affiliation_name": row["raw_org_name"],
            },
        }
        for row in payload["input"]["resolved"]
    ]
    return {"edges": edges, "stats": {"edges": len(edges)}}
