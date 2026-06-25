"""Sync local schema documents and SQLAlchemy models from a MySQL database.

The script reads connection settings from environment variables:

    MYSQL_HOST, MYSQL_PORT, MYSQL_DATABASE, MYSQL_USERNAME, MYSQL_PASSWORD

It generates:

    schemas/ddl/<domain>/*.sql
    schemas/specifications/<domain>.md
    schemas/README.md
    db_model/*.py
"""

from __future__ import annotations

import keyword
import os
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from typing import Any

import pymysql

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "schemas"
DDL_DIR = SCHEMAS_DIR / "ddl"
SPEC_DIR = SCHEMAS_DIR / "specifications"
DB_MODEL_DIR = ROOT / "db_model"


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

DOMAIN_LABELS = {
    "scholar": "人才专家",
    "chinese_paper": "中文论文",
    "foreign_paper": "外文论文",
    "paper_common": "论文通用",
    "patent": "专利",
    "domestic_project": "国内项目",
    "foreign_project": "国外项目",
    "domestic_organization": "国内机构",
    "foreign_organization": "国外机构",
    "industry_chain": "产业链",
    "policy": "政策",
    "report": "报告",
}


def connect() -> pymysql.Connection:
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USERNAME", "root"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "gkx"),
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def domain_for_table(table_name: str) -> str:
    if table_name.startswith("dwd_scholar"):
        return "scholar"
    if table_name.startswith("ods_patent"):
        return "patent"
    if table_name.startswith("ods_zh_project"):
        return "domestic_project"
    if table_name.startswith("ods_en_project"):
        return "foreign_project"
    if table_name.startswith("dwd_industry_chain") or table_name.startswith(
        "dwd_org_industry_chain"
    ):
        return "industry_chain"
    if table_name.startswith("dwd_org_"):
        return "domestic_organization"
    if table_name.startswith("dwd_forg_"):
        return "foreign_organization"
    if table_name.startswith("dwd_zh_") or table_name == "ods_zh_journal":
        return "chinese_paper"
    if table_name.startswith("dwd_en_") or table_name == "ods_en_journal":
        return "foreign_paper"
    if table_name.startswith("dwd_author_"):
        return "paper_common"
    if "policy" in table_name:
        return "policy"
    if "report" in table_name:
        return "report"
    return "paper_common"


def clean_generated_dirs() -> None:
    for directory in (DDL_DIR, SPEC_DIR):
        directory.mkdir(parents=True, exist_ok=True)
        for path in directory.rglob("*"):
            if path.is_file():
                path.unlink()
        for path in sorted(directory.rglob("*"), reverse=True):
            if path.is_dir():
                path.rmdir()

    for path in DB_MODEL_DIR.glob("*.py"):
        if path.name != "base.py":
            path.unlink()


def fetch_metadata(
    conn: pymysql.Connection,
) -> tuple[list[dict[str, Any]], dict[str, list[dict[str, Any]]]]:
    database = os.getenv("MYSQL_DATABASE", "gkx")
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS, DATA_LENGTH, INDEX_LENGTH
            FROM information_schema.TABLES
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME
            """,
            (database,),
        )
        tables = list(cur.fetchall())

        cur.execute(
            """
            SELECT
                TABLE_NAME,
                COLUMN_NAME,
                ORDINAL_POSITION,
                COLUMN_TYPE,
                DATA_TYPE,
                IS_NULLABLE,
                COLUMN_KEY,
                COLUMN_DEFAULT,
                EXTRA,
                COLUMN_COMMENT
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
            ORDER BY TABLE_NAME, ORDINAL_POSITION
            """,
            (database,),
        )
        columns_by_table: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for row in cur.fetchall():
            columns_by_table[row["TABLE_NAME"]].append(row)

        for table in tables:
            cur.execute(f"SHOW CREATE TABLE `{table['TABLE_NAME']}`")
            row = cur.fetchone()
            table["create_sql"] = row["Create Table"]

    return tables, columns_by_table


def write_ddl(tables: list[dict[str, Any]]) -> None:
    counters: dict[str, int] = defaultdict(int)
    for table in tables:
        name = table["TABLE_NAME"]
        domain = domain_for_table(name)
        counters[domain] += 1
        directory = DDL_DIR / domain
        directory.mkdir(parents=True, exist_ok=True)
        sql = table["create_sql"].rstrip() + ";\n"
        path = directory / f"{counters[domain]:02d}_{name}.sql"
        path.write_text(sql, encoding="utf-8")


def md_escape(value: Any) -> str:
    if value is None:
        return ""
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def write_specifications(
    tables: list[dict[str, Any]], columns_by_table: dict[str, list[dict[str, Any]]]
) -> None:
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in tables:
        by_domain[domain_for_table(table["TABLE_NAME"])].append(table)

    for domain in DOMAIN_ORDER:
        domain_tables = by_domain.get(domain, [])
        if not domain_tables:
            continue
        lines = [
            f"# {DOMAIN_LABELS[domain]}字段规范",
            "",
            f"来源数据库：`{os.getenv('MYSQL_DATABASE', 'gkx')}`",
            f"生成日期：`{date.today().isoformat()}`",
            "",
            "| 表名 | 表注释 | 估算行数 | 字段数 |",
            "|---|---|---:|---:|",
        ]
        for table in domain_tables:
            table_name = table["TABLE_NAME"]
            lines.append(
                f"| `{table_name}` | {md_escape(table['TABLE_COMMENT'])} | "
                f"{table['TABLE_ROWS'] or 0} | {len(columns_by_table[table_name])} |"
            )

        for table in domain_tables:
            table_name = table["TABLE_NAME"]
            lines.extend(
                [
                    "",
                    f"## `{table_name}`",
                    "",
                    f"表注释：{md_escape(table['TABLE_COMMENT']) or '-'}",
                    "",
                    "| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |",
                    "|---:|---|---|---|---|---|---|---|",
                ]
            )
            for column in columns_by_table[table_name]:
                lines.append(
                    f"| {column['ORDINAL_POSITION']} | `{column['COLUMN_NAME']}` | "
                    f"`{md_escape(column['COLUMN_TYPE'])}` | {column['IS_NULLABLE']} | "
                    f"{md_escape(column['COLUMN_KEY'])} | {md_escape(column['COLUMN_DEFAULT'])} | "
                    f"{md_escape(column['EXTRA'])} | {md_escape(column['COLUMN_COMMENT'])} |"
                )

        (SPEC_DIR / f"{domain}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_schema_readme(
    tables: list[dict[str, Any]], columns_by_table: dict[str, list[dict[str, Any]]]
) -> None:
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in tables:
        by_domain[domain_for_table(table["TABLE_NAME"])].append(table)

    total_columns = sum(len(columns_by_table[table["TABLE_NAME"]]) for table in tables)
    lines = [
        "# 数据库 Schema 说明",
        "",
        "本目录维护与远程 MySQL 数据库 `gkx` 当前真实结构一致的字段规范和建表脚本。",
        "DDL 与字段说明由 `script/sync_schema_from_mysql.py` 从 `information_schema` 和 `SHOW CREATE TABLE` 生成。",
        "",
        f"生成日期：`{date.today().isoformat()}`",
        f"表总数：`{len(tables)}`",
        f"字段总数：`{total_columns}`",
        "",
        "## 目录结构",
        "",
        "```text",
        "schemas/",
        "├── specifications/    字段规范、表注释、字段注释和估算行数",
        "├── ddl/               按数据域拆分的 MySQL 建表 SQL",
        "└── README.md          本说明文件",
        "```",
        "",
        "## 数据域清单",
        "",
        "| 数据域 | 字段规范 | DDL 目录 | 表数 | 字段数 | 估算行数 |",
        "|---|---|---|---:|---:|---:|",
    ]
    for domain in DOMAIN_ORDER:
        domain_tables = by_domain.get(domain, [])
        if not domain_tables:
            continue
        column_count = sum(len(columns_by_table[table["TABLE_NAME"]]) for table in domain_tables)
        row_count = sum(table["TABLE_ROWS"] or 0 for table in domain_tables)
        lines.append(
            f"| {DOMAIN_LABELS[domain]} | `specifications/{domain}.md` | "
            f"`ddl/{domain}/` | {len(domain_tables)} | {column_count} | {row_count} |"
        )

    lines.extend(
        [
            "",
            "## 维护规则",
            "",
            "1. 当前目录以远程数据库 `gkx` 的真实表结构为准，不再保留旧版 62 表的冗余拆分定义。",
            "2. 表之间不额外补充物理外键；若源库没有主键或索引，本目录也不人为添加。",
            "3. 若远程库结构变化，重新执行同步脚本生成 DDL、字段规范和 ORM。",
            "4. 同步脚本只读取数据库元数据，不读取业务数据，也不会修改远程数据库。",
            "",
            "## 同步命令",
            "",
            "```bash",
            "MYSQL_HOST=183.240.141.251 \\",
            "MYSQL_PORT=3318 \\",
            "MYSQL_DATABASE=gkx \\",
            "MYSQL_USERNAME=gkx_reader_zp \\",
            "MYSQL_PASSWORD='***' \\",
            "uv run python script/sync_schema_from_mysql.py",
            "```",
        ]
    )
    (SCHEMAS_DIR / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def class_name(table_name: str) -> str:
    parts = re.split(r"[^0-9A-Za-z]+", table_name)
    return "".join(part[:1].upper() + part[1:] for part in parts if part)


def attr_name(column_name: str) -> str:
    name = re.sub(r"\W", "_", column_name)
    if not name or name[0].isdigit():
        name = f"col_{name}"
    if keyword.iskeyword(name):
        name = f"{name}_"
    return name


def type_expr(column: dict[str, Any]) -> str:
    data_type = column["DATA_TYPE"].lower()
    column_type = column["COLUMN_TYPE"].lower()
    length_match = re.search(r"\((\d+)(?:,(\d+))?\)", column_type)
    if data_type in {"varchar", "char", "binary", "varbinary"}:
        if length_match:
            return f"String({length_match.group(1)})"
        return "String()"
    if data_type in {"text", "tinytext", "mediumtext", "longtext"}:
        return "Text()"
    if data_type == "bigint":
        return "BigInteger()"
    if data_type in {"int", "integer", "mediumint"}:
        return "Integer()"
    if data_type in {"smallint", "tinyint"}:
        return "SmallInteger()"
    if data_type in {"double", "float"}:
        return "Float()"
    if data_type in {"decimal", "numeric"}:
        if length_match and length_match.group(2):
            return f"Numeric({length_match.group(1)}, {length_match.group(2)})"
        if length_match:
            return f"Numeric({length_match.group(1)})"
        return "Numeric()"
    if data_type == "date":
        return "Date()"
    if data_type in {"datetime", "timestamp", "time"}:
        return "DateTime()"
    if data_type == "json":
        return "JSON()"
    if data_type == "year":
        return "Integer()"
    return "Text()"


def type_name(type_expression: str) -> str:
    return type_expression.split("(", 1)[0]


def python_repr(value: Any) -> str:
    if value is None:
        return "None"
    return repr(str(value))


def column_line(column: dict[str, Any], primary_keys: set[str]) -> str:
    col_name = column["COLUMN_NAME"]
    args = [python_repr(col_name), type_expr(column)]
    kwargs = []
    if col_name in primary_keys:
        kwargs.append("primary_key=True")
    kwargs.append(f"nullable={column['IS_NULLABLE'] == 'YES'}")
    if column["COLUMN_COMMENT"]:
        kwargs.append(f"comment={python_repr(column['COLUMN_COMMENT'])}")
    return f"    {attr_name(col_name)} = Column({', '.join(args + kwargs)})"


def write_db_models(
    tables: list[dict[str, Any]], columns_by_table: dict[str, list[dict[str, Any]]]
) -> None:
    by_domain: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for table in tables:
        by_domain[domain_for_table(table["TABLE_NAME"])].append(table)

    all_classes: list[tuple[str, str]] = []
    for domain in DOMAIN_ORDER:
        domain_tables = by_domain.get(domain, [])
        if not domain_tables:
            continue
        used_types = {
            type_name(type_expr(column))
            for table in domain_tables
            for column in columns_by_table[table["TABLE_NAME"]]
        }
        imports = sorted(["Column", *used_types])
        lines = [
            "from sqlalchemy import (",
            *[f"    {name}," for name in imports],
            ")",
            "",
            "from db_model.base import Base",
            "",
            "",
        ]
        for table in domain_tables:
            table_name = table["TABLE_NAME"]
            cols = columns_by_table[table_name]
            primary_keys = {col["COLUMN_NAME"] for col in cols if col["COLUMN_KEY"] == "PRI"}
            cls = class_name(table_name)
            all_classes.append((domain, cls))
            lines.append(f"class {cls}(Base):")
            if table["TABLE_COMMENT"]:
                lines.append(f'    """{table["TABLE_COMMENT"]}"""')
            lines.append(f"    __tablename__ = {table_name!r}")
            if table["TABLE_COMMENT"]:
                lines.append(f'    __table_args__ = {{"comment": {table["TABLE_COMMENT"]!r}}}')
            lines.append("")
            for column in cols:
                lines.append(column_line(column, primary_keys))
            if not primary_keys and cols:
                mapper_col = attr_name(cols[0]["COLUMN_NAME"])
                lines.append("")
                lines.append(
                    "    # Source table has no physical primary key; this is ORM identity only."
                )
                lines.append(f'    __mapper_args__ = {{"primary_key": [{mapper_col}]}}')
            lines.extend(["", ""])

        (DB_MODEL_DIR / f"{domain}.py").write_text(
            "\n".join(lines).rstrip() + "\n", encoding="utf-8"
        )

    init_lines = ["from db_model.base import Base"]
    for domain in sorted({domain for domain, _ in all_classes}):
        classes = [cls for file_domain, cls in all_classes if file_domain == domain]
        if not classes:
            continue
        init_lines.append(f"from db_model.{domain} import (")
        for cls in classes:
            init_lines.append(f"    {cls},")
        init_lines.append(")")
    init_lines.extend(["", "__all__ = [", '    "Base",'])
    for _, cls in all_classes:
        init_lines.append(f'    "{cls}",')
    init_lines.append("]")
    (DB_MODEL_DIR / "__init__.py").write_text("\n".join(init_lines) + "\n", encoding="utf-8")


def main() -> None:
    clean_generated_dirs()
    with connect() as conn:
        tables, columns_by_table = fetch_metadata(conn)
    write_ddl(tables)
    write_specifications(tables, columns_by_table)
    write_schema_readme(tables, columns_by_table)
    write_db_models(tables, columns_by_table)
    print(
        f"Synced {len(tables)} tables and {sum(len(v) for v in columns_by_table.values())} columns."
    )


if __name__ == "__main__":
    main()
