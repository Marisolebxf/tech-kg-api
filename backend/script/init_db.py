"""Execute all DDL scripts in schemas/ddl/ against the configured MySQL database.

Usage:
    cd backend
    uv run python script/init_db.py

Reads connection info from environment variables (or .env via python-dotenv):
    MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USERNAME, MYSQL_PASSWORD

Defaults target the laboratory/server-side copied database, not the read-only
vendor source database used by sync_schema_from_mysql.py.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pymysql
from dotenv import load_dotenv

DOMAIN_ORDER = [
    "scholar",
    "chinese_paper",
    "foreign_paper",
    "paper_common",
    "patent",
    "domestic_project",
    "foreign_project",
    "domestic_organization",
    "foreign_organization",
    "industry_chain",
    "policy",
    "report",
]

DDL_DIR = Path(__file__).resolve().parent.parent / "schemas" / "ddl"


def get_connection() -> pymysql.Connection:
    load_dotenv()
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USERNAME", "root"),
        password=os.getenv("MYSQL_PASSWORD", "123456789"),
        database=os.getenv("MYSQL_DATABASE", "gkx_local"),
        charset="utf8mb4",
        autocommit=True,
    )


def execute_sql_file(cursor: pymysql.cursors.Cursor, path: Path) -> None:
    sql = path.read_text(encoding="utf-8")
    cursor.execute(sql.rstrip().rstrip(";"))


def main() -> None:
    if not DDL_DIR.exists():
        print(f"ERROR: DDL directory not found: {DDL_DIR}")
        sys.exit(1)

    conn = get_connection()
    cursor = conn.cursor()

    total = 0
    errors = 0

    for domain in DOMAIN_ORDER:
        domain_dir = DDL_DIR / domain
        if not domain_dir.exists():
            print(f"SKIP: {domain}/ not found")
            continue

        sql_files = sorted(domain_dir.glob("*.sql"))
        print(f"\n{'=' * 60}")
        print(f"Domain: {domain} ({len(sql_files)} files)")
        print(f"{'=' * 60}")

        for sql_file in sql_files:
            try:
                execute_sql_file(cursor, sql_file)
                print(f"  OK: {sql_file.name}")
                total += 1
            except Exception as e:
                print(f"  FAIL: {sql_file.name} -> {e}")
                errors += 1

    cursor.close()
    conn.close()

    print(f"\n{'=' * 60}")
    print(f"Done. Success: {total}, Failed: {errors}")
    print(f"{'=' * 60}")

    if errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
