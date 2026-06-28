# Tech KG API Backend

后端采用 Python + FastAPI，实现知识图谱构建服务和数据访问层。

## 环境和连接信息

当前后端已经从旧 Java/SpringBoot 方案迁移为 Python/FastAPI。最终服务会部署在实验室服务器上；数据厂商提供的 `gkx` 只有使用权限，团队已经复制到服务器 MySQL 的 `gkx_local`，后端默认连接这份副本。

### 实验室服务器 / Docker 开发环境

| 组件 | 本机访问地址 | Compose 服务名 | 账号 | 密码/说明 |
|---|---|---|---|---|
| MySQL 数据副本 | `127.0.0.1:3306/gkx_local` | `tdsql-mysql` | `root` | `123456789`，复制自厂商 `gkx` |
| Redis | `127.0.0.1:6379`，DB `0` | `redis` | - | 无密码 |
| Kafka | `127.0.0.1:9092` | `kafka` | - | Consumer Group `techkg` |
| Milvus | `127.0.0.1:19530` | `milvus` | - | 无账号密码配置 |
| MinIO | API `127.0.0.1:9000`，控制台 `127.0.0.1:9001` | `minio` | `minioadmin` | `minioadmin` |

后端如果直接在宿主机运行，连接本地服务用 `127.0.0.1`；后端如果在 Docker Compose 的 `api` 容器内运行，连接 MySQL 要用 `tdsql-mysql`，连接 Redis/Kafka/Milvus 要用服务名 `redis`、`kafka`、`milvus`。

如果服务器已经有名为 `mysql` 的容器并且其中已有 `gkx_local`，不要再启动项目 Compose 里的 `tdsql-mysql`，避免 3306 端口冲突；后端直接连接现有 `127.0.0.1:3306/gkx_local` 即可。

### 远程数据源和服务器资源

| 组件 | 地址 | 账号 | 密码/说明 |
|---|---|---|---|
| 厂商源 MySQL | `183.240.141.251:3318/gkx` | `gkx_reader_zp` | `Zp_Use_Gkx_db@123456`，只读/只使用，不直接写入 |
| 服务器管理库 | `10.50.125.110:5306/trendAdmin` | `root` | `q123456Q.`，不是厂商数据副本 |
| 服务器 Redis | `10.50.125.110:8379`，DB `0` | - | `redisTrend1.` |
| MongoDB | `10.50.125.110:47017/test` | `root` | `x+s9zI&VA!s` |
| ElasticSearch | `http://123.57.233.22:9200` | `elastic` | `*7A0#7i7@DzKD1pr` |
| Nginx/GLM 网关 | `https://analysis_ckcest.aminer.cn/microtrend-api-beta/` | - | HTTP 网关 |
| TRSGraph | `127.0.0.1:9669`（后端和 TRSGraph 同机时） | `root` | `trsadmin` |

TRSGraph 由外部 TRSGraph 服务提供，当前 Python 后端只负责连接。环境变量见 `.env.example`，分环境配置见 `config/config_dev.yml`、`config/config_stage.yml`、`config/config_product.yml`。

### 配置文件定位

“位置”指配置文件在当前仓库中的相对路径。旧 Java/SpringBoot 文档里的 `backend/src/main/resources/application*.yml` 是 Java 项目路径，当前 Python/FastAPI 后端没有这些文件，等价配置已经迁移到 `.env` 和 `config/config_*.yml`。

| 文件 | 位置 | 用途 |
|---|---|---|
| 后端入口 | `main.py` | 创建 FastAPI 应用、注册中间件和路由 |
| 后端环境变量 | `.env` | 本机或服务器直接启动后端时读取的实际连接信息，不提交 Git |
| 后端环境变量模板 | `.env.example` | 新环境复制为 `.env` 后按实际环境修改 |
| 后端开发配置 | `config/config_dev.yml` | dev 默认值和环境变量占位，默认业务库为 `gkx_local` |
| 后端测试配置 | `config/config_stage.yml` | stage 环境配置，敏感值从环境变量传入 |
| 后端生产配置 | `config/config_product.yml` | product 环境配置，敏感值从环境变量传入 |
| Python 依赖和检查配置 | `pyproject.toml` | uv 依赖、pytest、ruff 配置 |
| 后端 Docker 镜像 | `Dockerfile` | 构建 FastAPI 后端镜像 |
| 后端 Docker 编排 | `docker-compose.yml` | 只启动后端 API 容器，适合已有外部基础设施时使用 |
| 项目级 Docker 编排 | `../docker-compose.yml` | 启动 MySQL/Redis/Kafka/Milvus/MinIO，也可启动 API 容器 |

### Docker 和代码部署的关系

MySQL/Redis/Kafka/Milvus 容器保存的是基础设施和数据。只修改 Python 代码时，通常只需要重启后端进程或重建 API 镜像，不需要重建 MySQL 容器。数据库内容能否修改取决于连接目标：`gkx_local` 是当前业务默认副本库；厂商 `gkx` 是只读源库；`trendAdmin` 是共享管理库；历史 `techkg` 若仍存在，先确认用途再迁移或停用。

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
| ORM 模型 | `db_model/*.py` | 93 张 `gkx_local` 表的 SQLAlchemy 映射 |
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

## 数据库 Schema

`schemas/` 和 `db_model/` 已按远程 MySQL 数据库 `gkx` 的真实结构同步，当前包含 93 张表、1686 个字段。

| 数据域 | 字段规范 | DDL 目录 | 表数 |
|---|---|---|---:|
| 人才专家 | `schemas/specifications/scholar.md` | `schemas/ddl/scholar/` | 6 |
| 中文论文 | `schemas/specifications/chinese_paper.md` | `schemas/ddl/chinese_paper/` | 4 |
| 外文论文 | `schemas/specifications/foreign_paper.md` | `schemas/ddl/foreign_paper/` | 6 |
| 论文通用 | `schemas/specifications/paper_common.md` | `schemas/ddl/paper_common/` | 2 |
| 专利 | `schemas/specifications/patent.md` | `schemas/ddl/patent/` | 9 |
| 国内项目 | `schemas/specifications/domestic_project.md` | `schemas/ddl/domestic_project/` | 2 |
| 国外项目 | `schemas/specifications/foreign_project.md` | `schemas/ddl/foreign_project/` | 2 |
| 国内机构 | `schemas/specifications/domestic_organization.md` | `schemas/ddl/domestic_organization/` | 41 |
| 国外机构 | `schemas/specifications/foreign_organization.md` | `schemas/ddl/foreign_organization/` | 10 |
| 产业链 | `schemas/specifications/industry_chain.md` | `schemas/ddl/industry_chain/` | 5 |
| 政策 | `schemas/specifications/policy.md` | `schemas/ddl/policy/` | 4 |
| 报告 | `schemas/specifications/report.md` | `schemas/ddl/report/` | 2 |

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
SOURCE_MYSQL_HOST=183.240.141.251 \
SOURCE_MYSQL_PORT=3318 \
SOURCE_MYSQL_DATABASE=gkx \
SOURCE_MYSQL_USERNAME=gkx_reader_zp \
SOURCE_MYSQL_PASSWORD='***' \
uv run python script/sync_schema_from_mysql.py
```

脚本说明见 `script/README.md`，接口契约目录说明见 `idl/README.md`。

## 启动

下面命令从项目根目录 `tech-kg-api/` 执行。

### 方式一：服务器已有 MySQL 副本

如果服务器已经有 `mysql` 容器，并且 `gkx_local` 已经存在，不要再启动项目根目录 Compose 里的 `tdsql-mysql`：

```bash
cd backend
uv sync
cp .env.example .env
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 方式二：从零启动 Docker 基础设施

如果本机或服务器没有 MySQL/Redis/Kafka/Milvus，先在项目根目录启动基础设施，再启动后端：

```bash
docker compose up -d tdsql-mysql redis kafka milvus

cd backend
uv sync
cp .env.example .env
MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_DATABASE=gkx_local MYSQL_USERNAME=root MYSQL_PASSWORD=123456789 \
  uv run python script/init_db.py

uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 方式三：Docker 启动后端 API 容器

```bash
docker compose up --build api
```

健康检查：

```text
GET /health
```

测试：

```bash
uv run ruff check .
uv run pytest tests -m "not external"
```
