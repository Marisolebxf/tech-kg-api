# 数据读取与增量水位

> 来源：`backend/docs/kg_sdk.md` §3-4 · `docs/script-sdk/reading.html` · `backend/script/entity_extractors_one_entity/common.py`

## watermark 增量水位（平台托管）

抽取通道的增量水位**完全由平台管理**，脚本不用管：

- **读源**：`read_source_batch` 按来源绑定游标分批——水位模式 `WHERE time > :wm ORDER BY time, pk`，或 pk keyset 模式（合成唯一 pk）；
- **推进**：该来源**全部批次成功后** `advance_schema_extract_watermark` 一次性推进（watermark 模式写时间；keyset 模式把 pk 游标写进 checkpoint）——并发下逐批推进会留洞，所以收口一次推；
- **失败**：停在上一轮水位，下轮断点续读；执行失败可 `POST /task-center/tasks/{id}/retry` 走 Temporal reset 重放。

脚本返回 dict 里的 `_watermark` / `_checkpoint` 元字段**被忽略**（平台按批次游标管理水位），仍会从输出里剥离、不进任务详情展示。`ctx.config.watermark` 不保证有值（抽取通道不依赖），脚本内查找表等自建增量请自行管理游标。

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

## transform 脚本与增量的关系

平台通道里**脚本不做增量读源**——平台按来源水位分批把 `rows` 送进 `@step` 声明的抽取步（第 1 步消费 `rows`），脚本只做逐批转换。`iter_rows` / `apply_since` 供脚本内自建读取用（如增量加载查找表），或独立 CLI 运行旧 ETL 脚本（回退手段，D5 暂缓）：

```python
def transform(payload: dict) -> dict:
    rows = payload["rows"]  # 平台按来源水位分批送入，无需自行增量
    entities = [mapper(r) for r in rows]
    return {"entities": entities, "failures": []}
```

