# Tech KG API Backend

本后端采用 Python + FastAPI 实现，目录结构按《国科信后端技术选型及脚手架设计》中的 Python DDD 分层要求组织。

## 技术栈

| 组件 | 版本 |
|---|---|
| Python | 3.11.13 |
| FastAPI | 0.110.2 |
| Redis | 7.0.1 |
| aiomysql | 0.2.0 |
| pymysql | 1.2.0 |
| SQLAlchemy | 2.0.42 |
| pydantic | 2.11.7 |

## 目录说明

```text
backend/
├── biz/            # 接口层：handler 和 router
├── application/    # 应用层：用例编排
├── service/        # 领域层：核心业务对象和业务规则
├── dao/            # 数据接入层：SQL 和数据查询封装
├── db_model/       # 数据表 model 定义
├── schemas/        # 数据库建表 DDL 和字段规范（9 个数据域、62 张表）
├── infra/          # 基础设施：MySQL、Redis、图数据库、模型服务等
├── utils/          # 通用组件：日志、配置、错误码、常量和工具函数
├── middleware/     # 中间件：日志、鉴权、trace_id、异常处理
├── idl/            # 接口定义文件
├── config/         # dev、stage、product 环境配置
├── script/         # 启动和维护脚本
├── tests/          # 测试：unit、integration
├── legacy/         # 旧代码临时存放目录，迁移完成后删除
├── main.py         # FastAPI 应用入口
├── Dockerfile
└── docker-compose.yml
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

## 知识图谱构建服务模块

当前脚手架已按知识图谱构建服务预置 9 个模块入口，状态为 `scaffold`，后续业务代码按模块逐步补充：

| 模块编码 | 模块名称 | 接口 |
|---|---|---|
| expert_direct_relation | 科技专家/人才直接关系 | `/api/v1/kg-construction/expert-direct-relations` |
| expert_indirect_relation | 科技单节点间接关系 | `/api/v1/kg-construction/expert-indirect-relations` |
| expert_cooperation_achievement | 科技两点合作成果 | `/api/v1/kg-construction/expert-cooperation-achievements` |
| expert_colleague_relation | 科技专家同事关系 | `/api/v1/kg-construction/expert-colleague-relations` |
| expert_alumni_relation | 科技专家校友关系 | `/api/v1/kg-construction/expert-alumni-relations` |
| expert_paper_cooperation | 科技专家论文合作关系 | `/api/v1/kg-construction/expert-paper-cooperation-relations` |
| expert_enterprise_relation | 重点关注科技企业关系 | `/api/v1/kg-construction/expert-enterprise-relations` |
| industry_chain_topn_event | 科技产业链点TOP-N事件关系 | `/api/v1/kg-construction/industry-chain-topn-event-relations` |
| industry_chain_panorama | 科技产业链全景图 | `/api/v1/kg-construction/industry-chain-panorama` |

模块清单接口：

```text
GET /api/v1/kg-construction/modules
GET /api/v1/kg-construction/modules/{module_code}
```

每个模块都已经预置独立开发文件，后续按模块补充业务：

```text
biz/handler/expert_direct_relation.py
application/expert_direct_relation.py
service/expert_direct_relation.py
```

其他 8 个模块同理。`biz/handler/kg_construction.py` 只保留模块清单接口，不承载具体模块业务。

共享数据访问层按数据对象组织，不按 9 个模块重复拆分：

```text
dao/
├── scholar.py
├── paper.py
├── patent.py
├── project.py
├── organization.py
├── industry_chain.py
└── relation.py
```

数据模型和基础设施分别放在：

```text
db_model/    # SQLAlchemy ORM 表模型（62 个模型类，与 DDL 一一对应）
schemas/     # 原始建表 DDL（按数据域）+ 字段规范文档
infra/       # MySQL、Redis、TRSGraph、模型服务等连接
script/      # 维护脚本（init_db.py 一键建表等）
```

### db_model 使用说明

`db_model/` 包含 62 张表的 SQLAlchemy ORM 模型，按数据域分文件：

```text
db_model/
├── base.py              # DeclarativeBase 基类
├── scholar.py           # 学者相关 6 表
├── patent.py            # 专利相关 5 表
├── paper.py             # 中文论文 9 表 + 英文论文 10 表
├── project.py           # 国内项目 2 表 + 国外项目 2 表
├── organization.py      # 国内机构 16 表 + 海外机构 8 表
├── industry_chain.py    # 产业链 4 表
└── __init__.py          # 统一导出所有模型
```

使用示例：

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from db_model import DwdScholar

engine = create_engine("mysql+pymysql://root:<password>@127.0.0.1:3306/techkg")

# 插入
with Session(engine) as session:
    session.add(DwdScholar(scholar_id="SCH001", name_zh="张三", paper_nums=42))
    session.commit()

# 读取（推荐 pandas）
import pandas as pd
df = pd.read_sql_table("dwd_scholar", engine)
```

### script 目录

```bash
# 一键建表（执行 schemas/ddl/ 下全部 62 张表的 DDL）
uv run python script/init_db.py
```

### schemas 目录

`schemas/` 维护要素库的字段规范和 MySQL 建表脚本，当前包含 9 个数据域、62 张表：

| 数据域 | 字段规范 | DDL 目录 | 表数 |
|---|---|---|---:|
| 人才专家 | `schemas/specifications/scholar.md` | `schemas/ddl/scholar/` | 6 |
| 专利 | `schemas/specifications/patent.md` | `schemas/ddl/patent/` | 5 |
| 国内机构 | `schemas/specifications/domestic_organization.md` | `schemas/ddl/domestic_organization/` | 16 |
| 国外机构 | `schemas/specifications/foreign_organization.md` | `schemas/ddl/foreign_organization/` | 8 |
| 中文论文 | `schemas/specifications/chinese_paper.md` | `schemas/ddl/chinese_paper/` | 9 |
| 外文论文 | `schemas/specifications/foreign_paper.md` | `schemas/ddl/foreign_paper/` | 10 |
| 国内项目 | `schemas/specifications/domestic_project.md` | `schemas/ddl/domestic_project/` | 2 |
| 国外项目 | `schemas/specifications/foreign_project.md` | `schemas/ddl/foreign_project/` | 2 |
| 产业链 | `schemas/specifications/industry_chain.md` | `schemas/ddl/industry_chain/` | 4 |

详细说明见 `schemas/README.md`。

## 外部组件

本项目基础设施配置参考 `tech-kg-engine/DEVELOP.md`：

| 组件 | 开发环境默认值 | 说明 |
|---|---|---|
| MySQL | `127.0.0.1:3306/techkg` | Docker Compose 中服务名为 `tdsql-mysql`，本地容器名为 `mysql` |
| Redis | `127.0.0.1:6379` | 本地开发默认无密码 |
| Kafka | `127.0.0.1:9092` | 预留消息组件配置 |
| Milvus | `127.0.0.1:19530` | 预留向量库配置 |
| TRSGraph | `127.0.0.1:9669` | 拓尔思图数据库，不使用 Neo4j |

TRSGraph 当前由外部服务器安装包方式部署，不通过本项目 `docker-compose.yml` 启动。若后端和 TRSGraph 在同一台服务器，可使用 `127.0.0.1:9669`；若不在同一台服务器，`TRSGRAPH_HOST` 应配置为 TRSGraph Graph 服务所在服务器 IP。

相关环境变量见 `.env.example`，分环境配置见：

```text
config/config_dev.yml
config/config_stage.yml
config/config_product.yml
```

## 开发约定

1. 新代码按分层职责放入对应目录。
2. `legacy/` 只用于旧代码迁移参考，不新增业务代码。
3. 接口入口放在 `biz/handler/`，统一路由注册放在 `biz/router/register.py`。
4. 应用流程编排放在 `application/`，核心业务规则放在 `service/`。
5. 数据查询封装放在 `dao/`，表结构模型放在 `db_model/`。
6. 外部服务、MySQL、Redis、TRSGraph、模型服务接入放在 `infra/`。
7. 新增模块时先补 `service` 中的业务对象，再由 `application` 编排，最后在 `biz/handler` 暴露接口。
8. `dao/` 按专家、论文、专利、项目、机构、产业链、关系等数据对象复用，不按每个业务模块重复造查询层。
9. `legacy/` 中代码只用于迁移参考，迁移完成后删除，不在其中继续开发新功能。

## 测试规范

```text
tests/
├── unit/             # 单元测试：不依赖真实数据库和外部服务
├── integration/      # 集成测试：接口、层间调用、组件集成
└── conftest.py       # pytest 公共 fixture
```

测试放置规则：

1. `service/` 中的算法、规则、计算逻辑，对应测试放入 `tests/unit/`。
2. `biz/handler/`、`application/` 的接口和流程测试，放入 `tests/integration/`。
3. 需要真实 MySQL、Redis、TRSGraph、Kafka、Milvus 的测试，必须加 `@pytest.mark.external`。
4. 普通 CI 默认执行不依赖外部服务的测试：`pytest tests -m "not external"`。

示例：

```python
import pytest


@pytest.mark.external
async def test_trsgraph_connection():
    ...
```

## 启动

本地启动：

```bash
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

Docker Compose 启动：

```bash
docker compose up --build
```

健康检查：

```text
GET /health
```

运行测试：

```bash
uv run pytest tests -m "not external"
```
