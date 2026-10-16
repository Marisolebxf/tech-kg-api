"""One-entity transform for Paper（平台喂数抽取：脚本只输出实体 JSON）。

入库/索引/消歧/游标推进全部由平台完成；本脚本只做 行 → 实体 转换，
逐行解析失败进 ``failures``（平台落 T_EXTRACT_FAIL 审核 case 供重跑）。
"""

from typing import Any

from script.entity_extractors_one_entity.mappers import paper_record
from script.extract_transform_common import entity_transform

# 来源绑定元数据（script/register_platform_extraction.py 读取建 GraphSchemaSource）
# dwd_scholar_papers 为厂商全量论文库（73.8万行，id 小整数空间与 zh/en 雪花 id 不冲突）；
# query_sql 只取 mapper 所需列（摘要等大文本不进 payload），is_deleted=1 剔除，
# dwd_id 为表真主键作 keyset 游标（time 留空走 pk keyset 模式）。
SOURCES = [
    {"table": "dwd_zh_paper", "pk": "id", "time": "update_time"},
    {"table": "dwd_en_paper", "pk": "id", "time": "update_time"},
    {
        "table": "dwd_scholar_papers",
        "pk": "dwd_id",
        "time": "",
        "query_sql": (
            "SELECT dwd_id, id, doi, zh_name, en_name, paper_url, "
            "publication_en_name AS publication_id, "
            "DATE_FORMAT(cover_date_start, '%Y') AS cover_year_start, updated_time "
            "FROM dwd_scholar_papers WHERE is_deleted = 0"
        ),
    },
]


def transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：payload["rows"] → {"entities": [...], "failures": [...]}。"""
    return entity_transform(payload, builder=paper_record)
