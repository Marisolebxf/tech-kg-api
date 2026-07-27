"""初始化 TRSGraph `dev` 空间的项目域 schema（幂等）。

以 ontology Tag `Project` 为准（不用旧 ZhProject/EnProject）。

用法：
  TRS_GRAPH_SPACE=dev python -m script.init_project_schema
"""

from __future__ import annotations

from pathlib import Path

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

CREATE_SPACE_DDL: list[str] = [
    "CREATE SPACE IF NOT EXISTS dev(vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);",
]

SCHEMA_FILE = Path(__file__).resolve().parent / "ngql" / "project_schema.ngql"


def _load_schema_statements() -> list[str]:
    text = SCHEMA_FILE.read_text(encoding="utf-8")
    statements: list[str] = []
    buf: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        buf.append(stripped)
        if stripped.endswith(";"):
            statements.append(" ".join(buf))
            buf = []
    if buf:
        statements.append(" ".join(buf))
    return statements


def init_project_schema() -> None:
    settings = TRSGraphSettings.from_env()
    settings.space = "dev"

    bootstrap = TRSGraphClient(TRSGraphSettings.from_env())
    bootstrap.connect()
    try:
        for stmt in CREATE_SPACE_DDL:
            try:
                bootstrap.execute_write(stmt)
                print(f"ok: {stmt[:80]}")
            except Exception as exc:  # noqa: BLE001
                print(f"skip create space: {exc}")
    finally:
        bootstrap.close()

    # Nebula needs a short wait after CREATE SPACE before USE
    import time

    time.sleep(2)

    client = TRSGraphClient(settings)
    client.connect()
    try:
        for stmt in _load_schema_statements():
            try:
                client.execute_write(stmt)
                print(f"ok: {stmt[:100]}")
            except Exception as exc:  # noqa: BLE001
                print(f"skip ddl (may already exist): {exc}")
    finally:
        client.close()


if __name__ == "__main__":
    init_project_schema()
