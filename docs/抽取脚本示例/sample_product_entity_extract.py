"""实体抽取示例脚本（STEPS 多步版）：Product（产品）← 模拟来源表 demo_product。

这是「平台喂数批次抽取」（kg.schema.extract）的可上传样例：在 Schema 管理页
（/schema）对 Product Schema 点「上传脚本」选择本文件，再到「来源表」绑定
demo_product，点「保存并触发抽取」即可运行（也可在图谱构建页建 extract 任务）。

多步形态：脚本顶层声明 ``STEPS`` 清单（与 ``transform`` 互斥，二者只能取一），
平台按序执行、每步一次 Temporal activity——第 k 步失败只重试第 k 步，前序步
输出经事件历史重放。本示例三步链：行清洗 → LLM 补简介 → 出实体点。

管道契约（backend/script/extract_transform_common.py 同款约定）：

- 平台按来源绑定分批读源表（querySql 绑定走水位/keyset，普通表走
  LIMIT/OFFSET），把行 JSON 放进**第 1 步** payload 的 ``rows``；
- 第 N>1 步 payload 为 ``{"input": 上一步完整输出, "source_table": ...,
  "kind": ..., "source": ...}``（无 rows）；上一步返回值里的额外键原样流向
  下一步 ``input``——本示例前两步只出中转数据、末步才出 entities；
- 每步返回 ``{"entities"|"edges", "failures", "stats"?}``；**任意一步**出了
  entities/edges，平台就在该步之后写图（nGQL INSERT VERTEX，列级 upsert
  幂等，实体再接同名消歧 T_LINK）——本示例只有末步出 entities；
- 水位推进仍由平台在来源全部批次整链成功后统一负责（不做 per-step 水位），
  整链重跑幂等——脚本不连图、不写库；
- 逐行异常只进 ``failures``（毒行隔离，不炸批次，跨步聚合）→ 平台落
  T_EXTRACT_FAIL 审核 case，人工可在审核工作台点重跑；
- ``props`` 只输出 Schema 已注册的业务列：未注册列会被平台剔除，NOT NULL
  溯源列（create_time/update_time/source_table）平台兜底补默认值。

SDK 用法（``from kg_sdk import current_context``，任务运行时平台经
KG_SCRIPT_CTX 注入；未选择对应资源时属性为 None，脚本判空降级）：

- ``ctx.llm``：任务选择了 LLM 配置才有。第 2 步用它给缺 description 的
  产品补一行简介（每批限量、失败静默降级）；
- ``ctx.config``：来源级增量游标（``kg_script_watermark``，``source:{绑定id}``
  为键，多步链里每一步读到的相同）——``ctx.config.watermark`` 是时间水位，
  ``ctx.config.checkpoint["pkCursor"]`` 是 keyset 游标。querySql 绑定的行过滤
  平台已按水位做完，脚本侧一般只作观测/排查；**只读**——脚本返回值里的
  ``_watermark``/``_checkpoint`` 会被平台忽略（水位在来源整链成功后推进）；
  第 1 步演示读取；
- ``ctx.step_id`` / ``ctx.attempt``：多步时 step_id 形如
  ``source:{绑定id}#{stepId}``，用于日志/审核观测；
- ``ctx.prev_outputs``：本批次已完成各步 ``{stepId: 输出}``，可跨非相邻步
  取数；S3 中转开时步间透传无截断（关时大输出按预算截断），
  只作旁路观测，业务数据走 ``input``。

模拟来源表 demo_product 的列（换成真实表时同步调整 step_normalize 即可）：
    id, name, category, description, tech_fields, price, status, updated_time
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
    {"id": "enrich", "fn": "step_enrich"},
    {"id": "emit", "fn": "step_emit"},
]

# LLM 补简介的每批上限：每批一个子进程、逐行同步调用，不设上限会把
# 500 行的批次拖到超时（默认 timeoutSeconds=600）。
_LLM_MAX_ROWS = 10

# VID 公式与 script/entity_extractors_one_entity/common.py 的 product_vid 同源：
# NFKC + 空白折叠 + casefold 后取完整 md5——关系抽取脚本必须用同一公式，
# 否则边端点对不上实体点。
_VID_MAX_BYTES = 64


def _clean(value: Any) -> str:
    """strip + 折叠空白，空白返回空串。"""
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


def product_vid(name: Any) -> str:
    """产品稳定 vid：product_{md5(规范化名称)}，超 64 字节截断加 md5 后缀。"""
    normalized = unicodedata.normalize("NFKC", _clean(name)).casefold()
    if not normalized:
        raise ValueError("missing product name")
    vid = f"product_{_md5_hex(normalized)}"
    if len(vid.encode("utf-8")) <= _VID_MAX_BYTES:
        return vid
    return vid[: _VID_MAX_BYTES - 33] + "_" + _md5_hex(vid)


def _to_float(value: Any) -> float | None:
    """宽松数值解析：去千分位/百分号，非法返回 None。"""
    raw = _clean(value).replace(",", "").replace("%", "").replace("¥", "")
    if not raw or raw.casefold() in {"-", "n/a", "null", "none"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _record_id(row: Mapping[str, Any], payload: Mapping[str, Any]) -> str:
    pk = (payload.get("source") or {}).get("pkColumn") or "id"
    if row.get(pk) is not None:
        return str(row[pk])
    digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"row:{digest[:16]}"


def _llm_summaries(llm: Any, missing: list[tuple[str, str]]) -> dict[str, str]:
    """给缺 description 的产品补一行简介；llm 为 None / 调用失败一律静默返回空。

    LLMClient.synthesize 内部吞异常返回 None，这里仍做兜底——SDK 客户端可能
    被观测代理包装（ObservedLLMClient），不保证零抛出。
    """
    if llm is None or not missing:
        return {}
    results: dict[str, str] = {}
    for name, category in missing[:_LLM_MAX_ROWS]:
        prompt = (
            f"用一句不超过 50 字的中文介绍产品「{name}」"
            f"（类别：{category or '未知'}），只输出介绍文本，不要任何前缀。"
        )
        try:
            text = llm.synthesize(prompt)
        except Exception:  # noqa: BLE001 —— LLM 失败不阻塞抽取
            text = None
        if text:
            results[name] = text.strip()[:200]
    return results


def step_normalize(payload: Mapping[str, Any]) -> dict[str, Any]:
    """第 1 步：行清洗（strip/空白折叠，丢产品名缺失行）。

    只出中转数据：额外键 ``cleaned`` 原样流向 enrich 步的 ``input``。
    """
    from kg_sdk import current_context

    rows = payload.get("rows") or []
    failures: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        name = _clean(row.get("name"))
        if not name:
            # 逐行失败进 failures：平台落 T_EXTRACT_FAIL 审核 case，可点重跑
            failures.append(
                {"recordId": _record_id(row, payload), "error": "产品名 name 为空"}
            )
            continue
        cleaned.append(
            {
                **row,
                "name": name,
                "category": _clean(row.get("category")),
                "description": _clean(row.get("description")),
                "tech_fields": _clean(row.get("tech_fields")),
                "status": _clean(row.get("status")),
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


def step_enrich(payload: Mapping[str, Any]) -> dict[str, Any]:
    """第 2 步：LLM 补简介（``ctx.llm`` 可选注入，未选/失败静默降级）。"""
    from kg_sdk import current_context

    ctx = current_context()
    cleaned = payload["input"].get("cleaned") or []

    # SDK 演示：ctx.prev_outputs 按 stepId 读任意已完成步的输出（这里是第 1
    # 步的 stats）。仅作旁路观测/分支用——S3 中转开时无截断（关时大输出按
    # 预算截断），业务数据请走 payload["input"]。
    normalize_stats = (
        (ctx.prev_outputs.get("normalize", {}).get("stats") if ctx else None) or {}
    )

    missing = [
        (row["name"], row.get("category") or "")
        for row in cleaned
        if not row.get("description")
    ]
    summaries = _llm_summaries(ctx.llm if ctx else None, missing)
    return {
        "cleaned": cleaned,
        "summaries": summaries,
        "stats": {
            "cleaned": normalize_stats.get("cleaned", len(cleaned)),
            "missingDesc": len(missing),
            "llmFilled": len(summaries),
        },
    }


def step_emit(payload: Mapping[str, Any]) -> dict[str, Any]:
    """第 3 步：出实体点 ``{"id": vid, "props": {...}}``（平台负责 nGQL 写图）。"""
    cleaned = payload["input"].get("cleaned") or []
    summaries = payload["input"].get("summaries") or {}
    entities: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in cleaned:
        try:
            vid = product_vid(row["name"])
            props: dict[str, Any] = {
                "id": _clean(row.get("id")) or vid,
                "name": row["name"],
                "category": row.get("category") or "",
                "tech_fields": row.get("tech_fields") or "",
                "price": _to_float(row.get("price")),
                "status": row.get("status") or "",
            }
            description = row.get("description") or summaries.get(row["name"])
            if description:
                props["description"] = description
            entities.append({"id": vid, "props": props})
        except Exception as exc:  # noqa: BLE001 —— 毒行隔离，只进 failures 不炸批次
            failures.append(
                {"recordId": _record_id(row, payload), "error": f"{type(exc).__name__}: {exc}"[:1000]}
            )
    return {
        "entities": entities,
        "failures": failures,
        "stats": {"entities": len(entities), "failed": len(failures)},
    }
