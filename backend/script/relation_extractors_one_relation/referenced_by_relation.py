"""One-relation extractor: REFERENCED_BY（paper_rp_ 桩 → Report）.

复刻旧 paper_journal_chain_etl.py 口径：dwd_zh_report_paper，起点为独立前缀
``paper_rp_{paper_id}`` 桩（不去 ``__数字`` 后缀，允许悬空），report_id 为
JSON 数组或单值逐个展开，confidence=0.8。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.referenced_by_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

import json

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    print_json,
    run_relation_extractor,
)

SQL = "SELECT paper_id, paper_doi, report_id FROM dwd_zh_report_paper"


def _report_ids(raw: str) -> list[str]:
    raw = str(raw or "").strip()
    if not raw:
        return []
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
            return [str(item) for item in parsed if item]
        except json.JSONDecodeError:
            return [raw]
    return [raw]


def referenced_by(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    paper_id = str(row.get("paper_id") or "").strip()
    if not paper_id:
        return []
    records = []
    for rid in _report_ids(row.get("report_id")):
        records.append(
            EdgeRecord(
                "REFERENCED_BY",
                f"paper_rp_{paper_id}",
                f"report_{rid}",
                {"confidence": 0.8},
                rank=0,
                validate_endpoints=False,
            )
        )
    return records


def build_sources() -> list[tuple[str, str, object]]:
    """构造 sources；单源固定，无需 payload 参数。"""
    return [("dwd_zh_report_paper", SQL, referenced_by)]


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources()
    print_json(
        run_relation_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=sources,
        )
    )


def workflow(payload: dict) -> dict:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources()
    return run_relation_extractor(
        database=common["database"],
        batch_size=common["batch_size"],
        limit=common["limit"],
        dry_run=common["dry_run"],
        ingest_batch=common["ingest_batch"],
        since=common["since"],
        sources=sources,
    )


if __name__ == "__main__":
    main()
