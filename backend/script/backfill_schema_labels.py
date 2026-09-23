"""回填 Schema 目录中文名：按映射表补/纠 label。

背景：自动化登记脚本曾拿英文名顶 label（register_graph_schemas 反向登记 /
register_platform_extraction 平台喂数注册），Schema 管理页第一列（中文名）
因此显示英文。两类修法（幂等，可对任意空间重跑）：

- PRODUCT_LABELS（产品口径权威命名）：label 与目标不一致就改——覆盖此前
  回填的错值和 is_system=1 种子行的旧称（如 通用人员 → 科技专家）；
- 其余映射：只改 label=英文名 的行，人工维护过的中文 label 不动。

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

# 产品口径权威命名：label <> 目标即改（含 is_system 种子行与历史回填错值）
_LIST_FORCE = text(
    "SELECT id, kind, name, label FROM kg_schema_definition "
    "WHERE graph_space = :space AND is_deleted = 0 "
    "AND name IN :names AND label <> :label"
).bindparams(bindparam("names", expanding=True))
# 其余映射：只补 label=英文名 的行
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
    from script.schema_label_map import PRODUCT_LABELS, SCHEMA_LABELS

    other_labels = {n: v for n, v in SCHEMA_LABELS.items() if n not in PRODUCT_LABELS}
    engine = get_workflow_engine()
    total = 0
    with engine.begin() as conn:
        for space in [s.strip() for s in args.space.split(",") if s.strip()]:
            # 权威命名：逐名比对（每名目标不同），不一致即改
            for name, label in PRODUCT_LABELS.items():
                rows = conn.execute(
                    _LIST_FORCE, {"space": space, "names": [name], "label": label}
                ).mappings()
                for row in rows:
                    tag = "dry-run" if args.dry_run else "✓"
                    logger.info(
                        "[%s] %s %s %s: %s -> %s（产品口径）",
                        tag,
                        space,
                        row["kind"],
                        name,
                        row["label"],
                        label,
                    )
                    if not args.dry_run:
                        conn.execute(_SET_LABEL, {"label": label, "id": row["id"]})
                    total += 1
            # 其余映射：只补 label=英文名
            rows = conn.execute(
                _LIST_PENDING, {"space": space, "names": list(other_labels)}
            ).mappings()
            for row in rows:
                label = other_labels[row["name"]]
                tag = "dry-run" if args.dry_run else "✓"
                logger.info(
                    "[%s] %s %s %s: %s -> %s",
                    tag,
                    space,
                    row["kind"],
                    row["name"],
                    row["name"],
                    label,
                )
                if not args.dry_run:
                    conn.execute(_SET_LABEL, {"label": label, "id": row["id"]})
                total += 1
    if not args.dry_run:
        logger.info("完成：共回填 %d 条", total)
    return 0


if __name__ == "__main__":
    sys.exit(main())
