"""一次性把 kg_schema_definition 里所有 pending 的 schema 在当前图空间建 TAG/EDGE。

SCHEMA_AUTO_INIT 启动时只 populate 了 MySQL 的 kg_schema_definition 行，没执行图 DDL
（CREATE TAG/EDGE）。本脚本扫所有 kind=entity/relation、ddl_status != success 的行，
调 service.schema_ddl.run_schema_ddl 在当前 TRS_GRAPH_SPACE 上执行 DDL，并回写
ddl_status / ddl_statement / ddl_error / ddl_executed_at。

用法：
    docker exec tech-kg-api-dev2 .venv/bin/python -m script.run_dev2_schema_ddl
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from db_model.schema_management import GraphSchemaDefinition
from infra.mysql import get_engine
from service.schema_ddl import run_schema_ddl

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    engine = get_engine()
    failed: list[str] = []
    with Session(engine) as session:
        defs = session.scalars(
            select(GraphSchemaDefinition)
            .where(GraphSchemaDefinition.kind.in_(["entity", "relation"]))
            .options(selectinload(GraphSchemaDefinition.properties))
        ).all()
        logger.info("found %d schema definitions", len(defs))
        for d in defs:
            kind = d.kind
            name = d.name
            props = [
                {
                    "name": p.name,
                    "data_type": p.data_type,
                    "required": p.required,
                }
                for p in (d.properties or [])
            ]
            try:
                result = run_schema_ddl(kind, name, props)
                d.ddl_statement = result["statement"]
                d.ddl_status = result["status"]
                d.ddl_error = result["error"]
                if result["executed_at"]:
                    d.ddl_executed_at = datetime.fromisoformat(result["executed_at"])
                session.flush()
                logger.info(
                    "%s %s -> %s%s",
                    kind,
                    name,
                    result["status"],
                    f" err={result['error'][:120]}" if result["error"] else "",
                )
                if result["status"] != "succeeded":
                    failed.append(f"{kind}:{name}")
            except Exception as exc:
                logger.exception("%s %s DDL raised", kind, name)
                d.ddl_status = "failed"
                d.ddl_error = str(exc)[:1024]
                session.flush()
                failed.append(f"{kind}:{name}")
        session.commit()
    logger.info("done; failed=%d", len(failed))
    if failed:
        logger.warning("failed schemas: %s", ", ".join(failed))
        # 用 quote 让 \n 等字符可见，避免日志截断
        print(f"FAILED={quote(','.join(failed))}", file=sys.stderr)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
