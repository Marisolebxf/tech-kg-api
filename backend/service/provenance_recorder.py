"""查到即记：查询时记录实体/关系的真实获取来源，九大业务模块统一口径。

## 规则

1. **入图血缘优先透传**：节点属性里 ETL 写入的 MySQL 血缘
   （``source_table`` / ``source_field`` / ``source_record_id`` /
   ``ingest_batch`` / ``ingest_time``）本来就是"来源记录"，查询时读到即透传。
2. **无血缘时如实记录查询来源**：节点未携带血缘时，记录本次查询真实走过的
   路径——trs-graph 图空间 + 节点的识别属性，不编造 MySQL 表名，也不留空。
3. **派生展示元素记录派生路径**：由属性字符串生成的虚拟节点（如机构节点）
   由调用方记录"宿主实体 + 属性名"，保证画布上每个节点/边都可溯源。

返回字段与各模块响应中的溯源三要素一致：
``sourceTable``（源数据表）/ ``sourceField``（英文字段名）/
``sourceValue``（字段值）/ ``ingestBatch`` / ``ingestTime``，
另附 ``sourceKind``（``"mysql"`` 入图血缘 / ``"graph"`` 图库查询兜底）
供调用方在 summary 里说明来源性质。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# 节点用于被识别/命名的属性，按优先级排列；无血缘节点的"英文字段名"取自这里。
IDENTIFYING_PROP_CANDIDATES: tuple[str, ...] = (
    "scholar_id",
    "org_id",
    "organization_id",
    "keyword",
    "name_zh",
    "name_cn",
    "name_en",
    "name",
    "title_zh",
    "title",
    "node_name",
    "chain_name",
    "event_name",
)

# 已知的 MySQL 源表 → 主键字段映射（与同事关系模块原口径一致）。
_MYSQL_SOURCE_FIELDS: dict[str, str] = {
    "dwd_scholar": "scholar_id",
    "dwd_org_stock_base": "org_id",
}


def graph_source_table(space: str | None) -> str:
    """图库查询来源的"源数据表"标记：实体本次是从图空间查到的。"""
    return f"trs-graph / space={space or 'dev'}"


def _clean(value: Any) -> str:
    text = str(value if value is not None else "").strip()
    return text


def identifying_prop(props: Mapping[str, Any]) -> tuple[str, str]:
    """返回节点的识别属性 ``(字段名, 值)``；全空时回退 ``("vid", "")``。"""
    for key in IDENTIFYING_PROP_CANDIDATES:
        value = _clean(props.get(key))
        if value:
            return key, value
    return "vid", ""


def record_node_source(
    props: Mapping[str, Any],
    labels: Iterable[str] = (),
    *,
    space: str | None = None,
) -> dict[str, str]:
    """查到即记：单个图节点的溯源字段。

    Args:
        props: 图节点 properties。
        labels: 节点标签（用于 Person/Organization 的字段推断）。
        space: 图空间名；无血缘兜底时写入"源数据表"。

    Returns:
        ``{sourceTable, sourceField, sourceValue, ingestBatch, ingestTime,
        sourceKind}``，字段值均为非空字符串（缺失时为 ``"-"``）。
    """
    label_set = {str(label) for label in labels}
    source_table = _clean(props.get("source_table")) or _clean(props.get("organization_base"))

    ingest_batch = _clean(props.get("ingest_batch")) or "-"
    ingest_time = _clean(props.get("ingest_time")) or "-"

    if source_table:
        # 入图血缘存在：透传表名，并按节点标签推断 MySQL 主键字段。
        source_field = _clean(props.get("source_field")) or _MYSQL_SOURCE_FIELDS.get(
            source_table, ""
        )
        source_value = (
            _clean(props.get("source_record_id"))
            or _clean(props.get("scholar_id"))
            or _clean(props.get("organization_id"))
        )
        if not source_field:
            if "Person" in label_set and source_value:
                source_field = "scholar_id" if source_table == "dwd_scholar" else "source_record_id"
            elif _clean(props.get("organization_id")) == "scholar_id" and source_value:
                source_field = "scholar_id"
            elif _clean(props.get("organization_id")):
                source_field = "organization_id"
                source_value = _clean(props.get("organization_id"))
            else:
                source_field = "source_record_id"
        return {
            "sourceTable": source_table,
            "sourceField": source_field or "-",
            "sourceValue": source_value or "-",
            "ingestBatch": ingest_batch,
            "ingestTime": ingest_time,
            "sourceKind": "mysql",
        }

    # 无入图血缘：如实记录本次查询来源（图空间 + 识别属性），不编造表名。
    prop_name, prop_value = identifying_prop(props)
    return {
        "sourceTable": graph_source_table(space),
        "sourceField": prop_name,
        "sourceValue": prop_value or "-",
        "ingestBatch": ingest_batch,
        "ingestTime": ingest_time,
        "sourceKind": "graph",
    }


def record_derived_source(
    *,
    host_table: str,
    host_field: str,
    host_value: str = "-",
) -> dict[str, str]:
    """查到即记：派生展示元素（属性字符串生成的虚拟节点等）的溯源字段。

    Args:
        host_table: 宿主实体的源数据表（有血缘时为其 MySQL 表名，否则图空间标记）。
        host_field: 派生所用的宿主属性名（如 ``scholar_org``）。
        host_value: 宿主属性值（可选）。

    Returns:
        与 :func:`record_node_source` 同构的字段字典，``sourceKind="derived"``。
    """
    return {
        "sourceTable": host_table,
        "sourceField": host_field,
        "sourceValue": host_value or "-",
        "ingestBatch": "-",
        "ingestTime": "-",
        "sourceKind": "derived",
    }
