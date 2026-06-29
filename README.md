# tech-kg-api

科技知识图谱 monorepo：后端 API（Python FastAPI）+ 前端（Vue 3）。
图库为 NebulaGraph，通过 **trs-graph-service**（Java Spring Boot REST 服务）访问，后端用 `infra/graph_db.TRSGraphClient` 做 ORM 风格封装。

## 环境要求

后端：

- Python 3.11.13（`>=3.11.13,<3.12`）
- [uv](https://docs.astral.sh/uv/)

前端：

- Node.js 20+
- [pnpm](https://pnpm.io/)

外部依赖：

- **trs-graph-service**（默认 `http://localhost:8090`，NebulaGraph REST 网关）
- **MySQL 8.0**（业务数据）
- （可选）智谱 GLM API Key——仅「企业背景关联分析」用，未配置时自动降级

## 快速开始

### 方式一：Docker（推荐）

```bash
docker compose up --build
# 后端 api:  http://localhost:8001  (容器内 8000)
# 前端 web:  http://localhost:8088  (容器内 80)
# 接口文档:  http://localhost:8001/docs
```

`docker-compose.yml` 通过 `host.docker.internal` 连接宿主机上的 trs-graph-service / MySQL；如端口 8001/8088 被占用，改 compose 里的 host 端口即可（不要停其它服务让端口）。

### 方式二：本地开发

```bash
# 后端
cd backend
uv sync --dev
cp .env.example .env        # 填 TRS_GRAPH_* / MYSQL_* / LLM_*
uv run uvicorn main:app --reload   # 入口是 backend/main.py

# 前端
cd frontend
pnpm install
pnpm dev                    # /api 代理到 VITE_API_TARGET（默认 http://localhost:8100）
```

## 后端架构（DDD 分层）

请求链路：`main.py` → `biz/router/register.py` → `biz/handler/*` → `application/*` → `service/*` → `dao/*` + `db_model/*` + `infra/*`。

| 目录 | 职责 |
|------|------|
| `biz/handler/` | FastAPI `APIRouter`（路由唯一入口），挂载在 `/api/v1` 下；薄层：解析请求→调 application |
| `biz/schemas/` | Pydantic v2 请求/响应模型，每模块一文件 |
| `application/` | 编排层，每模块一个类，包装一个 service |
| `service/` | 业务逻辑；KG 构造模块继承 `service/base_module.KGModuleScaffoldService`，目录登记在 `service/module_catalog.py` |
| `dao/` | MySQL 查询对象，各持一个 SQLAlchemy `Session` |
| `db_model/` | SQLAlchemy ORM 模型（共享 `db_model/base.Base`） |
| `infra/` | 基础设施单例：`mysql.py` / `redis.py` / `llm.py` / `graph_db/`；均从环境变量 / `.env` 读配置（`config/*.yml` 为 legacy，不加载） |

新增一个 KG 构造功能 = 加 schemas + handler + application + service + dao/model 五层，并在 `biz/router/register.py` 注册路由。

### 重点关注科技企业关系子系统（3 模块）

- **专家-企业关系构建** `POST /api/v1/kg-construction/expert-enterprise-relations/build` —— 写 `EMPLOYED_BY` 边，英文码 `/` 拼接存 `relation_type`，响应映射中文标签，按企业去重返回该专家全部关系。
- **角色与合作详情标注** `POST /api/v1/kg-construction/relation-detail-annotations/annotate` —— 给已有 `EMPLOYED_BY` 边补 role/tech_field/时段，角色按 `ROLE_CATALOG` 映射 L1/L2/L3。
- **企业背景关联分析** `POST /api/v1/kg-construction/enterprise-background-analyses/analyze` —— 聚合 MySQL（行业地位/核心技术/经营财务）+ LLM 合成结论（失败降级）。
- **下拉选项聚合** `GET /api/v1/kg-construction/options` —— 供前端参数弹窗动态拉取学者/企业/关系/角色/维度/CPC 选项。

## TRS 图库客户端（`infra/graph_db`）

图库是 NebulaGraph，经 trs-graph-service 的 REST API 访问。认证用 `X-API-Key` 头，图空间用 `X-Graph-Space` 头。`infra/graph_db/client.TRSGraphClient` 是 ORM 风格客户端。

### 连接

两个线程安全懒加载单例（`infra/graph_db/__init__.py`），首次使用时连接，`main.py` lifespan 关闭时释放：

```python
from infra.graph_db import get_techkg_client, get_trs_graph_client

client = get_techkg_client()   # 图空间固定 techkg（业务服务都用它）
# 或
client = get_trs_graph_client()  # 图空间取 TRS_GRAPH_SPACE 环境变量
```

> **vid 约定**：trs-graph-service 只把属性键 `vid`/`id`/`name` 当作顶点 id。客户端在 `create_node`/`merge_node`/`batch_create_nodes` 时若这三者都不存在，会自动把首个属性值提升为 vid（贴合 techkg「自然键即 vid」约定，如 `org_id`/`scholar_id`），否则服务端会生成 UUID 但读不回（404）。

### 节点 CRUD

```python
from infra.graph_db import get_techkg_client

g = get_techkg_client()

# 创建（properties 含 vid/id/name 之一即作为顶点 id）
alice = g.create_node(["DemoPerson"], {"name": "Alice", "age": 30})
# alice.id == "Alice"

# 幂等创建/更新（identity_props 的值会被提升为 vid）
bob = g.merge_node(["DemoPerson"], {"demo_id": "bob"}, {"age": 25, "city": "北京"})
# bob.id == "bob"

# 按 vid 获取（不存在返回 None）
node = g.get_node("Alice")

# 按标签分页
page = g.get_nodes_by_label("DemoPerson", limit=10, offset=0)
# page.items -> [GraphNode, ...]   page.total -> 总数

# 按标签 + 属性查找（需对应属性已建索引，否则 Nebula 报 IndexNotFound）
page = g.find_nodes(["DemoPerson"], {"name": "Alice"})

# 更新属性
alice = g.update_node("Alice", {"age": 31, "city": "深圳"})

# 删除（detach=True 同时删除关联边）
g.delete_node("Alice", detach=True)

# 批量创建
g.batch_create_nodes(
    [{"name": f"P_{i}", "age": 20 + i} for i in range(5)],
    ["DemoPerson"],
)
```

> **索引与扫描的坑**：Nebula 的 `MATCH (n:Tag) RETURN n`（即 `get_nodes_by_label`/`find_nodes`）依赖 TAG 索引扫描。若只建了**属性索引**（如 `ON DemoPerson(name(256))`），则**缺该属性的顶点不会被扫到**。需要枚举某 TAG 的全部顶点时，建一个**空索引**：`CREATE TAG INDEX IF NOT EXISTS dp_full_idx ON DemoPerson();`（边同理用 `ON EdgeType()`）。`find_nodes` 按属性过滤时则用对应属性的索引。

### 边 CRUD

边 id 形如 `"sourceId->targetId@ranking"`。

```python
# 创建（INSERT EDGE，rank=0，同源同目标同 rank 为 upsert）
edge = g.create_edge("Alice", "bob", "DemoKnows", {"since": 2020})
# edge.id == "Alice->bob@0"

# 幂等创建/更新
edge = g.merge_edge("Alice", "bob", "DemoKnows",
                    identity_props={"since": 2020},
                    properties={"level": "close"})

# 按 id 获取（不存在返回 None）
edge = g.get_edge("Alice->bob@0", edge_type="DemoKnows")

# 按类型分页
page = g.get_edges_by_type("DemoKnows", limit=10)

# 按类型 + 属性查找（需边属性已建索引）
page = g.find_edges("DemoKnows", {"since": 2020})

# 更新属性
edge = g.update_edge("Alice->bob@0", {"level": "best"}, edge_type="DemoKnows")

# 删除
g.delete_edge("Alice->bob@0", edge_type="DemoKnows")

# 批量创建
g.batch_create_edges(
    [{"sourceId": "Alice", "targetId": f"P_{i}", "weight": i} for i in range(3)],
    "DemoKnows",
)
```

### 图遍历

```python
# 邻居节点（direction: "out" / "in" / "both"）
nbrs = g.get_neighbours("Alice", direction="out", edge_type="DemoKnows", limit=20)

# 节点的边
edges = g.get_node_edges("Alice", direction="both", edge_type="DemoKnows", limit=20)

# 最短路径
path = g.shortest_path("Alice", "bob", edge_type="DemoKnows", max_depth=10)
# path.nodes -> [GraphNode, ...]   path.edges -> [GraphEdge, ...]   无路径返回 None
```

### nGQL 透传（execute_query / execute_read / execute_write）

DDL（CREATE/ALTER TAG/EDGE/SPACE）走 nGQL。注意 Nebula 属性投影需用 tag 限定写法 `n.Tag.prop`（`n.prop` 返回空）。


```python
# 通用查询
r = g.execute_query('MATCH (n:DemoPerson) WHERE id(n)=="Alice" RETURN n LIMIT 1;')
# r.records -> [{"n": {"id":..., "labels":..., "properties":...}}, ...]

# 只读
r = g.execute_read("RETURN 1+1 AS two;")

# 写入 / DDL（CREATE SPACE 后有传播延迟，后续 DDL 可能瞬态失败，需重试）
g.execute_write('CREATE TAG IF NOT EXISTS DemoPerson(name string, age int, city string, demo_id string);')
g.execute_write('CREATE EDGE IF NOT EXISTS DemoKnows(since int, level string, weight int);')
g.execute_write('ALTER EDGE EMPLOYED_BY ADD (tech_field string);')
```

### Schema 管理

```python
from infra.graph_db import GraphIndexSpec, GraphConstraintSpec

# 创建索引（string 属性自动补长度(256)）
g.create_index(GraphIndexSpec(label="DemoPerson", properties=["name"], unique=False))

# 列出 / 删除索引
g.list_indexes(label="DemoPerson")
g.drop_index("DemoPerson", ["name"])

# 约束（服务端映射为 TAG INDEX）
g.create_constraint(GraphConstraintSpec(
    name="demo_person_name_unique", label="DemoPerson", property="name", kind="unique"))
g.list_constraints()
g.drop_constraint("demo_person_name_unique")

# 统计与元信息
g.node_count(label="DemoPerson")   # 按标签计数
g.edge_count(edge_type="DemoKnows")  # 按类型计数
g.labels()                          # 所有 TAG
g.edge_types()                      # 所有 EDGE
```

### 关闭连接

正常由 `main.py` lifespan 在关闭时调用；如需手动：

```python
from infra.graph_db import close_techkg_client, close_trs_graph_client
close_techkg_client()
close_trs_graph_client()
```

## 运行测试

```bash
cd backend
uv run ruff format .          # 格式化
uv run ruff check .           # lint（自动修：--fix）
uv run pytest                 # 全部
PYTHONPATH=. uv run pytest tests -m "not external" -v   # CI 跑的（不依赖真实服务）
```

- `external` 标记：需要真实 MySQL/Redis/TRSGraph/Kafka/Milvus 的测试，CI 用 `-m "not external"` 跳过。
- 图客户端单测用 `httpx.MockTransport` 打桩 trs-graph REST，无需真实服务。
- 集成测试用 `tests/conftest.py` 的 `async_client` fixture（ASGI transport 打 `main.app`）。

## 项目结构

```
tech-kg-api/                       # monorepo 根
├── backend/                       # FastAPI 后端
│   ├── main.py                    # 入口（lifespan + 路由注册）
│   ├── biz/                       # handler / schemas / router
│   ├── application/               # 编排层
│   ├── service/                   # 业务逻辑 + module_catalog
│   ├── dao/                       # MySQL 查询对象
│   ├── db_model/                  # SQLAlchemy ORM
│   ├── infra/                     # mysql / redis / llm / graph_db
│   │   └── graph_db/              # TRSGraphClient（trs-graph REST 封装）
│   ├── script/                    # init_db / init_graph_schema / load_graph ETL
│   ├── schemas/ddl                # 建表 SQL
│   ├── tests/                     # unit + integration
│   └── .env.example
├── frontend/                      # Vue 3 + TS + Vite（单页 App.vue）
│   ├── Dockerfile / nginx.conf
│   └── src/App.vue
└── docker-compose.yml             # api(8001) + web(8088)
```

## 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `TRS_GRAPH_BASE_URL` | `http://localhost:8090` | trs-graph-service 地址 |
| `TRS_GRAPH_SPACE` | `entity_binding_demo` | 图空间（`get_techkg_client` 固定 `techkg`，忽略此项） |
| `TRS_GRAPH_API_KEY` | — | `X-API-Key` 认证（必填） |
| `TRS_GRAPH_TIMEOUT` | `30` | 请求超时（秒） |
| `MYSQL_HOST` / `MYSQL_PORT` | `127.0.0.1` / `3306` | MySQL 连接 |
| `MYSQL_DATABASE` / `MYSQL_USERNAME` / `MYSQL_PASSWORD` | `techkg` / `root` / — | MySQL 库/账密 |
| `LLM_API_KEY` | — | 智谱 GLM key；未配置时 #3 自动降级 |
| `LLM_MODEL` | `glm-4.7-flash` | LLM 模型（推理模型，读 `message.content`） |
| `LLM_BASE_URL` | `https://open.bigmodel.cn/api/paas/v4` | LLM 接口地址 |

