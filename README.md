# tech-kg-api

亿级知识图谱 API 接口仓库

## 环境要求

- Python 3.11+
- [uv](https://docs.astral.sh/uv/)

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Marisolebxf/tech-kg-api.git
cd tech-kg-api
```

### 2. 安装依赖

```bash
uv sync
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，设置 Neo4j 密码
# GRAPH_DB_PASSWORD=<your_password>
```

### 4. 启动服务

```bash
uv run uvicorn app.main:app --reload
```

启动后访问：

- <http://localhost:8000/hello>
- <http://localhost:8000/api>
- <http://localhost:8000/docs> （自动生成的接口文档）

## Neo4j GraphRAG Demo

项目内置了一个基于 Neo4j 的 GraphRAG demo，路径如下：

- `GET /api/v1/graphrag/demo/overview`
- `POST /api/v1/graphrag/demo/init`
- `POST /api/v1/graphrag/demo/query`

建议流程：

```bash
# 1) 先准备 Neo4j，并在 .env 中填好连接信息
cp .env.example .env

# 2) 启动服务
uv run uvicorn app.main:app --reload

# 3) 初始化 demo 图谱
curl -X POST http://localhost:8000/api/v1/graphrag/demo/init \
  -H "Content-Type: application/json" \
  -d '{"reset": true}'

# 4) 发起查询
curl -X POST http://localhost:8000/api/v1/graphrag/demo/query \
  -H "Content-Type: application/json" \
  -d '{"query": "GraphRAG 和普通向量检索有什么区别？", "top_k": 3}'
```

这个 demo 采用的是一个轻量 GraphRAG 流程：

1. 文本 chunk 存入 Neo4j，并附带一个本地 hash embedding
2. 查询时先做 chunk 相似度召回
3. 再沿 `MENTIONS` 和 `RELATED_TO` 关系做一跳图扩展
4. 最后返回证据块、相关实体和拼接答案

## 运行测试

```bash
uv run pytest
```

## 项目结构

```
tech-kg-api/
  ├── app/                    # FastAPI 主服务
  │   ├── main.py             # 主入口
  │   ├── routers/            # HTTP 路由
  │   ├── schemas/            # 请求/响应模型
  │   └── services/           # 业务逻辑
  ├── graph_db/               # 图数据库 service 层
  │   ├── services/           # Service 类（NodeService, EdgeService 等）
  │   ├── backends/           # 后端实现（Neo4j）
  │   ├── query/              # Cypher 查询构建器
  │   ├── base.py             # 抽象基类
  │   ├── config.py           # 配置 & 连接工厂
  │   └── models.py           # 数据模型
  ├── tests/
  ├── .env.example            # 环境变量模板
  └── pyproject.toml
```

## graph_db Service 层

`graph_db` 是项目内的图数据库操作服务层，封装了节点、边、遍历、查询、Schema 等 CRUD 操作，供 `app/` 中其他服务调用。

### 连接数据库

```python
from graph_db import connect, GraphDBConfig

db = connect(GraphDBConfig.from_env())
```

或直接指定参数：

```python
db = connect(GraphDBConfig(
    uri="bolt://localhost:7687",
    username="neo4j",
    password="your_password",
))
```

### 节点操作（NodeService）

```python
from graph_db.services import NodeService

nodes = NodeService(db)

# 创建
alice = nodes.create(["Person"], {"name": "Alice", "age": 30})

# 幂等创建/更新
bob = nodes.merge(["Person"], {"name": "Bob"}, {"age": 25})

# 按 ID 获取
node = nodes.get(alice.id)

# 按标签列表
result = nodes.list_by_label("Person", limit=10, offset=0)

# 按标签 + 属性查找
result = nodes.find(["Person"], {"name": "Alice"})

# 更新属性
nodes.update(alice.id, {"age": 31, "city": "北京"})

# 删除（detach=True 同时删除关联关系）
nodes.delete(alice.id, detach=True)

# 批量创建
result = nodes.batch_create(
    [{"name": f"Person_{i}", "age": 20 + i} for i in range(100)],
    labels=["Person"],
)
```

### 关系操作（EdgeService）

```python
from graph_db.services import EdgeService

edges = EdgeService(db)

# 创建
edge = edges.create(alice.id, bob.id, "KNOWS", {"since": 2020})

# 幂等创建/更新
edge = edges.merge(
    alice.id, bob.id, "KNOWS",
    identity_props={"since": 2020},
    properties={"level": "close"},
)

# 按 ID 获取
edge = edges.get(edge.id)

# 按类型列表
result = edges.list_by_type("KNOWS", limit=10)

# 按类型 + 属性查找
result = edges.find("KNOWS", {"since": 2020})

# 更新属性
edges.update(edge.id, {"level": "best"})

# 删除
edges.delete(edge.id)

# 批量创建
result = edges.batch_create(
    [{"source_id": alice.id, "target_id": bob.id, "weight": i} for i in range(10)],
    edge_type="LINKS",
)
```

### 图遍历（TraversalService）

```python
from graph_db.services import TraversalService

traversal = TraversalService(db)

# 邻居节点（direction: "out" / "in" / "both"）
neighbours = traversal.neighbours(alice.id, direction="out", edge_type="KNOWS", limit=20)

# 节点的边
node_edges = traversal.node_edges(alice.id, direction="both", limit=20)

# 最短路径
path = traversal.shortest_path(alice.id, bob.id, edge_type="KNOWS", max_depth=10)
# path.nodes -> [Node, ...]
# path.edges -> [Edge, ...]
```

### Cypher 查询（QueryService）

```python
from graph_db.services import QueryService

query = QueryService(db)

# 通用查询
result = query.execute(
    "MATCH (n:Person) WHERE n.age > $age RETURN n.name AS name",
    params={"age": 25},
)
# result.records -> [{"name": "Alice"}, ...]

# 只读查询（可路由到读副本）
result = query.read("MATCH (n) RETURN count(n) AS total")

# 写入查询（自动重试瞬态错误）
result = query.write("CREATE (n:Test {ts: timestamp()}) RETURN n")
```

### Schema 管理（SchemaService）

```python
from graph_db.services import SchemaService
from graph_db.models import IndexSpec, ConstraintSpec

schema = SchemaService(db)

# 创建索引
schema.create_index(IndexSpec(label="Person", properties=["name"], unique=False))

# 创建唯一约束
schema.create_index(IndexSpec(label="Person", properties=["name"], unique=True))

# 列出索引
indexes = schema.list_indexes()

# 删除索引
schema.drop_index(label="Person", properties=["name"])

# 创建约束
schema.create_constraint(ConstraintSpec(
    name="person_name_unique", label="Person", property="name", kind="unique",
))

# 列出约束
constraints = schema.list_constraints()

# 删除约束
schema.drop_constraint("person_name_unique")
```

### 数据库信息（SchemaService）

```python
schema = SchemaService(db)

schema.node_count()                          # 节点总数
schema.node_count(label="Person")            # 按标签计数
schema.edge_count()                          # 边总数
schema.edge_count(edge_type="KNOWS")         # 按类型计数
schema.labels()                              # 所有标签
schema.edge_types()                          # 所有关系类型
```

### 关闭连接

```python
db.close()
```

## 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `GRAPH_DB_BACKEND` | `neo4j` | 图数据库后端类型 |
| `GRAPH_DB_URI` | `bolt://localhost:7687` | 数据库连接 URI |
| `GRAPH_DB_USERNAME` | `neo4j` | 数据库用户名 |
| `GRAPH_DB_PASSWORD` | — | 数据库密码（必填） |
| `GRAPH_DB_DATABASE` | `neo4j` | 目标数据库名 |
| `GRAPH_DB_MAX_CONNECTION_POOL_SIZE` | `50` | 连接池大小 |
| `GRAPH_DB_CONNECTION_TIMEOUT` | `30` | 连接超时（秒） |
