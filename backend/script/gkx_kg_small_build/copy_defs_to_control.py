"""把误注册到 techkg_platform_dev2 的 gkx_kg_sm 40 条 Schema 定义搬到运行时真库 techkg_control。

背景：dev2 运行时的 Schema 目录在 WORKFLOW_MYSQL（temporal-mysql-dev2:3306 的
techkg_control），register.py 走了 infra.mysql（techkg_platform_dev2 陈旧副本）。
Nebula DDL 已真实执行（gkx_kg_sm 15 TAG + 25 EDGE），S3 脚本对象已上传（bucket 共享，
object_key 含 schema id），这里只搬目录行：kg_schema_definition / property / script / source。

用法（api 容器内）::

    PYTHONPATH=/app /app/.venv/bin/python -m script.gkx_kg_small_build.copy_defs_to_control
"""

from __future__ import annotations

import logging

from sqlalchemy import bindparam, text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("copy_defs_to_control")

GRAPH_SPACE = "gkx_kg_sm"


def main() -> None:
    from infra.mysql import get_engine as get_src_engine  # techkg_platform_dev2（误注册处）
    from infra.workflow_mysql import get_workflow_engine

    dst_engine = get_workflow_engine()  # techkg_control（运行时真库）
    with get_src_engine().connect() as src, dst_engine.begin() as dst:
        ids = [
            r[0] for r in src.execute(
                text("SELECT id FROM kg_schema_definition "
                     "WHERE graph_space = :g AND is_deleted = 0"),
                {"g": GRAPH_SPACE},
            ).fetchall()
        ]
        logger.info("源库 gkx_kg_sm 定义 %d 条", len(ids))
        if not ids:
            raise SystemExit("源库没有 gkx_kg_sm 定义，无事可做")
        clash = dst.execute(
            text("SELECT id FROM kg_schema_definition WHERE id IN :ids").bindparams(
                bindparam("ids", ids, expanding=True)
            )
        ).fetchall()
        if clash:
            raise SystemExit(f"目标库已有同名 id {len(clash)} 条，先人工处理")

        ph = ",".join(f":i{n}" for n in range(len(ids)))
        flat = {f"i{n}": v for n, v in enumerate(ids)}

        # 1) 定义行：只搬两边共有列；owner 是目标库专有列，固定给 2672
        defs = src.execute(
            # 实体(kind='entity')先于关系(kind='relation')：目标库有 source_schema_id
            # 自引用 FK，同批多行 INSERT 里父行必须排在前面
            text("SELECT * FROM kg_schema_definition WHERE graph_space = :g ORDER BY kind"),
            {"g": GRAPH_SPACE},
        ).mappings().fetchall()
        dst_cols = {
            r[0] for r in dst.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema = DATABASE() AND table_name = 'kg_schema_definition'"
            )).fetchall()
        }
        common = [k for k in defs[0].keys() if k in dst_cols]
        dst.execute(
            text(
                f"INSERT INTO kg_schema_definition ({','.join(common)}, owner) VALUES "
                + ", ".join(
                    f"({','.join(f':r{n}_{k}' for k in common)}, '2672')"
                    for n in range(len(defs))
                )
            ),
            {
                f"r{n}_{k}": row.get(k)
                for n, row in enumerate(defs)
                for k in common
            },
        )
        logger.info("kg_schema_definition 搬 %d 行（%d 共有列 + owner）", len(defs), len(common))

        # 2) 子表：按外键列过滤，同样取共有列
        for table, fk in (
            ("kg_schema_property", "schema_id"),
            ("kg_schema_script", "schema_id"),
            ("kg_schema_source", "schema_id"),
        ):
            rows = src.execute(
                text(f"SELECT * FROM {table} WHERE {fk} IN ({ph})"), flat
            ).mappings().fetchall()
            if not rows:
                logger.warning("%s 无行可搬", table)
                continue
            dst_cols = {
                r[0] for r in dst.execute(text(
                    f"SELECT column_name FROM information_schema.columns "
                    f"WHERE table_schema = DATABASE() AND table_name = '{table}'"
                )).fetchall()
            }
            common = [k for k in rows[0].keys() if k in dst_cols]
            dst.execute(
                text(
                    f"INSERT INTO {table} ({','.join(common)}) VALUES "
                    + ", ".join(
                        f"({','.join(f':r{n}_{k}' for k in common)})"
                        for n in range(len(rows))
                    )
                ),
                {
                    f"r{n}_{k}": row.get(k)
                    for n, row in enumerate(rows)
                    for k in common
                },
            )
            logger.info("%s 搬 %d 行", table, len(rows))

        dist = dst.execute(text(
            "SELECT kind, COUNT(*) FROM kg_schema_definition "
            "WHERE graph_space = :g AND is_deleted = 0 GROUP BY kind"
        ), {"g": GRAPH_SPACE}).fetchall()
        logger.info("目标库 gkx_kg_sm 分布: %s", dist)
    logger.info("提交完成")


if __name__ == "__main__":
    main()
