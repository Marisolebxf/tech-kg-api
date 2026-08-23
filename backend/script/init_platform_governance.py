"""只初始化平台角色、人工修正、同步任务与管理审计表。"""

from __future__ import annotations

from script.init_db import DDL_DIR, execute_sql_file, get_connection


def main() -> None:
    ddl_file = DDL_DIR / "platform_governance" / "01_platform_governance.sql"
    connection = get_connection()
    try:
        with connection.cursor() as cursor:
            execute_sql_file(cursor, ddl_file)
        print(f"OK: {ddl_file}")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
