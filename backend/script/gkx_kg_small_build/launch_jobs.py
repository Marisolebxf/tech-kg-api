"""创建 gkx_kg_sm 构建任务（3 个 chain）：实体批 15 先跑，关系批 A/B 建好待触发。

以用户 2672（platform_admin、MYSQL-A176CF7A 与 gkx_kg_sm 的创建者）身份走
job_service.create_job —— 任务归属本人，图谱构建页可见。

用法（api 容器内）::

    PYTHONPATH=/app /app/.venv/bin/python -m script.gkx_kg_small_build.launch_jobs \
        [--datasource-id MYSQL-A176CF7A] [--database gkx_kg] [--graph-space gkx_kg_sm] \
        [--trigger-relations-too]   # 实体关系一起跑（默认只跑实体批）
"""

from __future__ import annotations

import argparse
import asyncio
import logging

from sqlalchemy import text

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("launch_small_jobs")

USER_ID = "2672"
USERNAME = "19941138056"

# 与 spec.py 顺序一致：实体全部，关系按量分两批（A=大头，B=其余）
ENTITY_TAGS = [
    "Person", "Paper", "Patent", "PatentFamily", "Project", "Organization", "News",
    "Event", "Journal", "Keyword", "Report", "Product", "IndustryChain", "IndustryNode",
    "CitationStub",
]
RELATION_BATCH_A = [
    "AUTHORED_BY", "COAUTHOR_WITH", "CITES", "HAS_KEYWORD", "INVOLVED_IN",
    "EXECUTIVE_OF", "BENEFICIAL_OWNER_OF", "INVESTS_IN", "PUBLISHED_IN",
    "BELONGS_TO_NODE", "SHAREHOLDER_OF", "PRODUCES", "APPLIED_BY",
]
RELATION_BATCH_B = [
    "MEMBER_OF_FAMILY", "INVENTED_BY", "LEGAL_REP_OF", "HAS_PARTICIPANT",
    "AFFILIATED_WITH", "HAS_NEWS", "ACQUIRES", "LEADS", "HAS_NODE", "FUNDED_BY",
    "SUBSIDIARY_OF", "ACTUAL_CONTROLLER_OF",
]


def _schema_ids(session, graph_space: str, names: list[str]) -> list[str]:
    rows = session.execute(
        text(
            "SELECT name, id, kind FROM kg_schema_definition "
            "WHERE graph_space = :g AND is_deleted = 0"
        ),
        {"g": graph_space},
    ).fetchall()
    by_name = {r[0]: r[1] for r in rows}
    missing = [n for n in names if n not in by_name]
    if missing:
        raise SystemExit(f"图空间 {graph_space} 缺 Schema: {missing}")
    return [by_name[n] for n in names]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--datasource-id", default="MYSQL-A176CF7A")
    parser.add_argument("--database", default="gkx_kg_sm")
    parser.add_argument("--graph-space", default="gkx_kg_sm")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--trigger-relations-too", action="store_true")
    args = parser.parse_args()

    from application.workflow_jobs import workflow_job_application
    from infra.workflow_mysql import create_workflow_session
    from service.platform_access import PlatformActor
    from service.schema_extraction import ensure_extract_script_ready

    job_service = workflow_job_application.service

    with create_workflow_session() as session:
        entity_ids = _schema_ids(session, args.graph_space, ENTITY_TAGS)
        rel_a_ids = _schema_ids(session, args.graph_space, RELATION_BATCH_A)
        rel_b_ids = _schema_ids(session, args.graph_space, RELATION_BATCH_B)

    all_ids = entity_ids + rel_a_ids + rel_b_ids
    not_ready = []
    for schema_id in all_ids:
        try:
            ensure_extract_script_ready(schema_id)
        except Exception as exc:  # noqa: BLE001
            not_ready.append((schema_id, str(exc)[:200]))
    if not_ready:
        for schema_id, err in not_ready:
            logger.error("不可抽取 %s: %s", schema_id, err)
        raise SystemExit(f"{len(not_ready)} 个 Schema 不可抽取，任务不建")
    logger.info("预检通过：40 个 Schema 脚本+来源+S3 本体齐备")

    actor = PlatformActor(
        user_id=USER_ID, username=USERNAME, display_name=USERNAME,
        email="", is_admin=True,
    )

    base = {
        "taskType": "chain",
        "batchSize": args.batch_size,
        "mysqlDatasourceId": args.datasource_id,
        "mysqlDatabase": args.database,
        "graphSpace": args.graph_space,
        "schedule": {"kind": "once"},
    }

    async def run() -> None:
        plans = [
            ("gkx_kg_sm建图-实体批(15)", entity_ids, True),
            ("gkx_kg_sm建图-关系批A(13)", rel_a_ids, args.trigger_relations_too),
            ("gkx_kg_sm建图-关系批B(12)", rel_b_ids, args.trigger_relations_too),
        ]
        for name, schema_ids, run_now in plans:
            job = await job_service.create_job(
                actor, {**base, "name": name, "schemaIds": schema_ids, "runNow": run_now}
            )
            logger.info(
                "任务 %s → %s（%d Schema，runNow=%s，执行=%s，状态=%s）",
                name, job["id"], len(schema_ids), run_now,
                job.get("lastExecutionId"), job.get("lastExecutionStatus"),
            )

    asyncio.run(run())


if __name__ == "__main__":
    main()
