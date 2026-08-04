# Tech KG API Backend

FastAPI 后端，负责知识图谱构建、Schema 管理、任务控制、人工审核、算子管理和图谱查询。

## 开发

```bash
uv sync --dev
cp .env.example .env
uv run uvicorn main:app --reload
```

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -m "not external"
```

Python 版本为 `>=3.11.13,<3.12`。默认 API 地址为 `http://localhost:8000`，健康检查为 `GET /health`。

## 分层

```text
main.py                         # create_app + lifespan
biz/
├── errors.py                   # 统一错误响应
├── handler/                    # FastAPI 路由
├── router/register.py          # 声明式路由清单
└── schemas/                    # Pydantic 模型
application/                    # 用例编排
service/                        # 业务规则与工作流
dao/                            # SQLAlchemy 查询对象
db_model/                       # ORM 模型
infra/                          # 外部客户端与生命周期
script/                         # 初始化、索引、ETL、Worker
schemas/                        # DDL 与图谱规范
tests/                          # unit + integration
```

约定：

- handler 只解析协议和映射错误，不承载业务逻辑。
- 数据模型统一放在 `biz/schemas/`，不再使用并行的 `biz/schema/`。
- 同步数据库、图服务或 CPU 工作使用普通 `def` handler，由 FastAPI 在线程池执行。
- 只有包含真实 `await` 的 handler 使用 `async def`。
- service 通过 DAO 访问 MySQL；跨服务编排放在 application 层。
- 外部客户端惰性创建，由 `infra/lifecycle.py` 在关闭时统一释放。

## 响应和状态码

成功和错误均使用：

```json
{"code": 200, "success": true, "data": {}, "msg": "success"}
```

`code` 与 HTTP 状态码保持一致。常见状态：

| HTTP | 场景 |
| --- | --- |
| `200` | 同步查询或更新成功 |
| `201` | 资源创建成功 |
| `202` | 工作流或任务已受理 |
| `400` | 业务输入或脚本错误 |
| `403` | 权限不足 |
| `404` | 资源不存在 |
| `409` | ID、名称或版本冲突 |
| `422` | Pydantic 参数校验失败 |
| `502` | 图服务或对象存储等上游失败 |

异步接口返回 `statusUrl`；客户端应轮询该地址，而不是把受理响应视为执行完成。

## 工作流与任务

任务控制面使用 SQLite 保存批次、任务、执行和 Schedule 快照，Temporal 负责实际调度。

- 即时触发会同步创建批次和任务记录。
- 任务 `kind` 根据实体/关系参数生成，`dataDomain` 根据请求业务域生成。
- 客户端指定的 `workflowId` 必须唯一；重复请求返回 `409`。
- Temporal 不可用时记录为 `LOCAL_FALLBACK/QUEUED`。
- API lifespan 会启动补偿下发器，按 `WORKFLOW_RETRY_INTERVAL_SECONDS` 重试排队记录。
- Worker 在工作流完成、失败或取消时通过 Activity 主动回写 execution、task 和 batch。
- `GET /workflow-system/executions/{id}/status` 仍可用于实时校验和故障恢复。

回写使用同一个 SQLite 事务更新 execution、task 和 batch；SQLite 启用 WAL 和 busy timeout。

## Schema 脚本

Schema 创建或更新时会把 Python 脚本保存到 S3。脚本需定义：

```python
def transform(payload):
    return payload
```

`POST /api/v1/schema-management/schemas/{id}/execute` 将固定的 bucket、object key 和 sha256 绑定到 `kg.schema.execute` 工作流。Worker 下载该版本脚本，并在隔离子进程中执行 `transform(payload)`。

这只是进程隔离，不是安全沙箱。上传和执行接口必须受严格授权保护。

`kg.schema.execute` 在转换后调用受控持久化 Activity：实体结果创建/合并节点，关系结果校验端点后创建边。Activity 根据 Schema 属性创建缺失的 TAG/EDGE，上传脚本本身不持有图数据库凭据。

## 配置

运行时读取 `.env` 和环境变量；`config/config_*.yml` 为 legacy，不由应用加载。

关键变量：

| 变量 | 说明 |
| --- | --- |
| `MYSQL_*` | 默认业务数据库 |
| `GKX_ELEMENT_MYSQL_*` | 机构 ETL 只读数据源 |
| `TRS_GRAPH_*` | trs-graph-service 地址、空间和 API key |
| `SCHEMA_S3_*` | Schema 脚本对象存储 |
| `OPERATOR_S3_*` | 用户算子对象存储 |
| `TEMPORAL_*` | Temporal 地址、namespace 和 task queue |
| `WORKFLOW_DATABASE_PATH` | 控制面 SQLite 文件 |
| `WORKFLOW_RETRY_INTERVAL_SECONDS` | 降级任务补偿间隔，默认 30 秒 |
| `MILVUS_*` | 向量数据库 |
| `LLM_*` | 可选模型服务；未配置 key 时业务降级 |

## 认证边界

当前代码没有统一认证中间件。生产部署必须由网关完成：

- 身份认证与角色授权；
- 覆盖并注入可信的 `X-User-Id`；
- 上传和脚本执行接口访问控制；
- 审计日志、限流、请求体大小限制；
- 内部算子重载接口的网络隔离和令牌校验。

接口细节见 `docs/`。

## 已知边界

- 工作流控制面使用本地 SQLite，适合单实例或开发环境；多副本部署应迁移到共享数据库。
- 上传脚本采用子进程隔离而非容器级安全沙箱，生产环境仍应使用受限 Worker。

六个原说明型模块的执行契约见 `docs/kg_modules_api.md`。
