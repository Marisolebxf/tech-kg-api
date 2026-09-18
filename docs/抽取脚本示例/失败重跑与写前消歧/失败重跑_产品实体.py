"""失败重跑示例脚本（@step 多步版）：Product（产品）← 模拟来源表 demo_fail_product。

演示「平台喂批次抽取」（kg.schema.extract）的**逐行失败 → T_EXTRACT_FAIL →
点重跑**闭环：

- 毒行（产品名缺失/占位）只进 ``failures``，不炸批次（毒行隔离）；
- 平台把 failures 落成 T_EXTRACT_FAIL 审核 case（队列 category=C），
  人工在审核工作台点「重跑」→ ``POST /manual-reviews/production/
  rerun-extract-failures`` → 新执行 triggerSource=RERUN（按 recordId 回读源行）；
- 修好源数据后重跑，case 转 RESOLVED；仍失败则原 case 结案、新 case
  attempt+1。

failures 契约（backend/service/temporal_workflows.py ``_shape_step_failures`` /
``record_extract_failures``）：**recordId 必填**（None 的条目被整条丢弃），
error 为自由文本（平台截 1000 字符）。recordId 用源表主键，重跑时平台按
``WHERE pk IN (...)`` 精确回读这些行。

多步形态：``@step`` 装饰器（步顺序 = 函数源码出现顺序，与顶层 ``transform``
互斥）。本示例两步链：行清洗 → 出实体点。每步一次 Temporal activity，
第 k 步失败只重试第 k 步。

数据配套：``demo_数据.sql`` 的 A1 段（表 demo_fail_product：3 条好行 +
3 条毒行）。本地零库验证：``python 本地验证.py``（见同目录 README）。

模拟来源表 demo_fail_product 的列：
    id, product_name, product_seq, company_name, credit_code, update_time
"""

from __future__ import annotations

import hashlib
import json
import unicodedata
from collections.abc import Mapping
from typing import Any

from kg_sdk import step

_VID_MAX_BYTES = 64

# 视为「产品名缺失」的占位值（清洗后小写比对）
_PLACEHOLDER_NAMES = {"", "n/a", "na", "null", "none", "-", "无", "未知", "待补充"}


def _clean(value: Any) -> str:
    """strip + 折叠空白，空白返回空串。"""
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _md5_hex(value: str) -> str:
    return hashlib.md5(value.encode("utf-8"), usedforsecurity=False).hexdigest()


def product_vid(name: Any) -> str:
    """产品稳定 vid：product_{md5(规范化名称)}，超 64 字节截断加 md5 后缀。

    与 docs/抽取脚本示例/sample_product_entity_extract.py 同公式；关系脚本
    引用产品端点时必须用同一公式，否则边端点对不上实体点。
    """
    normalized = unicodedata.normalize("NFKC", _clean(name)).casefold()
    if not normalized:
        raise ValueError("missing product name")
    vid = f"product_{_md5_hex(normalized)}"
    if len(vid.encode("utf-8")) <= _VID_MAX_BYTES:
        return vid
    return vid[: _VID_MAX_BYTES - 33] + "_" + _md5_hex(vid)


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
    """第 1 步：行清洗。产品名缺失/占位的毒行 → failures（可点重跑），不炸批次。"""
    rows = payload.get("rows") or []
    failures: list[dict[str, Any]] = []
    cleaned: list[dict[str, Any]] = []
    for row in rows:
        record_id = _record_id(row, payload)
        name = _clean(row.get("product_name"))
        if name.casefold() in _PLACEHOLDER_NAMES:
            # 逐行失败进 failures：平台落 T_EXTRACT_FAIL 审核 case（category=C），
            # 人工修数后可在审核工作台点「重跑」→ triggerSource=RERUN 的新执行。
            # recordId 必填且非 None，否则整条被平台丢弃。
            failures.append(
                {
                    "recordId": record_id,
                    "error": f"产品名 product_name 缺失或占位（id={record_id}）",
                }
            )
            continue
        cleaned.append(
            {
                **row,
                "product_name": name,
                "product_seq": _clean(row.get("product_seq")),
                "company_name": _clean(row.get("company_name")),
                "credit_code": _clean(row.get("credit_code")),
            }
        )
    # 只出中转数据：额外键 cleaned 原样流向 emit 步的 input
    return {
        "cleaned": cleaned,
        "failures": failures,
        "stats": {"rows": len(rows), "cleaned": len(cleaned), "failed": len(failures)},
    }


@step
def emit(payload: dict[str, Any]) -> dict[str, Any]:
    """第 2 步：出实体点 ``{"id": vid, "props": {...}}``（平台负责 nGQL 写图）。

    逐行 try/except：万一还有未预见的毒行，也只进 failures 不炸批次。
    """
    cleaned = payload["input"].get("cleaned") or []
    entities: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in cleaned:
        try:
            vid = product_vid(row["product_name"])
            entities.append(
                {
                    "id": vid,
                    "props": {
                        "id": _clean(row.get("id")) or vid,
                        "name": row["product_name"],
                        "product_name": row["product_name"],
                        "product_seq": row.get("product_seq") or "",
                        "company_name": row.get("company_name") or "",
                        "credit_code": row.get("credit_code") or "",
                    },
                }
            )
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
