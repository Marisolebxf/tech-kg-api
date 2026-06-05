# 跨库绑定（Entity Binding）设计文档

## 概述

实现人才库、论文库、专利库、机构库之间的跨库实体绑定功能。人才库来自厂商A，论文库来自厂商B，需要将关键数据（如人才库专家与论文库作者、人才库专家与专利库发明人、机构库之间的实体）进行关联绑定。数据存储在 TRS Graph（基于 NebulaGraph）中，通过已有的 Java REST 服务 `trs-graph-service` 操作。

绑定策略：**规则召回 + LLM 精排**，先用规则匹配召回候选绑定对，再用 LLM（GLM）精确判断是否为同一实体。

交付范围：后端服务 + API + 简单前端展示页面。

---

## 1. TRS Graph Backend（graph_db 抽象层）

### 1.1 核心思路

在 `graph_db/backends/trs_graph_backend.py` 中实现 `TRSGraphDatabase(GraphDatabase)`，通过 HTTP 调用 `trs-graph-service`（localhost:8090）完成所有操作。

### 1.2 构造与连接

```python
class TRSGraphDatabase(GraphDatabase):
    def __init__(self, base_url: str = "http://localhost:8090",
                 graph_space: str = "entity_binding_demo",
                 timeout: int = 30):
        self._base_url = base_url.rstrip("/")
        self._graph_space = graph_space
        self._timeout = timeout
        self._client: httpx.Client | None = None
```

- `connect()` → 创建 `httpx.Client`，设置 `X-Graph-Space` 为默认 header
- `close()` → 关闭 client
- `is_connected()` → GET `/health`

### 1.3 方法到 HTTP 的映射

| graph_db 方法 | trs-graph-service HTTP | 说明 |
|---|---|---|
| `create_node` | POST `/api/v1/nodes` | labels[0] → TAG，其余 → `_additional_labels` |
| `merge_node` | POST `/api/v1/nodes/merge` | 同上 |
| `get_node` | GET `/api/v1/nodes/{id}` | |
| `get_nodes_by_label` | GET `/api/v1/nodes/label/{label}` | |
| `find_nodes` | POST `/api/v1/nodes/find` | |
| `update_node` | PUT `/api/v1/nodes/{id}` | |
| `delete_node` | DELETE `/api/v1/nodes/{id}` | |
| `batch_create_nodes` | POST `/api/v1/nodes/batch` | |
| `create_edge` | POST `/api/v1/edges` | |
| `merge_edge` | POST `/api/v1/edges/merge` | |
| `get_edge` | GET `/api/v1/edges/{src}/{dst}?type=&ranking=` | |
| `get_edges_by_type` | GET `/api/v1/edges/type/{type}` | |
| `find_edges` | POST `/api/v1/edges/find` | |
| `update_edge` | PUT `/api/v1/edges/{src}/{dst}` | |
| `delete_edge` | DELETE `/api/v1/edges/{src}/{dst}?type=&ranking=` | |
| `batch_create_edges` | POST `/api/v1/edges/batch` | |
| `get_neighbours` | GET `/api/v1/traversal/{id}/neighbours` | |
| `get_node_edges` | GET `/api/v1/traversal/{id}/edges` | |
| `shortest_path` | GET `/api/v1/traversal/path/shortest` | |
| `execute_query/read/write` | POST `/api/v1/query` `/read` `/write` | |
| `create/drop/list_index` | POST/DELETE/GET `/api/v1/schema/indexes` | |
| `create/drop/list_constraint` | POST/DELETE/GET `/api/v1/schema/constraints` | |
| `node_count/edge_count` | GET `/api/v1/schema/stats/...` | |
| `labels/edge_types` | GET `/api/v1/schema/labels` `/edge-types` | |

### 1.4 事务处理

TRS Graph（NebulaGraph）不支持 ACID 多语句事务。`transaction()` 返回 `TRSTransaction`：

- 缓存所有写操作到队列
- `commit()` 时批量执行
- `rollback()` 时清空队列
- 实质是**伪事务**，保证接口兼容但不保证原子性

### 1.5 Config 注册

在 `graph_db/config.py` 的 `connect()` 中，为非 Neo4j 后端传入 config：

```python
else:
    db = cls(config)
```

注册：`register_backend("trs_graph", TRSGraphDatabase)`

---

## 2. 跨库绑定核心逻辑

### 2.1 边类型定义

在 `entity_binding_demo` 空间中创建的 EDGE 类型：

| 边类型 | 源 TAG | 目标 TAG | 含义 |
|---|---|---|---|
| `bind_talent_paper_author` | talent | cn_paper | 人才库专家绑定到论文作者 |
| `bind_talent_patent_inventor` | talent | patent | 人才库专家绑定到专利发明人 |
| `bind_org_org` | cn_organization | cn_organization | 机构库跨库绑定 |

边属性：

```python
{
    "confidence": float,      # 绑定置信度 0-1
    "method": str,            # "rule" | "llm" | "rule+llm"
    "bound_at": str,          # 绑定时间 ISO format
    "rule_score": float,      # 规则匹配分数
    "llm_score": float,       # LLM 判断分数
    "status": str,            # "confirmed" | "candidate" | "rejected"
}
```

### 2.2 绑定 Pipeline

```
输入: 源TAG + 目标TAG + 绑定类型
  ↓
Step 1: 数据召回 — 从 TRS Graph 批量拉取源和目标节点
  ↓
Step 2: 规则召回 — 姓名匹配 + 机构相似度，生成候选绑定对
  ↓
Step 3: LLM 精排 — 对每个候选对，调用 GLM 判断是否同一实体
  ↓
Step 4: 结果写入 — 创建绑定边，写入置信度和状态
  ↓
输出: 绑定结果统计
```

### 2.3 Step 2：规则召回

**人才 ↔ 论文作者：**

- `talent.name_zh` / `name_en` 与 `cn_paper` 中 `authors` 字段做姓名匹配
- 辅助：`talent.scholar_org_name_zh` 与 `cn_paper.institution` 做机构相似度（Jaccard）
- 规则评分：`name_match(0.7) + org_similarity(0.3)`，阈值 ≥ 0.5 进入 LLM 精排

**人才 ↔ 专利发明人：**

- `talent.name_zh` 与 `patent.first_inventor_name` 姓名匹配
- 辅助：`talent.scholar_org_name_zh` 与 `patent.applicants` 机构匹配
- 同样评分逻辑

**机构 ↔ 机构：**

- `cn_organization.name_cn` 相似度（编辑距离 + Jaccard）
- 辅助：省份/城市一致加分
- 评分 ≥ 0.6 进入 LLM 精排

### 2.4 Step 3：LLM 精排

对每个候选绑定对，构造 prompt：

```
你是一个实体对齐专家。请判断以下两个实体是否为同一个现实实体。

实体A（来自{源库}）：{字段摘要}
实体B（来自{目标库}）：{字段摘要}

请严格以JSON格式回答：
{"is_same": true/false, "confidence": 0.0-1.0, "reason": "判断理由"}
```

- 使用 `zhipuai` GLM（项目中已有集成）
- `is_same=true` 且 `confidence >= 0.7` → status="confirmed"
- `is_same=true` 且 `0.5 <= confidence < 0.7` → status="candidate"
- 其余 → 不创建边

### 2.5 服务结构

```
app/services/
  entity_binding.py          # 绑定核心逻辑
  binding_matcher.py         # 规则召回匹配
```

**entity_binding.py** 主类：

```python
class EntityBindingService:
    def __init__(self, graph_db: GraphDatabase):
        self.db = graph_db
        self.matcher = BindingMatcher()

    def bind_talent_paper(self) -> BindingResult     # 人才↔论文
    def bind_talent_patent(self) -> BindingResult    # 人才↔专利
    def bind_org_org(self) -> BindingResult          # 机构↔机构
    def bind_all(self) -> dict                       # 执行全部绑定
    def get_binding_stats(self) -> dict              # 绑定统计
    def get_binding_detail(self, binding_type: str) -> list  # 绑定详情
```

**BindingResult**：

```python
class BindingResult(BaseModel):
    binding_type: str
    total_candidates: int      # 规则召回候选数
    confirmed: int             # LLM 确认数
    candidate: int             # 待确认数
    rejected: int              # LLM 拒绝数
    details: list[dict]        # 每条绑定的详细信息
```

---

## 3. API 路由 + 前端展示

### 3.1 API 路由

`app/routers/entity_binding.py`，前缀 `/api/v1/binding`

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/binding/execute` | 执行绑定（可指定类型或全部） |
| GET | `/api/v1/binding/stats` | 绑定统计概览 |
| GET | `/api/v1/binding/detail` | 绑定详情列表（支持分页、按类型筛选） |
| GET | `/api/v1/binding/graph` | 绑定关系图数据（供前端可视化） |
| POST | `/api/v1/binding/init-data` | 初始化测试数据（插入节点+创建边类型+索引） |
| DELETE | `/api/v1/binding/clear` | 清除绑定边（可选：清除测试数据） |

请求/响应模型：

```python
# 执行绑定请求
class BindingExecuteRequest(BaseModel):
    binding_type: str = "all"  # "talent_paper" | "talent_patent" | "org_org" | "all"

# 绑定统计响应
class BindingStatsResponse(BaseModel):
    talent_paper: BindingResult
    talent_patent: BindingResult
    org_org: BindingResult
    total_confirmed: int
    total_candidates: int

# 图数据响应（前端可视化用）
class BindingGraphResponse(BaseModel):
    nodes: list[dict]  # [{id, label, name, source_db, ...}]
    edges: list[dict]  # [{source, target, type, confidence, status, ...}]
```

### 3.2 前端展示

`app/static/binding.html`，通过 FastAPI 的 `StaticFiles` 挂载，不需要额外前端框架。

四个区域：

1. **操作区**：初始化数据按钮、执行绑定按钮（按类型选择）、清除按钮
2. **统计区**：三种绑定类型的 confirmed/candidate/rejected 计数，用 CSS 卡片展示
3. **绑定详情表**：表格展示每条绑定的源实体名→目标实体名、置信度、方法、状态
4. **关系图**：D3.js force graph 展示绑定关系 — 人才/论文/专利/机构节点用不同颜色，绑定边用虚线，边上标注置信度

技术选型：

- 纯 HTML + CSS + JS，无需构建工具
- D3.js（CDN 引入）做关系图可视化
- 调用 `/api/v1/binding/*` API 获取数据
- 请求绑定操作时显示 loading 状态

---

## 4. 测试数据 + 索引 + 启动流程

### 4.1 测试数据

**talent（5 条）** — 人才库（厂商A）的专家：

| VID | name_zh | name_en | scholar_org_name_zh | fields |
|---|---|---|---|---|
| talent_001 | 张伟 | Wei Zhang | 清华大学 | 知识图谱 |
| talent_002 | 李明 | Ming Li | 北京大学 | 自然语言处理 |
| talent_003 | 王芳 | Fang Wang | 浙江大学 | 计算机视觉 |
| talent_004 | 刘洋 | Yang Liu | 清华大学 | 机器学习 |
| talent_005 | 陈静 | Jing Chen | 复旦大学 | 数据挖掘 |

**cn_paper（6 条）** — 论文库（厂商B）的论文+作者信息：

| VID | zh_name | authors | author_id | institution |
|---|---|---|---|---|
| paper_001 | 基于知识图谱的... | 张伟 | auth_001 | 清华大学 |
| paper_002 | NLP前沿技术... | 李明 | auth_002 | 北京大学 |
| paper_003 | 深度学习在CV中的应用 | 王芳 | auth_003 | 浙大 |
| paper_004 | 机器学习优化方法 | 刘洋 | auth_004 | 清华大学计算机系 |
| paper_005 | 知识图谱构建研究 | 张伟 | auth_005 | Tsinghua University |
| paper_006 | 数据挖掘综述 | 陈静 | auth_006 | 复旦大学 |

**patent（4 条）** — 专利库的专利：

| VID | title_zh | first_inventor_name | applicants |
|---|---|---|---|
| patent_001 | 知识图谱构建方法 | 张伟 | 清华大学 |
| patent_002 | 自然语言处理装置 | 李明 | 北京大学 |
| patent_003 | 图像识别系统 | 王芳 | 浙江大学 |
| patent_004 | 智能推荐算法 | 赵磊 | 中科院 |

**cn_organization（4 条）** — 机构库：

| VID | name_cn | province | city |
|---|---|---|---|
| org_001 | 清华大学 | 北京市 | 北京 |
| org_002 | 北京大学 | 北京市 | 北京 |
| org_003 | 浙江大学 | 浙江省 | 杭州 |
| org_004 | 清华大学计算机系 | 北京市 | 北京 |

### 4.2 设计要点

- **同名不同写**：`王芳` 在 talent 中 org 是"浙江大学"，在 cn_paper 中 institution 是"浙大" — 规则召回应能匹配，LLM 精排应能确认
- **跨语言**：`张伟` 在 talent 中 org 是"清华大学"，在 paper_005 中 institution 是"Tsinghua University" — 规则召回可能漏掉（英文），LLM 应能识别
- **机构层级**：`清华大学` 和 `清华大学计算机系` — 机构绑定应能识别为相关实体
- **无匹配项**：`patent_004` 的发明人"赵磊"在人才库中不存在 — 不应产生绑定
- **歧义项**：如有同名不同人的情况 — LLM 应能区分

### 4.3 索引创建

```nGQL
CREATE TAG INDEX IF NOT EXISTS idx_talent_name ON talent(name_zh);
CREATE TAG INDEX IF NOT EXISTS idx_talent_name_en ON talent(name_en);
CREATE TAG INDEX IF NOT EXISTS idx_talent_org ON talent(scholar_org_name_zh);
CREATE TAG INDEX IF NOT EXISTS idx_paper_author ON cn_paper(authors);
CREATE TAG INDEX IF NOT EXISTS idx_paper_author_id ON cn_paper(author_id);
CREATE TAG INDEX IF NOT EXISTS idx_paper_inst ON cn_paper(institution);
CREATE TAG INDEX IF NOT EXISTS idx_patent_inventor ON patent(first_inventor_name);
CREATE TAG INDEX IF NOT EXISTS idx_org_name ON cn_organization(name_cn);
```

### 4.4 边类型创建

```nGQL
CREATE EDGE IF NOT EXISTS bind_talent_paper_author(confidence double, method string, bound_at string, rule_score double, llm_score double, status string);
CREATE EDGE IF NOT EXISTS bind_talent_patent_inventor(confidence double, method string, bound_at string, rule_score double, llm_score double, status string);
CREATE EDGE IF NOT EXISTS bind_org_org(confidence double, method string, bound_at string, rule_score double, llm_score double, status string);
```

### 4.5 启动流程

`POST /api/v1/binding/init-data` 执行顺序：

1. 创建边类型（3 条 CREATE EDGE nGQL）
2. 创建索引（8 条 CREATE TAG INDEX nGQL）
3. 插入 talent 节点（5 个）
4. 插入 cn_paper 节点（6 个）
5. 插入 patent 节点（4 个）
6. 插入 cn_organization 节点（4 个）
7. 返回初始化结果
