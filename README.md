# tech-kg-api

科技知识图谱构建服务 Monorepo：统一后端 API（Python / FastAPI）+ 前端工作台（Vue 3）。

本项目面向「知识图谱构建服务」的 9 个业务模块，提供算法测试、结构化结果预览、API 示例与开发者文档。后端采用 DDD 分层架构，并通过 integration 层挂载历史模块路由，前端为统一的单页应用（SPA）。

## 功能概览

| 模块 | 状态 | 说明 |
|------|------|------|
| 科技专家直接关系 | **已接入** | 直接关系 / 两跳 / 三跳关系构建 |
| 专家论文合作关系 | **已接入** | 基于论文作者、主题、被引等构建合作网络 |
| 重点科技企业关系 | **已接入** | 专家与企业任职、合作、技术关联 |
| 科技节点间接关系 | 脚手架 | 演示数据 + 预留 API |
| 科技两点合作成果 | 脚手架 | 演示数据 + 预留 API |
| 科技专家同事关系 | 脚手架 | 演示数据 + 预留 API |
| 科技专家校友关系 | 脚手架 | 演示数据 + 预留 API |
| 产业链点事件关系 | 脚手架 | 演示数据 + 预留 API |
| 科技产业链全景图 | 脚手架 | 演示数据 + 预留 API |

前端入口：`/`（构建后由后端静态托管，开发时独立启动 Vite dev server）。

## 环境要求

| 组件 | 版本 |
|------|------|
| Python | 3.11.x（见 `backend/pyproject.toml`） |
| [uv](https://docs.astral.sh/uv/) | 最新稳定版 |
| Node.js | 20+ |
| [pnpm](https://pnpm.io/) | 9.x |

可选依赖（按模块需要配置）：

- MySQL — 业务元数据
- TRSGraph / Nebula — 图数据库（专家关系、企业关系等）
- Redis、Kafka、Milvus — 缓存、消息、向量检索
- 智谱 AI 等 LLM 服务 — 部分智能分析能力

## 快速开始

### 1. 克隆仓库

```bash
git clone https://github.com/Marisolebxf/tech-kg-api.git
cd tech-kg-api
```

### 2. 配置环境变量

**切勿将 `.env` 提交到 Git。** 从模板复制后本地填写：

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env
```

根据实际部署修改数据库、图数据库、LLM 等连接信息。变量说明见 [`backend/.env.example`](backend/.env.example)。

### 3. 启动后端

```bash
cd backend
uv sync
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

常用地址：

- 健康检查：<http://localhost:8000/health>
- OpenAPI 文档：<http://localhost:8000/docs>
- 模块清单：`GET /api/v1/kg-construction/modules`

### 4. 启动前端（开发模式）

```bash
cd frontend
pnpm install
pnpm dev
```

默认开发地址：<http://127.0.0.1:8880>。Vite 会将 `/api` 代理到 `frontend/.env` 中的 `VITE_API_TARGET`。

### 5. 生产构建（可选）

```bash
cd frontend && pnpm build
cd ../backend && uv run uvicorn main:app --host 0.0.0.0 --port 8000
```

构建产物位于 `frontend/dist/`，后端 `main.py` 会自动挂载静态资源。

## Docker 部署

根目录提供 `docker-compose.yml`，可同时启动 API 与 Web 容器：

```bash
# 在项目根目录创建 .env，填入 TRS_GRAPH_*、MYSQL_* 等变量
docker compose up -d --build
```

默认映射：

- API：`8001` → 容器 `8000`
- Web：`8088` → 容器 `80`

## 主要 API 路由

### 知识图谱构建（脚手架 + 部分实现）

```
GET  /api/v1/kg-construction/modules
GET  /api/v1/kg-construction/modules/{module_code}
POST /api/v1/kg-construction/expert-enterprise-relations/build
```

### 专家直接关系（binding 模块）

```
GET /api/v1/binding/expert-direct-relation
GET /api/v1/binding/expert-direct-two-hop
GET /api/v1/binding/expert-direct-three-hop
```

### 专家论文合作（legacy 挂载）

```
POST /api/v1/scholar-paper-cooperation/demo/structured-result
POST /api/v1/scholar-paper-cooperation/demo/graph
```

### 通用选项

```
GET /api/v1/options/*
```

完整接口列表见 Swagger UI：`/docs`。

## 项目结构

```
tech-kg-api/
├── backend/
│   ├── main.py                 # FastAPI 入口，静态前端托管
│   ├── biz/                    # 接口层：handler + router
│   ├── application/            # 应用层：用例编排
│   ├── service/                # 领域层
│   ├── dao/                    # 数据访问
│   ├── infra/                  # MySQL、Redis、图数据库、LLM 等
│   ├── integration/            # 历史模块路由挂载（不修改 legacy 源码）
│   ├── legacy/                 # 历史模块代码
│   ├── schemas/                # 数据库 DDL
│   ├── tests/
│   └── .env.example
├── frontend/
│   ├── src/
│   │   ├── pages/kg-construction/   # 9 个模块页面
│   │   ├── layouts/                 # 统一布局与侧栏
│   │   ├── components/kg/           # 图谱、API 面板等组件
│   │   ├── composables/             # 图谱交互、视口适配
│   │   └── config/kg-modules.ts     # 模块注册表
│   └── .env.example
├── docker-compose.yml
└── README.md
```

后端分层与模块说明详见 [`backend/README.md`](backend/README.md)。

## 运行测试

```bash
cd backend
uv run pytest
```

CI 在 push / PR 到 `main` 时自动执行 Ruff 格式检查、Lint 与单元测试（见 `.github/workflows/`）。

## 开发说明

### 新增模块

1. 在 `backend/biz/handler/` 添加 handler，并在 `biz/router/register.py` 注册路由。
2. 在 `frontend/src/config/kg-modules.ts` 注册模块元数据（路由、子功能、API 路径）。
3. 在 `frontend/src/router/index.ts` 添加路由；`mode: 'live'` 接入真实页面，`mode: 'scaffold'` 使用演示页。

### Legacy 模块集成

历史模块通过 `backend/integration/legacy_mount.py` 动态挂载，无需修改 `legacy/` 内源码。当前已挂载：`scholar-paper-cooperation`。

### 前端图谱

共享工具位于 `frontend/src/utils/graph-layout.ts`、`graph-edges.ts`，交互逻辑在 `composables/useGraphNodeInteraction.ts` 与 `useAdaptiveGraphViewport.ts`。

## 安全提示

- `.env` 已在 `.gitignore` 中忽略，**请勿提交**含密码、API Key、内网地址的配置文件。
- 生产环境请通过密钥管理服务或 CI Secrets 注入敏感变量。
- `docker-compose.yml` 与 `.env.example` 仅提供占位符，不含真实凭据。

## License

内部项目，使用前请确认组织授权策略。
