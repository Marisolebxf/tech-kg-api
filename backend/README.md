# Tech KG API Backend

后端采用 Python + FastAPI，实现知识图谱构建服务和数据访问层。

## 连接信息

| 组件 | 地址 | 账号 | 密码/说明 |
|---|---|---|---|
| 源 MySQL | `183.240.141.251:3318/gkx` | `gkx_reader_zp` | `Zp_Use_Gkx_db@123456`，只读源库 |
| 服务器 MySQL | `10.50.125.110:5306/trendAdmin` | `root` | `q123456Q.` |
| 本地 MySQL | `127.0.0.1:3306/techkg` | `root` | `123456789` |
| Redis | `10.50.125.110:8379`，DB `0` | - | `redisTrend1.` |
| 本地 Redis | `127.0.0.1:6379`，DB `0` | - | 无密码 |
| MongoDB | `10.50.125.110:47017/test` | `root` | `x+s9zI&VA!s` |
| ElasticSearch | `http://123.57.233.22:9200` | `elastic` | `*7A0#7i7@DzKD1pr` |
| Nginx/GLM 网关 | `https://analysis_ckcest.aminer.cn/microtrend-api-beta/` | - | HTTP 网关 |
| MinIO | API `http://127.0.0.1:9000`，控制台 `http://127.0.0.1:9001` | `minioadmin` | `minioadmin` |
| Kafka | `127.0.0.1:9092`，Consumer Group `techkg` | - | 无账号密码配置 |
| Milvus | `127.0.0.1:19530` | - | 无账号密码配置 |
| TRSGraph | `127.0.0.1:9669`（后端和 TRSGraph 同在 211 服务器时） | `root` | `trsadmin` |

TRSGraph 由 Java Client/封装接入；当前业务后端为 Python。环境变量见 `.env.example`，分环境配置见 `config/config_dev.yml`、`config/config_stage.yml`、`config/config_product.yml`。

## 目录结构

```text
backend/
├── biz/            # 接口层：handler 和 router
├── application/    # 应用层：用例编排
├── service/        # 领域层：核心业务对象和业务规则
├── dao/            # 数据访问层
├── db_model/       # SQLAlchemy ORM，93 张 gkx 表
├── schemas/        # DDL 和字段规范
├── infra/          # MySQL、Redis、TRSGraph、模型服务等连接
├── utils/          # 日志、配置、错误码、常量和工具函数
├── middleware/     # 日志、鉴权、trace_id、异常处理
├── idl/            # 接口定义文件
├── config/         # dev、stage、product 环境配置
├── script/         # 初始化和维护脚本
├── tests/          # 测试
├── legacy/         # 历史代码参考
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
MYSQL_HOST=183.240.141.251 \
MYSQL_PORT=3318 \
MYSQL_DATABASE=gkx \
MYSQL_USERNAME=gkx_reader_zp \
MYSQL_PASSWORD='***' \
uv run python script/sync_schema_from_mysql.py
```

脚本说明见 `script/README.md`，接口契约目录说明见 `idl/README.md`。

## 启动

```bash
uv sync
cp .env.example .env
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload
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
