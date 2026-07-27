# 学者领域实体与关系映射（Scholar Domain Mapping）

> 领域负责人：**伟宁（Scholar）**
> 图空间：`dev`
> 覆盖范围：**Person 顶点** + **从 Person 出发的两条边**（`AFFILIATED_WITH`、`COAUTHOR_WITH`）
> 图客户端：`infra.graph_db.get_trs_graph_client`（不直接依赖 nebula3 SDK）

---

## 目录

- [0. 领域切片](#0-领域切片)
- [1. 抽取脚本与产物](#1-抽取脚本与产物)
- [2. 实体：`dwd_scholar` → `Person`](#2-实体dwd_scholar--person)
- [3. 关系：`dwd_scholar` → `AFFILIATED_WITH`](#3-关系dwd_scholar--affiliated_with)
- [4. 关系：`dwd_scholar_coauthor` → `COAUTHOR_WITH`](#4-关系dwd_scholar_coauthor--coauthor_with)
- [5. 未参与本轮的表](#5-未参与本轮的表)
- [6. 流程图](#6-流程图)
- [7. 时序图](#7-时序图)
- [8. 幂等 / 批次 / 回滚](#8-幂等--批次--回滚)
- [9. 使用方式](#9-使用方式)

---

## 0. 领域切片

TRSGraph 边是有向的，按领域分配我只做 **从 Person 出发的边**：

| 边类型 | 方向 | 来源 | 是否本轮 |
|--------|------|------|--------|
| `AFFILIATED_WITH` | Person → Organization | `dwd_scholar` | ✅ |
| `COAUTHOR_WITH`   | Person → Person       | `dwd_scholar_coauthor` | ✅ |
| `AUTHORED_BY`     | Paper → Person        | `dwd_scholar_paper_relation` | ❌（属于论文领域，起点是 Paper）|
| `LEADS`           | Project → Person      | 项目库 | ❌（属于项目领域）|
| `INVENTED_BY`     | Patent → Person       | 专利库 | ❌（属于专利领域）|
| `EXECUTIVE_OF` 等 | Person → Organization | 机构治理表 | ❌（属于机构领域，公司治理关系而非学术从属）|

Organization、Paper、Project、Patent 顶点由对应领域负责创建；本脚本只落 Person 顶点。

---

## 1. 抽取脚本与产物

| 步骤 | 脚本 | 产物 |
|------|------|------|
| 实体 | `backend/script/load_scholar_entities.py` | Person 顶点 |
| 关系 | `backend/script/load_scholar_relations.py` | `AFFILIATED_WITH` + `COAUTHOR_WITH` 边 |

两个脚本都通过 `infra.graph_db.get_trs_graph_client()` 获取图客户端，
用 `merge_node` / `merge_edge` 幂等写入。

---

## 2. 实体：`dwd_scholar` → `Person`

**VID**：`person_{scholar_id}`
**标签**：`Person`
**identityProps**：`{"source_record_id": scholar_id}`（`merge_node` 用它去重）

### 2.1 基本属性

| 源字段 | 类型 | 图属性 | 处理 |
|--------|------|--------|------|
| `scholar_id` | varchar(32) | `source_record_id` + VID 组成 | `person_{scholar_id}` |
| `name_en` | varchar(128) | `Person.name_en` | 直连 |
| `name_zh` | varchar(128) | `Person.name_zh` | 直连 |
| `avatar` | varchar(256) | `Person.avatar` | 直连 |
| `scholar_org_name_zh` | varchar(1024) | `Person.scholar_org` | 中文优先，缺失时回退英文 |
| `scholar_org_name_en` | text | `Person.scholar_org`（回退） | 见上 |
| `bio` | text | `Person.biography` | 直连 |
| `bio_zh` | text | `Person.bio_zh` | 直连 |
| `paper_nums` | int | `Person.paper_nums` | 缺失置 0 |
| `citation_nums` | int | `Person.citation_nums` | 缺失置 0 |
| `h_index` | int | `Person.h_index` | 缺失置 0 |
| `status` | int(1) | `Person.scholar_status` + 过滤条件 | 只入库 `status=1` |
| `update_time` | datetime | `Person.source_update_time` | 格式化 `YYYY-MM-DD HH:MM:SS` |

### 2.2 工作经历（7 列 → 7 属性）

`work_experience_*` 全部按原字段名直连到 `Person.work_experience_*`：

`work_experience_date`、`work_experience_institution_en/zh`、`work_experience_department_en/zh`、`work_experience_position_en/zh`

### 2.3 教育背景（5 列 → 5 属性）

`education_background_*` 全部按原字段名直连到 `Person.education_background_*`：

`education_background_date`、`education_background_institution_en/zh`、`education_background_degree_en/zh`

### 2.4 溯源属性块（7 字段）

| 属性 | 取值 |
|------|------|
| `source_system` | 固定 `"gkx_element"` |
| `source_table` | 固定 `"dwd_scholar"` |
| `source_record_id` | `scholar_id` |
| `source_url` | 空字符串（本表无原文链接） |
| `ingest_batch` | 运行时生成，形如 `BATCH_20260727_031310_scholar_entities` |
| `ingest_time` | ETL 执行时刻 |
| `source_update_time` | `update_time` |

### 2.5 从 `dwd_scholar_talent_flag` 补充

| 源字段 | 图属性 |
|--------|--------|
| `academician` | `Person.is_academician` |

以 `scholar_id` LEFT JOIN 到 `dwd_scholar`，作为 Person 的一个字段，**不新建实体**。

### 2.6 从 `dwd_scholar_research_direction` 补充

| 源字段 | 图属性 |
|--------|--------|
| `fields` | `Person.research_fields` |

同 `scholar_id` 有多行时用中文分号 `；` 拼接。

---

## 3. 关系：`dwd_scholar` → `AFFILIATED_WITH`

**方向**：`Person → Organization`
**identityProps**：`{"source_record_id": scholar_id}`（`merge_edge` 用它做幂等去重）

### 3.1 端点 VID

| 端 | VID 规则 |
|----|--------|
| 起点 Person | `person_{scholar_id}` |
| 终点 Organization | `org_{scholar_org_id}` 优先；若 `scholar_org_id` 缺失，回退 `org_{md5(scholar_org_name_zh 或 en)[:16]}` |

回退方案确保能落地关系；同名机构的对齐/去重留给后续。

### 3.2 边属性

| 源字段 | 边属性 | 处理 |
|--------|--------|------|
| `scholar_org_name_zh` / `_en` | `AFFILIATED_WITH.affiliation_name` | 中文优先 |
| — | `AFFILIATED_WITH.source` | 固定 `"scholar"` |
| — | `AFFILIATED_WITH.source_table` | 固定 `"dwd_scholar"` |
| `scholar_id` | `AFFILIATED_WITH.source_record_id` | 用作 identityProps |
| — | `AFFILIATED_WITH.ingest_batch` | 批次号 |
| — | `AFFILIATED_WITH.ingest_time` | 时间戳 |

### 3.3 跳过条件

`scholar_org_id` 与 `scholar_org_name_*` 全部为空的记录，无法定位机构 VID，
计入 `skipped_no_org` 但不阻塞流程。

---

## 4. 关系：`dwd_scholar_coauthor` → `COAUTHOR_WITH`

**方向**：`Person → Person`
**identityProps**：`{"source_record_id": "{scholar_id}_{co_scholar_id}"}`

### 4.1 字段映射

| 源字段 | 图上位置 | 处理 |
|--------|--------|------|
| `scholar_id` | 起点 VID | `person_{scholar_id}` |
| `co_scholar_id` | 终点 VID | `person_{co_scholar_id}` |
| `co_paper_count` | `COAUTHOR_WITH.co_paper_count` | 缺失置 0 |
| `co_scholar_name_en/zh` | 不映射 | 冗余展示字段，作者姓名以 Person 顶点属性为准 |
| `co_scholar_avatar` | 不映射 | 同上 |
| `co_scholar_org_name_en/zh` | 不映射 | 机构信息由 Person + AFFILIATED_WITH 表达 |
| `status` | 过滤条件 | 仅取 `status=1` |
| `create_time` / `update_time` | 不映射 | 溯源只用批次号 |
| — | `COAUTHOR_WITH.source_table` | 固定 `"dwd_scholar_coauthor"` |
| — | `COAUTHOR_WITH.source_record_id` | 组合键 `{scholar_id}_{co_scholar_id}` |
| — | `COAUTHOR_WITH.ingest_batch` | 批次号 |
| — | `COAUTHOR_WITH.ingest_time` | 时间戳 |

### 4.2 双向说明

`dwd_scholar_coauthor` 天然对称：同一对合作学者存 `(A, B)` 和 `(B, A)` 两行。
本脚本按行 1:1 落两条**有向边**，保持源数据原貌，不做去重。

生产数据实际规模（`gkx_element` 中 `status=1`）：

- 2063 位学者
- 156141 行合作关系（平均 75.6 位合作者/学者，最高 100）

---

## 5. 未参与本轮的表

| 表 | 说明 |
|----|------|
| `dwd_scholar_papers` | 论文实体，属于**论文领域（亚涛）** |
| `dwd_scholar_paper_relation` | 起点为 Paper，`AUTHORED_BY: Paper → Person` 属于**论文领域** |

`Person` 侧只做出向边；论文侧的入向边在合并时会通过 `person_{scholar_id}` VID 自动对齐。

---

## 6. 流程图

### 6.1 实体抽取

```mermaid
flowchart LR
    subgraph MySQL[gkx_element MySQL]
        S[(dwd_scholar<br/>status=1)]
        T[(dwd_scholar_talent_flag)]
        R[(dwd_scholar_research_direction)]
    end

    subgraph ETL[backend/script/load_scholar_entities.py]
        PRE[预加载 talent_flag &<br/>research_direction 到内存<br/>scholar_id -> value]
        DAO[SQLAlchemy 分页读取<br/>batch=500]
        MAP[属性拼装<br/>Person 顶点]
        BATCH[ingest_batch =<br/>BATCH_yyyymmdd_HHMMSS_scholar_entities]
    end

    subgraph Graph[TRSGraph dev]
        P[[Person 顶点]]
    end

    T --> PRE
    R --> PRE
    S --> DAO
    PRE --> MAP
    DAO --> MAP
    BATCH --> MAP
    MAP -->|infra.graph_db.get_trs_graph_client<br/>merge_node| P
```

### 6.2 关系抽取

```mermaid
flowchart LR
    subgraph MySQL[gkx_element MySQL]
        S2[(dwd_scholar<br/>status=1)]
        C[(dwd_scholar_coauthor<br/>status=1)]
    end

    subgraph ETL2[backend/script/load_scholar_relations.py]
        DAO2[SQLAlchemy 分页读取]
        MAP2[VID 构造 + 属性拼装]
        BATCH2[ingest_batch =<br/>BATCH_yyyymmdd_HHMMSS_scholar_rel]
    end

    subgraph Graph2[TRSGraph dev]
        AW[[Person -[AFFILIATED_WITH]-> Organization]]
        CW[[Person -[COAUTHOR_WITH]-> Person]]
    end

    S2 -->|scholar_id + scholar_org_*| DAO2
    C -->|scholar_id + co_scholar_id +<br/>co_paper_count| DAO2
    DAO2 --> MAP2
    BATCH2 --> MAP2
    MAP2 -->|infra.graph_db.get_trs_graph_client<br/>merge_edge| AW
    MAP2 -->|infra.graph_db.get_trs_graph_client<br/>merge_edge| CW
```

---

## 7. 时序图

### 7.1 单条 `dwd_scholar` 记录的写入

```mermaid
sequenceDiagram
    autonumber
    participant Runner as CLI Runner
    participant SQLA as SQLAlchemy Session
    participant Client as TRSGraphClient
    participant Svc as trs-graph-service<br/>(dev space)

    Runner->>SQLA: SELECT scholar_id, name_*, org_*, bio_*,<br/>work_experience_*, education_background_*,<br/>paper_nums, citation_nums, h_index, status,<br/>update_time FROM dwd_scholar WHERE status=1
    SQLA-->>Runner: rows

    Runner->>SQLA: SELECT scholar_id, academician<br/>FROM dwd_scholar_talent_flag
    SQLA-->>Runner: talent_flags map

    Runner->>SQLA: SELECT scholar_id, fields<br/>FROM dwd_scholar_research_direction
    SQLA-->>Runner: directions map

    loop 每位学者
        Runner->>Runner: props = merge(row, talent, direction, provenance)
        Runner->>Client: merge_node(["Person"],<br/>{"source_record_id": scholar_id}, props)
        Client->>Svc: POST /api/v1/nodes/merge
        Svc-->>Client: 200 OK
        Client-->>Runner: GraphNode
    end
```

### 7.2 单条 `dwd_scholar_coauthor` 记录的写入

```mermaid
sequenceDiagram
    autonumber
    participant Runner as CLI Runner
    participant SQLA as SQLAlchemy Session
    participant Client as TRSGraphClient
    participant Svc as trs-graph-service<br/>(dev space)

    Runner->>SQLA: SELECT scholar_id, co_scholar_id,<br/>co_paper_count FROM dwd_scholar_coauthor<br/>WHERE status=1
    SQLA-->>Runner: rows (~156k)

    loop 每条合作关系
        Runner->>Runner: src=person_{scholar_id}<br/>dst=person_{co_scholar_id}<br/>rid={scholar_id}_{co_scholar_id}
        Runner->>Client: merge_edge(src, dst,<br/>"COAUTHOR_WITH",<br/>{"source_record_id": rid}, props)
        Client->>Svc: POST /api/v1/edges/merge
        Svc-->>Client: 200 OK
    end
```

---

## 8. 幂等 / 批次 / 回滚

* `merge_node` / `merge_edge` 以 `identityProps` 做 upsert，重复执行仅更新属性，不产生重复顶点或边。
* 每次执行生成新的 `ingest_batch`（顶点、边分别有独立命名空间：`_scholar_entities` / `_scholar_rel`），
  用于按批次回溯或删除：

```ngql
# 按批次统计
MATCH (v:Person) WHERE v.Person.ingest_batch == "BATCH_20260727_031310_scholar_entities"
RETURN count(v);

MATCH ()-[e]->() WHERE e.ingest_batch == "BATCH_20260727_031310_scholar_rel"
RETURN count(e);
```

* 出现异常需回滚时，可按 `ingest_batch` 精确删除，不影响其他领域数据。

---

## 9. 使用方式

```bash
cd backend

# 干跑（不写库，只统计和预览）
MYSQL_DATABASE=gkx_element uv run python -m script.load_scholar_entities --dry-run
MYSQL_DATABASE=gkx_element uv run python -m script.load_scholar_relations --dry-run

# 实际写入 dev 空间
TRS_GRAPH_SPACE=dev MYSQL_DATABASE=gkx_element \
    uv run python -m script.load_scholar_entities

TRS_GRAPH_SPACE=dev MYSQL_DATABASE=gkx_element \
    uv run python -m script.load_scholar_relations
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `MYSQL_HOST/PORT/USERNAME/PASSWORD` | 指向 `gkx_element` 所在 MySQL |
| `MYSQL_DATABASE` | 固定 `gkx_element`（也可用 CLI `--database`） |
| `TRS_GRAPH_BASE_URL` | 默认 `http://localhost:8090` |
| `TRS_GRAPH_SPACE` | 固定 `dev` |
| `TRS_GRAPH_API_KEY` | trs-graph-service API Key |

### 运行顺序建议

1. **实体先行**：先跑 `load_scholar_entities.py` 建好 Person 顶点。
2. **机构先行**：`AFFILIATED_WITH` 依赖 Organization 顶点（周威领域）；若目标 VID 不存在，
   `merge_edge` 会挂空边端点，可以在 Organization 批次落地后再运行本脚本。
3. **合作者**：`COAUTHOR_WITH` 只依赖 Person 顶点。
