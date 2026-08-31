# 环境变量参考

> 来源：根/backend `README.md` · `docker-compose*.yml` · `CLAUDE.md`。配置统一走 env / `.env`（python-dotenv）；`backend/config/*.yml` 是遗留文件，**不加载**。

## 图数据库（trs-graph）

| 变量 | 说明 |
|---|---|
| `TRS_GRAPH_BASE_URL` | trs-graph REST 地址（默认 `http://localhost:8090`） |
| `TRS_GRAPH_SPACE` | 默认图空间（`get_trs_graph_client()` 用；`get_techkg_client()` 固定 techkg） |
| `TRS_GRAPH_API_KEY` | `X-API-Key` |
| `TRS_GRAPH_TIMEOUT` | 请求超时 |

## MySQL / Milvus

| 变量 | 说明 |
|---|---|
| `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USERNAME` / `MYSQL_PASSWORD` | 连接（脚本路径与 SDK env 驱动路径共用这套） |
| `MILVUS_URI` 或 `MILVUS_HOST` + `MILVUS_PORT` | `MilvusClient` 单例（容器内跑 Milvus 相关脚本需 `docker exec -e MILVUS_URI=...` 显式传入） |

## LLM / embedding

| 变量 | 说明 |
|---|---|
| `LLM_API_KEY` / `ZHIPUAI_API_KEY` | 未配置 → `get_llm_client()` 返回 `None`，调用方降级 |
| `PATENT_EMBEDDING_BASE_URL` | 专利 m3e embedding（默认 `http://m3e-embedding:8010/v1`） |

## 认证

| 变量 | 说明 |
|---|---|
| `AUTH_ENABLED` | 总开关；false = dev 上下文、admin 放行 |
| `AUTH_SESSION_COOKIE` | session cookie 名（`techkg_session`） |
| `AUTH_SESSION_BACKEND` | `redis` |
| `USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED` | 门户 SSO 开关（生产 true） |
| `PLATFORM_BOOTSTRAP_FIRST_ADMIN` / `PLATFORM_INITIAL_ADMIN_USER_IDS` | 首管理员引导 |

## 工作流 / 任务 / 脚本 SDK

| 变量 | 说明 |
|---|---|
| `TEMPORAL_ADDRESS` | Temporal server |
| `WORKFLOW_DATABASE_PATH` | SQLite 控制面路径（`var/` 下） |
| `KG_SCRIPT_CTX` | activity 向脚本子进程注入的 Context 连接参数（JSON） |
| `KG_ACCESS_LOG` | 访问溯源 sidecar 临时文件路径 |

## Schema / 修正 / 缓存

| 变量 | 说明 |
|---|---|
| `SCHEMA_S3_*` | schema 脚本对象存储 |
| `SCHEMA_AUTO_INIT` | 启动播种 schema catalog |
| `CORRECTION_SYNC_WORKER_ENABLED` / `CORRECTION_SYNC_INTERVAL_SECONDS` | 修正同步 dispatcher |
| `RESULT_CACHE_TTL` | 结果缓存 TTL（600s） |
| `PREWARM_BUSINESS` | 启动预热九模块缓存 |

## 前端（构建期）

| 变量 | 默认 | 说明 |
|---|---|---|
| `VITE_BASE` | `./` | 部署基路径（dev2 构建传 `/`；文档站 base 由它推导） |
| `VITE_API_BASE` | `/api` | API 前缀 |
| `VITE_API_TARGET` | `http://localhost:8100` | dev 代理目标 |
| `VITE_GRAPH_SPACE` | `test` | 默认图空间 |
| `VITE_AUTH_ENABLED` | `false` | 前端鉴权开关 |
| `VITE_PORTAL_EMBEDDED_DEFAULT` / `VITE_PORTAL_ALLOWED_ORIGINS` / `VITE_PORTAL_TARGET_ORIGIN` / `VITE_PORTAL_SOURCE` | — | 门户 iframe 嵌入配置 |

## 后端工具链

Python `>=3.11.13,<3.12`（Docker 用 `python:3.11-slim`）；ruff `line-length=100`（E501 不启用）；pytest `asyncio_mode=auto`，CI 跑 `-m "not external"`。
