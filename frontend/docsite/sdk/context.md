# 运行上下文 Context

> 来源：`backend/docs/kg_sdk.md` §1-2/§6-7 · `backend/sdk/kg_sdk.py` · `docs/script-sdk/context.html`

平台用户脚本只有一个入口形态——**单参函数**，`ctx` 不经参数传入，统一用 `current_context()` 取：

| 入口签名 | 通道 | 说明 |
|---|---|---|
| `def transform(payload: dict) -> dict` | Schema 管理上传（`kg.schema.extract`，**唯一通道**） | 平台按来源分批送 `rows`，脚本只做转换，返回 `{entities|edges, failures}` |
| `def workflow(payload: dict) -> dict` | 旧签名兼容 | 仅入口名不同，ctx 取法一致 |

`Context` 里的客户端是**懒构造**的——第一次访问 `.mysql` / `.graph` / `.milvus` / `.llm` / `.embedding` 时才建连并缓存。

**降级约定**：触发任务时如果没有选某个资源（MySQL 数据源 / 图数据空间 / 向量数据空间 / 语言模型 / 向量模型），对应属性返回 `None`，**不抛异常**。脚本务必 `if ctx.llm:` 判空后再用。一条脚本里同时用数据库、LLM、向量库做"抽取→对齐→落库"非常常见。

`Context` 由平台在 worker 子进程外解析好"连接参数"（不是活对象，无法跨进程 pickle），序列化进 `KG_SCRIPT_CTX` 环境变量；`kg_sdk.Context` 据此按需构造客户端。密钥经 env 传递，安全面与脚本本就能读到的 `MYSQL_PASSWORD` 等 `sub_env` 一致。

## 客户端属性（懒构造，未配置返回 `None`）

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.mysql` | `infra.mysql.MySQLClient \| None` | 触发时所选 MySQL 数据源 + 库；可用 `.create_session()` / `.session_scope()` / `.engine` |
| `ctx.graph` | `infra.graph_db.TRSGraphClient \| None` | 触发时所选图数据空间（NebulaGraph 图空间）；构造时已 `connect()` |
| `ctx.milvus` | `pymilvus.MilvusClient \| None` | 触发时所选向量数据空间（Milvus 向量库）+ 库 |
| `ctx.llm` | `infra.llm.LLMClient \| None` | 触发时所选语言模型（OpenAI 兼容 chat）；`.synthesize(prompt)` 返回 `str \| None` |
| `ctx.embedding` | `infra.llm.EmbeddingClient \| None` | 触发时所选向量模型（embedding）；`.embed(texts)` / `.embed_one(text)` |

## 增量游标与调度元数据

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.config.watermark` | `str \| None` | 上次**成功**运行该 (definition, step) 的时间（ISO `YYYY-MM-DDTHH:MM:SS`）；首次运行为 `None` |
| `ctx.config.checkpoint` | `dict \| None` | 上次成功运行脚本自填的检查点（见[增量水位](/sdk/incremental)） |
| `ctx.step_id` | `str \| None` | 多步通道遗留字段；抽取通道不注入（`None`） |
| `ctx.attempt` | `int \| None` | 多步通道遗留字段；抽取通道不注入（`None`） |
| `ctx.prev_outputs` | `dict` | 多步通道遗留字段；抽取通道恒为 `{}` |
| `ctx.execution_id` | `str \| None` | 工作流执行记录 id |
| `ctx.task_id` | `str \| None` | 任务中心 task id |
| `ctx.definition_id` | `str \| None` | 工作流定义 id（水位按此 + step_id 索引） |

抽取通道（`transform`）注入 `definition_id` / `execution_id` / `task_id` / `config` 与资源连接参数；`step_id` / `attempt` / `prev_outputs` 是多步通道遗留，恒为 `None`/`{}`。

## 脚本入口：current_context()

平台脚本都是单参签名（`transform(payload)`，旧 `workflow(payload)` 兼容），平台不向其传 `ctx`：

```python
from kg_sdk import current_context


def transform(payload):
    ctx = current_context()
    if ctx is None:
        # 本地 dev：没有注入 context，自行回退
        return {"entities": [], "failures": []}
    with ctx.mysql.session_scope() as s:
        ...  # 例：加载查找表做行级消歧（ctx.mysql 默认回退来源绑定数据源）
    return {"entities": [...], "failures": []}
```

`current_context()` 在同一子进程内缓存；未配置 `KG_SCRIPT_CTX` 时返回 `None`（本地独立运行不受影响）。

## 资源选择器（ctx 注入来源）

抽取执行 payload 可带以下资源选择器（worker 内 `_resolve_resources` 解析成连接参数进 `KG_SCRIPT_CTX`；任一解析失败独立降级为缺该 key，对应 `ctx` 属性返回 `None`）。资源统一在**配置管理**页维护，共五个分类：**语言模型 / 向量模型 / MySQL 数据源 / 向量数据空间 / 图数据空间**：

| 字段 | 作用 |
|---|---|
| `mysql_datasource_id` | 选 MySQL 数据源（配置管理 → MySQL 数据源） |
| `mysql_database` | 覆盖该数据源的默认库 |
| `graph_space` | 选图数据空间 |
| `milvus_config_id` | 选向量数据空间（Milvus 向量库配置） |
| `milvus_database` | 覆盖该配置的默认库 |
| `llm_config_id` | 选语言模型（OpenAI 兼容 chat 模型） |
| `embedding_config_id` | 选向量模型（embedding） |
| `since` | 业务自带的"起始时间"提示（透传，与平台水位无关） |

**当前抽取入口（Schema 抽取触发 / Job / 自动策略）的 payload 默认只带 `schemaId` / `graphSpace` / `batchSize` / `triggerSource`**——即脚本实际通常拿到：`ctx.mysql`（未显式选 MySQL 时**回退来源绑定数据源**）+ `ctx.source`（来源表元数据，不含 `datasourceId`）；`graph` / `llm` / `embedding` 未选为 `None`，脚本按降级约定判空。历史示例（对 `definitions/{id}/execute` 传 `mysqlDatasourceId` 等驼峰字段）已随独立脚本通道下线而失效。

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
