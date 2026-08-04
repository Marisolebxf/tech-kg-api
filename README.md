# tech-kg-api

科技知识图谱 monorepo：FastAPI 后端、Vue 3 前端，以及本地开发所需的 Temporal、Milvus 和 S3 兼容对象存储。

## 快速开始

环境要求：Python 3.11、[uv](https://docs.astral.sh/uv/)、Node.js 20+、pnpm 和 Docker Compose。

```bash
# 完整环境
docker compose up --build

# 后端本地开发
cd backend
uv sync --dev
cp .env.example .env
uv run uvicorn main:app --reload

# 前端本地开发
cd frontend
pnpm install
pnpm dev
```

默认地址：

| 服务 | 地址 |
| --- | --- |
| Web | `http://localhost:8088` |
| API | `http://localhost:8001` |
| OpenAPI | `http://localhost:8001/docs` |
| Temporal UI | `http://localhost:8233` |
| Health | `http://localhost:8001/health` |

后端依赖外部 MySQL 和 trs-graph-service。连接信息通过 `backend/.env` 或部署环境变量提供；不要把真实账号、密码和公网地址写入仓库。

## 后端结构

请求链路：

```text
main.py
  -> biz/router/register.py
  -> biz/handler/*
  -> application/*
  -> service/*
  -> dao/* + db_model/* + infra/*
```

| 目录 | 职责 |
| --- | --- |
| `backend/biz/handler/` | FastAPI 路由；同步业务使用 `def`，真正异步的 I/O 使用 `async def` |
| `backend/biz/schemas/` | Pydantic 请求和响应模型 |
| `backend/application/` | 跨服务用例编排 |
| `backend/service/` | 业务规则、工作流和图谱能力 |
| `backend/dao/` | SQLAlchemy 数据访问 |
| `backend/db_model/` | ORM 模型 |
| `backend/infra/` | MySQL、S3、Milvus、LLM、TRSGraph 等客户端及生命周期 |
| `backend/script/` | 初始化、索引和 ETL 脚本 |
| `backend/tests/` | unit 与 integration 测试 |

应用由 `main.create_app()` 创建。路由采用声明式注册；进程关闭时会统一释放数据库连接池和外部客户端。

## API 契约

除 `/health` 外，业务接口位于 `/api/v1`。JSON 响应统一使用：

```json
{
  "code": 200,
  "success": true,
  "data": {},
  "msg": "success"
}
```

错误同样使用该结构，并返回真实 HTTP 状态码：参数错误 `422`、未找到 `404`、冲突 `409`、上游图服务错误 `502`、未知错误 `500`。

异步受理接口返回 HTTP `202`，响应包含 `taskId`、`executionId`、`workflowId` 和 `statusUrl`。主要接口：

- `POST /api/v1/task-center/trigger`
- `POST /api/v1/workflow-system/definitions/{id}/execute`
- `POST /api/v1/workflow-system/schedules/{id}/trigger`
- `POST /api/v1/schema-management/schemas/{id}/execute`
- `GET /api/v1/workflow-system/executions/{id}/status`

详细契约见：

- [后端说明](backend/README.md)
- [工作流 API](backend/docs/workflow_operations_api.md)
- [Schema 管理 API](backend/docs/schema_management_api.md)
- [KG 构造模块 API](backend/docs/kg_modules_api.md)
- [算子注册](backend/docs/operator_registry.md)

## 基础设施

- 图数据库：NebulaGraph，经 trs-graph-service HTTP API 访问。
- 业务数据：MySQL。
- 工作流：Temporal；API 进程负责控制面，`temporal-worker` 执行 Workflow 和 Activity。
- Schema 脚本：S3 兼容存储中的 Python 文件。
- 用户算子：独立 S3 兼容存储，支持热更新。
- 向量检索：Milvus；M3E 服务提供 512 维嵌入。

Schema 脚本和用户工作流脚本会执行 Python 代码，只能向受信任用户开放。生产环境必须在网关层完成认证、授权、审计、限流和上传访问控制，并建议把脚本执行 Worker 放入受限容器。

## 验证

```bash
cd backend
uv run ruff format --check .
uv run ruff check .
uv run pytest -m "not external"

cd ../frontend
pnpm build
```

需要真实 MySQL、TRSGraph、Temporal 或 Milvus 的测试使用 `external` 标记，不进入默认 CI 测试集。
