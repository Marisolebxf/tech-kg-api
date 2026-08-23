"""一键构建学者域图空间 + 向量检索（MySQL -> 图数据库 + Milvus）。

全部配置来自环境变量，本脚本不做任何硬编码：

  - TRS_GRAPH_SPACE          目标图空间（graph 侧隔离单位）
  - SCHOLAR_MILVUS_COLLECTION 学者向量集合名（默认 scholar_person；
                             在 test 空间实验时建议设为 scholar_person_test，
                             避免动到共享集合）
  - MYSQL_* / MILVUS_*       数据库与向量库连接

按顺序编排六个既有步骤：

  1. schema   -> script.init_scholar_schema        （幂等：DESCRIBE 对比后 CREATE/ALTER）
  2. entities -> script.load_scholar_entities      （MySQL 学者表 -> Person 顶点）
  3. relations-> script.load_scholar_relations     （任职/合作边）
  4. milvus   -> script.build_scholar_milvus_index （Person -> 向量集合，upsert 不删旧）
  5. align    -> script.align_scholar_affiliations （组织对齐，写 SAME_AS；依赖组织向量集合）
  6. dedupe   -> script.dedupe_scholar_persons     （学者消歧，写 SAME_AS；默认 dry-run，
                                                    本脚本实跑时自动加 --write）

用法示例（在 test 空间验证，向量集合同步隔离）：

    TRS_GRAPH_SPACE=test SCHOLAR_MILVUS_COLLECTION=scholar_person_test \
    MYSQL_DATABASE=gkx_element PYTHONPATH=. \
        ./.venv/bin/python -m script.rebuild_scholar_graph

常用参数：
    --dry-run          各步骤只打印动作，不写图/不写向量库
    --create-space     目标空间不存在时先创建（需 TRS_GRAPH_BOOTSTRAP_SPACE 提供上下文）
    --stages ...       只跑部分步骤，逗号分隔（如 schema,entities,relations）
"""

from __future__ import annotations

import argparse
import logging
import os
import subprocess
import sys

logger = logging.getLogger(__name__)

STAGES: list[tuple[str, str]] = [
    ("schema", "script.init_scholar_schema"),
    ("entities", "script.load_scholar_entities"),
    ("relations", "script.load_scholar_relations"),
    ("milvus", "script.build_scholar_milvus_index"),
    ("align", "script.align_scholar_affiliations"),
    ("dedupe", "script.dedupe_scholar_persons"),
]

# 实跑（非 dry-run）时各步骤追加的参数
REAL_ARGS: dict[str, list[str]] = {
    "schema": [],
    "entities": [],
    "relations": [],
    "milvus": [],
    "align": [],
    "dedupe": ["--write"],  # dedupe 默认 dry-run，实跑需显式 --write
}


def _run_stage(name: str, module: str, args: list[str]) -> int:
    cmd = [sys.executable, "-m", module, *args]
    logger.info("=== 步骤 %s: %s ===", name, " ".join(cmd))
    # 环境变量原样透传（TRS_GRAPH_SPACE / SCHOLAR_MILVUS_COLLECTION / MYSQL_* 均由调用方决定）
    proc = subprocess.run(cmd, env=os.environ.copy())
    if proc.returncode != 0:
        logger.error("步骤 %s 失败（exit %s），中止后续步骤", name, proc.returncode)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="一键构建学者域图空间 + 向量检索")
    parser.add_argument(
        "--stages",
        default="schema,entities,relations,milvus,align,dedupe",
        help="要执行的步骤，逗号分隔，默认全部六步",
    )
    parser.add_argument("--dry-run", action="store_true", help="各步骤只打印动作，不写图/向量库")
    parser.add_argument(
        "--create-space",
        action="store_true",
        help="目标空间不存在时先创建（传给 init_scholar_schema）",
    )
    parser.add_argument(
        "--graph-space", default=None, help="覆盖 TRS_GRAPH_SPACE（默认取环境变量）"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="小规模测试：entities/relations/milvus 各只处理前 N 条（默认全量）",
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )

    selected = [s.strip() for s in args.stages.split(",") if s.strip()]
    known = {name for name, _ in STAGES}
    unknown = [s for s in selected if s not in known]
    if unknown:
        parser.error(f"未知步骤: {unknown}，可选: {sorted(known)}")

    if args.graph_space:
        os.environ["TRS_GRAPH_SPACE"] = args.graph_space
    env = os.environ

    space = env.get("TRS_GRAPH_SPACE", "(未设置)")
    collection = env.get("SCHOLAR_MILVUS_COLLECTION", "scholar_person")
    logger.info(
        "目标图空间: %s | 向量集合: %s | MySQL 库: %s | dry_run=%s",
        space,
        collection,
        env.get("MYSQL_DATABASE", "(未设置)"),
        args.dry_run,
    )
    if "milvus" in selected and "SCHOLAR_MILVUS_COLLECTION" not in env:
        logger.warning(
            "未设置 SCHOLAR_MILVUS_COLLECTION，将使用默认集合 %r——如该集合为共享/生产集合，"
            "实验时请显式指定（例如 scholar_person_test）",
            collection,
        )

    for name, module in STAGES:
        if name not in selected:
            logger.info("--- 跳过步骤 %s", name)
            continue
        stage_args = [] if args.dry_run else list(REAL_ARGS[name])
        if args.dry_run:
            stage_args.append("--dry-run")
        if name == "schema" and args.create_space:
            stage_args.append("--create-space")
        if args.limit is not None and name in ("entities", "relations", "milvus"):
            stage_args.extend(["--limit", str(args.limit)])
        rc = _run_stage(name, module, stage_args)
        if rc != 0:
            return rc

    logger.info("全部步骤完成: %s", ",".join(selected))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
