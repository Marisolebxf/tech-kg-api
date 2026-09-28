"""HAS_OUTPUT 关系抽取步（@step 薄适配层，yunfei_test 空间还原专用）。

直接调用老一对一脚本模块的 ``transform(payload)``——抽取逻辑与旧脚本完全
一致（行 → 记录的映射、vid 公式、provenance 均复用老代码），本文件只按
新规范以 @step 声明入口，供平台喂数管道（kg.schema.extract）调度。

宽表例外：dwd_{zh,en}_project_output 的 JSON 产出列均行 20-44KB，随平台
querySql 读取会被包成 ``SELECT * FROM (…) WHERE … ORDER BY … LIMIT``——
JSON 列进派生表 filesort 直接 MySQL 1038（Out of sort memory）。绑定侧只投
窄键列（id + 常量 wm_col），本层按本批 id 回源补齐全部列后整体走老
transform，行集与老 SQL（o.* JOIN 项目表）逐行等价。
"""

from __future__ import annotations

from typing import Any

from kg_sdk import step
from sqlalchemy import text

from script.relation_extractors_one_relation import has_output_relation as legacy
from script.relation_extractors_one_relation.common import mysql_engine

# 回源表白名单（表名来自 source_table，拼 SQL 前固定）
BACKFILL_TABLES = ("dwd_zh_project_output", "dwd_en_project_output")


@step
def emit(payload):
    rows = payload.get("rows") or []
    if rows:
        payload = {**payload, "rows": _backfill(payload.get("source_table"), rows)}
    return legacy.transform(payload)


def _backfill(source_table: Any, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按本批 id 回源补齐宽列（无 ORDER BY 的 IN 点查，不触发 filesort）。"""
    table = str(source_table or "").rsplit(".", 1)[-1]
    if table not in BACKFILL_TABLES:
        return rows
    ids = [str(r["id"]) for r in rows if r.get("id") is not None]
    if not ids:
        return rows
    full: dict[str, dict[str, Any]] = {}
    engine = mysql_engine()
    try:
        for start in range(0, len(ids), 500):
            chunk = ids[start : start + 500]
            placeholders = ", ".join(f":i{n}" for n in range(len(chunk)))
            sql = text(f"SELECT * FROM `{table}` WHERE `id` IN ({placeholders})")
            with engine.connect() as conn:
                for raw in conn.execute(sql, {f"i{n}": v for n, v in enumerate(chunk)}).mappings():
                    full[str(raw["id"])] = dict(raw)
    finally:
        engine.dispose()
    # 平台行序保留；回源缺行按窄行原样透传（老 transform 缺列时跳过该行）
    return [full.get(str(r.get("id")), r) for r in rows]
