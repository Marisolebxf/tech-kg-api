"""把一对一抽取脚本注册为平台喂数抽取（kg.schema.extract）。

对注册表每个条目：按 name 查找（缺失则创建）schema → 上传转换后脚本
（入口 ``transform(payload)``）→ ``replace_sources`` 绑定来源表（复杂 SQL 走
query_sql）。幂等：重复执行覆盖脚本与来源绑定；同名 schema（如 HAS_KEYWORD
被 paper/patent/project 三方产出）后者覆盖前者，与旧 dev2_api_flow_batch 流程一致。

数据源：默认取 ``MYSQL_DATASOURCE_ID`` env；否则 platform_mysql_datasource 里
``is_default`` 的那行；都没有则报错退出。绑定前用 information_schema 校验
pk/time 列存在（query_sql 用 LIMIT 0 试跑），不合法的来源跳过并告警。

用法（容器内）::

    PYTHONPATH=. uv run python -m script.register_platform_extraction \
        [--user admin] [--datasource-id XXX] [--database gkx_element] [--dry-run]
"""

from __future__ import annotations

import argparse
import importlib
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("register_platform_extraction")

BACKEND_DIR = Path(__file__).resolve().parents[1]

BASE_PROPS = ["id", "name", "source_table", "create_time", "update_time"]

# (脚本模块, kind, schema 名, 关系端点 tag)
# 实体按 TAG 名建/找；关系按边类型名建/找，端点引用注册表中的实体 schema。
# 顺序有意义：同名 schema 后者覆盖前者（HAS_KEYWORD/AUTHORED_BY/CITES 冲突时
# 以领域主脚本胜出——paper_has_keyword、authored_by、paper_cites 放最后）。
ENTITY_REGISTRY: list[tuple[str, str]] = [
    ("script.entity_extractors_one_entity.datasource_entity", "DataSource"),
    ("script.entity_extractors_one_entity.industry_chain_entity", "IndustryChain"),
    ("script.entity_extractors_one_entity.industry_node_entity", "IndustryNode"),
    ("script.entity_extractors_one_entity.person_entity", "Person"),
    ("script.entity_extractors_one_entity.organization_entity", "Organization"),
    ("script.entity_extractors_one_entity.patent_family_entity", "PatentFamily"),
    ("script.entity_extractors_one_entity.event_entity", "Event"),
    ("script.entity_extractors_one_entity.news_entity", "News"),
    ("script.entity_extractors_one_entity.product_entity", "Product"),
    ("script.entity_extractors_one_entity.journal_entity", "Journal"),
    ("script.entity_extractors_one_entity.report_entity", "Report"),
    ("script.entity_extractors_one_entity.keyword_entity", "Keyword"),
    ("script.entity_extractors_one_entity.patent_entity", "Patent"),
    ("script.entity_extractors_one_entity.paper_entity", "Paper"),
    ("script.entity_extractors_one_entity.project_entity", "Project"),
]

RELATION_REGISTRY: list[tuple[str, str, str, str]] = [
    # (脚本模块, 边类型, source tag, target tag)
    (
        "script.relation_extractors_one_relation.authored_by_fallback_relation",
        "AUTHORED_BY",
        "Paper",
        "Person",
    ),
    ("script.relation_extractors_one_relation.patent_cites_relation", "CITES", "Patent", "Patent"),
    (
        "script.relation_extractors_one_relation.project_has_keyword_relation",
        "HAS_KEYWORD",
        "Project",
        "Keyword",
    ),
    (
        "script.relation_extractors_one_relation.patent_has_keyword_relation",
        "HAS_KEYWORD",
        "Patent",
        "Keyword",
    ),
    (
        "script.relation_extractors_one_relation.member_of_family_relation",
        "MEMBER_OF_FAMILY",
        "Patent",
        "PatentFamily",
    ),
    (
        "script.relation_extractors_one_relation.funded_by_relation",
        "FUNDED_BY",
        "Project",
        "Organization",
    ),
    ("script.relation_extractors_one_relation.leads_relation", "LEADS", "Project", "Person"),
    (
        "script.relation_extractors_one_relation.has_participant_relation",
        "HAS_PARTICIPANT",
        "Project",
        "Person",
    ),
    (
        "script.relation_extractors_one_relation.has_output_relation",
        "HAS_OUTPUT",
        "Project",
        "Paper",
    ),
    (
        "script.relation_extractors_one_relation.affiliated_with_relation",
        "AFFILIATED_WITH",
        "Person",
        "Organization",
    ),
    (
        "script.relation_extractors_one_relation.child_of_relation",
        "CHILD_OF",
        "IndustryNode",
        "IndustryNode",
    ),
    (
        "script.relation_extractors_one_relation.downstream_of_relation",
        "DOWNSTREAM_OF",
        "IndustryNode",
        "IndustryNode",
    ),
    (
        "script.relation_extractors_one_relation.has_node_relation",
        "HAS_NODE",
        "IndustryChain",
        "IndustryNode",
    ),
    (
        "script.relation_extractors_one_relation.belongs_to_node_relation",
        "BELONGS_TO_NODE",
        "Organization",
        "IndustryNode",
    ),
    (
        "script.relation_extractors_one_relation.covers_chain_relation",
        "COVERS_CHAIN",
        "News",
        "IndustryChain",
    ),
    (
        "script.relation_extractors_one_relation.referenced_by_relation",
        "REFERENCED_BY",
        "Paper",
        "Report",
    ),
    (
        "script.relation_extractors_one_relation.published_in_relation",
        "PUBLISHED_IN",
        "Paper",
        "Journal",
    ),
    (
        "script.relation_extractors_one_relation.coauthor_with_relation",
        "COAUTHOR_WITH",
        "Person",
        "Person",
    ),
    ("script.relation_extractors_one_relation.paper_cites_relation", "CITES", "Paper", "Paper"),
    (
        "script.relation_extractors_one_relation.paper_has_keyword_relation",
        "HAS_KEYWORD",
        "Paper",
        "Keyword",
    ),
    (
        "script.relation_extractors_one_relation.authored_by_relation",
        "AUTHORED_BY",
        "Paper",
        "Person",
    ),
]

# 机构域 11 组 spec 驱动脚本：(relation key, 脚本文件名, source tag, target tag)；
# 边类型从 catalog 推导（一个 key 可能对应多条同类型 spec）
_ORG_RELATION_KEYS: list[tuple[str, str, str, str]] = [
    ("legal_representative", "legal_rep_of_relation", "Person", "Organization"),
    ("executive", "executive_of_relation", "Person", "Organization"),
    ("shareholder", "shareholder_of_relation", "Organization", "Organization"),
    ("actual_controller", "actual_controller_of_relation", "Organization", "Organization"),
    ("beneficial_owner", "beneficial_owner_of_relation", "Person", "Organization"),
    ("subsidiary", "subsidiary_of_relation", "Organization", "Organization"),
    ("investment", "invests_in_relation", "Organization", "Organization"),
    ("acquisition", "acquires_relation", "Organization", "Organization"),
    ("product", "produces_relation", "Organization", "Product"),
    ("news", "has_news_relation", "News", "Organization"),
    ("event", "involved_in_relation", "Event", "Organization"),
]


def _org_relation_entries() -> list[tuple[str, str, str, str]]:
    from script.relation_extractors_one_relation.catalog import SPECS_BY_KEY

    entries: list[tuple[str, str, str, str]] = []
    for key, filename, source_tag, target_tag in _ORG_RELATION_KEYS:
        module_name = f"script.relation_extractors_one_relation.{filename}"
        edge_types = sorted({spec.edge_type for spec in SPECS_BY_KEY[key]})
        for edge_type in edge_types:
            entries.append((module_name, edge_type, source_tag, target_tag))
    return entries


def _resolve_datasource_id(explicit: str | None) -> tuple[str, dict[str, Any]]:
    from db_model.mysql_datasource import MysqlDatasource
    from infra.mysql import get_mysql_client

    with get_mysql_client().session_scope() as session:
        if explicit:
            row = session.get(MysqlDatasource, explicit)
            if row is None:
                raise SystemExit(f"指定数据源不存在: {explicit}")
        else:
            row = (
                session.query(MysqlDatasource).filter(MysqlDatasource.is_default.is_(True)).first()
            )
            if row is None:
                count = session.query(MysqlDatasource).count()
                if count == 1:
                    row = session.query(MysqlDatasource).first()
                else:
                    raise SystemExit(
                        f"platform_mysql_datasource 无默认数据源且共 {count} 行，请用 --datasource-id 指定"
                    )
        return str(row.id), {
            "host": row.host,
            "port": row.port,
            "username": row.username,
            "password": row.password,
            "database": row.default_database,
        }


_PK_CANDIDATES = (
    "id",
    "org_id",
    "news_id",
    "case_no",
    "scholar_id",
    "paper_id",
    "author_id",
    "chain_code",
    "node_id",
    "publication_id",
    "report_id",
)


def _validate_sources(
    params: dict[str, Any], database: str, sources: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """普通表按 information_schema **自动探测** pk/时间列（各表主键口径不一，
    脚本 SOURCES 里的 pk/time 只作参考）；query_sql 用 LIMIT 0 试跑并保留脚本
    声明的合成唯一 pk。不合法来源跳过并告警。"""
    from urllib.parse import quote_plus

    url = (
        f"mysql+pymysql://{params['username']}:{quote_plus(params['password'])}"
        f"@{params['host']}:{params['port']}/{database}?charset=utf8mb4"
    )
    engine = create_engine(url)
    valid: list[dict[str, Any]] = []
    try:
        with engine.connect() as conn:
            for src in sources:
                label = src.get("table") or str(src.get("query_sql") or "")[:40]
                try:
                    if src.get("query_sql"):
                        conn.execute(text(f"SELECT * FROM ({src['query_sql']}) AS _src LIMIT 0"))
                        valid.append(src)
                        continue
                    rows = conn.execute(
                        text(
                            "SELECT column_name FROM information_schema.columns "
                            "WHERE table_schema = :db AND table_name = :t "
                            "ORDER BY ordinal_position"
                        ),
                        {"db": database, "t": src["table"]},
                    ).fetchall()
                    cols = [r[0] for r in rows]
                    if not cols:
                        logger.warning("跳过 %s：库 %s 中不存在", label, database)
                        continue
                    pk = next((c for c in _PK_CANDIDATES if c in cols), cols[0])
                    time_col = (
                        "updated_time"
                        if "updated_time" in cols
                        else ("update_time" if "update_time" in cols else "")
                    )
                    valid.append({**src, "pk": pk, "time": time_col})
                except Exception as exc:  # noqa: BLE001
                    logger.warning("跳过 %s：%s", label, exc)
    finally:
        engine.dispose()
    return valid


def _find_schema(session: Session, *, kind: str, name: str) -> str | None:
    return session.execute(
        text("SELECT id FROM kg_schema_definition WHERE kind = :k AND name = :n LIMIT 1"),
        {"k": kind, "n": name},
    ).scalar()


def _module_sources(module: Any) -> list[dict[str, Any]]:
    raw = getattr(module, "SOURCES", None) or []
    normalized = []
    for src in raw:
        if callable(src):  # org wrapper SOURCES 是函数
            src = src()
        normalized.append(
            {
                "table": src["table"],
                "pk": src.get("pk") or "id",
                "time": src.get("time") or "",
                "query_sql": src.get("query_sql"),
            }
        )
    return normalized


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="platform-admin")
    parser.add_argument("--datasource-id", default=None)
    parser.add_argument("--database", default="gkx_element")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    import os

    from infra.workflow_mysql import get_workflow_engine
    from service.schema_management import SchemaManagementService

    datasource_id, ds_params = _resolve_datasource_id(
        args.datasource_id or os.getenv("MYSQL_DATASOURCE_ID")
    )
    logger.info("数据源 %s → %s", datasource_id, args.database)

    entries: list[tuple[str, str, str, str | None, str | None]] = []
    for module_name, tag in ENTITY_REGISTRY:
        entries.append((module_name, "entity", tag, None, None))
    for module_name, edge, source_tag, target_tag in RELATION_REGISTRY + _org_relation_entries():
        entries.append((module_name, "relation", edge, source_tag, target_tag))

    engine = get_workflow_engine()
    bound, skipped = 0, 0
    with Session(engine) as session:
        service = SchemaManagementService(session)
        for module_name, kind, name, source_tag, target_tag in entries:
            module = importlib.import_module(module_name)
            sources = _module_sources(module)
            schema_id = _find_schema(session, kind=kind, name=name)
            created = False
            if schema_id is None:
                # 直接调 service 层（无 HTTP CamelModel 转换），payload 用 snake_case
                payload = {
                    "schema_key": f"{name.lower().replace('_', '-')}-{uuid4().hex[:6]}",
                    "name": name,
                    "label": name,
                    "description": f"{name} 平台喂数抽取（register_platform_extraction 创建）",
                    "identity_key": "id" if kind == "entity" else "",
                    "mappings": [],
                    "version": "v1.0",
                    "is_core": False,
                    "properties": [
                        {
                            "name": prop,
                            "data_type": "string",
                            "required": prop in ("id", "name"),
                            "rule": "",
                            "category": "core",
                        }
                        for prop in BASE_PROPS
                    ],
                }
                if kind == "relation":
                    source_id = _find_schema(session, kind="entity", name=source_tag or "")
                    target_id = _find_schema(session, kind="entity", name=target_tag or "")
                    if not source_id or not target_id:
                        logger.warning(
                            "跳过 %s：端点实体 schema 缺失 (%s/%s)", name, source_tag, target_tag
                        )
                        skipped += 1
                        continue
                    payload["source_schema_id"] = source_id
                    payload["target_schema_id"] = target_id
                if args.dry_run:
                    logger.info("[dry-run] 将创建 %s schema %s (%s)", kind, name, module_name)
                    continue
                created = True
                schema_id = (
                    service.create_entity(payload=payload, user_id=args.user)
                    if kind == "entity"
                    else service.create_relation(payload=payload, user_id=args.user)
                )["id"]
            valid_sources = _validate_sources(ds_params, args.database, sources)
            if not valid_sources:
                logger.warning("跳过 %s：无有效来源绑定", name)
                skipped += 1
                continue
            if args.dry_run:
                logger.info(
                    "[dry-run] %s %s ← %s（%d 个来源，query_sql %d）",
                    "创建+绑定" if created else "更新",
                    name,
                    module_name.rsplit(".", 1)[-1],
                    len(valid_sources),
                    sum(1 for s in valid_sources if s.get("query_sql")),
                )
                continue
            script_path = Path(f"{module_name.replace('.', '/')}.py")
            service.replace_script(
                schema_id=schema_id,
                user_id=args.user,
                filename=script_path.name,
                content_type="text/x-python",
                script_data=script_path.read_bytes(),
                is_platform_admin=True,
            )
            service.replace_sources(
                schema_id=schema_id,
                sources=[
                    {
                        "datasource_id": datasource_id,
                        "database_name": args.database,
                        "table_name": s["table"],
                        "pk_column": s["pk"],
                        "time_column": s["time"],
                        "query_sql": s.get("query_sql"),
                    }
                    for s in valid_sources
                ],
                user_id=args.user,
                is_platform_admin=True,
            )
            bound += 1
            logger.info(
                "%s %s ← %s（%d 个来源%s）",
                "创建并绑定" if created else "更新",
                name,
                module_name.rsplit(".", 1)[-1],
                len(valid_sources),
                "，含 query_sql" if any(s.get("query_sql") for s in valid_sources) else "",
            )
    logger.info("完成：绑定 %d，跳过 %d", bound, skipped)


if __name__ == "__main__":
    main()
