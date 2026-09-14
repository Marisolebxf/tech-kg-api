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

## CLI 入口（旧 ETL 脚本）

`run_*_extractor` 家族是旧按域大批 ETL 的主流程（与平台抽取双轨并存，作回退手段保留）。每个脚本是可独立调试的 CLI，约定 `build_sources(vars(args))` 把「参数 → sources」的决策收成一份：

```python
def build_sources(payload: dict):
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
```

> 旧脚本被 `kg.custom.python` 子进程加载的 `workflow(payload)` 入口已随该通道下线（2026-09-14 D2）；平台通道的脚本入口是 `transform(payload)`（平台分批送 `rows`，见下节示例）。

通用 CLI 7 参数（`build_parser`）：`--log-level` / `--database` / `--batch-size` / `--limit` / `--since` / `--dry-run` / `--ingest-batch`。

## 完整示例：论文实体 transform 脚本

在 **Schema 管理页**上传（唯一入口；LLM 安全校验通过后存 S3），绑定来源表后由 `kg.schema.extract` 执行——平台分批送 `rows`，脚本只做转换，落图 / 消歧 / 索引 / 水位全部由平台收尾：

```python
"""论文实体抽取：源行 → Paper 实体。"""
import json


def transform(payload):
    """只做转换：输入平台分批送来的 rows，输出 entities/failures。"""
    from kg_sdk import current_context

    ctx = current_context()  # mysql 默认回退来源绑定数据源；llm 未选为 None
    entities, failures = [], []
    for row in payload["rows"]:
        try:
            entities.append({
                "id": row["paper_id"],
                "props": {"title": row["title"], "abstract": row.get("abstract", "")},
            })
        except Exception as exc:  # 逐行失败 → T_EXTRACT_FAIL 审核 case，可点重跑
            failures.append({"recordId": str(row.get("paper_id")), "error": str(exc)})
    # 可选 pendingReview：低置信/消歧候选 → 审核队列（可带 templateId=T_LINK）
    return {"entities": entities, "failures": failures}
```

上传与执行闭环：Schema 管理上传脚本（语法 + 入口检查 + LLM 安全校验）→ 绑定来源表（复杂 SQL 走 `query_sql`）→ 触发抽取。平台按来源水位分批读源、隔离子进程跑 `transform`、实体 nGQL `INSERT VERTEX` 入库、入口消歧、重建索引（失败降级不拖垮抽取）、来源全部批次成功后一次性推水位。
