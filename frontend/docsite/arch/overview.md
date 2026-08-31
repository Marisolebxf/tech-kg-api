# 总体架构与 DDD 分层

> 来源：根 `CLAUDE.md` · 根/backend `README.md`

本仓库是 monorepo：`backend/`（Python FastAPI）+ `frontend/`（Vue 3 + TS + Vite）。顶层 `docker-compose.yml` 构建并运行两个应用及配套基础设施（Milvus+etcd+MinIO、RustFS、schema MinIO、m3e-embedding、auth-redis、Temporal）。

## 请求流（后端 DDD 五层）

```text
main.py → biz/router/register.py → biz/handler/* → application/* → service/* → dao/* + db_model/* + infra/*
```

| 层 | 职责 |
|---|---|
| `biz/handler/` | FastAPI `APIRouter`——**路由唯一定义处**，由 `biz/router/register.py` 挂载到 `/api/v1`。Handler 很薄：解析请求 → 调 application → 返回响应 |
| `biz/schemas/` | Pydantic v2 请求/响应模型，一个模块一个文件；`common.py` 是 `ApiResponse` 信封 |
| `application/` | 薄编排层，一个领域模块一个类，包一个 service |
| `service/` | 业务逻辑。每个图谱构建模块继承 `service/base_module.KGModuleScaffoldService`（设 `module_code`，从 `service/module_catalog.py` 继承 `describe()`）；catalog 是九个图谱构建模块的注册表 |
| `dao/` | MySQL 查询对象（如 `ScholarDAO`），每个持有一个 SQLAlchemy `Session`；`dao/sql/` 存原生 SQL 片段 |
| `db_model/` | SQLAlchemy ORM 模型（都继承 `db_model/base.Base`），一个表族一个文件 |
| `infra/` | 基础设施单例，全部从 env / `.env`（python-dotenv）读配置 |

## 路由分组

Router 分三组：**protected**（依赖 `require_authenticated_user`）、**admin**（再加 `require_platform_admin`）、**internal**（无鉴权：`manual_review_internal`、`operator` internal）。

## infra/ 基础设施一览

| 模块 | 说明 |
|---|---|
| `mysql.py` | 同步 SQLAlchemy engine + `get_mysql_client()` / `session_scope()` |
| `redis.py` / `llm.py` | Redis 单例 / LLM 客户端（进程单例，未配 key 返回 `None`，调用方降级） |
| `gkx.py` / `gkx_element.py` | 供应商源库 `gkx_local` 与 `gkx_element` 的**只读** session factory（显式只读事务，禁止写） |
| `graph_db/` | trs-graph 客户端（见[图数据库](/arch/graph)） |
| `graph_api_client.py` | 部分旧 ETL 脚本用的底层 HTTP 客户端 |
| `milvus.py` | `MilvusClient` 单例 + `OrganizationMilvusStore`（懒加载 pymilvus） |
| `s3.py` | 通用 boto3 S3 包装（MinIO 兼容）；`operator_store.py` 把用户算子包持久化到 S3（RustFS） |
| `result_cache.py` | 进程内预序列化 JSON 响应缓存（见[性能优化](/arch/perf)） |
| `user_center.py` | 统一用户中心 OAuth2 客户端 |

其他目录：`operators/`（`scholar/` 内置算子源码 + `user/` 运行时缓存，gitignored）、`organization_ETL/` + `script/`（ETL 脚本与 worker）、`schemas/`（nGQL DDL/spec 文件）、`var/`（SQLite 工作流 DB 等运行态）。

## 新增一个图谱构建功能

一个功能 = 五层各一份（schemas + handler + application + service + dao/model 按需），再：

1. 在 `biz/router/register.py` 注册 router；
2. 在 `service/module_catalog.py` 加模块条目。

「重点关注科技企业关系子系统」（`expert_enterprise_relation` / `relation_detail_annotation` / `enterprise_background_analysis` + 共享 catalog 与 options 端点）是最完整的参考实现。

## 前端结构

Vue 3 + TS + Vite + pnpm，element-plus + arco-design/web-vue + vue-flow（图画布）+ echarts；API 客户端在 `src/api/`：

- `views/business-service/` —— 九个图谱构建子功能路由（`/expert-direct`、`/enterprise-relation` 等）；
- `views/platform/` —— 工作台总览、图谱构建、运营中心、人工审核工作台、流程实例详情；
- `views/admin/` —— 修正中心、成员管理；
- `views/auth/` —— 登录、用户中心、账号安全、操作日志；
- `stores/auth.ts` —— 认证状态；`portal/iframeBridge.ts` —— 门户 iframe 嵌入时桥接门户登录态。

开发代理：`/api` → `VITE_API_TARGET`（默认 `http://localhost:8100`）；生产 nginx 反代 `/api/` → `http://api:8000`。
