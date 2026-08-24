"""One-relation extractor: REFERENCED_BY（paper_rp_ 桩 → Report）.

复刻旧 paper_journal_chain_etl.py 口径：dwd_zh_report_paper，起点为独立前缀
``paper_rp_{paper_id}`` 桩（不去 ``__数字`` 后缀，允许悬空），report_id 为
JSON 数组或单值逐个展开，confidence=0.8。
"""

import json

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
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


def main() -> None:
    parser = build_parser(__doc__ or "")
    args = parser.parse_args()
    configure_logging(args.log_level)
    print_json(
        run_relation_extractor(
            database=args.database,
            batch_size=args.batch_size,
            limit=args.limit,
            dry_run=args.dry_run,
            ingest_batch=args.ingest_batch,
            since=args.since,
            sources=[("dwd_zh_report_paper", SQL, referenced_by)],
        )
    )


if __name__ == "__main__":
    main()
