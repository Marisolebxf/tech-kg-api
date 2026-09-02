"""平台喂数抽取脚本的共享转换器（kg.schema.extract 管道）。

脚本契约：``transform(payload)`` 收 ``payload["rows"]``（平台按来源绑定分批读的行
JSON），只做转换，返回::

    {"entities": [{"id": vid, "props": {...}}], "failures": [{"recordId", "error"}]}
    {"edges": [{"fromId", "toId", "props": {...}}], "failures": [...]}

可选键 ``pendingReview``：低置信/歧义候选（如机构名命中多个机构）入审核队列，
item 形状见 script/workflows/sample_step_pipeline.py；``stats`` 原样透传展示。
入库/索引/消歧/游标全部由平台负责——脚本不连图、不写库（resolver 类查找表经
``kg_sdk.current_context()`` 的 mysql/graph 客户端按需加载）。

逐行异常只进 ``failures``（毒行隔离，不炸批次；平台落 T_EXTRACT_FAIL 审核 case
供人工点击重跑），不抛出。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from typing import Any

logger = logging.getLogger("extract_transform_common")

EntityBuilder = Callable[[str, Mapping[str, Any], str], Iterable[Any]]


def platform_clients(required: Iterable[str] = ("mysql", "graph")) -> Any:
    """从 KG_SCRIPT_CTX 取平台注入的 kg_sdk 上下文；缺资源抛 RuntimeError。

    只有平台任务/Schema 抽取运行时才有注入（CLI 直跑没有）。
    """
    from kg_sdk import current_context

    ctx = current_context()
    if ctx is None:
        raise RuntimeError(
            f"本抽取脚本需要平台注入资源 {sorted(required)}（请在数据抽取任务中运行，CLI 直跑不支持）"
        )
    missing = [name for name in required if getattr(ctx, name, None) is None]
    if missing:
        raise RuntimeError(f"任务未选择所需资源: {missing}（建任务/触发时请选择对应配置）")
    return ctx


def _record_id(row: Mapping[str, Any], pk_column: str | None) -> str:
    if pk_column and row.get(pk_column) is not None:
        return str(row[pk_column])
    digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"row:{digest[:16]}"


def _split_source(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    source = payload.get("source") or {}
    source_table = str(payload.get("source_table") or source.get("tableName") or "")
    table = source_table.rsplit(".", 1)[-1]
    pk_column = str(source.get("pkColumn") or "id")
    batch = f"se-{str(source.get('id') or 'x')[:8]}"
    return table, pk_column, batch


def entity_transform(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None = None,
    mapper_by_table: dict[str, EntityBuilder] | None = None,
) -> dict[str, Any]:
    """实体转换：行 → ``{"id": vid, "props": properties}``。"""

    def to_json(record: Any) -> dict[str, Any]:
        return {"id": record.vid, "props": record.properties}

    return _run(
        payload, builder=builder, mapper_by_table=mapper_by_table, to_json=to_json, key="entities"
    )


def edge_transform(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None = None,
    mapper_by_table: dict[str, EntityBuilder] | None = None,
) -> dict[str, Any]:
    """关系转换：行 → ``{"fromId", "toId", "props"}``。"""

    def to_json(record: Any) -> dict[str, Any]:
        return {
            "fromId": record.source_vid,
            "toId": record.target_vid,
            "props": record.properties,
        }

    return _run(
        payload, builder=builder, mapper_by_table=mapper_by_table, to_json=to_json, key="edges"
    )


def _run(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None,
    mapper_by_table: dict[str, EntityBuilder] | None,
    to_json: Callable[[Any], dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    table, pk_column, batch = _split_source(payload)
    if builder is None and mapper_by_table:
        builder = mapper_by_table.get(table)
    if builder is None:
        raise RuntimeError(f"来源表 {table} 没有对应的转换 mapper")
    rows = payload.get("rows") or []
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in rows:
        record_id = _record_id(row, pk_column)
        try:
            mapped = list(builder(table, row, batch) or [])
            records.extend(to_json(r) for r in mapped)
        except Exception as exc:  # noqa: BLE001
            logger.warning("行转换失败 table=%s record=%s: %s", table, record_id, exc)
            failures.append({"recordId": record_id, "error": f"{type(exc).__name__}: {exc}"[:1000]})
    output: dict[str, Any] = {key: records, "failures": failures}
    if table:
        output["stats"] = {
            "table": table,
            "rows": len(rows),
            key: len(records),
            "failed": len(failures),
        }
    return output


def pending_review_items(
    reviews: Iterable[Any],
    *,
    source_table: str,
    kind: str = "relation",
    template_id: str | None = None,
) -> list[dict[str, Any]]:
    """把脚本内产出的歧义/低置信候选（dict 或 dataclass）转成 pendingReview 项。

    兼容 dict 与属性对象（ReviewRecord）：取 patent_id/relation_type/source_name/
    reason/confidence/candidates/evidence/patent_vid/source_record_id 字段。
    入队后走 T_DIRECT（或 ``template_id``）审核，pipeline 不暂停。
    """

    def pick(review: Any, name: str, default: Any = None) -> Any:
        if isinstance(review, Mapping):
            return review.get(name, default)
        return getattr(review, name, default)

    items: list[dict[str, Any]] = []
    for review in reviews:
        candidates = pick(review, "candidates") or []
        item: dict[str, Any] = {
            "kind": pick(review, "kind") or kind,
            "candidate": {
                "reason": pick(review, "reason"),
                "confidence": pick(review, "confidence"),
                "candidates": candidates,
                "source_record_id": pick(review, "source_record_id"),
            },
            "objectId": pick(review, "source_record_id") or pick(review, "patent_id"),
            "objectName": pick(review, "source_name"),
            "edgeType": pick(review, "relation_type") or pick(review, "edge_type"),
            "fromId": pick(review, "patent_vid") or pick(review, "source_vid"),
            "toId": pick(review, "target_vid"),
            "reason": str(pick(review, "reason") or "歧义候选待人工确认"),
            "confidence": pick(review, "confidence"),
            "evidence": pick(review, "evidence") or [],
            "sourceTable": pick(review, "source_table") or source_table,
            "sourceRecordId": pick(review, "source_record_id"),
        }
        if template_id:
            item["templateId"] = template_id
        items.append(item)
    return items
