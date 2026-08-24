"""One-entity extractor for PatentFamily.

复用专利聚合 SQL（keyset 游标分页），族号缺失不建点；溯源表名与旧口径一致
（dwd_patent_family）。MEMBER_OF_FAMILY 边由关系脚本承接。

Dual-mode 入口：
- CLI: ``python -m script.entity_extractors_one_entity.patent_family_entity --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

from script.entity_extractors_one_entity.common import (
    build_parser,
    common_args_from_payload,
    configure_logging,
    print_json,
    run_entity_extractor,
)
from script.entity_extractors_one_entity.mappers import patent_family_record
from script.entity_extractors_one_entity.patent_entity import PATENT_SQL


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；patent 单源固定，无需 payload 参数。"""
    return [("dwd_patent", PATENT_SQL, patent_family_record)]


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources()
    print_json(
        run_entity_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            sources=sources,
            cursor_column="source_row_id",
        )
    )


def workflow(payload: dict) -> dict:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources()
    return run_entity_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        sources=sources,
        cursor_column="source_row_id",
    )


if __name__ == "__main__":
    main()
