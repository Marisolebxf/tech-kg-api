# 抽取脚本 SDK（`kg_sdk`）

> 本文档的在线版本在平台文档中心（部署后访问 `/docs/sdk/`，VitePress，源 `frontend/docsite/sdk/`）。
> 面向在平台上编写"实体/关系抽取脚本"的开发者。脚本运行时由平台注入一个 `Context` 对象，
> 里面提供已配置好的 MySQL / trs-graph / Milvus / LLM / embedding 客户端，以及一个带
> `watermark`（上次成功运行时间）的 `config`，支撑增量抽取。

## 1. 概览

平台支持两种用户脚本：

| 工作流类型 | 脚本签名 | Context 入口 |
|---|---|---|
| `kg.custom.steps`（多步流水线，推荐） | `def step_xxx(payload: dict, ctx: Context) -> dict` | `ctx` 已被平台包装成 `Context`，直接用 `ctx.mysql` 等 |
| `kg.custom.python`（单函数，旧） | `def workflow(payload: dict) -> dict` | `from kg_sdk import current_context; ctx = current_context()` |

`Context` 里的客户端是**懒构造**的——第一次访问 `.mysql` / `.graph` / `.milvus` / `.llm` / `.embedding` 时才建连，并缓存。

**降级约定**：触发任务时如果没有选某个资源（数据源/图空间/Milvus/LLM/embedding），对应的属性返回 `None`，**不抛异常**。脚本务必 `if ctx.llm:` 判空后再用——这与 `infra.llm.get_llm_client()` 既有约定一致。一条脚本里同时用数据库、LLM、向量库做"抽取→对齐→落库"非常常见。

`Context` 由平台在 worker 子进程外解析好"连接参数"（不是活对象，无法跨进程 pickle），序列化进 `KG_SCRIPT_CTX` 环境变量；`kg_sdk.Context` 据此按需构造客户端。密钥经 env 传递，安全面与脚本本就能读到的 `MYSQL_PASSWORD` 等 `sub_env` 一致。

## 2. `Context` API

```python
from kg_sdk import Context, current_context
```

### 客户端属性（懒构造，未配置返回 `None`）

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.mysql` | `infra.mysql.MySQLClient \| None` | 触发时所选 MySQL 数据源 + 库；未选则 `None`。可用 `.create_session()` / `.session_scope()` |
| `ctx.graph` | `infra.graph_db.TRSGraphClient \| None` | 触发时所选图空间；构造时已 `connect()`。未选则 `None` |
| `ctx.milvus` | `pymilvus.MilvusClient \| None` | 触发时所选 Milvus 配置 + 库；未选则 `None` |
| `ctx.llm` | `infra.llm.LLMClient \| None` | 触发时所选 LLM（OpenAI 兼容，chat）；未选或缺 key 则 `None`。`.synthesize(prompt)` 返回 `str \| None` |
| `ctx.embedding` | `infra.llm.EmbeddingClient \| None` | 触发时所选 embedding 模型；未选或缺 key 则 `None`。`.embed(texts)` / `.embed_one(text)` |

### 增量游标与元数据

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.config.watermark` | `str \| None` | 上次**成功**运行该 (definition, step) 的时间（ISO `YYYY-MM-DDTHH:MM:SS`）。首次运行为 `None` |
| `ctx.config.checkpoint` | `dict \| None` | 上次成功运行脚本自填的检查点（见 §3） |
| `ctx.step_id` | `str \| None` | 当前 step id（`kg.custom.steps` 有；单参为 `None`） |
| `ctx.attempt` | `int \| None` | 当前 step 的 activity 重试次数（第 1 次 = 1；单参为 `None`） |
| `ctx.prev_outputs` | `dict` | 前面各 step 的返回值，键为 step id（`kg.custom.steps` 有；单参为 `{}`） |
| `ctx.execution_id` | `str \| None` | 工作流执行记录 id |
| `ctx.task_id` | `str \| None` | 任务中心 task id |
| `ctx.definition_id` | `str \| None` | 工作流定义 id（水位按此 + step_id 索引） |

> 单参脚本（`workflow(payload)`）只有 `definition_id` / `execution_id` / `task_id` / `config`（水位 step 固定为 `"_default"`）可用；`step_id` / `attempt` / `prev_outputs` 为 `None`/`{}`，因为单函数脚本没有 step 概念。

## 3. 增量抽取

`config.watermark` 记录上次成功运行时间。平台在 step **成功返回后**自动写入本次水位（默认 = 当前时间）。脚本可以在返回 dict 里带 `_watermark` / `_checkpoint` 覆盖默认值——例如用本批数据的最大 `updated_at` 做水位，下次只跑增量。

```python
def step_load(payload, ctx):
    sql = "SELECT id, name, updated_at FROM paper WHERE updated_at > :wm ORDER BY updated_at"
    rows = []
    with ctx.mysql.session_scope() as s:
        result = s.execute(text(sql), {"wm": ctx.config.watermark or "1970-01-01"})
        rows = [dict(r._mapping) for r in result]
    # 用本批最大 updated_at 做下次水位；空批则保留旧水位（传 None → 平台写 now()，
    # 这里显式回传旧值更精确：空批不前进水位）
    max_ts = max((r["updated_at"] for r in rows), default=None)
    return {
        "count": len(rows),
        "items": rows,
        "_watermark": max_ts.isoformat() if max_ts else ctx.config.watermark,
    }
```

- 平台写水位用 `_watermark`（ISO 字符串，解析失败回退 `now()`）和 `_checkpoint`（任意 JSON，例如 `{"last_id": 12345}`）。
- 这两个字段会从 step 输出里剥离，不会出现在任务详情页的 step 结果里。
- step 失败/超时不写水位——下次重置（reset）后重读上次成功水位，重处理同一窗口，幂等。
- 不同 step 各有独立水位（按 `(definition_id, step_id)` 索引）。

## 4. 多步流水线：`prev_outputs` 链式

`kg.custom.steps` 里前一步返回的 dict 自动作为后一步 `ctx.prev_outputs[step_id]`：

```python
def step_extract(payload, ctx):
    papers = ctx.prev_outputs.get("load", {}).get("items", [])
    extracted = []
    for p in papers:
        ents = extract_entities(p["name"], ctx)   # 用 ctx.llm
        extracted.append({"paper_id": p["id"], "entities": ents})
    return {"items": extracted}

def step_persist(payload, ctx):
    for rec in ctx.prev_outputs.get("extract", {}).get("items", []):
        ctx.graph.merge_node(["Paper"], {"vid": rec["paper_id"], ...})
    return {"persisted": len(rec)}
```

## 5. LLM / embedding 降级

未选 LLM/embedding 时属性为 `None`，脚本应降级（例如走规则抽取或跳过向量化）：

```python
def extract_entities(text, ctx):
    if ctx.llm is None:
        return rule_based_extract(text)  # 降级：规则
    prompt = f"从以下文本抽取实体，返回 JSON 数组：\n{text}"
    raw = ctx.llm.synthesize(prompt)  # str | None
    if not raw:
        return rule_based_extract(text)  # LLM 失败再降级
    return json.loads(raw)


def embed_and_store(rec, ctx):
    if ctx.embedding is None or ctx.milvus is None:
        return  # 未配置向量库，跳过
    vec = ctx.embedding.embed_one(rec["name"])  # list[float] | None
    if vec:
        ctx.milvus.upsert("paper", [{**rec, "dense_vector": vec}])
```

## 6. 单参脚本入口

`kg.custom.python` 的 `workflow(payload)` 是单参签名，平台不向其传 `ctx`。需要 Context 时用 `current_context()`：

```python
from kg_sdk import current_context


def workflow(payload):
    ctx = current_context()
    if ctx is None:
        # legacy 运行 / 本地 dev：没有注入 context，自行回退
        return {"status": "no-context"}
    with ctx.mysql.session_scope() as s:
        ...
    return {"status": "ok", "_watermark": "2026-08-25T12:00:00"}
```

`current_context()` 在同一子进程内缓存；未配置 `KG_SCRIPT_CTX` 时返回 `None`（不影响没用 SDK 的老脚本）。

## 7. 触发端字段名

调用 `POST /api/v1/workflow-system/definitions/{id}/execute` 时，除 `payload` 外可选传以下字段（均为可选；不传 = 该资源走默认/env，对应 `ctx` 属性为 `None`）：

| 字段 | 作用 |
|---|---|
| `mysqlDatasourceId` | 选 MySQL 数据源（配置页增删） |
| `mysqlDatabase` | 覆盖该数据源的默认库（下拉从 `GET /mysql-datasources/{id}/databases` 取） |
| `graphSpace` | 选图空间（`GET /graph-spaces` 列出） |
| `milvusConfigId` | 选 Milvus 配置（配置页增删） |
| `milvusDatabase` | 覆盖该配置的默认库（`GET /milvus-configs/{id}/databases`） |
| `llmConfigId` | 选 LLM（配置页增删，OpenAI 兼容 chat 模型） |
| `embeddingConfigId` | 选 embedding 模型（配置页增删） |
| `since` | 业务自带的"起始时间"提示（透传进 payload，与 `watermark` 无关） |

示例：

```bash
curl -X POST http://api:8000/api/v1/workflow-system/definitions/paper-pipeline/execute \
  -H 'Content-Type: application/json' \
  -d '{
    "payload": {"stage": "all", "max_records": 1000},
    "mysqlDatasourceId": "MYSQL-AB12CD34",
    "mysqlDatabase": "gkx_element",
    "graphSpace": "techkg",
    "milvusConfigId": "MILVUS-EF56GH78",
    "milvusDatabase": "techkg",
    "llmConfigId": "LLM-1234ABCD",
    "embeddingConfigId": "EMB-5678EFGH"
  }'
```

## 8. 完整最小示例：4-step 论文流水线

`paper_pipeline.py`（上传到 `POST /workflow-system/definitions/steps`，附 step manifest）：

```python
"""论文实体流水线：增量加载 → LLM 抽取 → 向量化 → 落图。"""

import json
from sqlalchemy import text


def step_load(payload, ctx):
    """增量加载：只取 watermark 之后的论文。"""
    with ctx.mysql.session_scope() as s:
        rows = s.execute(
            text(
                "SELECT id, title, abstract, updated_at FROM paper "
                "WHERE updated_at > :wm ORDER BY updated_at LIMIT :n"
            ),
            {"wm": ctx.config.watermark or "1970-01-01", "n": payload.get("max_records", 500)},
        ).fetchall()
    items = [
        {"id": r.id, "title": r.title, "abstract": r.abstract, "updated_at": r.updated_at}
        for r in rows
    ]
    max_ts = max((r["updated_at"] for r in items), default=None)
    return {
        "items": items,
        "_watermark": max_ts.isoformat() if max_ts else ctx.config.watermark,
        "_checkpoint": {"batch_size": len(items)},
    }


def step_extract(payload, ctx):
    """LLM 抽取实体（未配 LLM 则降级规则）。"""
    items = ctx.prev_outputs.get("load", {}).get("items", [])
    out = []
    for p in items:
        if ctx.llm is None:
            ents = []
        else:
            raw = ctx.llm.synthesize(f"从论文标题抽取关键实体，返回 JSON 数组：\n{p['title']}")
            ents = json.loads(raw) if raw else []
        out.append({"paper_id": p["id"], "entities": ents})
    return {"items": out}


def step_embed(payload, ctx):
    """向量化标题并写 Milvus（未配则跳过）。"""
    items = ctx.prev_outputs.get("extract", {}).get("items", [])
    if ctx.embedding is None or ctx.milvus is None:
        return {"embedded": 0, "skipped": True}
    titles = [i["paper_id"] for i in items]  # 简化：实际应 embed 标题
    vecs = ctx.embedding.embed([i["paper_id"] for i in items]) or []
    records = [{"vid": i["paper_id"], "dense_vector": v} for i, v in zip(items, vecs)]
    if records:
        ctx.milvus.upsert("paper", records)
    return {"embedded": len(records)}


def step_persist(payload, ctx):
    """落图：merge Paper 节点 + AUTHOR 边。"""
    items = ctx.prev_outputs.get("extract", {}).get("items", [])
    for p in items:
        ctx.graph.merge_node(["Paper"], {"vid": p["paper_id"], "title": p.get("title", "")})
    return {"persisted": len(items)}
```

对应 manifest（上传时 `steps` 表单字段，JSON 编码）：

```json
[
  {"id": "load",    "name": "增量加载",  "functionName": "step_load",    "timeoutSeconds": 600,  "retryPolicy": {"maximumAttempts": 3}},
  {"id": "extract","name": "LLM 抽取",  "functionName": "step_extract", "timeoutSeconds": 1200, "retryPolicy": {"maximumAttempts": 3}},
  {"id": "embed",  "name": "向量化",    "functionName": "step_embed",    "timeoutSeconds": 600,  "retryPolicy": {"maximumAttempts": 2}},
  {"id": "persist","name": "落图",      "functionName": "step_persist", "timeoutSeconds": 1800, "retryPolicy": {"maximumAttempts": 1}}
]
```

触发（带选择器，见 §7）后：每步成功，平台自动写 `(paper-pipeline, load)` 等水位；下次只增量加载 `updated_at > 上次水位` 的论文。失败步走 `POST /task-center/tasks/{id}/retry` reset，已完成步靠 Temporal event history replay 不重跑，失败步重读上次成功水位重处理同一窗口。

## 附：相关后端端点

| 端点 | 用途 |
|---|---|
| `GET/POST/PUT/DELETE /api/v1/mysql-datasources[/{id}]` | MySQL 数据源 CRUD |
| `POST /mysql-datasources/{id}/set-default` · `POST /{id}/test` · `GET /{id}/databases` | 设默认 / 测连 / 列库 |
| `GET/POST/PUT/DELETE /api/v1/milvus-configs[/{id}]` + `/set-default` `/test` `/databases` | Milvus 配置同款 |
| `GET/POST/PUT/DELETE /api/v1/embedding-config[/{id}]` + `/set-default` `/test` | embedding 模型同款 |
| `GET/POST/PUT/DELETE /api/v1/llm-config/llm-configs[/{id}]` + `/set-default` `/test` | LLM 同款（已有） |
| `GET /api/v1/graph-spaces` | 列出图空间（只读） |
| `POST /api/v1/workflow-system/definitions/steps` | 上传 step pipeline 脚本 + manifest |
| `POST /api/v1/workflow-system/definitions/{id}/execute` | 触发（带 §7 选择器） |
