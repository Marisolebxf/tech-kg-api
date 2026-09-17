# 抽取脚本 SDK（`kg_sdk`）

> 本文档的在线版本在平台文档中心（部署后访问 `/docs/sdk/`，VitePress，源 `frontend/docsite/sdk/`）。
> 面向在平台上编写"实体/关系抽取脚本"的开发者。脚本运行时由平台注入一个 `Context` 对象，
> 里面提供已配置好的 MySQL / trs-graph / Milvus / LLM / embedding 客户端，以及该来源绑定的
> `watermark`（上次成功抽取游标），支撑增量语义。

## 1. 概览

平台只有**一条**用户脚本通道：Schema 管理页上传 `.py`（SSE 流式校验：语法检查 → LLM 安全校验 → 存 S3），由 Temporal workflow `kg.schema.extract` 执行。脚本**只做转换**——平台按来源绑定分批读源表行、把行放进 payload 调脚本，脚本返回实体/关系 JSON，写图/消歧/索引/推水位全部由平台完成。

| 脚本形态 | 签名 | 说明 |
|---|---|---|
| 单步（默认） | `def transform(payload: dict) -> dict` | 旧入口名 `workflow` 仍兼容，新脚本请用 `transform` |
| 多步 | 顶层声明 `STEPS = [{"id": ..., "fn": ...}, ...]`，每个 `fn` 均为单参顶层函数 | 与 `transform` 互斥，最长 16 步（`service/script_steps.py` 上传时静态校验） |

> 原 `kg.custom.python` / `kg.custom.steps` 独立上传通道（`POST /definitions/python|steps`、双参 step runner）已于 2026-09-14 清理批次4-D2 下线；多步能力并入脚本顶层 `STEPS` 声明。

`Context` 里的客户端是**懒构造**的——第一次访问 `.mysql` / `.graph` / `.milvus` / `.llm` / `.embedding` 时才建连，并缓存。需要 Context 时用 `from kg_sdk import current_context`。

**降级约定**：触发时如果没有选某个资源（图空间/Milvus/LLM/embedding），对应的属性返回 `None`，**不抛异常**。脚本务必 `if ctx.llm:` 判空后再用——这与 `infra.llm.get_llm_client()` 既有约定一致。

`Context` 由平台在 worker 子进程外解析好"连接参数"（不是活对象，无法跨进程 pickle），序列化进 `KG_SCRIPT_CTX` 环境变量；`kg_sdk.Context` 据此按需构造客户端。密钥经 env 传递，安全面与脚本本就能读到的 `MYSQL_PASSWORD` 等 `sub_env` 一致。

## 2. `Context` API

```python
from kg_sdk import Context, current_context
```

### 客户端属性（懒构造，未配置返回 `None`）

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.mysql` | `infra.mysql.MySQLClient \| None` | 触发任务所选 MySQL 数据源 + 库；未显式选时**自动回退到来源表绑定的数据源**（脚本内可 `ctx.mysql.engine` 加载查找表） |
| `ctx.graph` | `infra.graph_db.TRSGraphClient \| None` | 触发时所选图数据空间（NebulaGraph 图空间）；构造时已 `connect()`。未选则 `None` |
| `ctx.milvus` | `pymilvus.MilvusClient \| None` | 触发时所选向量数据空间（Milvus 向量库）+ 库；未选则 `None` |
| `ctx.llm` | `infra.llm.LLMClient \| None` | 触发时所选语言模型（OpenAI 兼容，chat）；未选或缺 key 则 `None`。`.synthesize(prompt)` 返回 `str \| None` |
| `ctx.embedding` | `infra.llm.EmbeddingClient \| None` | 触发时所选向量模型（embedding）；未选或缺 key 则 `None`。`.embed(texts)` / `.embed_one(text)` |

### 增量游标与元数据

| 属性 | 类型 | 说明 |
|---|---|---|
| `ctx.config.watermark` | `str \| None` | 该来源绑定**上次成功抽取**的时间列水位（ISO `YYYY-MM-DDTHH:MM:SS`）。首次运行为 `None`。**只读**（见 §3） |
| `ctx.config.checkpoint` | `dict \| None` | querySql 绑定走 pk keyset 游标时，游标在 `checkpoint.pkCursor` |
| `ctx.step_id` | `str` | 观测标识：多步形如 `source:{绑定id}#{stepId}`，单步为 `_default` |
| `ctx.attempt` | `int` | 当前步 activity 的 Temporal 重试次数（第 1 次 = 1） |
| `ctx.prev_outputs` | `dict` | 本批次已完成各步的返回值 `{stepId: 输出}`（单步脚本为 `{}`） |
| `ctx.execution_id` | `str \| None` | 工作流执行记录 id |
| `ctx.task_id` | `str \| None` | 任务中心 task id |
| `ctx.definition_id` | `str \| None` | 合成工作流定义 id（`schema-extract-{key}`） |

## 3. 水位：只读语义

水位由**平台管理，脚本不可覆盖**——脚本返回值里的 `_watermark` / `_checkpoint` 元字段会被剥离忽略（`_strip_watermark_meta`）。语义：

- 每个**来源绑定**独立水位（`kg_script_watermark`，键 `schema-extract-{key}` + `source:{绑定行 id}`），类比 Kafka consumer offset；
- 只有该来源**全部批次整链成功后**才一次性推进；任一批失败不推进，重跑重读上次成功水位、重处理同一窗口（幂等）；不做 per-step 水位；
- 读取模式：`query_sql` 绑定走水位/pk keyset 游标（合成唯一 pk，游标存 `checkpoint.pkCursor`）；普通表走 LIMIT/OFFSET（与旧脚本同语义）；
- `ctx.config.watermark` / `ctx.config.checkpoint` 可读——脚本自读库（经 `ctx.mysql`）做查找表加载等辅助读取时可作参考，但抽取主链路的增量由平台读源时保证。

## 4. 多步脚本：顶层 `STEPS` 声明

脚本顶层用 list 字面量声明步清单（上传时 `service/script_steps.py` 纯 ast 静态校验：id 匹配 `[A-Za-z0-9_-]{1,64}` 且唯一、fn 必须是顶层函数、与 `transform` 互斥、最长 16 步）：

```python
STEPS = [
    {"id": "normalize", "fn": "step_normalize"},   # 第一步消费平台读的源表行
    {"id": "resolve",   "fn": "step_resolve"},     # 后续步消费上一步输出
    {"id": "emit",      "fn": "step_emit"},
]
```

- 第 1 步 payload 与单步相同：`{"rows": [...], "source_table": "库.表", "kind": "entity"|"relation", "source": {...}}`；
- 第 N>1 步 payload 为 `{"input": 上一步完整输出, "source_table": ..., "kind": ..., "source": ...}`（**不再带 rows**）；`ctx.prev_outputs` 可读本批次已完成各步输出；
- 每步一次 `execute_transform` activity，第 k 步失败由 Temporal **只重试第 k 步**（前序步输出经事件历史重放）；任意一步返回 `entities`/`edges` 即在该步之后写图（实体再接消歧）；
- 步间透传有大小防护（input 单值 512KB / prevOutputs 单值 128KB / 额外键合计 256KB，超限截断为 `_truncated` 标记并告警）；
- `failures` / `pendingReview` 跨步聚合进现有链路（见 §9）。

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

## 6. 脚本入口与 `current_context`

入口是单参 `transform(payload)`，平台不向其传 `ctx`。需要 Context 时用 `current_context()`：

```python
from kg_sdk import current_context


def transform(payload):
    ctx = current_context()
    if ctx is None:
        # 本地 dev：没有注入 context，自行回退
        return {"status": "no-context"}
    rows = payload["rows"]  # 平台读好的本批行
    ...
    return {"entities": [...]}
```

`current_context()` 在同一子进程内缓存；未配置 `KG_SCRIPT_CTX` 时返回 `None`（不影响没用 SDK 的脚本）。

## 7. 触发端字段名

创建任务（`POST /api/v1/workflow-system/jobs`，`taskType` 固定为 `extract`，选 Schema + 批大小）时可选传以下资源字段（不传 = 该资源走默认/env，对应 `ctx` 属性为 `None`；`ctx.mysql` 未选时回退来源绑定数据源）。资源统一在**配置管理**页维护，共五个分类：**语言模型 / 向量模型 / MySQL 数据源 / 向量数据空间 / 图数据空间**：

| 字段 | 作用 |
|---|---|
| `schemaId` + `batchSize` | 目标 Schema（须已有脚本+来源绑定）与批大小（1–5000） |
| `mysqlDatasourceId` | 选 MySQL 数据源（配置管理 → MySQL 数据源） |
| `mysqlDatabase` | 覆盖该数据源的默认库（下拉从 `GET /mysql-datasources/{id}/databases` 取） |
| `graphSpace` | 选图数据空间（配置管理 → 图数据空间，`GET /graph-spaces` 列出） |
| `milvusConfigId` | 选向量数据空间（配置管理 → 向量数据空间，即 Milvus 向量库配置） |
| `milvusDatabase` | 覆盖该配置的默认库（`GET /milvus-configs/{id}/databases`） |
| `llmConfigId` | 选语言模型（配置管理 → 语言模型，OpenAI 兼容 chat 模型） |
| `embeddingConfigId` | 选向量模型（配置管理 → 向量模型） |

一次性直触发（不经任务）走 `POST /api/v1/schema-management/schemas/{id}/extract`，仅接受 `graphSpace` / `batchSize`。回填走 `POST /schemas/{id}/backfill`（清水位全量重跑，脚本落后时需 `force`）。

## 8. 完整最小示例：STEPS 三步流水线

`paper_pipeline.py`（Schema 管理页上传，SSE 校验通过后存 S3）：

```python
"""论文实体流水线：行规整 → 查找表富集 → 输出实体。"""

from sqlalchemy import text

from kg_sdk import current_context

STEPS = [
    {"id": "normalize", "fn": "step_normalize"},
    {"id": "enrich",    "fn": "step_enrich"},
    {"id": "emit",      "fn": "step_emit"},
]


def step_normalize(payload):
    """第 1 步：消费平台读的源表行，规整字段。"""
    rows = payload["rows"]
    return {"items": [
        {"id": r["id"], "title": (r.get("title") or "").strip(), "org_id": r.get("org_id")}
        for r in rows
    ]}


def step_enrich(payload):
    """第 2 步：用 ctx.mysql 查找表富集（mysql 未选时自动用来源绑定数据源）。"""
    ctx = current_context()
    items = payload["input"]["items"]
    if ctx is not None and ctx.mysql is not None:
        with ctx.mysql.session_scope() as s:
            org_names = dict(
                s.execute(text("SELECT id, name FROM org")).fetchall()
            )  # 简化示意
        for it in items:
            it["org_name"] = org_names.get(it.get("org_id"))
    return {"items": items}


def step_emit(payload):
    """第 3 步：输出实体（平台负责写图/消歧/索引/推水位）。"""
    items = payload["input"]["items"]
    return {
        "entities": [
            {"id": it["id"], "props": {"id": it["id"], "name": it["title"]}}
            for it in items
        ]
    }
```

每步成功由平台按来源推进水位；失败批不推水位，重跑重读上次成功水位重处理同一窗口。

## 9. 平台喂数模式（与自读库的区别）

平台喂数是**唯一**模式：平台负责读源表与写图，脚本只做转换。

1. 平台按每张来源表绑定的**时间列水位**（默认 `update_time`，每张表独立）分批读取行：
   `SELECT * FROM db.table WHERE time_col > :水位 ORDER BY time_col, pk LIMIT :batchSize`（querySql 绑定走水位/pk keyset；普通表走 LIMIT/OFFSET）；
2. 把行 JSON 放进 `payload["rows"]`，调脚本的 `transform(payload)`（旧 `workflow` 名兼容）；
3. 脚本**只做转换**：返回实体或关系 dict，不自读库（查找表除外）、不自写图；
4. 平台对返回结果写图（实体走 nGQL `INSERT VERTEX`；只写 Schema 目录中未删除的属性——已删属性「插空」即省略键），然后推进该来源表的水位。

返回格式（`props` 键名须在 Schema 目录内）：

```python
def transform(payload):
    rows = payload["rows"]  # 本批行（JSON dict）
    table = payload["source_table"]  # "库名.表名"
    kind = payload["kind"]  # "entity" | "relation"

    return {
        "entities": [
            {"id": row["id"], "props": {"id": row["id"], "name": row["name"]}},
        ]
    }
    # 关系：{"edges": [{"fromId": "S-1", "toId": "O-1", "props": {...}}]}
```

注意：

- 可选 `failures: [{recordId, error}]`——逐行解析失败由平台记 **T_EXTRACT_FAIL** 审核 case（`POST /manual-reviews/production/rerun-extract-failures` 可按执行重跑）；
- 可选 `pendingReview: [...]`——低置信/消歧候选进审核队列（item 可带 `templateId=T_LINK`，同名冲突裁决）；
- 脚本返回的 `_watermark` / `_checkpoint` 元字段**被忽略**——水位由平台按批次最大时间列值管理（见 §3）；
- 多张来源表并行抽取、单表内批次串行；执行进度在任务中心 / `get_progress` 查询可见，多步脚本带分步计数 `steps: {stepId: {records, written, failed}}`。

## 附：相关后端端点

| 端点 | 用途 |
|---|---|
| `GET/POST/PUT/DELETE /api/v1/mysql-datasources[/{id}]` | MySQL 数据源 CRUD |
| `POST /mysql-datasources/{id}/set-default` · `POST /{id}/test` · `GET /{id}/databases` | 设默认 / 测连 / 列库 |
| `GET/POST/PUT/DELETE /api/v1/milvus-configs[/{id}]` + `/set-default` `/test` `/databases` | Milvus 配置同款 |
| `GET/POST/PUT/DELETE /api/v1/embedding-config[/{id}]` + `/set-default` `/test` | embedding 模型同款 |
| `GET/POST/PUT/DELETE /api/v1/llm-config/llm-configs[/{id}]` + `/set-default` `/test` | LLM 同款 |
| `GET /api/v1/graph-spaces` | 列出图空间（只读） |
| `POST /api/v1/workflow-system/jobs` | 创建 extract 任务（§7 资源选择器） |
| `PUT /api/v1/schema-management/schemas/{id}/sources` | 绑定来源表（§9 平台喂数） |
| `POST /api/v1/schema-management/schemas/{id}/extract` | 触发平台喂数抽取（`graphSpace`/`batchSize`） |
| `POST /api/v1/schema-management/schemas/{id}/backfill` | 清水位全量重跑（脚本落后需 `force`） |
| `GET /mysql-datasources/{id}/tables?database=` · `GET /{id}/tables/{t}/columns` | 来源表绑定选表 / 选列 |
