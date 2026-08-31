# 图数据库：trs-graph（NebulaGraph）

> 来源：`CLAUDE.md` graph_db 节 · 根 `README.md` · `backend/docs/rebuild_graph_data_scripts.md`

图是 **NebulaGraph**，通过 **trs-graph-service**（Java Spring Boot REST API，默认 `http://localhost:8090`）HTTP 访问：

- 认证：`X-API-Key` 头；图空间：`X-Graph-Space` 头；
- ORM 风格客户端：`infra/graph_db/client.TRSGraphClient`；
- 两个线程安全懒加载单例（`infra/graph_db/__init__.py`）：`get_trs_graph_client()`（空间来自 `TRS_GRAPH_SPACE` env）与 `get_techkg_client()`（固定 `techkg`）。首次使用才连接；`main.py` lifespan 关闭时调 `close_*_client()`。

## 节点与边 CRUD（全 REST）

节点：`create_node` / `merge_node` / `update_node` / `delete_node` / `get_node` / `get_nodes_by_label` / `find_nodes`（返回真实 vid，不是 UUID）。边：`create_edge` / `update_edge` / `get_edge` / `get_node_edges` / `get_edges_by_type`。

::: warning 属性必须匹配 schema
`merge_node` / `create_node` 发送的属性必须完全匹配目标 Tag 的 schema——未知列返回 `400 SemanticError: Unknown column 'X' in schema`。写入前用 `DESCRIBE TAG <label>`（经 `execute_query`）列出合法属性。已在 dev2 空间对 Paper tag 全量验证（create/get/update/delete/merge/find，2026-08-25）。
:::

## nGQL 与 DDL

DDL（`CREATE/ALTER TAG/EDGE/SPACE`）走 nGQL：`execute_query` / `execute_write` / `execute_read`。注意 **schema 传播延迟**：`CREATE SPACE` 后紧跟的 DDL 可能短暂 500，重试即可。

## 配置

`TRS_GRAPH_*` 环境变量（`BASE_URL` / `SPACE` / `API_KEY` / `TIMEOUT`），见 `infra/graph_db/config.py`。

## ETL / 重建脚本

`backend/script/` 与 `backend/organization_ETL/`：

- `init_graph_schema.py` —— `CREATE SPACE techkg` + Scholar/Organization/`EMPLOYED_BY` DDL；
- `load_graph.py` —— MySQL → techkg ETL（幂等 merge 节点/边）；
- `init_db.py` —— MySQL schema 初始化；
- 按域 ETL：`organization_*`、`load_scholar_*`、`load_patent_*`、`load_project_*`、`load_paper_journal_graph.py`；部分构建 Milvus 索引（`build_*_milvus_index.py`）。

容器内跑 ETL 时 Milvus/MySQL env 需显式传入（`docker exec -e MILVUS_URI=... tech-kg-api ...`）。抽取脚本 SDK 的写入约定（VID/rank/merge 保护）见 [SDK 文档](/sdk/context)。
