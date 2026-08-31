# 运行上下文 Context

> 来源：`backend/docs/kg_sdk.md` §1-2/§6-7 · `backend/sdk/kg_sdk.py` · `docs/script-sdk/context.html`

平台支持两种用户脚本：

| 工作流类型 | 脚本签名 | Context 入口 |
|---|---|---|
| `kg.custom.steps`（多步流水线，推荐） | `def step_xxx(payload: dict, ctx: Context) -> dict` | `ctx` 已被平台包装成 `Context`，直接用 `ctx.mysql` 等 |
| `kg.custom.python`（单函数，旧） | `def workflow(payload: dict) -> dict` | `from kg_sdk import current_context; ctx = current_context()` |

`Context` 里的客户端是**懒构造**的——第一次访问 `.mysql` / `.graph` / `.milvus` / `.llm` / `.embedding` 时才建连并缓存。

**降级约定**：触发任务时如果没有选某个资源（数据源/图空间/Milvus/LLM/embedding），对应属性返回 `None`，**不抛异常**。脚本务必 `if ctx.llm:` 判空后再用。一条脚本里同时用数据库、LLM、向量库做"抽取→对齐→落库"非常常见。

`Context` 由平台在 worker 子进程外解析好"连接参数"（不是活对象，无法跨进程 pickle），序列化进 `KG_SCRIPT_CTX` 环境变量；`kg_sdk.Context` 据此按需构造客户端。密钥经 env 传递，安全面与脚本本就能读到的 `MYSQL_PASSWORD` 等 `sub_env` 一致。

## 客户端属性（懒构造，未配置返回 `None`）

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.mysql` | `infra.mysql.MySQLClient \| None` | 触发时所选 MySQL 数据源 + 库；可用 `.create_session()` / `.session_scope()` / `.engine` |
| `ctx.graph` | `infra.graph_db.TRSGraphClient \| None` | 触发时所选图空间；构造时已 `connect()` |
| `ctx.milvus` | `pymilvus.MilvusClient \| None` | 触发时所选 Milvus 配置 + 库 |
| `ctx.llm` | `infra.llm.LLMClient \| None` | 触发时所选 LLM（OpenAI 兼容 chat）；`.synthesize(prompt)` 返回 `str \| None` |
| `ctx.embedding` | `infra.llm.EmbeddingClient \| None` | 触发时所选 embedding 模型；`.embed(texts)` / `.embed_one(text)` |

## 增量游标与调度元数据

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.config.watermark` | `str \| None` | 上次**成功**运行该 (definition, step) 的时间（ISO `YYYY-MM-DDTHH:MM:SS`）；首次运行为 `None` |
| `ctx.config.checkpoint` | `dict \| None` | 上次成功运行脚本自填的检查点（见[增量水位](/sdk/incremental)） |
| `ctx.step_id` | `str \| None` | 当前 step id（`kg.custom.steps` 有；单参为 `None`） |
| `ctx.attempt` | `int \| None` | 当前 step 的 activity 重试次数（第 1 次 = 1） |
| `ctx.prev_outputs` | `dict` | 前面各 step 的返回值，键为 step id（单参为 `{}`） |
| `ctx.execution_id` | `str \| None` | 工作流执行记录 id |
| `ctx.task_id` | `str \| None` | 任务中心 task id |
| `ctx.definition_id` | `str \| None` | 工作流定义 id（水位按此 + step_id 索引） |

单参脚本（`workflow(payload)`）只有 `definition_id` / `execution_id` / `task_id` / `config`（水位 step 固定为 `"_default"`）可用；`step_id` / `attempt` / `prev_outputs` 为 `None`/`{}`。

## 单参脚本入口：current_context()

`kg.custom.python` 的 `workflow(payload)` 是单参签名，平台不向其传 `ctx`：

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

## 触发端字段名

调用 `POST /api/v1/workflow-system/definitions/{id}/execute` 时，除 `payload` 外可选传以下字段（不传 = 对应 `ctx` 属性为 `None`）：

| 字段 | 作用 |
|---|---|
| `mysqlDatasourceId` | 选 MySQL 数据源（配置页增删） |
| `mysqlDatabase` | 覆盖该数据源的默认库（下拉从 `GET /mysql-datasources/{id}/databases` 取） |
| `graphSpace` | 选图空间（`GET /graph-spaces` 列出） |
| `milvusConfigId` | 选 Milvus 配置 |
| `milvusDatabase` | 覆盖该配置的默认库 |
| `llmConfigId` | 选 LLM（OpenAI 兼容 chat 模型） |
| `embeddingConfigId` | 选 embedding 模型 |
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
    "llmConfigId": "LLM-1234ABCD",
    "embeddingConfigId": "EMB-5678EFGH"
  }'
```

## LLM / embedding 降级

未选 LLM/embedding 时属性为 `None`，脚本应降级（走规则抽取或跳过向量化）：

```python
def extract_entities(text, ctx):
    if ctx.llm is None:
        return rule_based_extract(text)  # 降级：规则
    raw = ctx.llm.synthesize(prompt)  # str | None
    if not raw:
        return rule_based_extract(text)  # LLM 失败再降级
    return json.loads(raw)
```
