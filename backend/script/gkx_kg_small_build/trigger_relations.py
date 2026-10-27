"""实体批成功后：触发 gkx_kg_sm 的关系批 A/B chain 任务（按任务名前缀查，不写死 id）。

用法（api 容器内）::

    PYTHONPATH=/app /app/.venv/bin/python -m script.gkx_kg_small_build.trigger_relations \
        [--graph-space gkx_kg_sm]
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("trigger_small_relations")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-space", default="gkx_kg_sm")
    args = parser.parse_args()

    from application.workflow_jobs import workflow_job_application
    from infra.workflow_mysql import create_workflow_session
    from service.platform_access import PlatformActor

    job_service = workflow_job_application.service
    with create_workflow_session() as session:
        rows = session.execute(
            text("SELECT id, name, status FROM workflow_jobs WHERE name LIKE :p"),
            {"p": f"{args.graph_space}建图-%"},
        ).fetchall()
    if not rows:
        raise SystemExit(f"没有找到 {args.graph_space} 的建图任务")
    for job_id, name, status in rows:
        logger.info("现有任务 %s %s（%s）", job_id, name, status)
    rel_jobs = [(r[0], r[1]) for r in rows if "关系批" in r[1]]

    actor = PlatformActor(
        user_id="2672", username="19941138056", display_name="19941138056",
        email="", is_admin=True,
    )

    async def run() -> None:
        for job_id, name in rel_jobs:
            job = await job_service.trigger_job(actor, job_id)
            logger.info(
                "触发 %s（%s）→ 执行=%s 状态=%s", job_id, name,
                job.get("lastExecutionId"), job.get("lastExecutionStatus"),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
