#!/usr/bin/env python3
"""Safe standalone CLI for the domestic/foreign organization MySQL -> TRSGraph ETL."""

from __future__ import annotations

import argparse
import json
import logging
import os
import platform
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

BUNDLE_ROOT = Path(__file__).resolve().parent
BACKEND_ROOT = BUNDLE_ROOT.parent
DEFAULT_ENV_FILE = BUNDLE_ROOT / ".env"
if not DEFAULT_ENV_FILE.exists():
    DEFAULT_ENV_FILE = BACKEND_ROOT / ".env"

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="国内外机构 MySQL -> TRSGraph 独立 ETL（目标空间固定为 dev）"
    )
    parser.add_argument(
        "--env-file",
        default=str(DEFAULT_ENV_FILE),
        help="环境变量文件，优先 organization_ETL/.env，否则使用 backend/.env",
    )
    parser.add_argument("--log-level", default="INFO")
    commands = parser.add_subparsers(dest="command", required=True)

    preflight = commands.add_parser("preflight", help="只读检查 Python、MySQL、源表和图服务")
    preflight.add_argument("--scope", choices=("all", "domestic", "foreign"), default="all")

    schema = commands.add_parser("init-schema", help="初始化/补齐 dev 图 Schema")
    schema.add_argument("--yes", action="store_true", help="确认执行图 Schema 写入")

    for name, help_text in (
        ("dry-run", "读取真实数据并演练转换，不写节点或边"),
        ("write", "按实体在前、关系在后的顺序正式写图"),
    ):
        run = commands.add_parser(name, help=help_text)
        run.add_argument("--stage", choices=("all", "entity", "relation"), default="all")
        run.add_argument("--scope", choices=("all", "domestic", "foreign"), default="all")
        run.add_argument("--table", default="all", help="实体来源表；默认 all")
        run.add_argument("--relation", default="all", help="关系族；默认 all")
        run.add_argument("--max-records", type=int, help="每张来源表最多读取条数；不填为全量")
        run.add_argument("--entity-batch-size", type=int, default=100)
        run.add_argument("--relation-batch-size", type=int, default=500)
        run.add_argument("--alignment-mode", choices=("exact", "hybrid"), default="exact")
        run.add_argument("--ingest-batch", help="批次号；不填自动生成")
        run.add_argument("--no-report", action="store_true", help="不生成前后验收快照")
        if name == "write":
            run.add_argument("--yes", action="store_true", help="确认正式写入目标图空间")

    commands.add_parser("verify", help="只读输出当前机构图谱验收快照")
    return parser


def _load_environment(env_file: str) -> Path:
    from dotenv import load_dotenv

    path = Path(env_file).expanduser().resolve()
    if path.exists():
        load_dotenv(path, override=False)
    os.environ.setdefault("TRS_GRAPH_SPACE", "dev")
    os.environ.setdefault(
        "ORGANIZATION_REPORT_DIR", str(BUNDLE_ROOT / "var" / "reports" / "organization")
    )
    os.environ.setdefault("ORG_MILVUS_STATE_DIR", str(BUNDLE_ROOT / "var" / "organization_milvus"))
    space = os.environ["TRS_GRAPH_SPACE"]
    if space not in {"dev", "test"} and not space.startswith("org_etl_test_"):
        raise ValueError("机构 ETL 仅允许 dev、test 或 org_etl_test_ 前缀的隔离测试空间")
    os.chdir(BUNDLE_ROOT)
    return path


def _selected_tables(scope: str) -> tuple[Any, ...]:
    from script.organization_etl_common import DOMAIN_TABLE_SPECS

    if scope == "all":
        return DOMAIN_TABLE_SPECS
    return tuple(spec for spec in DOMAIN_TABLE_SPECS if spec.scope == scope)


def _preflight(scope: str, env_path: Path) -> tuple[int, dict[str, Any]]:
    from sqlalchemy import text

    from infra.gkx_element import build_gkx_element_url, gkx_element_read_session
    from infra.graph_db import TRSGraphClient
    from infra.graph_db.config import TRSGraphSettings
    from script.organization_etl_common import RELATION_SPECS

    report: dict[str, Any] = {
        "ok": False,
        "checkedAt": datetime.now(UTC).isoformat(timespec="seconds"),
        "python": platform.python_version(),
        "envFile": str(env_path) if env_path.exists() else "not found; process environment used",
        "scope": scope,
    }
    errors: list[str] = []
    if sys.version_info[:2] != (3, 11):
        errors.append("Python 必须为 3.11.x")

    selected = _selected_tables(scope)
    expected_tables = sorted({spec.name for spec in selected})
    try:
        with gkx_element_read_session() as session:
            meta = (
                session.execute(text("SELECT DATABASE() AS db, VERSION() AS version"))
                .mappings()
                .one()
            )
            rows = session.execute(
                text(
                    "SELECT TABLE_NAME, COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS "
                    "WHERE TABLE_SCHEMA = DATABASE()"
                )
            ).mappings()
            columns_by_table: dict[str, set[str]] = {}
            for row in rows:
                columns_by_table.setdefault(str(row["TABLE_NAME"]), set()).add(
                    str(row["COLUMN_NAME"])
                )
            missing_tables = sorted(set(expected_tables) - set(columns_by_table))
            selected_relations = [
                spec for spec in RELATION_SPECS if scope == "all" or spec.scope == scope
            ]
            required_columns_by_table: dict[str, set[str]] = {}
            for spec in selected_relations:
                required_columns_by_table.setdefault(spec.source_table, set()).update(
                    spec.required_columns
                )
            missing_columns = {
                table: sorted(required - columns_by_table.get(table, set()))
                for table, required in required_columns_by_table.items()
                if table in columns_by_table and required - columns_by_table.get(table, set())
            }
            report["mysql"] = {
                "ok": not missing_tables and not missing_columns,
                "database": meta["db"],
                "version": meta["version"],
                "expectedTableCount": len(expected_tables),
                "foundTableCount": len(set(expected_tables) & set(columns_by_table)),
                "missingTables": missing_tables,
                "missingRequiredColumns": missing_columns,
                "connection": build_gkx_element_url().split("@", 1)[-1],
            }
            if missing_tables:
                errors.append(f"MySQL 缺少 {len(missing_tables)} 张机构来源表")
            if missing_columns:
                errors.append(f"MySQL 有 {len(missing_columns)} 张表缺少关系抽取必需字段")
    except Exception as exc:
        report["mysql"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        errors.append("MySQL 连接或元数据检查失败")

    graph: TRSGraphClient | None = None
    try:
        settings = TRSGraphSettings.from_env()
        graph = TRSGraphClient(settings)
        graph.connect()
        report["graph"] = {
            "ok": True,
            "baseUrl": settings.base_url,
            "space": settings.space,
            "labels": sorted(graph.labels()),
            "edgeTypes": sorted(graph.edge_types()),
        }
    except Exception as exc:
        report["graph"] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
        errors.append("TRSGraph 服务连接失败")
    finally:
        if graph is not None:
            graph.close()

    report["errors"] = errors
    report["ok"] = not errors
    return (0 if report["ok"] else 2), report


def _workflow_run(args: argparse.Namespace, *, dry_run: bool) -> tuple[int, dict[str, Any]]:
    from script.workflows.organization_ingest_workflow import workflow

    if not dry_run and not args.yes:
        raise ValueError("正式写入必须显式增加 --yes")
    payload = {
        "stage": args.stage,
        "scope": args.scope,
        "table": args.table,
        "relation": args.relation,
        "max_records": args.max_records,
        "entity_batch_size": args.entity_batch_size,
        "relation_batch_size": args.relation_batch_size,
        "dry_run": dry_run,
        "alignment_mode": args.alignment_mode,
        "ingest_batch": args.ingest_batch,
        "space": os.environ["TRS_GRAPH_SPACE"],
        "report": not args.no_report,
    }
    result = workflow(payload)
    failures = []
    quality_issues = []
    for section in ("entities", "relations"):
        for name, stats in result.get(section, {}).items():
            if int(stats.get("failed", 0)) > 0:
                failures.append(f"{section}.{name}.failed={stats.get('failed', 0)}")
            for field in ("invalid", "source_missing", "target_missing", "unresolved_identifier"):
                value = int(stats.get(field, 0))
                if value > 0:
                    quality_issues.append(f"{section}.{name}.{field}={value}")
    if failures:
        result["failedItems"] = failures
    if quality_issues:
        result["qualityIssues"] = quality_issues
    exit_code = 1 if failures else 0
    if not failures and quality_issues:
        exit_code = 3
    return exit_code, result


def _init_schema(confirmed: bool) -> tuple[int, dict[str, Any]]:
    if not confirmed:
        raise ValueError("初始化 Schema 必须显式增加 --yes")
    from infra.graph_db import get_trs_graph_client
    from script.organization_entity_etl import initialize_schema
    from script.organization_etl_common import exclusive_etl_lock

    with exclusive_etl_lock("organization_entity_schema", "schema"):
        graph = get_trs_graph_client()
        initialize_schema(graph)
    return 0, {
        "ok": True,
        "space": os.environ["TRS_GRAPH_SPACE"],
        "message": "机构图 Schema 已初始化/补齐",
    }


def _verify() -> tuple[int, dict[str, Any]]:
    from infra.graph_db import get_trs_graph_client
    from script.organization_acceptance import collect_graph_snapshot

    return 0, collect_graph_snapshot(get_trs_graph_client())


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        stream=sys.stderr,
    )
    try:
        env_path = _load_environment(args.env_file)
        if args.command == "preflight":
            code, result = _preflight(args.scope, env_path)
        elif args.command == "init-schema":
            code, result = _init_schema(args.yes)
        elif args.command == "dry-run":
            code, result = _workflow_run(args, dry_run=True)
        elif args.command == "write":
            code, result = _workflow_run(args, dry_run=False)
        else:
            code, result = _verify()
        print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
        return code
    except Exception as exc:
        logging.getLogger("organization_ETL").exception("执行失败")
        print(
            json.dumps(
                {"ok": False, "errorType": type(exc).__name__, "error": str(exc)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
