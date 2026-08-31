# 抽取主流程与双入口

> 来源：`docs/script-sdk/runners.html` · `docs/script-sdk/examples.html` · `backend/docs/kg_sdk.md` §8

`run_entity_extractor` / `run_relation_extractor`——你只写 SQL 和 mapper，循环、容错、统计全部内置。

## 主流程函数

```python
run_entity_extractor(*, database, batch_size, limit, dry_run, ingest_batch,
                     sources: list[tuple[table, sql, mapper]],
                     since=None, global_limit=False, dedupe=None,
                     cursor_column=None, extra_params=None) -> dict

run_relation_extractor(*, database, batch_size, limit, dry_run, ingest_batch,
                       sources, since=None, dedupe=None,
                       cursor_column=None, extra_params=None) -> dict
```

内置的完整循环（两个函数结构对称）：

```text
for table, sql, mapper in sources:      # ① 逐源
    sql = apply_since(sql, since)       # ② 增量注入
    for row in iter_rows(engine, sql):  # ③ 分页
        try:
            mapped = mapper(table, row, batch_id)   # ④ 行级容错
        except Exception:
            stats["invalid"] += 1; log.warning(exc_info=True); continue
        ...dedupe / 攒批...             # ⑤ batch_size 攒批写入
# ⑥ finally: engine.dispose()；返回 summary dict
```

| 参数 | 语义 |
|---|---|
| `since` | 对每个源 SQL 注入 `updated_time > :since`（自动处理 ORDER BY 位置） |
| `limit` | 单源行数上限；实体版配 `global_limit=True` 时跨源全局生效 |
| `dedupe="first"` | 实体：同一 VID 首条胜出；关系：同一 `(type, src, dst)` 首条胜出 |
| `cursor_column` | keyset 游标分页列（旧专利脚本口径，如 `"id"`） |
| `extra_params` | 附加 SQL 绑定参数（如 `:table_suffix`） |
| `ingest_batch` | 缺省自动生成 `ENTITY_/RELATION_` + UTC 时间戳 |

## sources 声明

`sources` 是 `(表名, SQL, mapper)` 三元组列表。表名同时用作溯源的 `source_table` 与 summary 的 key——**用真实表名，不要用别名**：

```python
sources = [
    ("dwd_zh_author", "SELECT * FROM dwd_zh_author ORDER BY paper_id, author_id", authored_by),
    ("dwd_en_author", "SELECT * FROM dwd_en_author ORDER BY paper_id, author_id", authored_by),
]
```

机构域多表共享一个 mapper 时可表驱动生成（表目录在 `org_catalog.py`）。

## summary 统计口径

```json
{
  "ingest_batch": "RELATION_20260828T093000Z",
  "sources": {
    "dwd_zh_author": {
      "scanned": 12000,    // 读到的源行数
      "valid": 11800,      // mapper 产出的记录数（含缺主键跳过）
      "written": 11500,    // 实际写图（rank 通道含 merge 更新）
      "updated": 0,        // 实体 merge 保护命中的更新数（关系版无此键）
      "invalid": 12,       // mapper 抛异常的行数
      "missing_source": 280,  // 关系版：端点验存起点缺失
      "missing_target": 8     // 关系版：端点验存终点缺失
    }
  }
}
```

**invalid 与 missing 的区别**：`invalid` = mapper 抛异常（代码 bug 或极端脏数据，看 warning 日志定位）；`missing_*` = 记录合法但端点不在图里（多半是实体脚本没先跑，属于编排问题）。两者都不中断运行——任务结束看 summary 决定是否补跑。

## 双入口模式：CLI + Temporal

每个脚本同时是（1）可独立调试的 CLI（2）被 Temporal activity 子进程加载的 workflow 函数。约定用 `build_sources(payload)` 把「参数 → sources」的决策收成一份，两个入口共享：

```python
def build_sources(payload: dict):
    # payload 既来自 vars(args)（CLI），也来自 Temporal 注入 —— 同形态
    table_choice = payload.get("table", "all")
    tables = TABLES if table_choice == "all" else (table_choice,)
    return [(t, f"SELECT * FROM {t} ORDER BY id", my_mapper) for t in tables]


def main() -> None:                      # CLI 入口
    parser = build_parser(__doc__ or "")  # 通用 7 参数 + 脚本专属参数
    parser.add_argument("--table", choices=("all", *TABLES), default="all")
    args = parser.parse_args()
    configure_logging(args.log_level)
    sources = build_sources(vars(args))   # vars(args) 就是 payload
    print_json(run_relation_extractor(..., sources=sources))


def workflow(payload: dict) -> dict:      # Temporal 入口
    common = common_args_from_payload(payload)  # argparse 的 dict 化镜像
    configure_logging(common["log_level"])
    sources = build_sources(payload)
    return run_relation_extractor(**common, sources=sources)
```

通用 CLI 7 参数（`build_parser`）：`--log-level` / `--database` / `--batch-size` / `--limit` / `--since` / `--dry-run` / `--ingest-batch`。

## 完整示例：4-step 论文流水线

上传到 `POST /workflow-system/definitions/steps`（附 step manifest）：增量加载 → LLM 抽取 → 向量化 → 落图。

```python
"""论文实体流水线：增量加载 → LLM 抽取 → 向量化 → 落图。"""
import json
from sqlalchemy import text


def step_load(payload, ctx):
    """增量加载：只取 watermark 之后的论文。"""
    with ctx.mysql.session_scope() as s:
        rows = s.execute(
            text("SELECT id, title, abstract, updated_at FROM paper "
                 "WHERE updated_at > :wm ORDER BY updated_at LIMIT :n"),
            {"wm": ctx.config.watermark or "1970-01-01",
             "n": payload.get("max_records", 500)},
        ).fetchall()
    items = [{"id": r.id, "title": r.title, "abstract": r.abstract,
              "updated_at": r.updated_at} for r in rows]
    max_ts = max((r["updated_at"] for r in items), default=None)
    return {"items": items,
            "_watermark": max_ts.isoformat() if max_ts else ctx.config.watermark}


def step_extract(payload, ctx):
    """LLM 抽取实体（未配 LLM 则降级为空）。"""
    items = ctx.prev_outputs.get("load", {}).get("items", [])
    out = []
    for p in items:
        raw = ctx.llm.synthesize(
            f"从论文标题抽取关键实体，返回 JSON 数组：\n{p['title']}"
        ) if ctx.llm else None
        out.append({"paper_id": p["id"], "entities": json.loads(raw) if raw else []})
    return {"items": out}


def step_embed(payload, ctx):
    """向量化并写 Milvus（未配则跳过）。"""
    items = ctx.prev_outputs.get("extract", {}).get("items", [])
    if ctx.embedding is None or ctx.milvus is None:
        return {"embedded": 0, "skipped": True}
    vecs = ctx.embedding.embed([i["paper_id"] for i in items]) or []
    records = [{"vid": i["paper_id"], "dense_vector": v}
               for i, v in zip(items, vecs)]
    if records:
        ctx.milvus.upsert("paper", records)
    return {"embedded": len(records)}


def step_persist(payload, ctx):
    """落图：merge Paper 节点。"""
    items = ctx.prev_outputs.get("extract", {}).get("items", [])
    for p in items:
        ctx.graph.merge_node(["Paper"], {"vid": p["paper_id"],
                                         "title": p.get("title", "")})
    return {"persisted": len(items)}
```

manifest（上传时 `steps` 表单字段，JSON 编码）：

```json
[
  {"id": "load",    "name": "增量加载", "functionName": "step_load",    "timeoutSeconds": 600,  "retryPolicy": {"maximumAttempts": 3}},
  {"id": "extract", "name": "LLM 抽取", "functionName": "step_extract", "timeoutSeconds": 1200, "retryPolicy": {"maximumAttempts": 3}},
  {"id": "embed",   "name": "向量化",   "functionName": "step_embed",   "timeoutSeconds": 600,  "retryPolicy": {"maximumAttempts": 2}},
  {"id": "persist", "name": "落图",     "functionName": "step_persist", "timeoutSeconds": 1800, "retryPolicy": {"maximumAttempts": 1}}
]
```

触发后：每步成功，平台自动写 `(paper-pipeline, load)` 等水位；下次只增量加载 `updated_at > 上次水位` 的论文。失败步走 `POST /task-center/tasks/{id}/retry` reset，已完成步靠 Temporal event history replay 不重跑，失败步重读上次成功水位重处理同一窗口。
