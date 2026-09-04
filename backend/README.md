# Tech KG API Backend

后端采用 Python + FastAPI，实现知识图谱构建服务和数据访问层。

统一用户中心 OAuth2、Redis 会话和浏览器/第三方 API 鉴权的配置说明见
[`docs/auth_integration.md`](docs/auth_integration.md)。

## 环境和连接信息

当前后端已经从旧 Java/SpringBoot 方案迁移为 Python/FastAPI。开发环境默认连接服务器 MySQL 中的科技要素业务库 `gkx_element`。厂商源库 `gkx` 只用于只读同步；`gkx_local` 仅是部分历史模块可能显式指定的兼容库名，不是当前默认业务库。

### 实验室服务器 / Docker 开发环境

| 组件 | 本机访问地址 | Compose 服务名 | 账号 | 密码/说明 |
|---|---|---|---|---|
| MySQL 科技要素业务库 | `127.0.0.1:3306/gkx_element` | `mysql`（当前 dev 外部网络服务） | 由 `.env` 配置 | 项目 Compose 不创建该服务 |
| Redis | `127.0.0.1:6379`，DB `0` | `redis` | - | 无密码 |
| Kafka | `127.0.0.1:9092` | `kafka` | - | Consumer Group `techkg` |
| Milvus | `127.0.0.1:19530` | `milvus` | - | 无账号密码配置 |
| RustFS（schema 脚本 / 用户算子 / Milvus 内部存储共用） | API `127.0.0.1:9020`，控制台 `127.0.0.1:9021` | `operator-rustfs` | `rustfsadmin` | `rustfsadmin`，Python 通过 S3 API 使用，栈内不部署 MinIO |

后端直接在宿主机运行时，MySQL 地址通常使用 `127.0.0.1`；后端在项目 Compose 的 `api` 容器内运行时，通过外部 Docker 网络使用服务名 `mysql`。Milvus 使用 Compose 服务名 `milvus`，M3E 向量服务使用 `m3e-embedding`。实际连接值以 `.env` 和 Compose 的 `environment` 覆盖项为准。 后期环境若使用 `tdsql-mysql`，通过部署环境设置 `MYSQL_HOST=tdsql-mysql`，无需修改代码。

当前项目 Compose 不创建 MySQL；启动 API 前，应确认外部 Docker 网络中已有名为 `mysql` 的服务，并且其中已存在 `gkx_element`。宿主机直接运行后端时，则按实际端口连接该数据库。

### 远程数据源和服务器资源

| 组件 | 地址 | 账号 | 密码/说明 |
|---|---|---|---|
| 厂商源 MySQL | `<vendor-mysql-host>:<port>/<database>` | `<read-only-user>` | 密码通过安全的部署变量提供，不写入仓库 |
| 服务器管理库 | `<management-db-host>:<port>/<database>` | `<database-user>` | 密码通过安全的部署变量提供，不写入仓库 |
| 服务器 Redis | `<redis-host>:<port>`，DB `<index>` | - | 密码通过安全的部署变量提供，不写入仓库 |
| MongoDB | `<mongodb-host>:<port>/<database>` | `<mongodb-user>` | 密码通过安全的部署变量提供，不写入仓库 |
| ElasticSearch | `<elasticsearch-url>` | `<elasticsearch-user>` | 密码通过安全的部署变量提供，不写入仓库 |
| Nginx/GLM 网关 | `<gateway-url>` | - | 实际地址通过部署环境配置 |
| TRSGraph | `127.0.0.1:9669`（后端和 TRSGraph 同机时） | `root` | `trsadmin` |

TRSGraph 由外部 TRSGraph 服务提供，当前 Python 后端只负责连接。环境变量见 `.env.example`，分环境配置见 `config/config_dev.yml`、`config/config_stage.yml`、`config/config_product.yml`。

### 配置文件定位

“位置”指配置文件在当前仓库中的相对路径。旧 Java/SpringBoot 文档里的 `backend/src/main/resources/application*.yml` 是 Java 项目路径，当前 Python/FastAPI 后端没有这些文件，等价配置已经迁移到 `.env` 和 `config/config_*.yml`。

| 文件 | 位置 | 用途 |
|---|---|---|
| 后端入口 | `main.py` | 创建 FastAPI 应用、注册中间件和路由 |
| 后端环境变量 | `.env` | 本机或服务器直接启动后端时读取的实际连接信息，不提交 Git |
| 后端环境变量模板 | `.env.example` | 新环境复制为 `.env` 后按实际环境修改 |
| 后端开发配置 | `config/config_dev.yml` | dev 默认值和环境变量占位，默认业务库为 `gkx_element`、默认图空间为 `dev` |
| 后端测试配置 | `config/config_stage.yml` | stage 环境配置，敏感值从环境变量传入 |
| 后端生产配置 | `config/config_product.yml` | product 环境配置，敏感值从环境变量传入 |
| Python 依赖和检查配置 | `pyproject.toml` | uv 依赖、pytest、ruff 配置 |
| 后端 Docker 镜像 | `Dockerfile` | 构建 FastAPI 后端镜像 |
| 后端 Docker 编排 | `docker-compose.yml` | 只启动后端 API 容器，适合已有外部基础设施时使用 |
| 项目级 Docker 编排 | `../docker-compose.yml` | 启动 API、M3E、Milvus 和共用的 RustFS S3（schema 脚本 / 用户算子 / Milvus 内部存储）；MySQL 使用外部现有服务 |

### Docker 和代码部署的关系

MySQL 和 Milvus 保存业务数据及索引。只修改 Python 代码时，通常只需重启后端进程或重建 API 镜像，不应重建或改动外部 MySQL。当前开发业务库是 `gkx_element`；厂商 `gkx` 是只读源库；`trendAdmin` 是共享管理库；`gkx_local` 和 `techkg` 仅在历史模块明确要求时使用。

## 目录结构

```text
backend/
├── biz/            # 接口层：handler 和 router
├── application/    # 应用层：用例编排
├── service/        # 领域层：核心业务对象和业务规则
│   └── common/     # 公共实体/关系/NLP 能力
├── dao/            # 数据访问层
│   ├── base.py     # 通用 SQLAlchemy CRUD 基类
│   └── scholar.py  # 专家/人才 DAO 示例
├── db_model/       # SQLAlchemy ORM，93 张 gkx 表
├── schemas/        # DDL 和字段规范
├── infra/          # MySQL Session、Redis、TRSGraph、模型服务等连接
├── utils/          # 日志、配置、错误码、常量和工具函数
├── middleware/     # 日志、鉴权、trace_id、异常处理
├── idl/            # 接口定义文件
├── config/         # dev、stage、product 环境配置
├── script/         # 初始化和维护脚本
├── tests/          # 测试
└── main.py         # FastAPI 应用入口
```

核心调用链路：

```text
main.py
  -> biz/router/register.py
  -> biz/handler/{module}.py
  -> application/{module}.py
  -> service/{module}.py
  -> dao/{data_object}.py
```

已注册的知识图谱构建模块：

| 模块编码 | 模块名称 |
|---|---|
| `expert_direct_relation` | 科技专家/人才直接关系 |
| `expert_indirect_relation` | 科技单节点间接关系 |
| `expert_cooperation_achievement` | 科技两点合作成果 |
| `expert_colleague_relation` | 科技专家同事关系 |
| `expert_alumni_relation` | 科技专家校友关系 |
| `expert_paper_cooperation` | 科技专家论文合作关系 |
| `expert_enterprise_relation` | 重点关注科技企业关系 |
| `industry_chain_topn_event` | 科技产业链点 TOP-N 事件关系 |
| `industry_chain_panorama` | 科技产业链全景图 |

模块清单接口：

```text
GET /api/v1/kg-construction/modules
GET /api/v1/kg-construction/modules/{module_code}
```

## 数据库 ORM 和 DAO

当前已经补齐基础 ORM 操作能力：

| 层 | 文件 | 作用 |
|---|---|---|
| ORM 模型 | `db_model/*.py` | 93 张科技要素表的 SQLAlchemy 映射，运行时由 `MYSQL_DATABASE` 选择目标库 |
| MySQL 连接 | `infra/mysql.py` | 创建 engine、session factory、事务上下文和 FastAPI dependency |
| 通用 DAO | `dao/base.py` | `get`、`list`、`count`、`create`、`update`、`delete`、`bulk_create` |
| 示例 DAO | `dao/scholar.py` | 按主键、`scholar_id`、姓名查询专家 |

业务模块不要直接在 `service/` 里操作 ORM 或拼 SQL，统一通过 `dao/` 封装数据库访问：

```python
from dao.scholar import ScholarDAO


class ExpertAlumniRelationService:
    def __init__(self) -> None:
        self._scholar_dao = ScholarDAO()

    def infer(self, scholar_id: str) -> dict:
        scholar = self._scholar_dao.get_by_scholar_id(scholar_id)
        return {"scholar": scholar}
```

如果多个 DAO 操作必须放在同一个事务里，可以复用同一个 session：

```python
from dao.scholar import ScholarDAO
from infra.mysql import session_scope


with session_scope() as session:
    scholar_dao = ScholarDAO(session=session)
    scholar = scholar_dao.get_by_scholar_id("xxx")
```

## 公共能力接口

可复用实体/关系/NLP 能力已放入 `service/common/`，当前通过统一前缀 `/api/v1/common-capabilities` 暴露：

| 能力 | 接口 | 说明 |
|---|---|---|
| 能力元信息 | `GET /api/v1/common-capabilities/metadata` | 查看已注册公共能力 |
| 实体抽取 | `POST /api/v1/common-capabilities/entity-extraction` | 支持 `work`、`education`、`abstract`、`general` 场景 |
| 实体对齐 | `POST /api/v1/common-capabilities/entity-alignment` | 中英文/跨图谱实体候选召回和规则裁决 |
| 实体消歧 | `POST /api/v1/common-capabilities/entity-disambiguation` | 根据上下文将 mention 链接到候选实体 |
| 关系抽取 | `POST /api/v1/common-capabilities/relation-extraction` | 支持 `rule`、`llm`、`hybrid`；无 `LLM_API_KEY` 时规则能力仍可用 |
| 批量关系抽取 | `POST /api/v1/common-capabilities/relation-extraction/batch` | 多文本关系抽取并合并去重 |
| 关系抽取示例 | `GET /api/v1/common-capabilities/relation-extraction/examples` | 返回内置示例文本 |

## 专利图谱Schema

当前`schemas/`只维护最新专利图谱设计：

- `schemas/specifications/patent_ontology.md`
- `schemas/specifications/patent_mapping.md`
- `schemas/specifications/patent_relation_extraction.md`
- `dao/sql/patent_entity_extract.sql`
- `schemas/ddl/patent_ddl.ngql`

ORM 文件：

```text
db_model/
├── scholar.py
├── chinese_paper.py
├── foreign_paper.py
├── paper_common.py
├── patent.py
├── domestic_project.py
├── foreign_project.py
├── domestic_organization.py
├── foreign_organization.py
├── industry_chain.py
├── policy.py
└── report.py
```

同步 schema：

```bash
SOURCE_MYSQL_HOST=<vendor-mysql-host> \
SOURCE_MYSQL_PORT=<port> \
SOURCE_MYSQL_DATABASE=<database> \
SOURCE_MYSQL_USERNAME=<read-only-user> \
SOURCE_MYSQL_PASSWORD='<set-in-secret-store>' \
uv run python script/sync_schema_from_mysql.py
```

脚本说明见 `script/README.md`，接口契约目录说明见 `idl/README.md`。

## 启动

下面命令从项目根目录 `tech-kg-api/` 执行。

### 方式一：服务器已有 MySQL 副本

如果服务器已经有 `mysql` 服务，并且 `gkx_element` 已经存在，可直接启动后端。项目根目录 Compose 不会新建 MySQL：

```bash
cd backend
uv sync
cp .env.example .env
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 方式二：初始化已有开发业务库

`init_db.py` 不创建数据库，只在已经存在的 `gkx_element` 中执行 `schemas/ddl/` 下由本项目维护的表 DDL。专利厂商源表不由该脚本创建。

```bash
cd backend
uv sync
cp .env.example .env
MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_DATABASE=gkx_element MYSQL_USERNAME=root MYSQL_PASSWORD=实际密码 \
  uv run python script/init_db.py

uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 方式三：Docker 启动后端 API 容器

```bash
docker compose up --build api
```

启用统一用户中心登录前，复制模板并在本机/部署环境填写应用凭证：

```bash
cp .env.example .env
```

至少配置 `AUTH_ENABLED=true`、`AUTH_SESSION_BACKEND=redis`、
`USER_CENTER_CLIENT_ID`、`USER_CENTER_CLIENT_SECRET` 和已登记的
`USER_CENTER_REDIRECT_URI`。`USER_CENTER_CLIENT_SECRET` 不属于前端配置，
不得写入 Vue、Docker 镜像、Git 提交或测试表；服务器部署时使用环境变量或密钥管理系统注入。
新建应用未分配 OAuth scope 时保持 `USER_CENTER_SCOPE=`，否则用户中心会拒绝过大的授权范围。

如果启动页提示缺少 Client ID/Secret，说明运行进程没有加载上述后端环境变量，
不是前端缺少配置。配置完成后重启 FastAPI/`api` 容器即可。

健康检查：

```text
GET /health
```

测试：

```bash
uv run ruff check .
uv run pytest tests -m "not external"
```
