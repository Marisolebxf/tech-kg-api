"""学者域图谱 schema 初始化（幂等；目标图空间由参数/环境变量决定）。

与 ``init_project_schema.py`` / ``init_paper_journal_schema.py`` 的区别：本脚本
**不硬编码空间名**，从 ``--space`` 或 ``TRS_GRAPH_SPACE`` 取，因此可以先在
``test`` 等隔离空间上验证再动 ``dev``。

覆盖范围（与学者域脚本实际写入的属性集一一对齐）：
  - Tag  ``Person``          ← ``load_scholar_entities.py``
  - Edge ``AFFILIATED_WITH`` ← ``load_scholar_relations.py``
  - Edge ``COAUTHOR_WITH``   ← ``load_scholar_relations.py``
  - Edge ``STUDIED_AT``      ← ``load_scholar_relations.py``（校友邻域）
  - Edge ``SAME_AS``         ← ``align_scholar_affiliations.py`` / ``dedupe_scholar_persons.py``

属性集必须是并集：trs-graph 的 merge 接口不接收 schema 之外的属性，缺一个字段
整条顶点/边就 400，所以这里把四类对象需要写的属性全部列出。

对已有空间（如 ``dev``，``Person`` 可能已被其它领域建成更窄的 schema）只做
``ALTER ... ADD`` 补列，**从不删列、不改类型**；已存在但类型不符的列会被报告并跳过，
需要人工决定。

用法::

    cd backend

    # 只看会执行什么，不动图
    TRS_GRAPH_SPACE=test uv run python -m script.init_scholar_schema --dry-run

    # 在已存在的空间上建/补 schema
    uv run python -m script.init_scholar_schema --space test

    # 空间也不存在时，顺带建空间（CREATE SPACE 需要一个已存在的空间作为执行上下文）
    uv run python -m script.init_scholar_schema --space scholar_test --create-space
"""

from __future__ import annotations

import argparse
import os
import time

from infra.graph_db import TRSGraphClient
from infra.graph_db.config import TRSGraphSettings

# ---------------------------------------------------------------------------
# 属性集（字段名与类型须与 script/load_scholar_*.py 写入的 props 完全一致）
# ---------------------------------------------------------------------------
_PROVENANCE: list[tuple[str, str]] = [
    ("source_table", "string"),
    ("source_record_id", "string"),
    ("ingest_batch", "string"),
    ("ingest_time", "string"),
]

# script/scholar_provenance.py: confidence_props()
_CONFIDENCE: list[tuple[str, str]] = [
    ("confidence", "double"),
    ("match_method", "string"),
    ("match_evidence", "string"),
]

# script/scholar_provenance.py: organization_provenance()
_ORG_PROVENANCE: list[tuple[str, str]] = [
    ("organization_base", "string"),
    ("organization_id", "string"),
]

# load_scholar_entities.py: _build_person_props()
PERSON_PROPS: list[tuple[str, str]] = [
    ("name_zh", "string"),
    ("name_en", "string"),
    ("email", "string"),
    ("source", "string"),
    ("avatar", "string"),
    ("scholar_org", "string"),
    ("bio_zh", "string"),
    ("biography", "string"),
    ("paper_nums", "int64"),
    ("citation_nums", "int64"),
    ("h_index", "int64"),
    ("scholar_status", "int64"),
    ("is_academician", "string"),
    ("research_fields", "string"),
    ("work_experience_date", "string"),
    ("work_experience_institution_zh", "string"),
    ("work_experience_department_zh", "string"),
    ("work_experience_position_zh", "string"),
    ("work_experience_institution_en", "string"),
    ("work_experience_department_en", "string"),
    ("work_experience_position_en", "string"),
    ("education_background_date", "string"),
    ("education_background_institution_zh", "string"),
    ("education_background_degree_zh", "string"),
    ("education_background_institution_en", "string"),
    ("education_background_degree_en", "string"),
    ("source_system", "string"),
    ("source_url", "string"),
    ("source_update_time", "string"),
    *_ORG_PROVENANCE,
    *_CONFIDENCE,
    *_PROVENANCE,
]

# load_scholar_relations.py: load_affiliations()
AFFILIATED_WITH_PROPS: list[tuple[str, str]] = [
    ("affiliation_name", "string"),
    ("work_experience_date", "string"),
    ("work_experience_department_zh", "string"),
    ("work_experience_position_zh", "string"),
    ("source", "string"),
    *_ORG_PROVENANCE,
    *_CONFIDENCE,
    *_PROVENANCE,
]

# load_scholar_relations.py: load_coauthors()
COAUTHOR_WITH_PROPS: list[tuple[str, str]] = [
    ("co_paper_count", "int64"),
    *_CONFIDENCE,
    *_PROVENANCE,
]

# load_scholar_relations.py: load_studied_at() — Person → Organization
STUDIED_AT_PROPS: list[tuple[str, str]] = [
    ("degree_zh", "string"),
    ("degree_en", "string"),
    ("education_date", "string"),
    ("institution_zh", "string"),
    ("institution_en", "string"),
    ("source_system", "string"),
    *_CONFIDENCE,
    *_PROVENANCE,
]

# align_scholar_affiliations.py + dedupe_scholar_persons.py
SAME_AS_PROPS: list[tuple[str, str]] = [
    ("match_score", "double"),
    ("match_source", "string"),
    ("orphan_name", "string"),
    ("canonical_name", "string"),
    ("signal_name", "double"),
    ("signal_org", "double"),
    ("signal_fields", "double"),
    ("signal_milvus", "double"),
    *_ORG_PROVENANCE,
    *_CONFIDENCE,
    *_PROVENANCE,
]

TAGS: dict[str, list[tuple[str, str]]] = {"Person": PERSON_PROPS}
EDGES: dict[str, list[tuple[str, str]]] = {
    "AFFILIATED_WITH": AFFILIATED_WITH_PROPS,
    "COAUTHOR_WITH": COAUTHOR_WITH_PROPS,
    "STUDIED_AT": STUDIED_AT_PROPS,
    "SAME_AS": SAME_AS_PROPS,
}

# 无属性 tag 索引：`MATCH (n:Person)` / `LOOKUP ON Person` 没有索引会退化成全空间
# ScanVertices（dev 上 count 一次要几百秒）。已有数据的空间建完索引还需
# `REBUILD TAG INDEX person_tag_idx;` 才能生效。
# 院校属性索引：校友 LOOKUP 兜底（ETL 未写 STUDIED_AT 时按院校缩小候选）。
INDEX_DDL: list[str] = [
    "CREATE TAG INDEX IF NOT EXISTS person_tag_idx ON Person();",
    "CREATE TAG INDEX IF NOT EXISTS person_edu_inst_zh_idx ON Person(education_background_institution_zh(256));",
    "CREATE TAG INDEX IF NOT EXISTS person_edu_inst_en_idx ON Person(education_background_institution_en(256));",
]

SCHEMA_PROPAGATION_WAIT = 15


def _create_ddl(kind: str, name: str, props: list[tuple[str, str]]) -> str:
    cols = ", ".join(f"{field} {ftype}" for field, ftype in props)
    return f"CREATE {kind} IF NOT EXISTS {name}({cols});"


def _describe(client: TRSGraphClient, kind: str, name: str) -> dict[str, str] | None:
    """返回 {字段名: 类型}；对象不存在时返回 None。"""
    try:
        result = client.execute_read(f"DESCRIBE {kind} {name}")
    except Exception:  # noqa: BLE001 — 不存在时 trs-graph 直接抛错
        return None
    return {str(row["Field"]): str(row["Type"]).lower() for row in result.records}


def _wait_visible(client: TRSGraphClient, kind: str, name: str, expected: set[str]) -> bool:
    """等 schema 传播：Nebula 的 DDL 不是立刻对所有 graphd 可见。"""
    for _ in range(SCHEMA_PROPAGATION_WAIT):
        existing = _describe(client, kind, name)
        if existing is not None and expected.issubset(existing.keys()):
            return True
        time.sleep(1)
    return False


def _sync_object(
    client: TRSGraphClient,
    kind: str,
    name: str,
    props: list[tuple[str, str]],
    *,
    dry_run: bool,
) -> None:
    existing = _describe(client, kind, name)

    if existing is None:
        ddl = _create_ddl(kind, name, props)
        if dry_run:
            print(f"[dry-run] {ddl}")
            return
        client.execute_write(ddl)
        if _wait_visible(client, kind, name, {f for f, _ in props}):
            print(f"created {kind} {name} ({len(props)} props)")
        else:
            print(f"created {kind} {name}，但 {SCHEMA_PROPAGATION_WAIT}s 内未完全可见，请复查")
        return

    missing = [(f, t) for f, t in props if f not in existing]
    conflicts = [
        (f, t, existing[f]) for f, t in props if f in existing and existing[f] != t.lower()
    ]
    for field, wanted, actual in conflicts:
        print(
            f"WARN {kind} {name}.{field}: 期望 {wanted}，实际 {actual}；类型不能 ALTER，需人工处理"
        )

    if not missing:
        print(f"{kind} {name} 已对齐（{len(existing)} props）")
        return

    ddl = f"ALTER {kind} {name} ADD ({', '.join(f'{f} {t}' for f, t in missing)});"
    if dry_run:
        print(f"[dry-run] {ddl}")
        return
    client.execute_write(ddl)
    if _wait_visible(client, kind, name, {f for f, _ in missing}):
        print(f"altered {kind} {name}: +{len(missing)} props")
    else:
        print(f"altered {kind} {name}，但 {SCHEMA_PROPAGATION_WAIT}s 内未完全可见，请复查")


def _create_space(space: str, bootstrap_space: str, *, dry_run: bool) -> None:
    """CREATE SPACE 是全局操作，但仍需一个已存在的空间作为连接上下文。"""
    ddl = (
        f"CREATE SPACE IF NOT EXISTS {space}"
        "(vid_type=FIXED_STRING(64), partition_num=10, replica_factor=1);"
    )
    if dry_run:
        print(f"[dry-run] (in {bootstrap_space}) {ddl}")
        return

    settings = TRSGraphSettings.from_env()
    settings.space = bootstrap_space
    client = TRSGraphClient(settings)
    client.connect()
    try:
        client.execute_write(ddl)
        print(f"ok: {ddl}")
    finally:
        client.close()
    # Nebula 建完空间后需要等一会儿才能 USE
    time.sleep(2)


def init_scholar_schema(
    space: str,
    *,
    create_space: bool,
    bootstrap_space: str,
    dry_run: bool,
) -> None:
    print(f"target space = {space}{' (dry-run)' if dry_run else ''}")

    if create_space:
        _create_space(space, bootstrap_space, dry_run=dry_run)

    settings = TRSGraphSettings.from_env()
    settings.space = space
    client = TRSGraphClient(settings)
    client.connect()
    try:
        for name, props in TAGS.items():
            _sync_object(client, "TAG", name, props, dry_run=dry_run)
        for name, props in EDGES.items():
            _sync_object(client, "EDGE", name, props, dry_run=dry_run)

        for ddl in INDEX_DDL:
            if dry_run:
                print(f"[dry-run] {ddl}")
                continue
            try:
                client.execute_write(ddl)
                print(f"ok: {ddl}")
            except Exception as exc:  # noqa: BLE001 — 索引可能已存在
                print(f"skip index (may already exist): {exc}")
    finally:
        client.close()

    if not dry_run:
        print(
            "提示：若该空间已有 Person 数据，需再执行 `REBUILD TAG INDEX person_tag_idx;` 索引才生效"
        )


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--space",
        default=os.environ.get("TRS_GRAPH_SPACE", "dev"),
        help="目标图空间（默认取 TRS_GRAPH_SPACE，回退 dev）。",
    )
    ap.add_argument(
        "--create-space",
        action="store_true",
        help="目标空间不存在时顺带创建（FIXED_STRING(64), partition 10, replica 1）。",
    )
    ap.add_argument(
        "--bootstrap-space",
        default="dev",
        help="执行 CREATE SPACE 时借用的已存在空间上下文（默认 dev）。",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要执行的 DDL，不改动图。",
    )
    return ap.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    init_scholar_schema(
        args.space,
        create_space=args.create_space,
        bootstrap_space=args.bootstrap_space,
        dry_run=args.dry_run,
    )
