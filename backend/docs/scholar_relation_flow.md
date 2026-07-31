# 学者领域 Milvus 索引、对齐与消歧

> 领域负责人：**伟宁（Scholar）**
> 图空间：`dev`
> 关联脚本：
> - `backend/script/build_scholar_milvus_index.py`
> - `backend/script/align_scholar_affiliations.py`
> - `backend/script/dedupe_scholar_persons.py`

本文档只描述本轮新增的**基于 Milvus 的索引、跨域对齐、同域消歧**流程。
关系抽取本身（`AFFILIATED_WITH` / `COAUTHOR_WITH` / `AUTHORED_BY` 兜底）**未做任何改动**，
字段与幂等约定详见 [`scholar_mapping.md`](./scholar_mapping.md)。

---

## 0. 抽取部分：无变化

| 边 | 脚本 | 状态 |
|----|------|------|
| `AFFILIATED_WITH` (Person → Organization) | `load_scholar_relations.py` | 未改动 |
| `COAUTHOR_WITH` (Person → Person) | `load_scholar_relations.py` | 未改动 |
| `AUTHORED_BY` 跨域兜底 (Paper → Person) | `load_scholar_relations.py --include-authored-by-fallback` | 未改动 |
| Person 顶点 | `load_scholar_entities.py` | 未改动 |

字段级映射见 [`scholar_mapping.md`](./scholar_mapping.md)。以下小节只讲新增内容。

---

## 1. 数据流全景（含新增部分）

```mermaid
flowchart LR
    subgraph Existing[已存在（本轮不改）]
        S["学者主表"]
        C["合作关系表"]
        P["学者论文关系表"]
        E1["实体抽取"]
        E2["关系抽取"]
        VP["Person 顶点"]
        RA["AFFILIATED_WITH"]
        RC["COAUTHOR_WITH"]
    end

    subgraph NewMilvus[本轮新增]
        IX["学者 Milvus 索引<br/>(scholar_person)"]
        OX["机构 Milvus 索引<br/>(organization / 他人构建)"]
        E3["索引构建"]
        E4["跨域对齐"]
        E5["同域消歧"]
        RS1["SAME_AS<br/>桩机构 → 真实机构"]
        RS2["SAME_AS<br/>Person ↔ Person"]
    end

    S --> E1 --> VP
    S --> E2 --> RA
    C --> E2 --> RC
    P --> E2

    VP --> E3 --> IX
    RA --> E4
    OX --> E4
    E4 --> RS1

    IX --> E5
    E5 --> RS2
```

---

## 2. Milvus 索引：`scholar_person` 集合

### 2.1 集合 Schema

| 字段 | 类型 | 说明 |
|------|------|------|
| `vid` | VARCHAR (主键) | `person_{scholar_id}` |
| `scholar_id` | VARCHAR | 供业务侧回查 |
| `name_zh` / `name_en` | VARCHAR | 元数据过滤 |
| `scholar_org` | VARCHAR | 机构名（未经对齐的原文本） |
| `research_fields` | VARCHAR | 研究方向 |
| `text` | VARCHAR | 拼接后的完整文本（供 debug） |
| `dense_vec` | FLOAT_VECTOR (512d) | `moka-ai/m3e-small` 稠密向量 |
| `sparse_vec` | SPARSE_FLOAT_VECTOR | BM25 稀疏向量 |

### 2.2 索引

- `dense_vec`：**HNSW**，metric = COSINE，`M=16`, `efConstruction=200`
- `sparse_vec`：**SPARSE_INVERTED_INDEX**，metric = IP

### 2.3 文本拼接

```
{name_zh}｜{name_en}｜机构：{scholar_org}｜研究方向：{research_fields}｜简介：{bio_zh[:500]}
```

### 2.4 构建流程

```mermaid
flowchart LR
    A["从图谱拉 Person 顶点<br/>（分页）"] --> B["拼接文本"]
    B --> C1["稠密编码：m3e-small (512d)"]
    B --> C2["BM25 拟合语料 + 稀疏编码"]
    C1 --> D["组装行数据"]
    C2 --> D
    D --> E["建/复用 scholar_person 集合"]
    E --> F["分批 upsert（200 行/批）"]
    F --> G["flush + 建索引"]
```

### 2.5 混合检索接口

```python
milvus.hybrid_search(
    collection_name="scholar_person",
    reqs=[dense_req, sparse_req],
    ranker=RRFRanker(k=60),
    limit=top_k,
)
```

---

## 3. 跨域对齐：`AFFILIATED_WITH` 桩机构 → 真实机构

### 3.1 触发条件

`AFFILIATED_WITH` 终点满足回退 VID 形态：正则 `^org_[a-f0-9]{16}$`。
这类桩机构由抽取步骤在缺少 `scholar_org_id` 时按机构名 md5 摘要生成。

### 3.2 对齐流程图

```mermaid
flowchart TD
    A[开始] --> B[遍历 AFFILIATED_WITH 边]
    B --> C[获取桩终点集合并去重]
    C --> D{还有桩机构?}
    D -->|否| Z[结束]
    D -->|是| E[取机构名称<br/>先边属性，再桩顶点属性]
    E --> F[稠密向量编码<br/>m3e-small]
    E --> G[BM25 稀疏向量编码]
    F --> H[组装查询向量]
    G --> H
    H --> I[Milvus hybrid_search<br/>RRF融合，top_k=5]
    I --> J[获取候选机构列表]
    J --> K{top1 分数 ≥ 0.65?}
    K -->|是| L[创建 SAME_AS 边<br/>桩机构 → 真实机构]
    L --> M[记录匹配分、名称、来源、批次号]
    M --> D
    K -->|否| N[skipped_low_score]
    N --> D

    style A fill:#e1f5fe
    style Z fill:#e1f5fe
    style L fill:#c8e6c9
    style N fill:#ffcdd2
```

### 3.3 对齐时序图

```mermaid
sequenceDiagram
    autonumber
    participant Aln as 对齐脚本
    participant Graph as 图数据库
    participant Milv as Milvus 机构集合

    Aln->>Graph: 遍历 AFFILIATED_WITH 边
    Graph-->>Aln: 桩终点集合（去重）

    loop 每个桩机构
        Aln->>Aln: 取名称（先边属性，再桩顶点属性）
        Aln->>Aln: 稠密 + BM25 稀疏 双编码
        Aln->>Milv: hybrid_search（RRF，top_k=5）
        Milv-->>Aln: 候选机构 + 融合分
        alt top1 分数 ≥ 阈值
            Aln->>Graph: merge_edge<br/>桩 -[SAME_AS]-> 真实
        else 低于阈值
            Aln->>Aln: skipped_low_score
        end
    end
```

### 3.3 参数

| 变量 | 默认 | 说明 |
|------|------|------|
| `SCHOLAR_ORG_COLLECTION` | `organization` | 机构领域 Milvus 集合名 |
| `SCHOLAR_ALIGN_TOPK` | `5` | 候选数 |
| `SCHOLAR_ALIGN_MIN_SCORE` | `0.65` | 融合分阈值 |
| `SCHOLAR_DENSE_MODEL` | `moka-ai/m3e-small` | 稠密模型 |
| `SCHOLAR_DENSE_DEVICE` | `cpu` | 推理设备 |

### 3.4 产物与保护

- 新增 `SAME_AS` 边（桩机构 → 真实机构），属性含匹配分、名称、来源、批次号。
- **不删、不改**原 `AFFILIATED_WITH`；查询侧遍历 `SAME_AS` 展开。
- 目标集合不存在时脚本仅记录 warning，不阻塞流水线。

---

## 4. 同域消歧：`Person ↔ Person` `SAME_AS`

### 4.1 问题

`scholar_id` 是 `dwd_scholar` 主键，不等同于自然人全局 ID：

- 同一位学者可能有多条 `scholar_id`（不同批次录入、换机构重新登记等）
- 姓名 / 拼写 / 中英文变体导致源数据无法直接判定
- 反之，不同人也可能同名（`张伟`、`Wang Fang` 之类）

### 4.2 流程

```mermaid
flowchart LR
    A["从图谱拉 Person 顶点"] --> B["拼接文本 + 编码 dense/BM25"]
    B --> C["每人在 scholar_person 集合<br/>hybrid_search top-k=5"]
    C --> D["候选 pair（字典序去重双向）"]
    D --> E["多信号打分"]
    E --> F1["综合分 ≥ 高阈值"]
    E --> F2["中间区间"]
    E --> F3["低于中阈值"]
    F1 --> G1["写 SAME_AS 边（--write）"]
    F2 --> G2["记入 JSON 报表<br/>人工/LLM 复核"]
    F3 --> G3["丢弃"]
```

### 4.3 多信号打分

| 信号 | 计算 | 权重 |
|------|------|------|
| Milvus 混合分（BM25+dense RRF） | `hybrid_search` 返回 score | 0.40 |
| 姓名相似度 | 中英各算 `WRatio`，取较大者 / 100 | 0.30 |
| 机构相似度 | `token_set_ratio(scholar_org)` / 100 | 0.20 |
| 研究方向 Jaccard | 按 `；,、` 切分求交并 | 0.10 |

综合分 = 加权和，取值区间 0~1。

### 4.4 决策阈值

| 综合分 | 处置 |
|--------|------|
| `≥ 0.75` | 高置信 → 直接写 `SAME_AS` |
| `0.55 ~ 0.75` | 疑似 → JSON 报表 |
| `< 0.55` | 丢弃 |

阈值可通过 `--high-threshold`、`--mid-threshold` 或 `SCHOLAR_DEDUPE_HIGH/MID` 覆盖。

### 4.5 幂等与产物

- 组合键 `identityProps = {"source_record_id": f"{a__b}"}`（按字典序规范化，避免双向重复）。
- `SAME_AS` 边属性带 `signal_*`、`match_score`、`ingest_batch/time`，可回溯判定依据。
- **不改动** `AFFILIATED_WITH` / `COAUTHOR_WITH`；查询侧遍历 `SAME_AS` 展开即可。

### 4.6 局限

- 目前**不引入合作者/论文交集信号**（避免每对 pair 都要查图，性能考虑）；生产可加 `signal_coauthor` / `signal_paper`。
- 中间区间需要 LLM 或人工判定；本脚本只出报表，不自动落图。

---

## 5. 命令速查

```bash
cd backend

# 建 Milvus 学者索引（BM25 + 稠密 + 混合）
uv run python -m script.build_scholar_milvus_index --dry-run
uv run python -m script.build_scholar_milvus_index

# 跨域对齐（依赖机构 Milvus 集合）
uv run python -m script.align_scholar_affiliations --dry-run
uv run python -m script.align_scholar_affiliations

# 同域消歧
uv run python -m script.dedupe_scholar_persons --dry-run --report /tmp/scholar_dedupe.json
uv run python -m script.dedupe_scholar_persons --write
```

### 环境变量

| 变量 | 说明 |
|------|------|
| `MILVUS_URI` | 默认 `http://127.0.0.1:19531` |
| `MILVUS_TOKEN` | 可选认证 token |
| `MILVUS_DB_NAME` | 默认 `default` |
| `SCHOLAR_DENSE_MODEL` | 稠密模型（默认 `moka-ai/m3e-small`） |
| `SCHOLAR_DENSE_DEVICE` | `cpu` 或 `cuda` |
| `SCHOLAR_ORG_COLLECTION` | 机构集合名，默认 `organization` |
| `SCHOLAR_ALIGN_TOPK` / `SCHOLAR_ALIGN_MIN_SCORE` | 跨域对齐 top-k 与阈值 |
| `SCHOLAR_DEDUPE_TOPK` / `SCHOLAR_DEDUPE_HIGH` / `SCHOLAR_DEDUPE_MID` | 同域消歧 top-k 与两档阈值 |
