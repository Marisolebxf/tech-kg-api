"""图库反向登记：把已存在 TAG/EDGE 但目录未登记的图空间补进 Schema 目录。

背景：数据绕过平台直接 DDL + 导入 Nebula 后，Schema 管理/图谱构建页因目录
（techkg_control.kg_schema_definition）无登记而空白。本脚本对指定图空间：
SHOW TAGS/EDGES → 对比目录 → 未登记类型走 SchemaManagementService.create_*
（DDL 为 CREATE TAG/EDGE IF NOT EXISTS，已有类型幂等跳过）。

中文名（label）取 script/schema_label_map.py 映射，缺失回退英文名并告警——
回填脚本 backfill_schema_labels.py 可在补映射后幂等重补存量。

关系两端类型 Nebula EDGE TYPE 本身不约束，用 MATCH 采样多数表决推断；
采样失败（无边数据/超时）的关系跳过并报告，不猜测。

用法（容器内，PYTHONPATH=/app）：
    python script/register_graph_schemas.py --space gaoxing_test --dry-run
    python script/register_graph_schemas.py --space gaoxing_test --space dev
"""

import argparse
import logging
import os
import re
import sys
from collections import Counter

import httpx

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("register_graph_schemas")

# Nebula 类型 → 平台 SchemaPropertyInput.data_type 白名单
TYPE_MAP = {
    "string": "string",
    "int8": "int64",
    "int16": "int64",
    "int32": "int64",
    "int64": "int64",
    "float": "double",
    "double": "double",
    "bool": "bool",
    "date": "date",
    "datetime": "datetime",
    "timestamp": "datetime",
    "time": "datetime",
    "geography": "geo",
}
# 与 biz/schemas/schema_management.py 的 KEY_PATTERN 一致
KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_-]{0,63}$")

# 端点提示：只有 DDL 没有数据的空类型采样不到两端，按业务语义给定
# （端点口径与图内同类已登记边一致，如 HAS_NEWS 为 organization_base→News）
ENDPOINT_HINTS: dict[str, tuple[str, str]] = {
    "BID_FOR": ("organization_base", "BidNotice"),
    "OUTPUT_OF": ("organization_base", "Project"),
    "PARTICIPATES_IN": ("organization_base", "Project"),
    "SOURCED_FROM": ("News", "DataSource"),
}


def build_client() -> httpx.Client:
    base = os.getenv("TRS_GRAPH_BASE_URL", "http://localhost:8090")
    key = os.getenv("TRS_GRAPH_API_KEY", "")
    return httpx.Client(
        base_url=base,
        headers={"X-API-Key": key, "Content-Type": "application/json"},
        timeout=float(os.getenv("TRS_GRAPH_TIMEOUT", "30")),
    )


def query(client: httpx.Client, space: str, ngql: str) -> list[dict]:
    r = client.post("/api/v1/query", headers={"X-Graph-Space": space}, json={"query": ngql})
    r.raise_for_status()
    body = r.json()
    if body.get("summary", {}).get("errorCode", 0) != 0:
        raise RuntimeError(f"nGQL 失败: {ngql[:80]} -> {str(body)[:200]}")
    return body.get("records", [])


def normalize_key(name: str) -> str:
    """TAG/EDGE 名 → schema_key（小写化；不合法字符替换为 _）。"""
    key = re.sub(r"[^a-z0-9_-]", "_", name.lower())
    if not key or not KEY_PATTERN.fullmatch(key):
        key = "e_" + key if not key or not key[0].isalpha() else key
    return key[:64]


def resolve_label(name: str) -> str:
    """中文名优先（schema_label_map），缺失回退英文名并告警提醒补映射。"""
    from script.schema_label_map import resolve_label as from_map

    label = from_map(name)
    if label == name:
        logger.warning(
            "%s 无中文名映射，label 暂用英文名（补映射后跑 backfill_schema_labels）", name
        )
    return label


def describe_properties(client: httpx.Client, space: str, kind: str, name: str) -> list[dict]:
    rows = query(client, space, f"DESCRIBE {kind} `{name}`;")
    props = []
    for row in rows:
        field, ntype = row.get("Field"), row.get("Type", "string")
        if not field:
            continue
        props.append(
            {
                "name": field,
                "data_type": TYPE_MAP.get(ntype, "string"),
                "required": row.get("Null") == "NO",
                "rule": "",
                "category": "core",
            }
        )
    return props


def sample_edge_endpoints(client: httpx.Client, space: str, edge: str) -> tuple[str, str] | None:
    """MATCH 采样 3 条边，labels 多数表决推断 (source_tag, target_tag)。"""
    try:
        rows = query(
            client,
            space,
            f"MATCH (s)-[e:`{edge}`]->(t) RETURN labels(s) AS st, labels(t) AS tt LIMIT 3",
        )
    except Exception as exc:
        logger.warning("边 %s 两端采样失败: %s", edge, exc)
        return None
    if not rows:
        logger.warning("边 %s 无数据可采样", edge)
        return None
    src = Counter(tuple(r["st"]) for r in rows).most_common(1)[0][0]
    dst = Counter(tuple(r["tt"]) for r in rows).most_common(1)[0][0]
    if not src or not dst:
        return None
    return src[0], dst[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--space", action="append", required=True, help="目标图空间（可多次）")
    parser.add_argument("--dry-run", action="store_true", help="只打印计划不落库")
    args = parser.parse_args()

    from infra.workflow_mysql import workflow_session_scope
    from service.schema_management import SchemaManagementService

    client = build_client()
    exit_code = 0
    for space in args.space:
        logger.info("==== 空间 %s ====", space)
        tags = [r["Name"] for r in query(client, space, "SHOW TAGS;")]
        edges = [r["Name"] for r in query(client, space, "SHOW EDGES;")]
        logger.info("图库: %d TAG / %d EDGE", len(tags), len(edges))

        with workflow_session_scope() as session:
            svc = SchemaManagementService(session)
            dao = svc._dao  # noqa: SLF001 只读复用 dao 的目录查询
            existing = {d.name for d in dao.list_all(graph_space=space)}

            # ---- 实体 ----
            entity_ids: dict[str, str] = {}
            for tag in [t for t in tags if t not in existing]:
                props = describe_properties(client, space, "TAG", tag)
                if args.dry_run:
                    logger.info("[dry-run] 登记 TAG %s（%d 属性）", tag, len(props))
                    continue
                try:
                    result = svc.create_entity(
                        payload={
                            "schema_key": normalize_key(tag),
                            "name": tag,
                            "label": resolve_label(tag),
                            "description": f"反向登记自图库 {space} 空间已有 TAG（{space}.`{tag}`）",
                            "properties": props,
                            "mappings": [],
                            "identity_key": "",
                            "version": "v1.0",
                            "is_core": False,
                            "graph_space": space,
                        },
                        user_id="script:register_graph_schemas",
                    )
                    entity_ids[tag] = result["id"]
                    logger.info("✓ TAG %s -> schema %s", tag, result["id"])
                except Exception as exc:
                    logger.error("✗ TAG %s 登记失败: %s", tag, exc)
                    exit_code = 1
            for tag in [t for t in tags if t in existing]:
                logger.info("跳过已登记 TAG %s", tag)

            # ---- 关系 ----（实体 id 以目录为准：新登记 + 原有）
            if not args.dry_run:
                for d in dao.list_all(graph_space=space):
                    if d.kind == "entity":
                        entity_ids.setdefault(d.name, d.id)

            for edge in [e for e in edges if e not in existing]:
                endpoints = sample_edge_endpoints(client, space, edge)
                if endpoints is None and edge in ENDPOINT_HINTS:
                    endpoints = ENDPOINT_HINTS[edge]
                    logger.info("边 %s 无数据可采样，采用端点提示 %s", edge, endpoints)
                if endpoints is None:
                    logger.error("✗ EDGE %s 无法推断两端（跳过，需手动登记）", edge)
                    exit_code = 1
                    continue
                src_tag, dst_tag = endpoints
                props = describe_properties(client, space, "EDGE", edge)
                if args.dry_run:
                    logger.info(
                        "[dry-run] 登记 EDGE %s: %s -> %s（%d 属性）",
                        edge,
                        src_tag,
                        dst_tag,
                        len(props),
                    )
                    continue
                src_id, dst_id = entity_ids.get(src_tag), entity_ids.get(dst_tag)
                if not src_id or not dst_id:
                    logger.error("✗ EDGE %s 端点 %s->%s 未在目录（跳过）", edge, src_tag, dst_tag)
                    exit_code = 1
                    continue
                try:
                    result = svc.create_relation(
                        payload={
                            "schema_key": normalize_key(edge),
                            "name": edge,
                            "label": resolve_label(edge),
                            "description": (
                                f"反向登记自图库 {space} 空间已有 EDGE（{space}.`{edge}`），"
                                "两端由数据采样推断"
                            ),
                            "properties": props,
                            "mappings": [],
                            "identity_key": "",
                            "version": "v1.0",
                            "is_core": False,
                            "source_schema_id": src_id,
                            "target_schema_id": dst_id,
                            "relation_category": "fact",
                            "graph_space": space,
                        },
                        user_id="script:register_graph_schemas",
                    )
                    logger.info(
                        "✓ EDGE %s: %s -> %s -> schema %s", edge, src_tag, dst_tag, result["id"]
                    )
                except Exception as exc:
                    logger.error("✗ EDGE %s 登记失败: %s", edge, exc)
                    exit_code = 1
            for edge in [e for e in edges if e in existing]:
                logger.info("跳过已登记 EDGE %s", edge)

    client.close()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
