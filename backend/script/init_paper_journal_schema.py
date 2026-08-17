"""论文/期刊/报告 图谱 Schema 初始化（在 TRSGraph dev 空间创建 Tag/Edge）。

用法：
    cd backend && PYTHONPATH=. .venv/bin/python script/init_paper_journal_schema.py
"""

from __future__ import annotations

import os
import time

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

SPACE = "dev"

# Tag DDL — 所有属性用 string，避免 nGQL INSERT 时 int/string 类型不匹配
TAG_DDL = [
    """CREATE TAG IF NOT EXISTS Paper(
        title_en string, title_zh string, doi string, publication_year string,
        publication_date string, language string, document_type string, publication_type string,
        volume string, issue string, start_page string, end_page string, is_oa string,
        source_url string, source string, created_time string, updated_time string
    )""",
    """CREATE TAG IF NOT EXISTS Journal(
        name_zh string, name_en string, name_abbr string, issn string, eissn string,
        country string, founding_time string, impact_factor string, is_sci string,
        jcr_zone string, cite_nums string, annual_publication string, publication_cycle string, source string
    )""",
    """CREATE TAG IF NOT EXISTS Report(
        title_cn string, title_en string, report_category string, report_type string,
        abstract string, keywords string, page_count string, publication_date string,
        source_url string, source string
    )""",
    """CREATE TAG IF NOT EXISTS Person(
        name_en string, name_zh string, email string, source string
    )""",
    """CREATE TAG IF NOT EXISTS Keyword(
        keyword string
    )""",
    # 溯源 + 置信度 mixin tag（挂到实体上，dev 已存在；这里供全新初始化）
    """CREATE TAG IF NOT EXISTS organization_base(
        organization_id string, confidence double,
        source_system string, source_table string, source_record_id string, source_url string,
        ingest_batch string, ingest_time string, source_update_time string, extra_json string
    )""",
]

# Edge DDL — 同上全部 string；论文域边带 confidence（标书「关系置信度」）
EDGE_DDL = [
    """CREATE EDGE IF NOT EXISTS AUTHORED_BY(
        author_order string, is_corresponding string, confidence double
    )""",
    """CREATE EDGE IF NOT EXISTS PUBLISHED_IN(
        volume string, issue string, start_page string, end_page string, publication_year string,
        confidence double
    )""",
    """CREATE EDGE IF NOT EXISTS CITES(
        reference_identifier string, confidence double
    )""",
    """CREATE EDGE IF NOT EXISTS CITED_BY(
        citation_identifier string, confidence double
    )""",
    """CREATE EDGE IF NOT EXISTS RELATED_TO(confidence double)""",
    """CREATE EDGE IF NOT EXISTS AFFILIATED_WITH(
        affiliation_name string, source string,
        work_experience_date string, work_experience_department_zh string,
        work_experience_position_zh string
    )""",
    """CREATE EDGE IF NOT EXISTS HAS_KEYWORD(confidence double)""",
    """CREATE EDGE IF NOT EXISTS OUTPUT_OF()""",
]


def get_client() -> TRSGraphClient:
    settings = TRSGraphSettings(
        base_url=os.getenv("TRS_GRAPH_BASE_URL", "http://localhost:8090"),
        space=SPACE,
        api_key=os.getenv("TRS_GRAPH_API_KEY"),
        timeout=int(os.getenv("TRS_GRAPH_TIMEOUT", "60")),
    )
    return TRSGraphClient(settings)


def run(client: TRSGraphClient, ngql: str, desc: str) -> None:
    try:
        client.execute_write(ngql)
        print(f"  ✅ {desc}")
    except Exception as exc:
        print(f"  ❌ {desc}: {exc}")


def main() -> None:
    client = get_client()
    client.connect()
    print(f"=== 初始化 {SPACE} 空间 Schema ===")

    # 1. 重建空间（先 DROP 再 CREATE，确保 schema 是全 string）
    run(client, f"DROP SPACE IF EXISTS {SPACE};", f"DROP SPACE {SPACE}")
    print("  等待 DROP 传播 (5s)...")
    time.sleep(5)
    run(
        client,
        f"CREATE SPACE IF NOT EXISTS {SPACE}(vid_type=FIXED_STRING(256), partition_num=10, replica_factor=1);",
        f"CREATE SPACE {SPACE}",
    )
    print("  等待空间传播 (10s)...")
    time.sleep(10)

    # 2. 创建 Tag
    print("\n--- 创建 Tag ---")
    for ddl in TAG_DDL:
        tag_name = ddl.split("CREATE TAG IF NOT EXISTS")[1].split("(")[0].strip()
        run(client, ddl, f"TAG {tag_name}")

    # 3. 创建 Edge
    print("\n--- 创建 Edge ---")
    for ddl in EDGE_DDL:
        edge_name = ddl.split("CREATE EDGE IF NOT EXISTS")[1].split("(")[0].strip().rstrip(")")
        run(client, ddl, f"EDGE {edge_name}")

    print(f"\n=== Schema 初始化完成 (空间: {SPACE}) ===")


if __name__ == "__main__":
    main()
