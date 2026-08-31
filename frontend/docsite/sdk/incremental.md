# 数据读取与增量水位

> 来源：`backend/docs/kg_sdk.md` §3-4 · `docs/script-sdk/reading.html` · `backend/script/entity_extractors_one_entity/common.py`

## watermark 增量水位

`ctx.config.watermark` 记录上次成功运行时间。平台在 step **成功返回后**自动写入本次水位（默认 = 当前时间）。脚本可以在返回 dict 里带 `_watermark` / `_checkpoint` 覆盖默认值——例如用本批数据的最大 `updated_at` 做水位，下次只跑增量。

```python
def step_load(payload, ctx):
    sql = "SELECT id, name, updated_at FROM paper WHERE updated_at > :wm ORDER BY updated_at"
    with ctx.mysql.session_scope() as s:
        result = s.execute(text(sql), {"wm": ctx.config.watermark or "1970-01-01"})
        rows = [dict(r._mapping) for r in result]
    # 用本批最大 updated_at 做下次水位；空批显式回传旧值 → 水位不前进
    max_ts = max((r["updated_at"] for r in rows), default=None)
    return {
        "count": len(rows),
        "items": rows,
        "_watermark": max_ts.isoformat() if max_ts else ctx.config.watermark,
    }
```

规则要点：

- 平台写水位用 `_watermark`（ISO 字符串，解析失败回退 `now()`）和 `_checkpoint`（任意 JSON，如 `{"last_id": 12345}`）。
- 这两个字段会从 step 输出里**剥离**，不会出现在任务详情页的 step 结果里。
- step 失败/超时**不写水位**——reset 后重读上次成功水位，重处理同一窗口，幂等。
- 不同 step 各有独立水位（按 `(definition_id, step_id)` 索引）。

## prev_outputs 多步链式

`kg.custom.steps` 里前一步返回的 dict 自动作为后一步 `ctx.prev_outputs[step_id]`：

```python
def step_extract(payload, ctx):
    papers = ctx.prev_outputs.get("load", {}).get("items", [])
    extracted = [extract_entities(p["name"], ctx) for p in papers]
    return {"items": extracted}


def step_persist(payload, ctx):
    for rec in ctx.prev_outputs.get("extract", {}).get("items", []):
        ctx.graph.merge_node(["Paper"], {"vid": rec["paper_id"]})
    return {"persisted": len(rec)}
```

## iter_rows：大表安全读取

```python
iter_rows(engine, sql, *, batch_size, limit=None, cursor_column=None, params=None)
    -> Iterable[dict[str, Any]]
```

分页读取，逐行 yield `dict(row)`：

- **默认 LIMIT/OFFSET 模式**：框架自动在 SQL 后拼 `LIMIT :limit OFFSET :offset`，每页一个独立连接（避免长事务）。源 SQL 一律**显式 `ORDER BY` 主键或唯一列**——不带排序的分页在 InnoDB 并发写入时不保证无重复/无遗漏。
- **keyset 游标模式**：指定 `cursor_column` 切换。要求 SQL 含 `:cursor` 绑定参数并按该列唯一排序，框架以每页末行的列值作为下一页游标。大表深分页（专利域）用它。

```python
# OFFSET 模式（中小表）
for row in iter_rows(engine, SQL, batch_size=500, limit=1000, params={"status": 1}):
    process(row)

# keyset 模式（大表深分页）
SQL = """
SELECT p.* FROM dwd_patent p
WHERE CAST(p.id AS UNSIGNED) > :cursor
ORDER BY CAST(p.id AS UNSIGNED)
"""
for row in iter_rows(engine, SQL, batch_size=500, cursor_column="id"):
    process(row)
```

`ctx` 场景下用 `iter_rows(ctx.mysql.engine, ...)`——连接参数由 activity 注入，不要用 env 驱动的 `mysql_engine()`。

## apply_since：增量条件注入

```python
apply_since(sql, since, col="updated_time") -> str
```

把 `col > :since` 注入源 SQL，自动处理三种形态：

```python
apply_since("SELECT * FROM t", "2026-08-01")
# SELECT * FROM t WHERE updated_time > :since

apply_since("SELECT * FROM t WHERE status = 1", "2026-08-01")
# ... WHERE status = 1 AND updated_time > :since   ← ORDER BY 保持末位
```

配合 `iter_rows` 时把绑定值传进 `params`：

```python
sql = apply_since(SQL, since)
rows = iter_rows(engine, sql, batch_size=500, params={"since": since} if since else None)
```

## 推荐的增量闭环

```python
def workflow(payload: dict) -> dict:
    # ① 优先级：显式 payload > 上次成功运行的水位
    ctx = current_context()
    since = payload.get("since")
    if ctx and ctx.config.watermark:
        since = since or ctx.config.watermark
    # ② 增量跑（主流程函数自动 apply_since + 注入 :since 绑定）
    summary = run_entity_extractor(..., since=since, sources=sources)
    # ③ 报告本次最大更新时间，供框架写回水位
    summary["watermark"] = max_source_update_time(summary)
    return summary
```

首次运行传 `since=None` 即全量。
