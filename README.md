# tech-kg-api

亿级知识图谱项目，包含 Python 后端（FastAPI）和 Vue 前端（Vite）。

---

## 仓库完整目录结构

```text
tech-kg-api/
├── backend/                          # Python + FastAPI 后端
│   ├── main.py                       # 应用入口，创建 FastAPI 实例
│   ├── biz/                          # 接口层
│   │   ├── router/
│   │   │   └── register.py           # 统一路由注册（所有模块 router 在此挂载）
│   │   └── handler/                  # 各模块 HTTP Handler（定义路由 + 参数校验）
│   │       ├── kg_construction.py    # 模块清单接口
│   │       ├── expert_direct_relation.py
│   │       ├── expert_indirect_relation.py
│   │       ├── expert_cooperation_achievement.py
│   │       ├── expert_colleague_relation.py
│   │       ├── expert_alumni_relation.py
│   │       ├── expert_paper_cooperation.py
│   │       ├── expert_enterprise_relation.py
│   │       ├── industry_chain_topn_event.py
│   │       ├── industry_chain_panorama.py
│   │       └── common_capability.py      # 公共能力接口
│   ├── application/                  # 用例编排层（调 service，组装输入输出）
│   │   ├── expert_direct_relation.py
│   │   ├── expert_indirect_relation.py
│   │   ├── expert_cooperation_achievement.py
│   │   ├── expert_colleague_relation.py
│   │   ├── expert_alumni_relation.py
│   │   ├── expert_paper_cooperation.py
│   │   ├── expert_enterprise_relation.py
│   │   ├── industry_chain_topn_event.py
│   │   ├── industry_chain_panorama.py
│   │   ├── kg_construction.py
│   │   └── common_capability.py
│   ├── service/                      # 领域服务层（核心业务逻辑 + 推理算法）
│   │   ├── base_module.py            # 模块脚手架基类
│   │   ├── module_catalog.py         # 模块注册表
│   │   ├── common/                   # 公共实体/关系/NLP 能力
│   │   ├── kg_construction.py        # 模块清单服务
│   │   ├── expert_direct_relation.py
│   │   ├── expert_indirect_relation.py
│   │   ├── expert_cooperation_achievement.py
│   │   ├── expert_colleague_relation.py
│   │   ├── expert_alumni_relation.py
│   │   ├── expert_paper_cooperation.py
│   │   ├── expert_enterprise_relation.py
│   │   ├── industry_chain_topn_event.py
│   │   └── industry_chain_panorama.py
│   ├── dao/                          # 数据访问层（查 MySQL、ES、图数据库）
│   │   ├── base.py                   # 通用 SQLAlchemy CRUD 基类
│   │   ├── scholar.py                # 专家/人才数据
│   │   ├── paper.py                  # 论文数据
│   │   ├── patent.py                 # 专利数据
│   │   ├── project.py                # 项目数据
│   │   ├── organization.py           # 机构数据
│   │   ├── relation.py               # 关系数据
│   │   └── industry_chain.py         # 产业链数据
│   ├── db_model/                     # SQLAlchemy ORM 模型（93 张表）
│   │   ├── scholar.py
│   │   ├── chinese_paper.py
│   │   ├── foreign_paper.py
│   │   ├── paper_common.py
│   │   ├── patent.py
│   │   ├── domestic_project.py
│   │   ├── foreign_project.py
│   │   ├── domestic_organization.py
│   │   ├── foreign_organization.py
│   │   ├── industry_chain.py
│   │   ├── policy.py
│   │   └── report.py
│   ├── schemas/                      # 数据库 Schema 文档
│   │   ├── ddl/                      # 各数据域 DDL 文件（93 张表）
│   │   │   ├── scholar/              # 人才专家（6 表）
│   │   │   ├── chinese_paper/        # 中文论文（4 表）
│   │   │   ├── foreign_paper/        # 外文论文（6 表）
│   │   │   ├── paper_common/         # 论文通用（2 表）
│   │   │   ├── patent/               # 专利（9 表）
│   │   │   ├── domestic_project/     # 国内项目（2 表）
│   │   │   ├── foreign_project/      # 国外项目（2 表）
│   │   │   ├── domestic_organization/# 国内机构（41 表）
│   │   │   ├── foreign_organization/ # 国外机构（10 表）
│   │   │   ├── industry_chain/       # 产业链（5 表）
│   │   │   ├── policy/               # 政策（4 表）
│   │   │   └── report/               # 报告（2 表）
│   │   └── specifications/           # 各数据域字段规范文档
│   ├── infra/                        # 基础设施连接
│   │   ├── mysql.py                  # MySQL engine/session 管理
│   │   ├── redis.py                  # Redis 连接管理
│   │   ├── graph_db.py               # TRSGraph 图数据库连接
│   │   └── llm.py                    # 大模型服务连接
│   ├── idl/                          # 接口定义文件（API 契约）
│   ├── config/                       # 环境配置
│   │   ├── config_dev.yml            # 开发环境
│   │   ├── config_stage.yml          # 测试环境
│   │   └── config_product.yml        # 生产环境
│   ├── middleware/                   # 中间件（日志、鉴权、trace_id）
│   ├── utils/                        # 工具函数（日志、配置加载、常量）
│   ├── script/                       # 维护脚本
│   │   ├── init_db.py                # 数据库初始化
│   │   └── sync_schema_from_mysql.py # 从远程 MySQL 同步 Schema
│   ├── tests/                        # 测试
│   ├── .env.example                  # 环境变量模板
│   ├── pyproject.toml                # Python 依赖
│   ├── Dockerfile                    # 容器构建
│   └── docker-compose.yml            # 本地编排
│
```

### 后端简易目录（一句话说明每层干什么）

```text
backend/
├── main.py              # 入口：启动 FastAPI
├── biz/handler/         # 路由层：定义 HTTP 接口（URL + 参数校验）
├── application/         # 编排层：组合调用 service，拼装返回值
├── service/             # 业务层：★ 核心推理算法写这里 ★
├── dao/                 # 数据层：查数据库（MySQL/ES/图库）
├── db_model/            # ORM：表结构映射（93 张表）
├── infra/               # 连接：MySQL/Redis/TRSGraph/LLM 客户端
├── config/              # 配置：dev/stage/product 三套环境
├── schemas/             # DDL：建表语句 + 字段规范
├── idl/                 # 契约：接口文档
├── script/              # 脚本：初始化、同步
└── tests/               # 测试
```

> 简单说：**请求进来 → handler 接 → application 编排 → service 算 → dao 查数据 → 返回结果**

│
├── frontend/                         # Vue 3 + Vite 前端
│   ├── src/
│   │   ├── main.ts                   # 前端入口
│   │   ├── App.vue                   # 根组件
│   │   ├── api/
│   │   │   └── http.ts               # Axios 实例（/api 代理 + 拦截器）
│   │   ├── layouts/
│   │   │   └── AppLayout.vue         # 全局布局（侧边栏 + 内容区）
│   │   ├── router/
│   │   │   └── index.ts              # 路由配置（9 个模块路由）
│   │   ├── stores/
│   │   │   └── app.ts                # Pinia 全局状态
│   │   ├── styles/
│   │   │   ├── reset.css             # 浏览器重置
│   │   │   ├── tokens.css            # 设计变量（颜色/间距/字号）
│   │   │   └── global.css            # 通用组件样式
│   │   ├── views/
│   │   │   ├── expert-colleague/     # 【已实现】科技专家同事关系
│   │   │   │   ├── ExpertColleagueView.vue
│   │   │   │   ├── mock.ts
│   │   │   │   ├── types.ts
│   │   │   │   └── components/
│   │   │   └── reasoning-placeholder/# 【占位模板】其他 8 个模块
│   │   │       └── ReasoningPlaceholderView.vue
│   │   ├── components/               # 跨页面公共组件
│   │   └── assets/
│   │       ├── icons/                # SVG 图标
│   │       └── images/               # 图片资源
│   ├── public/                       # 静态文件
│   ├── index.html
│   ├── vite.config.ts                # Vite 配置 + API 代理
│   ├── package.json
│   ├── pnpm-lock.yaml
│   └── .env.example                  # 前端环境变量
│
├── docker-compose.yml                # 项目级容器编排
├── .gitignore
└── README.md                         
```

---

## 模块扩展约定：单文件 → 包目录

当你的模块逻辑变复杂，单个 `.py` 文件装不下时，**将文件升级为同名包（目录）**：

```text
# 初始：简单模块，一个文件够用
service/
├── expert_alumni_relation.py          # class ExpertAlumniRelationService

# 升级：模块变复杂，拆为目录
service/
├── expert_alumni_relation/            # 变成包
│   ├── __init__.py                    # from .service import ExpertAlumniRelationService
│   ├── service.py                     # 主服务类
│   ├── rules.py                       # 推理规则
│   ├── evidence.py                    # 证据聚合
│   ├── scorer.py                      # 置信度计算
│   └── constants.py                   # 模块内常量

# handler、application 同理可升级：
biz/handler/
├── expert_alumni_relation/
│   ├── __init__.py
│   ├── router.py                      # 路由定义
│   ├── request.py                     # 请求模型
│   └── response.py                    # 响应模型
```

**关键：`__init__.py` 必须导出上层需要的类/对象，保证 import 路径不变。**

```python
# service/expert_alumni_relation/__init__.py
from .service import ExpertAlumniRelationService  # noqa: F401
```

这样 `application/expert_alumni_relation.py` 中的 `from service.expert_alumni_relation import ExpertAlumniRelationService` 无需修改，其他模块完全不受影响。

handler 升级为包时，需确保 `register.py` 中 `from biz.handler.expert_alumni_relation import router` 仍然能正常导入（在 `__init__.py` 中导出 `router`）。

---

## 九个模块总览

| # | 模块名称 | 后端 module_code | 后端 API 前缀 | 前端路径 | 前端状态 |
|---|---------|-----------------|--------------|---------|---------|
| 1 | 科技专家直接关系 | `expert_direct_relation` | `/api/v1/kg-construction/expert-direct-relations` | `/expert-direct` | 占位 |
| 2 | 科技节点间接关系 | `expert_indirect_relation` | `/api/v1/kg-construction/expert-indirect-relations` | `/node-indirect` | 占位 |
| 3 | 科技两点合作成果 | `expert_cooperation_achievement` | `/api/v1/kg-construction/expert-cooperation-achievements` | `/two-point-achievement` | 占位 |
| 4 | 科技专家同事关系 | `expert_colleague_relation` | `/api/v1/kg-construction/expert-colleague-relations` | `/expert-colleague` | ✅ 已实现 |
| 5 | 科技专家校友关系 | `expert_alumni_relation` | `/api/v1/kg-construction/expert-alumni-relations` | `/expert-alumni` | 占位 |
| 6 | 专家论文合作关系 | `expert_paper_cooperation` | `/api/v1/kg-construction/expert-paper-cooperations` | `/paper-cooperation` | 占位 |
| 7 | 重点科技企业关系 | `expert_enterprise_relation` | `/api/v1/kg-construction/expert-enterprise-relations` | `/enterprise-relation` | 占位 |
| 8 | 产业链点事件关系 | `industry_chain_topn_event` | `/api/v1/kg-construction/industry-chain-topn-events` | `/industry-chain-event` | 占位 |
| 9 | 科技产业链全景图 | `industry_chain_panorama` | `/api/v1/kg-construction/industry-chain-panoramas` | `/industry-chain-panorama` | 占位 |

---

## 九个模块 — 后端文件完整路径

> **当前状态：后端九个模块全部为脚手架占位文件，尚无实际业务逻辑。**
>
> 现有代码内容：
> - **Handler**：只注册了 `GET /` 返回模块描述，没有 `/infer` 推理接口
> - **Application**：只转发 `describe()` 方法
> - **Service**：只继承 `KGModuleScaffoldService` 基类，设了 `module_code`，无推理算法
> - **DAO**：空类占位（`ScholarDAO` 等只有 docstring）
> - **infra**：连接类空占位（`MySQLClient`、`RedisClient` 等未实现）
>
> 各负责人需要在对应文件中填充实际代码。

### 模块 1：科技专家直接关系

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/expert_direct_relation.py` |
| Application | `backend/application/expert_direct_relation.py` |
| Service | `backend/service/expert_direct_relation.py` |
| 推荐 DAO | `dao/scholar.py`, `dao/relation.py` |

### 模块 2：科技节点间接关系

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/expert_indirect_relation.py` |
| Application | `backend/application/expert_indirect_relation.py` |
| Service | `backend/service/expert_indirect_relation.py` |
| 推荐 DAO | `dao/scholar.py`, `dao/relation.py`, `dao/organization.py` |

### 模块 3：科技两点合作成果

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/expert_cooperation_achievement.py` |
| Application | `backend/application/expert_cooperation_achievement.py` |
| Service | `backend/service/expert_cooperation_achievement.py` |
| 推荐 DAO | `dao/scholar.py`, `dao/paper.py`, `dao/patent.py`, `dao/project.py` |

### 模块 4：科技专家同事关系 ✅

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/expert_colleague_relation.py` |
| Application | `backend/application/expert_colleague_relation.py` |
| Service | `backend/service/expert_colleague_relation.py` |
| 推荐 DAO | `dao/scholar.py`, `dao/organization.py`, `dao/relation.py` |

### 模块 5：科技专家校友关系

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/expert_alumni_relation.py` |
| Application | `backend/application/expert_alumni_relation.py` |
| Service | `backend/service/expert_alumni_relation.py` |
| 推荐 DAO | `dao/scholar.py`, `dao/organization.py` |

### 模块 6：专家论文合作关系

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/expert_paper_cooperation.py` |
| Application | `backend/application/expert_paper_cooperation.py` |
| Service | `backend/service/expert_paper_cooperation.py` |
| 推荐 DAO | `dao/scholar.py`, `dao/paper.py` |

### 模块 7：重点科技企业关系

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/expert_enterprise_relation.py` |
| Application | `backend/application/expert_enterprise_relation.py` |
| Service | `backend/service/expert_enterprise_relation.py` |
| 推荐 DAO | `dao/organization.py`, `dao/relation.py`, `dao/industry_chain.py` |

### 模块 8：产业链点事件关系

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/industry_chain_topn_event.py` |
| Application | `backend/application/industry_chain_topn_event.py` |
| Service | `backend/service/industry_chain_topn_event.py` |
| 推荐 DAO | `dao/industry_chain.py`, `dao/organization.py` |

### 模块 9：科技产业链全景图

| 层 | 文件路径 |
|----|---------|
| Handler | `backend/biz/handler/industry_chain_panorama.py` |
| Application | `backend/application/industry_chain_panorama.py` |
| Service | `backend/service/industry_chain_panorama.py` |
| 推荐 DAO | `dao/industry_chain.py`, `dao/organization.py` |

---

## 九个模块 — 前端文件完整路径

> **当前状态：除"科技专家同事关系"（模块4）已完整实现外，其余 8 个模块前端均使用通用占位模板 `ReasoningPlaceholderView.vue` 渲染，无独立页面。**
>
> 各负责人需为自己的模块创建独立页面目录并注册路由。

| # | 模块 | 页面目录 | 路由注册 | API 文件 |
|---|------|---------|---------|---------|
| 1 | 科技专家直接关系 | `frontend/src/views/expert-direct/` | `router/index.ts` | `api/expert-direct.ts` |
| 2 | 科技节点间接关系 | `frontend/src/views/node-indirect/` | `router/index.ts` | `api/node-indirect.ts` |
| 3 | 科技两点合作成果 | `frontend/src/views/two-point-achievement/` | `router/index.ts` | `api/two-point-achievement.ts` |
| 4 | 科技专家同事关系 | `frontend/src/views/expert-colleague/` ✅ | `router/index.ts` ✅ | `api/expert-colleague.ts` |
| 5 | 科技专家校友关系 | `frontend/src/views/expert-alumni/` | `router/index.ts` | `api/expert-alumni.ts` |
| 6 | 专家论文合作关系 | `frontend/src/views/paper-cooperation/` | `router/index.ts` | `api/paper-cooperation.ts` |
| 7 | 重点科技企业关系 | `frontend/src/views/enterprise-relation/` | `router/index.ts` | `api/enterprise-relation.ts` |
| 8 | 产业链点事件关系 | `frontend/src/views/industry-chain-event/` | `router/index.ts` | `api/industry-chain-event.ts` |
| 9 | 科技产业链全景图 | `frontend/src/views/industry-chain-panorama/` | `router/index.ts` | `api/industry-chain-panorama.ts` |

> 每个前端页面目录下应包含：`XxxView.vue`、`mock.ts`、`types.ts`、`components/`

---

## 后端代码调用链路

```text
HTTP 请求
  ↓
main.py                                    # FastAPI 应用入口
  ↓
biz/router/register.py                     # 挂载所有 handler 的 router
  ↓
biz/handler/{module}.py                    # 路由定义 + 请求参数校验
  ↓
application/{module}.py                    # 用例编排（组合多个 service）
  ↓
service/{module}.py                        # 核心业务逻辑（推理算法）
  ↓
dao/{data_domain}.py                       # 数据查询（MySQL/ES/TRSGraph）
  ↓
infra/mysql.py | infra/graph_db.py         # 底层连接
```

---

## 公共能力接口

公共实体/关系/NLP 能力已放入 `backend/service/common/`，供九个业务模块复用。统一接口前缀：

```text
/api/v1/common-capabilities
```

| 能力 | 接口 |
|------|------|
| 能力元信息 | `GET /api/v1/common-capabilities/metadata` |
| 实体抽取 | `POST /api/v1/common-capabilities/entity-extraction` |
| 实体对齐 | `POST /api/v1/common-capabilities/entity-alignment` |
| 实体消歧 | `POST /api/v1/common-capabilities/entity-disambiguation` |
| 关系抽取 | `POST /api/v1/common-capabilities/relation-extraction` |
| 批量关系抽取 | `POST /api/v1/common-capabilities/relation-extraction/batch` |
| 关系抽取示例 | `GET /api/v1/common-capabilities/relation-extraction/examples` |

当前只保留实体抽取、实体对齐、实体消歧、关系抽取等公共能力；旧图数据库 demo、旧 schema 说明和数据表说明不进入当前后端运行链路。

---

## 各模块开发指引

### 每个模块需要改动的文件清单

以你负责的模块 `{module}` 为例：

| 层级 | 后端文件 | 职责 |
|------|---------|------|
| Handler | `backend/biz/handler/{module}.py` | 定义 HTTP 路由、请求/响应模型 |
| Application | `backend/application/{module}.py` | 用例编排，调用 service |
| Service | `backend/service/{module}.py` | **核心：写推理算法和业务规则** |
| DAO | `backend/dao/scholar.py` 等 | 查数据库，按需新增方法 |
| IDL | `backend/idl/{module}.md` | 接口文档（请求参数/返回字段） |

| 层级 | 前端文件 | 职责 |
|------|---------|------|
| 页面 | `frontend/src/views/{module}/XxxView.vue` | 页面 UI + 交互逻辑 |
| Mock | `frontend/src/views/{module}/mock.ts` | 开发阶段模拟数据 |
| 类型 | `frontend/src/views/{module}/types.ts` | TS 类型定义 |
| API | `frontend/src/api/{module}.ts` | 调后端接口 |
| 路由 | `frontend/src/router/index.ts` | 注册路由到独立组件 |

---

### 后端开发步骤（以"科技专家校友关系"为例）

**Step 1：定义接口（Handler）**

编辑 `backend/biz/handler/expert_alumni_relation.py`：

```python
from fastapi import APIRouter
from pydantic import BaseModel
from application.expert_alumni_relation import ExpertAlumniRelationApplication

router = APIRouter(prefix="/kg-construction/expert-alumni-relations")
application = ExpertAlumniRelationApplication()

class InferRequest(BaseModel):
    data_source: str = "all"
    expert_a_id: str
    expert_b_id: str
    relation_type: str = "alumni"

class InferResponse(BaseModel):
    code: int = 0
    data: dict

@router.get("")
async def describe():
    return application.describe()

@router.post("/infer", response_model=InferResponse)
async def infer(request: InferRequest):
    result = application.infer(request)
    return {"code": 0, "data": result}
```

**Step 2：编排用例（Application）**

编辑 `backend/application/expert_alumni_relation.py`：

```python
from service.expert_alumni_relation import ExpertAlumniRelationService

class ExpertAlumniRelationApplication:
    def __init__(self):
        self._service = ExpertAlumniRelationService()

    def describe(self):
        return self._service.describe()

    def infer(self, request):
        return self._service.infer(
            expert_a_id=request.expert_a_id,
            expert_b_id=request.expert_b_id,
            relation_type=request.relation_type,
        )
```

**Step 3：实现业务逻辑（Service）— 重点**

编辑 `backend/service/expert_alumni_relation.py`：

```python
from service.base_module import KGModuleScaffoldService
from dao.scholar import ScholarDAO

class ExpertAlumniRelationService(KGModuleScaffoldService):
    module_code = "expert_alumni_relation"

    def __init__(self):
        super().__init__()
        self._scholar_dao = ScholarDAO()

    def infer(self, expert_a_id: str, expert_b_id: str, relation_type: str) -> dict:
        # 1. 查询专家 A、B 的教育履历
        # 2. 匹配学校 + 时间重叠
        # 3. 计算置信度
        # 4. 汇总证据链
        # 5. 返回结构化结果
        return {
            "relation_type": "校友关系",
            "confidence": 88,
            "school": "...",
            "overlap_period": "...",
            # ...
        }
```

**Step 4：数据查询（DAO）**

在现有 `backend/dao/scholar.py` 中添加需要的查询方法，或按需新建 DAO 文件。

---

### 前端开发步骤（以"科技专家校友关系"为例）

**Step 1：创建页面目录**

```bash
mkdir -p frontend/src/views/expert-alumni/components
```

**Step 2：复制模板并修改**

将 `expert-colleague/ExpertColleagueView.vue` 复制为 `expert-alumni/ExpertAlumniView.vue`，修改：
- 图谱数据（SVG 节点和连线）
- 结果表格字段
- Mock 数据
- 技术方案弹窗描述

**Step 3：注册路由**

编辑 `frontend/src/router/index.ts`：

```typescript
import ExpertAlumniView from '../views/expert-alumni/ExpertAlumniView.vue'

// 从 placeholderRoutes 中删除 /expert-alumni
// 在 routes 中添加：
{
  path: '/expert-alumni',
  name: 'expert-alumni',
  component: ExpertAlumniView,
  meta: { title: '科技专家校友关系' },
},
```

**Step 4：对接 API**

```typescript
// frontend/src/api/expert-alumni.ts
import { http } from './http'

export function inferAlumniRelation(params: Record<string, unknown>) {
  return http.post('/api/v1/kg-construction/expert-alumni-relations/infer', params)
}
```

页面中调用，替换 mock 数据。

---

## DAO 数据域对照

数据库访问统一走 `dao/`，不要在业务 `service/` 中直接操作 ORM 或拼 SQL。`backend/infra/mysql.py` 负责 SQLAlchemy engine/session，`backend/dao/base.py` 提供通用 CRUD，`backend/dao/scholar.py` 是专家/人才 DAO 示例。

| DAO 文件 | 数据域 | ORM 模型 | 适用模块 |
|---------|--------|----------|---------|
| `dao/base.py` | 通用能力 | `db_model/base.py` | 所有 DAO 的 CRUD 基类 |
| `dao/scholar.py` | 专家/人才 | `db_model/scholar.py` (6表) | 所有专家类模块 |
| `dao/paper.py` | 论文 | `db_model/chinese_paper.py` + `foreign_paper.py` | 论文合作 |
| `dao/patent.py` | 专利 | `db_model/patent.py` (9表) | 合作成果 |
| `dao/project.py` | 项目 | `db_model/domestic_project.py` + `foreign_project.py` | 合作成果 |
| `dao/organization.py` | 机构 | `db_model/domestic_organization.py` (41表) | 同事/企业关系 |
| `dao/relation.py` | 关系 | — | 所有模块 |
| `dao/industry_chain.py` | 产业链 | `db_model/industry_chain.py` (5表) | 产业链类模块 |

---

## 基础设施连接（infra）

| 文件 | 连接目标 | 用途 |
|------|---------|------|
| `infra/mysql.py` | MySQL | 结构化数据查询 |
| `infra/redis.py` | Redis | 缓存 |
| `infra/graph_db.py` | TRSGraph | 图数据库查询 |
| `infra/llm.py` | 大模型网关 | NLP/推理辅助 |

---

## 环境和连接信息

本仓库现在是 Python FastAPI 后端 + Vue 前端。旧 `tech-kg-engine` 仓库里的 Java/SpringBlade 说明只适合作为历史参考，不能直接照搬。

### 实验室服务器 / Docker 开发环境

最终服务会部署在实验室服务器上。数据厂商提供的 `gkx` 只有使用权限，不直接作为业务写入库；团队已经把厂商数据复制到实验室服务器 MySQL 的 `gkx_local`，后续开发和服务默认连接这份副本。

| 组件 | 本机访问地址 | Compose 服务名 | 账号 | 密码/说明 |
|------|--------------|----------------|------|----------|
| MySQL 数据副本 | `127.0.0.1:3306/gkx_local` | `tdsql-mysql` | `root` | `123456789`，复制自厂商 `gkx` |
| Redis | `127.0.0.1:6379`，DB 0 | `redis` | - | 无密码 |
| Kafka | `127.0.0.1:9092` | `kafka` | - | Consumer Group `techkg` |
| Milvus | `127.0.0.1:19530` | `milvus` | - | 向量库 |
| MinIO | API `127.0.0.1:9000`，控制台 `127.0.0.1:9001` | `minio` | `minioadmin` | `minioadmin` |

> 注意：宿主机上访问 MySQL 用 `127.0.0.1:3306`；API 容器内部访问同一个 MySQL 要用 Compose 服务名 `tdsql-mysql:3306`。
> 如果服务器已经有名为 `mysql` 的容器并且其中已有 `gkx_local`，不要再启动 `tdsql-mysql`，避免 3306 端口冲突；只需要让后端连接现有 `127.0.0.1:3306/gkx_local`。

### 远程数据源和服务器资源

下面这些不是当前业务默认写入库，主要用于同步真实 Schema、读取源数据或连接其他服务器资源：

| 组件 | 地址 | 账号 | 密码/说明 |
|------|------|------|----------|
| 厂商源 MySQL | `183.240.141.251:3318/gkx` | `gkx_reader_zp` | `Zp_Use_Gkx_db@123456`，只读/只使用，不直接写入 |
| 服务器管理库 | `10.50.125.110:5306/trendAdmin` | `root` | `q123456Q.`，管理类业务库，不是厂商数据副本 |
| Redis | `10.50.125.110:8379`，DB 0 | - | `redisTrend1.`，服务器 Redis |
| MongoDB | `10.50.125.110:47017/test` | `root` | `x+s9zI&VA!s` |
| ElasticSearch | `http://123.57.233.22:9200` | `elastic` | `*7A0#7i7@DzKD1pr` |
| Nginx/GLM 网关 | `https://analysis_ckcest.aminer.cn/microtrend-api-beta/` | - | HTTP 网关 |
| TRSGraph | `127.0.0.1:9669` | `root` | `trsadmin`，后端和 TRSGraph 同机时使用；否则改 `TRSGRAPH_HOST` |

### 配置文件定位

旧 Java 文档里有“配置文件定位”，是为了说明 Spring Boot 的 `application-*.yml` 和 Docker Compose 分别管什么。Python 版也需要这张表，避免把厂商源库 `gkx`、实验室副本 `gkx_local`、容器内服务名混在一起。

| 文件 | 位置 | 用途 |
|------|------|------|
| 项目级 Docker 编排 | `docker-compose.yml` | 启动本地 MySQL/Redis/Kafka/Milvus/MinIO，也可启动 API 容器 |
| 后端 Docker 镜像 | `backend/Dockerfile` | 构建 FastAPI 后端镜像 |
| 后端环境变量 | `backend/.env` | 本机或服务器直接启动后端时读取的实际连接信息 |
| 后端环境变量模板 | `backend/.env.example` | 新同学复制为 `.env` 后按环境修改 |
| 后端开发配置 | `backend/config/config_dev.yml` | Python 后端 dev 环境默认值和环境变量占位 |
| 后端测试/生产配置 | `backend/config/config_stage.yml`, `backend/config/config_product.yml` | stage/product 环境，敏感值必须从环境变量传入 |
| 前端 Vite 配置 | `frontend/vite.config.ts` | `/api` 代理、开发服务器端口、构建选项 |

### Docker 和代码部署的关系

Docker 里的 MySQL/Redis/Kafka/Milvus 是基础设施。只改 Python/Vue 代码时，通常不需要重建数据库容器；重启后端/前端即可。数据库容器的数据保存在 Docker volume 里，重建 API 镜像不会清空 MySQL 数据；只有删除 volume 或重新初始化数据库才会影响已有数据。

数据库内容能不能改，取决于你连的是哪个库：

| 目标库 | 是否建议修改数据 | 说明 |
|--------|------------------|------|
| 实验室副本 MySQL `gkx_local` | 可以 | 当前业务默认库，复制自厂商 `gkx`，团队可在这里做开发和补充数据 |
| 厂商源 MySQL `gkx` | 不建议，也通常没权限 | 数据厂商提供，只用于读取/同步，不直接写入 |
| 服务器管理库 `trendAdmin` | 谨慎 | 共享管理库，只有明确需要时再改 |
| 历史库 `techkg` | 视情况 | 旧 Java/早期实验库名，若服务器上仍有数据，先确认用途再迁移或停用 |

---

## 启动

### 方式一：服务器已有 MySQL 副本

如果实验室服务器已经有 `mysql` 容器，并且里面已经有 `gkx_local`，不要再启动 `tdsql-mysql`。这种情况下只启动后端和前端：

```bash
# 后端
cd backend
uv sync
cp .env.example .env
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 前端
cd ../frontend
pnpm install
pnpm dev
```

### 方式二：从零启动 Docker 基础设施

如果本机或服务器没有 MySQL/Redis/Kafka/Milvus，可以由项目 Compose 启动。首次初始化会执行 `backend/schemas/ddl/` 下的 DDL，目标库是 `gkx_local`：

```bash
# 在项目根目录
docker compose up -d tdsql-mysql redis kafka milvus

cd backend
uv sync
cp .env.example .env
MYSQL_HOST=127.0.0.1 MYSQL_PORT=3306 MYSQL_DATABASE=gkx_local MYSQL_USERNAME=root MYSQL_PASSWORD=123456789 \
  uv run python script/init_db.py

uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

cd ../frontend
pnpm install
pnpm dev
```

### 方式三：Docker 启动后端 API 容器

```bash
# 在项目根目录；会构建并启动 api，同时拉起依赖服务
docker compose up --build api
```

### 质量检查命令

```bash
# 后端
cd backend
uv run ruff check .
uv run pytest tests -m "not external"

# 前端
cd ../frontend
pnpm build
```

| 服务 | 地址 |
|------|------|
| 后端 API | http://localhost:8000 |
| API 文档 | http://localhost:8000/docs |
| 前端页面 | http://localhost:5174 |

---

## 技术栈

| 端 | 技术 |
|----|------|
| 前端 | Vue 3 / TypeScript / Vite / Vue Router / Pinia / pnpm |
| 后端 | Python 3.12 / FastAPI / SQLAlchemy / uv |
| 数据库 | MySQL / Redis / MongoDB / ElasticSearch / TRSGraph / Milvus |
| 部署 | Docker / docker-compose |
