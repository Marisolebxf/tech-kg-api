"""API 出口时间显示转换：数据库与内部逻辑保持 UTC，仅在响应用出口转北京时间。

背景：人工审核/执行历史等模块把 UTC 裸值直接返回，前端原样渲染导致
"晚上跑的任务显示成下午"（差 8 个时区）。各模块存储口径不一（有的 UTC、
有的 astimezone 本地时间），禁止按字段名全局批量转换，必须逐模块核实
存储口径后在出口调用本工具。
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

_CST = ZoneInfo("Asia/Shanghai")
_UTC = UTC

# 匹配平台通行的 "YYYY-MM-DD HH:MM:SS[.fff]"（T 或空格分隔）裸时间串
_TS_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(\.\d+)?$")

_CST_FMT = "%Y-%m-%d %H:%M:%S"

# 各模块 API 响应里的时间字段名（camel/snake 双口径）。按键名定向转换而非
# 全字段扫描：日期串、HH:MM 截止块、workflowId 内嵌时间等非键值不受影响。
_TIME_KEYS = frozenset(
    {
        "createdAt",
        "updatedAt",
        "startedAt",
        "completedAt",
        "finishedAt",
        "lastRunAt",
        "submittedAt",
        "heartbeatAt",
        "claimedAt",
        "slaClaimAt",
        "slaResolveAt",
        "executedAt",
        "expiresAt",
        "occurredAt",
        "lastModifiedAt",
        "lastExecutedAt",
        "syncedAt",
        "deletedAt",
        "archivedAt",
        "reviewedAt",
        "created_at",
        "updated_at",
        "started_at",
        "completed_at",
        "finished_at",
        "last_run_at",
        "submitted_at",
        "heartbeat_at",
        "claimed_at",
        "sla_claim_at",
        "sla_resolve_at",
        "executed_at",
        "reviewed_at",
        "next_retry_at",
    }
)


def deep_cst(obj):
    """递归遍历 dict/list，把键名在 ``_TIME_KEYS`` 里的 UTC 时间值转北京时间。

    值必须是时间串或 datetime 才转；日期串（如 "2026-10-09"）、HH:MM 片段、
    非 ISO 文本按原样返回。确认存储口径为 UTC 的模块响应出口才可使用。
    """
    if isinstance(obj, dict):
        return {
            key: (
                utc_to_cst_str(val)
                if key in _TIME_KEYS and isinstance(val, (str, datetime))
                else deep_cst(val)
            )
            for key, val in obj.items()
        }
    if isinstance(obj, list):
        return [deep_cst(item) for item in obj]
    return obj


def utc_to_cst_str(value):
    """UTC 裸时间 → 北京时间字符串；None/空串/非时间值原样返回。

    - datetime：naive 视为 UTC（存储约定），aware 按自带时区
    - 字符串：``YYYY-MM-DD[ T]HH:MM:SS[.f]`` 视为 UTC；
      结尾带 ``Z`` 或 ``±HH:MM`` 按自带时区；其余（日期串、空串、非时间）原样
    """
    if value is None:
        return None
    if isinstance(value, datetime):
        aware = value if value.tzinfo else value.replace(tzinfo=_UTC)
        return aware.astimezone(_CST).strftime(_CST_FMT)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return value
        # 带时区标记的 ISO 串：交给 datetime 解析后转北京
        if stripped.endswith(("Z", "z")) or re.search(r"[+-]\d{2}:?\d{2}$", stripped):
            try:
                return (
                    datetime.fromisoformat(stripped.replace("Z", "+00:00"))
                    .astimezone(_CST)
                    .strftime(_CST_FMT)
                )
            except ValueError:
                return value
        match = _TS_RE.match(stripped)
        if match:
            try:
                naive = datetime.fromisoformat(stripped.replace("T", " "))
                return naive.replace(tzinfo=_UTC).astimezone(_CST).strftime(_CST_FMT)
            except ValueError:
                return value
        return value
    return value
