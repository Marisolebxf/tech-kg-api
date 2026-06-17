"""初始化 techkg 图空间 schema（幂等）。

先在已存在空间（默认 entity_binding_demo）上下文执行 CREATE SPACE，
再切换到 techkg 执行 TAG/EDGE/INDEX DDL。

用法：python -m script.init_graph_schema
"""

from __future__ import annotations

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

# 在任意已存在空间上下文执行（CREATE SPACE 是全局操作）
CREATE_SPACE_DDL: list[str] = [
    "CREATE SPACE IF NOT EXISTS techkg(vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);",
]

# 在 techkg 空间执行
SCHEMA_DDL: list[str] = [
    "CREATE TAG IF NOT EXISTS Scholar(scholar_id string, name_zh string, name_en string, "
    "scholar_org_name_zh string, scholar_org_name_en string, h_index int64, "
    "citation_nums int64, paper_nums int64);",
    "CREATE TAG IF NOT EXISTS Organization(org_id string, name_cn string, province string, "
    "city string, org_type string, listing_status string, incorporation_year int64);",
    "CREATE EDGE IF NOT EXISTS EMPLOYED_BY(relation_type string, role string, "
    "start_date string, end_date string, source string);",
    "CREATE TAG INDEX IF NOT EXISTS scholar_id_idx ON Scholar(scholar_id(64));",
    "CREATE TAG INDEX IF NOT EXISTS org_name_idx ON Organization(name_cn(128));",
    "CREATE TAG INDEX IF NOT EXISTS org_id_idx ON Organization(org_id(64));",
    "CREATE EDGE INDEX IF NOT EXISTS employed_by_idx ON EMPLOYED_BY();",
]


def init_schema() -> None:
    # 1) 在默认空间上下文建 techkg 空间
    bootstrap = TRSGraphClient(TRSGraphSettings.from_env())
    bootstrap.connect()
    try:
        for stmt in CREATE_SPACE_DDL:
            bootstrap.execute_write(stmt)
    finally:
        bootstrap.close()
    # 2) 切到 techkg 建 schema（独立 settings，避免共享引用被改）
    techkg_settings = TRSGraphSettings.from_env()
    techkg_settings.space = "techkg"
    techkg = TRSGraphClient(techkg_settings)
    techkg.connect()
    try:
        for stmt in SCHEMA_DDL:
            techkg.execute_write(stmt)
    finally:
        techkg.close()


if __name__ == "__main__":
    init_schema()
