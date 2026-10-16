"""One-relation transform for ACTUAL_CONTROLLER_OF（实际控制）（平台喂数抽取：脚本只输出边 JSON）。

机构域 spec 驱动；resolver 每批从 mysql ctx 构建，端点不建点。
入库/索引/消歧/游标由平台负责，逐行失败进 failures（审核重跑）。
"""

from collections.abc import Mapping
from typing import Any

from script.relation_extractors_one_relation.org_edges import (
    transform_org_relation,
)

RELATION_KEY = "actual_controller"

# 来源绑定元数据（script/register_platform_extraction.py 读取建 GraphSchemaSource）。
# element 库 dwd_forg_act_contro_info（1,127 行）无 id/update_time 列：row_pk 别名成
# id 作 keyset 游标，time 留空走 pk keyset 模式；转换仍由 spec 驱动读同名列。
SOURCES = [
    {
        "table": "dwd_forg_act_contro_info",
        "pk": "id",
        "time": "",
        "query_sql": "SELECT *, row_pk AS id FROM dwd_forg_act_contro_info",
    },
]


def transform(payload: Mapping[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"edges": [...], "failures": [...]}。"""
    return transform_org_relation(RELATION_KEY, payload)
