"""回填 Schema 目录中文名：label=英文名 的存量记录按映射表补中文。

背景：自动化登记脚本曾拿英文名顶 label（register_graph_schemas 反向登记 /
register_platform_extraction 平台喂数注册），Schema 管理页第一列（中文名）
因此显示英文。本脚本只改 label=name 的行（人工维护过的中文 label 不动），
幂等，可对任意空间重跑。

用法（容器内，PYTHONPATH=/app）：
    python script/backfill_schema_labels.py --dry-run          # 只看会改哪些
    python script/backfill_schema_labels.py                    # 默认 dev,dev2
    python script/backfill_schema_labels.py --space gaoxing_test
"""

import argparse
import logging
import sys

from sqlalchemy import bindparam, text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("backfill_schema_labels")

_LIST_PENDING = text(
    "SELECT id, kind, name FROM kg_schema_definition "
    "WHERE graph_space = :space AND is_deleted = 0 "
    "AND label = name AND name IN :names"
).bindparams(bindparam("names", expanding=True))
_SET_LABEL = text(
    "UPDATE kg_schema_definition SET label = :label, updated_at = NOW() WHERE id = :id"
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--space",
        default="dev,dev2",
        help="目标图空间，逗号分隔（默认 dev,dev2）",
    )
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不落库")
    args = parser.parse_args()

    from infra.workflow_mysql import get_workflow_engine
    from script.schema_label_map import SCHEMA_LABELS

    names = list(SCHEMA_LABELS)
    engine = get_workflow_engine()
    total = 0
    with engine.begin() as conn:
        for space in [s.strip() for s in args.space.split(",") if s.strip()]:
            rows = conn.execute(_LIST_PENDING, {"space": space, "names": names}).mappings()
            pending = list(rows)
            if not pending:
                logger.info("空间 %s：没有 label=英文名 的待补记录", space)
                continue
            for row in pending:
                label = SCHEMA_LABELS[row["name"]]
                if args.dry_run:
                    logger.info("[dry-run] %s %s: %s -> %s", space, row["kind"], row["name"], label)
                    continue
                conn.execute(_SET_LABEL, {"label": label, "id": row["id"]})
                logger.info("✓ %s %s %s: label -> %s", space, row["kind"], row["name"], label)
            total += len(pending)
    if not args.dry_run:
        logger.info("完成：共回填 %d 条", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
