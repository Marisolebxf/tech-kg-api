# Tech KG API Frontend

前端采用 Vue 3 + TypeScript + Vite，使用 pnpm 管理依赖。前端不直接连接 MySQL、Redis、MongoDB、ElasticSearch 等后端中间件，统一通过后端 API 访问数据。

## 目录结构

```text
frontend/
├── src/
│   ├── api/
│   │   └── http.ts              # Axios 实例封装，统一处理 /api 代理和响应拦截
│   ├── assets/
│   │   ├── icons/               # SVG 图标（侧边栏、弹窗、流程图等）
│   │   └── images/              # 头像、Logo 等图片资源
│   ├── components/              # 跨页面复用的公共组件（目前为空，待提取）
│   ├── layouts/
│   │   └── AppLayout.vue        # 全局布局：侧边栏 + 主内容区（流式布局铺满视口）
│   ├── router/
│   │   └── index.ts             # Vue Router 配置，所有页面路由注册在此
│   ├── stores/
│   │   └── app.ts               # Pinia 全局状态
│   ├── styles/
│   │   ├── reset.css            # 浏览器基础重置样式、滚动条样式
│   │   ├── tokens.css           # 设计 Token（颜色/间距/圆角/阴影/字体变量）
│   │   └── global.css           # 通用 UI 组件样式（.kg-panel, .kg-button 等）
│   ├── views/
│   │   ├── expert-colleague/    # 【已实现】科技专家同事关系 - 完整页面（可作参考模板）
│   │   │   ├── ExpertColleagueView.vue   # 页面主文件（算法测试 + 开发者接口双视图）
│   │   │   ├── mock.ts                   # Mock 数据
│   │   │   ├── types.ts                  # TypeScript 类型定义
│   │   │   └── components/               # 页面私有组件
│   │   │       ├── RelationGraph.vue     # 关系图谱 SVG 组件
│   │   │       ├── RelationTable.vue     # 结果详情表格
│   │   │       ├── SearchPanel.vue       # 搜索面板
│   │   │       └── ExpertProfileCard.vue # 专家卡片
│   │   └── reasoning-placeholder/        # 【占位模板】其他推理模块通用占位页面
│   │       └── ReasoningPlaceholderView.vue
│   ├── main.ts                  # 应用入口
│   └── App.vue                  # 根组件
├── public/                      # 公共静态文件（favicon 等）
├── index.html                   # HTML 模板
├── vite.config.ts               # Vite 配置（路径别名、API 代理）
├── package.json                 # 依赖和脚本
├── pnpm-lock.yaml               # 依赖锁定
├── pnpm-workspace.yaml          # pnpm 工作区配置
└── .env.example                 # 环境变量模板
```

---

## 九个模块总览

| # | 模块名称 | 前端路径 | 前端状态 | 后端 module_code | 后端 API 路径 |
|---|---------|---------|---------|-----------------|--------------|
| 1 | 科技专家直接关系 | `/expert-direct` | 占位模板 | `expert_direct_relation` | `/api/v1/kg-construction/expert-direct-relations` |
| 2 | 科技节点间接关系 | `/node-indirect` | 占位模板 | `expert_indirect_relation` | `/api/v1/kg-construction/expert-indirect-relations` |
| 3 | 科技两点合作成果 | `/two-point-achievement` | 占位模板 | `expert_cooperation_achievement` | `/api/v1/kg-construction/expert-cooperation-achievements` |
| 4 | 科技专家同事关系 | `/expert-colleague` | ✅ 已实现 | `expert_colleague_relation` | `/api/v1/kg-construction/expert-colleague-relations` |
| 5 | 科技专家校友关系 | `/expert-alumni` | 占位模板 | `expert_alumni_relation` | `/api/v1/kg-construction/expert-alumni-relations` |
| 6 | 专家论文合作关系 | `/paper-cooperation` | 占位模板 | `expert_paper_cooperation` | `/api/v1/kg-construction/expert-paper-cooperations` |
| 7 | 重点科技企业关系 | `/enterprise-relation` | 占位模板 | `expert_enterprise_relation` | `/api/v1/kg-construction/expert-enterprise-relations` |
| 8 | 产业链点事件关系 | `/industry-chain-event` | 占位模板 | `industry_chain_topn_event` | `/api/v1/kg-construction/industry-chain-topn-events` |
| 9 | 科技产业链全景图 | `/industry-chain-panorama` | 占位模板 | `industry_chain_panorama` | `/api/v1/kg-construction/industry-chain-panoramas` |

---

## 各模块开发指引：从占位模板到完整功能

### 整体架构

```text
┌─────────────┐       ┌─────────────────────────────────────────────────┐
│   前端 Vue   │  ──>  │                后端 FastAPI                       │
│  localhost:5174      │  localhost:8000                                  │
│             │       │                                                  │
│  views/     │       │  biz/handler/ → application/ → service/ → dao/  │
│  expert-xxx/│       │  expert_xxx.py   expert_xxx.py  expert_xxx.py    │
└─────────────┘       └─────────────────────────────────────────────────┘
```

---

### 前端：如何为你的模块添加代码

以"科技专家校友关系"为例，完整步骤：

#### Step 1：创建页面目录

```text
src/views/expert-alumni/
├── ExpertAlumniView.vue       # 页面主文件
├── mock.ts                    # Mock 数据（后端没好之前用）
├── types.ts                   # 类型定义
└── components/                # 页面私有组件
    ├── AlumniGraph.vue        # 图谱可视化
    └── AlumniTable.vue        # 结果表格
```

#### Step 2：编写页面组件

参考 `src/views/expert-colleague/ExpertColleagueView.vue`，它包含：
- **算法测试视图**：左侧图谱 + 右侧详情表格
- **开发者接口视图**：请求参数表 + 返回字段表 + 代码示例
- **参数设置弹窗** + **技术方案弹窗**

复制该文件后修改数据和图谱内容即可。

#### Step 3：注册路由

编辑 `src/router/index.ts`：

```typescript
// 1. 导入你的组件
import ExpertAlumniView from '../views/expert-alumni/ExpertAlumniView.vue'

// 2. 从 placeholderRoutes 数组中删除 expert-alumni 那条

// 3. 在 routes 数组中添加独立路由
{
  path: '/expert-alumni',
  name: 'expert-alumni',
  component: ExpertAlumniView,
  meta: {
    title: '科技专家校友关系',
  },
},
```

#### Step 4：对接后端 API

在 `src/api/` 下新建接口文件：

```typescript
// src/api/expert-alumni.ts
import { http } from './http'

export function inferAlumniRelation(params: {
  expertAId: string
  expertBId: string
  // ...其他参数
}) {
  return http.post('/api/v1/kg-construction/expert-alumni-relations/infer', params)
}
```

然后在页面组件中调用替换 Mock 数据。

---

### 后端：如何为你的模块添加代码

后端已为每个模块预建了脚手架文件，你需要填充业务逻辑。

#### 后端代码调用链路

```text
请求进入
  ↓
biz/handler/expert_alumni_relation.py     # 路由 + 参数校验
  ↓
application/expert_alumni_relation.py      # 用例编排（调 service，组装结果）
  ↓
service/expert_alumni_relation.py          # 核心业务逻辑（推理规则、算法）
  ↓
dao/scholar.py, dao/paper.py, ...          # 数据访问（查 MySQL、ES、图数据库）
```

#### Step 1：定义接口契约（IDL）

在 `idl/` 目录下新建你的模块接口文档，定义请求参数和返回字段。

#### Step 2：编写 Handler（路由层）

编辑 `biz/handler/expert_alumni_relation.py`：

```python
from fastapi import APIRouter
from application.expert_alumni_relation import ExpertAlumniRelationApplication

router = APIRouter(prefix="/kg-construction/expert-alumni-relations")
application = ExpertAlumniRelationApplication()

@router.get("")
async def describe():
    """模块描述"""
    return application.describe()

@router.post("/infer")
async def infer(request: InferRequest):
    """推理接口 - 前端"执行测试"按钮调用"""
    return application.infer(request)
```

#### Step 3：编写 Application（用例层）

编辑 `application/expert_alumni_relation.py`：

```python
from service.expert_alumni_relation import ExpertAlumniRelationService

class ExpertAlumniRelationApplication:
    def __init__(self):
        self._service = ExpertAlumniRelationService()

    def describe(self):
        return self._service.describe()

    def infer(self, request):
        # 调用 service 执行推理
        result = self._service.infer(
            expert_a_id=request.expert_a_id,
            expert_b_id=request.expert_b_id,
        )
        return {"code": 0, "data": result}
```

#### Step 4：编写 Service（业务逻辑层）

编辑 `service/expert_alumni_relation.py`：

```python
from service.base_module import KGModuleScaffoldService
from dao.scholar import ScholarDAO

class ExpertAlumniRelationService(KGModuleScaffoldService):
    module_code = "expert_alumni_relation"

    def infer(self, expert_a_id: str, expert_b_id: str) -> dict:
        # 在这里写你的推理算法
        # 1. 从 DAO 查询专家教育履历
        # 2. 匹配学校 + 时间重叠
        # 3. 计算置信度
        # 4. 返回结构化结果
        pass
```

#### Step 5：使用 DAO 查询数据

已有 DAO 文件在 `dao/` 目录下，对应不同数据域：

| DAO 文件 | 数据域 | 可用于模块 |
|---------|--------|-----------|
| `dao/scholar.py` | 专家/人才 | 所有专家类模块 |
| `dao/paper.py` | 论文 | 论文合作关系 |
| `dao/patent.py` | 专利 | 合作成果 |
| `dao/project.py` | 项目 | 合作成果 |
| `dao/organization.py` | 机构 | 同事/校友关系 |
| `dao/relation.py` | 关系 | 所有模块 |
| `dao/industry_chain.py` | 产业链 | 产业链类模块 |

如果现有 DAO 不能满足需求，可以在 `dao/` 下新增文件或在现有文件中添加方法。

---

## 九个模块代码位置速查表

每个模块需要改动的文件（以 `expert_alumni` 为例，其他模块类推）：

| 层级 | 前端文件 | 后端文件 |
|------|---------|---------|
| 页面/路由 | `src/views/expert-alumni/ExpertAlumniView.vue` | `biz/handler/expert_alumni_relation.py` |
| 业务逻辑 | `src/views/expert-alumni/mock.ts` → 真实 API 调用 | `service/expert_alumni_relation.py` |
| 用例编排 | — | `application/expert_alumni_relation.py` |
| 数据访问 | `src/api/expert-alumni.ts` | `dao/scholar.py` 等 |
| 类型定义 | `src/views/expert-alumni/types.ts` | `idl/` 接口文档 |
| 路由注册 | `src/router/index.ts` | `biz/router/register.py`（已自动注册） |

---

## 布局方案说明

页面采用**流式布局**，自动铺满浏览器视口（100vw x 100vh）：
- 左侧边栏固定宽度（260px），右侧内容区弹性填充
- 内容区内部使用 CSS Grid 按比例分配：图谱区 1.6fr，详情区 1fr
- 无固定像素高度，所有区块通过 flex/grid 自适应视口高度

## 样式约定

| Token | 当前值 | 说明 |
|-------|--------|------|
| `--sidebar-width` | 260px | 侧边栏宽度 |
| `--control-height` | 36px | 输入框/按钮高度 |
| body font-size | 16px | 基础字号 |
| `.kg-panel__title` | 18px / 600 | 面板标题 |
| 菜单项 | 17px | 侧边栏导航文字 |
| 品牌标题 | 20px / 600 | "知识图谱平台" |

## 环境变量

配置文件参考 `.env.example`：

```env
VITE_API_TARGET=http://localhost:8000
VITE_NGINX_GATEWAY_URL=https://analysis_ckcest.aminer.cn/microtrend-api-beta/
```

| 变量 | 说明 |
|------|------|
| `VITE_API_TARGET` | Vite 开发代理转发到的后端 API 地址 |
| `VITE_NGINX_GATEWAY_URL` | Nginx/GLM 网关地址 |

开发环境中，`/api/*` 请求会被 Vite 代理到 `VITE_API_TARGET`（默认 `http://localhost:8000`）。

## 启动

下面命令从项目根目录 `tech-kg-api/` 执行：

```bash
# 终端一：后端
cd backend
uv sync
cp .env.example .env
uv run uvicorn main:app --host 0.0.0.0 --port 8000 --reload

# 终端二：前端
cd frontend
pnpm install
pnpm dev          # http://localhost:5174
```

## 技术栈

- 前端：Vue 3 (Composition API + `<script setup>`) / TypeScript / Vite / Vue Router / Pinia / pnpm
- 后端：Python / FastAPI / SQLAlchemy / uv
