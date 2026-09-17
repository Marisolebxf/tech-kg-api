"""抽取批载荷 S3 中转（claim-check）：activity 间传 key 而非载荷本体。

kg.schema.extract 的批数据（原始行 / 转换输出 / 步间透传 / 失败清单）原本随
activity 入参/返回值反复穿越 Temporal 事件历史（同一批数据 4~5 次），大表必然撞
历史总量与 gRPC 单消息上限。本模块把载荷归档到 RustFS S3（与 run 级脚本副本同桶），
事件历史只进元数据（key + 计数）。

确定性约束（违反即重放不安全）：
- key 一律在 activity 内生成（``activity.info()`` 的 workflow_id/run_id + request
  派生字段），workflow 只拿到字符串；activity 重试时同 request → 同 key → 覆盖写，
  天然幂等；
- 上传/下载只发生在 activity / worker 进程内，workflow 代码不做任何 IO；
- 唯一读 env 做控制流分支的位置是 ``read_source_batch``（链条起点，结果形状进
  历史后，下游全部按已记录形状分支，不受 env 翻转影响）。

key 布局（延续 ``runs/{workflow_id}/script.py`` 先例）::

    runs/{workflow_id}/{run_id}/payloads/{step_id}/{batch_idx:04d}/{artifact}.json.gz
    step_id 形如 source:{绑定id}（多步链带 #{stepId} 后缀）
    artifact: rows-{chunk:02d} | out-{chunk:02d} | resolved-{chunk:02d}
              | failures-{chunk:02d}

对象内容 = 脚本视角的精确 JSON（进什么存什么、出什么存什么），gzip（mtime=0）；
留档即当时脚本看到/产出的字节，排查脚本行为时下载到的就是保真数据。

清理：worker 每日按 mtime 清 ``runs/`` 前缀超保留期对象（兜底），并幂等套用
bucket lifecycle 规则（prefix=runs/，RustFS 配置 API 已验证支持；实际过期执行
未验证，故以扫描删除为准）。
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)

LIFECYCLE_RULE_ID = "expire-run-artifacts"


def payload_s3_enabled() -> bool:
    """总开关（默认关）。只在 read_source_batch 内读取决定批数据形状。"""
    return os.getenv("SCHEMA_EXTRACT_PAYLOAD_S3_ENABLED", "false").lower() == "true"


def payload_max_bytes() -> int:
    """单载荷对象（序列化 JSON）字节预算，默认 8MB。"""
    try:
        return max(
            64 * 1024,
            int(os.getenv("SCHEMA_EXTRACT_PAYLOAD_MAX_BYTES") or 0) or 8 * 1024 * 1024,
        )
    except ValueError:
        return 8 * 1024 * 1024


def payload_gzip_enabled() -> bool:
    return os.getenv("SCHEMA_EXTRACT_PAYLOAD_GZIP", "true").lower() != "false"


def payload_retention_days() -> int:
    try:
        return max(1, int(os.getenv("SCHEMA_EXTRACT_PAYLOAD_RETENTION_DAYS") or 0) or 7)
    except ValueError:
        return 7


def payload_cleanup_enabled() -> bool:
    return os.getenv("SCHEMA_EXTRACT_PAYLOAD_CLEANUP_ENABLED", "true").lower() != "false"


def _activity_run_ids() -> tuple[str, str]:
    """activity 上下文取 (workflow_id, run_id)；单测直调无上下文时 local- 兜底。"""
    from temporalio import activity

    try:
        info = activity.info()
        return info.workflow_id, info.workflow_run_id
    except RuntimeError:
        return f"local-{uuid4().hex}", "local"


def extract_payload_key(
    step_id: str,
    batch_idx: int,
    artifact: str,
    *,
    workflow_id: str | None = None,
    run_id: str | None = None,
) -> str:
    """载荷对象 key（纯派生：同上下文 + 同 request 字段 → 同 key）。"""
    if workflow_id is None or run_id is None:
        ctx_wf, ctx_run = _activity_run_ids()
        workflow_id = workflow_id or ctx_wf
        run_id = run_id or ctx_run
    return f"runs/{workflow_id}/{run_id}/payloads/{step_id}/{int(batch_idx):04d}/{artifact}.json.gz"


def dumps_payload(value: Any) -> bytes:
    """载荷序列化（与批行进 payload 的序列化参数一致，保证往返字节稳定）。"""
    return json.dumps(value, ensure_ascii=False, default=str).encode()


def _storage() -> Any:
    from infra.s3 import get_schema_s3_storage

    return get_schema_s3_storage()


def put_extract_payload(
    step_id: str, batch_idx: int, artifact: str, data: bytes, *, key: str | None = None
) -> str:
    """gzip(mtime=0) 后上传，返回对象 key（覆盖写幂等，activity 重试安全）。"""
    use_gzip = payload_gzip_enabled()
    body = gzip.compress(data, compresslevel=6, mtime=0) if use_gzip else data
    object_key = key or extract_payload_key(step_id, batch_idx, artifact)
    storage = _storage()
    storage.put_bytes(object_key, body, "application/json+gzip" if use_gzip else "application/json")
    return object_key


def put_extract_payload_json(step_id: str, batch_idx: int, artifact: str, value: Any) -> str:
    """JSON 序列化 + 上传（activity 内调用；IO 阻塞，调用方套 asyncio.to_thread）。"""
    return put_extract_payload(step_id, batch_idx, artifact, dumps_payload(value))


def get_extract_payload(key: str) -> bytes:
    """下载载荷并解压（gzip 魔数探测；IO 阻塞，调用方套 asyncio.to_thread）。"""
    storage = _storage()
    body = None
    try:
        body = storage.get_object(storage.bucket, key)
        data = body.read()
    finally:
        if body is not None:
            try:
                body.close()
            except Exception:  # noqa: BLE001
                logger.exception("关闭载荷流失败: %s", key)
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    return data


def load_extract_payload_json(key: str) -> Any:
    """下载并解析 JSON 载荷。"""
    return json.loads(get_extract_payload(key))


def _apply_lifecycle_rule() -> bool:
    """幂等套用 bucket lifecycle（prefix=runs/，保留期外过期；best-effort）。"""
    storage = _storage()
    try:
        try:
            rules = storage.get_lifecycle_rules()
        except Exception:  # noqa: BLE001
            rules = []
        rule = {
            "ID": LIFECYCLE_RULE_ID,
            "Filter": {"Prefix": "runs/"},
            "Status": "Enabled",
            "Expiration": {"Days": payload_retention_days()},
        }
        merged = [r for r in rules if r.get("ID") != LIFECYCLE_RULE_ID] + [rule]
        storage.put_lifecycle_rules(merged)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("套用 runs/ lifecycle 规则失败（清理以每日扫描为准）: %s", exc)
        return False


def cleanup_run_artifacts() -> dict[str, Any]:
    """worker 每日兜底：扫 runs/ 前缀删超保留期对象 + 幂等套用 lifecycle。"""
    applied = _apply_lifecycle_rule()
    storage = _storage()
    cutoff = datetime.now(UTC) - timedelta(days=payload_retention_days())
    deleted = 0
    for obj in storage.list_objects("runs/"):
        if obj.last_modified is None or obj.last_modified >= cutoff:
            continue
        try:
            storage.delete_object(storage.bucket, obj.object_key)
            deleted += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("清理载荷对象失败 %s: %s", obj.object_key, exc)
    if deleted:
        logger.info("载荷留档清理：删除 %s 个超保留期对象（runs/ 前缀）", deleted)
    return {"deleted": deleted, "lifecycleApplied": applied, "cutoff": cutoff.isoformat()}
