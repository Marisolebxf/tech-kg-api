# trs-graph 内部能力（infra/graph_db）设计

- 日期：2026-06-17
- 分支：`feature/trs-graph-app-service`（重置到 `origin/main` `1ffad7d` 后重新实现；旧 app/ 版工作备份于 `backup/trs-graph-app-service-old`）
- 状态：待评审
- 取代：`2026-06-17-trs-graph-app-service-design.md`（基于已删除的 `app/` 结构，作废）

## 1. 背景

远端 `main`（`1ffad7d`）已从旧的 FastAPI `app/` 结构迁移到新的 DDD 分层骨架：

```
main.py → biz/router/register → biz/handler/* → application/* → service/* → dao/* + db_model/* → infra/*
```

其中 `infra/` 是基础设施客户端层，目前全是占位 stub（`graph_db.py`/`mysql.py`/`llm.py`/`redis.py`）。`infra/graph_db.py` 已有一个 `TRSGraphClient` 空占位类，注释"以后按实验室提供的组件实现"。`dao/`+`db_model/`（SQLAlchemy ORM）是 MySQL 那套"orm crud"范式。旧 `graph_db/` 与 `app/` 已移入 `backend/legacy/`（ruff 排除），无任何代码引用 `infra.graph_db` 占位类。

本设计把 trs-graph 实现为 `infra/graph_db/` 内部能力，替换占位 stub，供 app 内 `application`/`service`/`dao` 层（内部 fc）直接 import 调用，对应"mysql orm crud"在 `infra/mysql.py` 的角色。

## 2. 目标与非目标

### 目标
- 删除占位文件 `backend/infra/graph_db.py`，替换为 `infra/graph_db/` 包。
- 实现 `TRSGraphClient`：通过 HTTP REST 调用 `trs-graph-service`（端口 8090，底层 NebulaGraph），提供节点/边 CRUD、遍历、nGQL 查询、批量、schema、数据库信息。
- 提供线程安全懒加载单例 `get_trs_graph_client()`/`close_trs_graph_client()` 供内部 fc 使用。
- 复用已 review 的客户端逻辑（来自 `backup/trs-graph-app-service-old` 的 `app/services/graph/`，源出 `refactor/trs-graph-db-api` 的 `trs_graph_backend.py`）。

### 非目标
- 不新增 router/handler（内部能力，非新 API 面）。
- 不动 `legacy/`。不 import `graph_db`/`legacy.graph_db`。
- 不接 NebulaGraph 原生 9669（采用 HTTP REST）。
- 不改 `dao/`/`db_model/`（MySQL 那套）。

## 3. 模块布局

删除 `backend/infra/graph_db.py`（占位）。新增包：

```
backend/infra/graph_db/
  __init__.py     # 公共 API：TRSGraphClient, get_trs_graph_client, close_trs_graph_client, models, exceptions, settings
  client.py       # TRSGraphClient — 全部 CRUD/遍历/查询/批量/schema/信息
  models.py       # GraphNode/GraphEdge/GraphPath/GraphQueryResult/GraphPagedResult/GraphIndexSpec/GraphConstraintSpec
  convert.py      # JSON↔模型 帮助函数
  exceptions.py   # GraphRepoError 层级（GraphConnectionError/GraphNotFoundError/GraphRequestError）
  config.py       # TRSGraphSettings（TRS_GRAPH_* 环境变量）
```

类名沿用占位名 `TRSGraphClient`（由旧实现的 `GraphRepo` 改名）。异常基类保留 `GraphRepoError`（最小改动；可后续统一为 `GraphClientError`，本次不改）。

## 4. 复用映射

| 旧（backup 分支 `app/services/graph/`） | 新（`infra/graph_db/`） | 改动 |
|------------------------------------------|-------------------------|------|
| `repository.py` `GraphRepo` | `client.py` `TRSGraphClient` | 类名改；导入改 `infra.graph_db.*` |
| `models.py` | `models.py` | 原样 |
| `convert.py` | `convert.py` | 原样 |
| `exceptions.py` | `exceptions.py` | 原样 |
| `config.py` `TRSGraphSettings` | `config.py` | 原样 |
| `__init__.py` `get_graph_repo`/`close_graph_repo` | `__init__.py` `get_trs_graph_client`/`close_trs_graph_client` | 函数名改；类名改 |
| `tests/test_graph_repo.py`（65） | `tests/unit/test_trs_graph_client.py` | 导入路径改；类名改；`_make_repo`→`_make_client` |
| `tests/integration/test_graph_repo_integration.py`（3） | `tests/integration/test_trs_graph_client_integration.py` | 同上 + 加 `@pytest.mark.external` |

逻辑、错误映射（404→GraphNotFoundError、非 2xx→GraphRequestError、传输→GraphConnectionError）、线程安全单例、所有兼容 quirk 处理（`_strip_quotes`、边类型自动查找、shortest_path 回填、批量 properties 扁平化）全部保留。

## 5. 配置

`TRS_GRAPH_*` 环境变量（同旧实现）：`TRS_GRAPH_BASE_URL`（默认 `http://localhost:8090`）、`TRS_GRAPH_SPACE`（默认 `entity_binding_demo`）、`TRS_GRAPH_API_KEY`、`TRS_GRAPH_TIMEOUT`（默认 30）。追加到 `backend/.env.example`。

## 6. 接入

- `backend/main.py`：加最小 `lifespan`，shutdown 时 `close_trs_graph_client()`。`get_trs_graph_client()` 懒加载，首用时才 connect（服务未就绪不影响启动）。
- 不加 router。

## 7. 测试

- 单测 `tests/unit/test_trs_graph_client.py`：平移 65 个用例（`httpx.MockTransport` 打桩）。
- 集成 `tests/integration/test_trs_graph_client_integration.py`：平移 3 个，加 `@pytest.mark.external`，服务不可用时自动 skip（probe 延迟到 fixture，不在 collection 触发）。
- 运行环境：现有 `.venv`（Python 3.13，httpx/pydantic/dotenv/sqlalchemy 齐全）；代码通过 `from __future__ import annotations` 兼容官方 target 3.11。

## 8. 交付物

- `backend/infra/graph_db/` 包（6 文件）
- 删除 `backend/infra/graph_db.py` 占位
- `backend/main.py` 加 lifespan
- `backend/.env.example` 加 `TRS_GRAPH_*`
- `backend/tests/unit/test_trs_graph_client.py`、`backend/tests/integration/test_trs_graph_client_integration.py`
- spec + plan 文档

## 9. 验收

- `pytest tests/unit/test_trs_graph_client.py tests/integration/test_trs_graph_client_integration.py` → 65 passed, 3 skipped（无真实服务时）。
- `ruff check` 全绿（`legacy` 已排除）。
- `grep -E "^\s*(import|from)\s+(graph_db|legacy)" backend/infra/graph_db/` 无匹配（与 legacy/旧 graph_db 解耦）。
- `from main import app` 仍可导入（不破坏现有入口）。
