"""把 gkx_kg 抽取步注册到 gkx_kg_sm 图空间（Schema 定义 + DDL + 脚本 + 来源绑定）。

与 register_platform_extraction 同一套服务层（SchemaManagementService），差异：
- spec 驱动（本包 spec.py：14 业务实体 + CitationStub 辅助 + 25 关系）；
- 指定 --graph-space（默认 gkx_kg_sm），定义/DDL/绑定全部落该空间；
- 关系来源 = kg_edge 按边类型 query_sql（端点 vid 直传，_pk 合成主键 keyset 分页）；
- 实体来源 = kg_* 单表（一实体一表），pk=keyset 分页（time 留空不走水位）。

用法（api 容器内）::

    PYTHONPATH=/app uv run python -m script.gkx_kg_small_build.register \
        [--user platform-admin] [--datasource-id MYSQL-XXXX] \
        [--database gkx_kg] [--graph-space gkx_kg_sm] [--dry-run]
"""

from __future__ import annotations

import argparse

import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session  # noqa: F401 (类型注解用)

from script.gkx_kg_small_build.spec import ENTITIES, RELATIONS

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("register_gkxkg_small")

STEPS_DIR = Path(__file__).resolve().parent / "steps"

_PY_TO_NEBULA = {"int": "int64", "float": "double", "bool": "string", "str": "string"}


def _load_step(module_attr: str) -> Any:
    """读步骤文件模块属性（SOURCES/_PROP_TYPES）。步骤含 ``from kg_sdk import step``，
    只有沙箱运行时可导入，注册进程用 AST 取字面量，不 exec 模块。"""

    class _Step:
        pass

    import ast as _ast

    def _eval(node: Any) -> Any:
        """literal_eval 外再支持 dict(...) 调用形式（生成器产出惯用 dict()）。"""
        if isinstance(node, _ast.Call) and isinstance(node.func, _ast.Name) \
                and node.func.id == "dict" and not node.args:
            return {kw.arg: _eval(kw.value) for kw in node.keywords if kw.arg}
        if isinstance(node, _ast.List):
            return [_eval(e) for e in node.elts]
        return _ast.literal_eval(node)

    tree = _ast.parse((STEPS_DIR / f"{module_attr}.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, _ast.Assign) and len(node.targets) == 1:
            tgt = node.targets[0]
            name = tgt.id if isinstance(tgt, _ast.Name) else None
            if name in ("SOURCES", "_PROP_TYPES"):
                try:
                    setattr(_Step, name, _eval(node.value))
                except ValueError:
                    pass
    return _Step


def _find_schema(session: Session, *, kind: str, name: str, graph_space: str) -> str | None:
    return session.execute(
        text(
            "SELECT id FROM kg_schema_definition "
            "WHERE kind = :k AND name = :n AND graph_space = :g AND is_deleted = 0 LIMIT 1"
        ),
        {"k": kind, "n": name, "g": graph_space},
    ).scalar()


def _resolve_datasource(session: Session, explicit: str | None) -> tuple[str, dict[str, Any]]:
    from db_model.mysql_datasource import MysqlDatasource

    if explicit:
        row = session.get(MysqlDatasource, explicit)
        if row is None:
            raise SystemExit(f"指定数据源不存在: {explicit}")
    else:
        row = session.query(MysqlDatasource).filter(MysqlDatasource.is_default.is_(True)).first()
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


def _validate_source(params: dict[str, Any], database: str, source: dict[str, Any]) -> bool:
    """query_sql 用 LIMIT 0 试跑；普通表查 information_schema。"""
    from urllib.parse import quote_plus

    url = (
        f"mysql+pymysql://{params['username']}:{quote_plus(params['password'])}"
        f"@{params['host']}:{params['port']}/{database}?charset=utf8mb4"
    )
    engine = create_engine(url)
    try:
        with engine.connect() as conn:
            if source.get("query_sql"):
                conn.execute(text(f"SELECT * FROM ({source['query_sql']}) AS _src LIMIT 0"))
            else:
                rows = conn.execute(
                    text(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_schema = :db AND table_name = :t LIMIT 1"
                    ),
                    {"db": database, "t": source["table"]},
                ).fetchall()
                if not rows:
                    logger.warning("表 %s 在库 %s 中不存在", source["table"], database)
                    return False
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("来源校验失败 %s: %s", source.get("table") or "query_sql", exc)
        return False
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user", default="platform-admin")
    parser.add_argument("--datasource-id", default=None)
    parser.add_argument("--database", default="gkx_kg_sm")
    parser.add_argument("--graph-space", default="gkx_kg_sm")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    from infra.mysql import session_scope
    from service.schema_management import SchemaManagementService

    created = bound = skipped = 0
    with session_scope() as session:
        service = SchemaManagementService(session)
        datasource_id, ds_params = _resolve_datasource(session, args.datasource_id)
        logger.info(
            "数据源 %s → 库 %s → 图空间 %s", datasource_id, args.database, args.graph_space
        )
        schema_ids: dict[str, str] = {}

        for ent in ENTITIES:
            tag = ent["tag"]
            step = _load_step(f"entity_{tag}")
            source = dict(table=ent["table"], pk=ent["pk"], time="")
            schema_id = _find_schema(
                session, kind="entity", name=tag, graph_space=args.graph_space
            )
            if schema_id is None:
                props = [
                    {"name": "id", "data_type": "string", "required": True, "rule": "", "category": "core"},
                    {"name": "name", "data_type": "string", "required": False, "rule": "", "category": "core"},
                ] + [
                    {"name": col, "data_type": typ, "required": False, "rule": "", "category": "core"}
                    for col, typ in ent["cols"]
                    if col not in ("id", "name")
                ]
                payload = {
                    "schema_key": f"{tag.lower()}-{uuid4().hex[:6]}",
                    "name": tag,
                    "label": ent["label"],
                    "description": f"{ent['label']}实体（gkx_kg_sm.{ent['table']} 一表直抽 → {args.graph_space}）",
                    "identity_key": "id",
                    "mappings": [],
                    "version": "v1.0",
                    "is_core": False,
                    "graph_space": args.graph_space,
                    "properties": props,
                }
                if args.dry_run:
                    logger.info("[dry-run] 将创建实体 %s（%d 属性）← %s", tag, len(props), ent["table"])
                    continue
                schema_id = service.create_entity(payload=payload, user_id=args.user)["id"]
                created += 1
            schema_ids[tag] = schema_id
            if not _validate_source(ds_params, args.database, source):
                skipped += 1
                continue
            if args.dry_run:
                logger.info("[dry-run] 绑定实体 %s ← %s（脚本 entity_%s.py）", tag, ent["table"], tag)
                continue
            step_file = STEPS_DIR / f"entity_{tag}.py"
            service.replace_script(
                schema_id=schema_id, user_id=args.user, filename=step_file.name,
                content_type="text/x-python", script_data=step_file.read_bytes(),
                is_platform_admin=True,
            )
            service.replace_sources(
                schema_id=schema_id,
                sources=[{
                    "datasource_id": datasource_id,
                    "database_name": args.database,
                    "table_name": source["table"],
                    "pk_column": source["pk"],
                    "time_column": source["time"],
                    "query_sql": None,
                }],
                user_id=args.user, is_platform_admin=True,
            )
            bound += 1
            logger.info("实体 %s 绑定完成 ← %s", tag, ent["table"])

        for rel in RELATIONS:
            edge = rel["edge"]
            step = _load_step(f"relation_{edge}")
            source = step.SOURCES[0]
            schema_id = _find_schema(
                session, kind="relation", name=edge, graph_space=args.graph_space
            )
            if schema_id is None:
                src_id = schema_ids.get(rel["src"]) or _find_schema(
                    session, kind="entity", name=rel["src"], graph_space=args.graph_space
                )
                dst_id = schema_ids.get(rel["dst"]) or _find_schema(
                    session, kind="entity", name=rel["dst"], graph_space=args.graph_space
                )
                if not src_id or not dst_id:
                    logger.warning("跳过 %s：端点实体缺失 %s/%s", edge, rel["src"], rel["dst"])
                    skipped += 1
                    continue
                prop_types = getattr(step, "_PROP_TYPES", {}) or {}
                props = [
                    {"name": "confidence", "data_type": "double", "required": False, "rule": "", "category": "core"},
                ] + [
                    {"name": k, "data_type": _PY_TO_NEBULA.get(t, "string"), "required": False, "rule": "", "category": "core"}
                    for k, t in prop_types.items() if k != "confidence"
                ]
                payload = {
                    "schema_key": f"{edge.lower().replace('_', '-')}-{uuid4().hex[:6]}",
                    "name": edge,
                    "label": rel["label"],
                    "description": f"{rel['label']}（gkx_kg_sm.sm_edge 直抽 → {args.graph_space}）",
                    "identity_key": "",
                    "mappings": [],
                    "version": "v1.0",
                    "is_core": False,
                    "graph_space": args.graph_space,
                    "properties": props,
                    "source_schema_id": src_id,
                    "target_schema_id": dst_id,
                }
                if args.dry_run:
                    logger.info("[dry-run] 将创建关系 %s %s→%s（%d 属性）", edge, rel["src"], rel["dst"], len(props))
                    continue
                schema_id = service.create_relation(payload=payload, user_id=args.user)["id"]
                created += 1
            if not _validate_source(ds_params, args.database, source):
                skipped += 1
                continue
            if args.dry_run:
                logger.info("[dry-run] 绑定关系 %s ← kg_edge query_sql", edge)
                continue
            step_file = STEPS_DIR / f"relation_{edge}.py"
            service.replace_script(
                schema_id=schema_id, user_id=args.user, filename=step_file.name,
                content_type="text/x-python", script_data=step_file.read_bytes(),
                is_platform_admin=True,
            )
            service.replace_sources(
                schema_id=schema_id,
                sources=[{
                    "datasource_id": datasource_id,
                    "database_name": args.database,
                    "table_name": source["table"],
                    "pk_column": source["pk"],
                    "time_column": source.get("time") or "",
                    "query_sql": source.get("query_sql"),
                }],
                user_id=args.user, is_platform_admin=True,
            )
            bound += 1
            logger.info("关系 %s 绑定完成 ← kg_edge", edge)

    logger.info("完成：新建 %d，绑定 %d，跳过 %d", created, bound, skipped)


if __name__ == "__main__":
    main()
