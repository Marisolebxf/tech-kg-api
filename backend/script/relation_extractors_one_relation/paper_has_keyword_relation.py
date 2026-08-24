"""One-relation extractor: HAS_KEYWORD（Paper → Keyword）.

复刻旧 paper_journal_chain_etl.py：dwd_zh/en_paper_classification.keywords，
中文逗号分割、英文 JSON 数组（失败回退逗号）；边属性仅 confidence=1.0，rank@0。
Keyword VID 用三域统一公式（keyword_vid，见 resolvers 模块说明）。

Dual-mode 入口：
- CLI: ``python -m script.relation_extractors_one_relation.paper_has_keyword_relation --dry-run --limit 1``
- Temporal workflow: 脚本顶层 ``workflow(payload)`` 函数，由
  ``service/temporal_workflows.py:execute_python_script`` Activity 子进程加载并调用。
  payload key 用 snake_case（跟 argparse 转换后的 vars(args) 同形态）。
"""

import json
from typing import Any

from script.relation_extractors_one_relation.common import (
    EdgeRecord,
    build_parser,
    common_args_from_payload,
    configure_logging,
    print_json,
    run_relation_extractor,
)
from script.relation_extractors_one_relation.resolvers import keyword_vid, paper_source_id

TABLES = ("dwd_zh_paper_classification", "dwd_en_paper_classification")


def _parse_keywords(raw: str, lang: str) -> list[str]:
    if lang == "en":
        try:
            return [str(x).strip() for x in json.loads(raw) if x]
        except (json.JSONDecodeError, TypeError):
            return [s.strip() for s in raw.split(",") if s.strip()]
    return [s.strip() for s in raw.split(",") if s.strip()]


def paper_has_keyword(table: str, row: dict, batch: str) -> list[EdgeRecord]:
    pid = paper_source_id(row.get("id"))
    raw = str(row.get("keywords") or "")
    if not pid or not raw:
        return []
    lang = "en" if table == "dwd_en_paper_classification" else "zh"
    records = []
    for kw in _parse_keywords(raw, lang):
        if not kw:
            continue
        records.append(
            EdgeRecord(
                "HAS_KEYWORD",
                f"paper_{pid}",
                keyword_vid(kw),
                {"confidence": 1.0},
                rank=0,
            )
        )
    return records


def build_sources(payload: dict[str, Any]) -> list[tuple[str, str, Any]]:
    """从 payload dict 构造 sources；CLI vars(args) 与 workflow payload 同形态。"""
    table_choice = payload.get("table", "all")
    tables = TABLES if table_choice == "all" else (table_choice,)
    return [
        (
            table,
            f"SELECT id, keywords, updated_time FROM {table} "
            "WHERE keywords IS NOT NULL AND keywords != ''",
            paper_has_keyword,
        )
        for table in tables
    ]


def main() -> None:
    parser = build_parser(__doc__ or "")
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources(vars(args))
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


def workflow(payload: dict[str, Any]) -> dict[str, Any]:
    """Temporal workflow 入口；payload 同 main() 的 vars(args) 形态。"""
    common = common_args_from_payload(payload)
    configure_logging(common["log_level"])
    sources = build_sources(payload)
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
