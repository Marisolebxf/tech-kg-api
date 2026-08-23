"""为已有图空间补充人工修正的软停用与幂等元数据字段。"""

from __future__ import annotations

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

DDL = (
    "ALTER TAG Scholar ADD (manual_disabled bool, correction_id string, corrected_at string);",
    "ALTER TAG Organization ADD (manual_disabled bool, correction_id string, corrected_at string);",
    "ALTER EDGE EMPLOYED_BY ADD (manual_disabled bool, correction_id string, corrected_at string);",
)


def main() -> None:
    client = TRSGraphClient(TRSGraphSettings.from_env())
    client.connect()
    try:
        for statement in DDL:
            try:
                client.execute_write(statement)
                print(f"OK: {statement}")
            except Exception as exc:  # noqa: BLE001 - 重复字段由图服务返回错误
                print(f"SKIP: {statement} ({exc})")
    finally:
        client.close()


if __name__ == "__main__":
    main()
