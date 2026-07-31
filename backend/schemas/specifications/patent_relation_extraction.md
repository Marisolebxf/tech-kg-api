# 专利关系抽取流程

## 1. 文档职责与范围

本文完整描述从`Patent`出发的七类有向关系，按“源数据可直接确定 → 标准业务标识唯一匹配 → 名称对齐与消歧”排序。图读写统一通过`infra.graph_db.get_trs_graph_client`，不直接使用`nebula3` Python SDK。

| 顺序 | 关系 | 确定方式 | 自动写边条件 |
|---:|---|---|---|
| 1 | `HAS_KEYWORD` | 源关键词确定性生成 | 关键词非空 |
| 2 | `MEMBER_OF_FAMILY` | 同域`patent_id`＋家族号 | 家族号非空且终点存在 |
| 3 | `CITES` | 专利标准编号唯一匹配 | 唯一Patent命中 |
| 4 | `OUTPUT_OF` | 项目同域源ID＋专利标准编号 | 两端均唯一命中 |
| 5 | `APPLIED_BY` | 申请人名称跨Person/Organization域裁决 | 机构唯一且人员域无同名，或有权威dev VID |
| 6 | `OWNED_BY` | 权利人名称对齐 | 唯一且证据充分 |
| 7 | `INVENTED_BY` | 人名＋附加证据消歧 | 不允许只凭姓名写边 |

## 2. 总处理流程

```mermaid
flowchart TD
    A[读取关系源表] --> B[展开数组并规范化名称或编号]
    B --> C{目标信息类型}

    C -->|关键词或同域家族号| D[确定性创建或复用目标]
    D --> E[取得目标真实VID<br/>confidence=1.0]

    C -->|专利号或项目同域源ID| F[优先精确索引或dev属性查询]
    F --> G{唯一命中?}
    G -->|是| H[取得真实VID<br/>confidence=1.0]
    G -->|否| I[记录未匹配]

    C -->|机构名或人名| J[规范名和alias精确候选]
    J --> K{候选唯一且实体域明确?}
    K -->|是| L[取得真实VID并记录证据]
    K -->|否| M[BM25/向量仅作候选增强]
    M --> N{存在机构 项目<br/>权威标识等附加证据?}
    N -->|是且唯一| L
    N -->|否| O[待消歧 不写边]

    E --> P[回dev校验起点 终点 Tag]
    H --> P
    L --> P
    P --> Q{同类型同端点边存在?}
    Q -->|否| R[get_trs_graph_client写入dev]
    Q -->|是| S[幂等跳过]
```

共同原则：

1. 同域ID仅在字段语义和值域已验证一致时使用。
2. 不同厂商或数据域的普通`id`不能直接关联，也不能构造dev VID。
3. 标准专利号可以跨域对齐，但必须规范化并唯一命中。
4. Milvus只返回候选及dev VID，最终实体和边必须回TRSGraph验证。
5. 相似度不是事实；人名、机构名不能仅凭向量分数自动写边。

## 3. 索引如何参与关系抽取

### 3.1 Patent自身八个Milvus索引

| 序号 | 索引名称 | Milvus字段 | 来源字段（中文说明） | 索引类型 | 使用的模型或算法 | 在关系构建中的作用 |
|---:|---|---|---|---|---|---|
| 1 | `dense_hnsw` | `dense_vector` | 中文标题（`title_zh`）、英文标题（`title_en`）、原始标题（`title_original`）、中文摘要（`abstract_zh`）、关键词（`keywords`） | HNSW，COSINE | `moka-ai/m3e-small`，512维归一化向量 | 中英文Patent标题、摘要语义候选召回 |
| 2 | `bm25_sparse_inverted` | `sparse_vector` | 专利业务ID、公开号、申请号、授权号、中英文及原始标题、中文摘要、关键词、IPC主分类、CPC主分类 | SPARSE_INVERTED_INDEX，IP | 自定义Hashed BM25，262144维稀疏空间 | 编号、关键词、专业术语和分类号相关性召回 |
| 3 | `publication_number_inverted` | `publication_number` | 公开号（`publication_number`） | 标量INVERTED | 不使用模型 | `CITES`、`OUTPUT_OF`精确定位Patent |
| 4 | `application_number_inverted` | `application_number` | 申请号（`application_number`） | 标量INVERTED | 不使用模型 | `CITES`、`OUTPUT_OF`精确定位Patent |
| 5 | `granted_number_inverted` | `granted_number` | 授权号（`granted_number`） | 标量INVERTED | 不使用模型 | `CITES`、`OUTPUT_OF`精确定位Patent |
| 6 | `family_number_inverted` | `simple_family_number` | 简单专利族号（`simple_family_number`） | 标量INVERTED | 不使用模型 | 核验同族Patent；不能代替PatentFamily终点 |
| 7 | `country_code_inverted` | `country_code` | 国家或地区代码（`country_code`） | 标量INVERTED | 不使用模型 | 按国家或地区过滤候选 |
| 8 | `source_table_inverted` | `source_table` | 数据来源表（`source_table`） | 标量INVERTED | 不使用模型 | 按来源表过滤候选 |

M3E语义文本只包含标题、摘要和关键词；专利编号、IPC、CPC由BM25和标量索引负责，避免编号干扰语义向量。

```mermaid
flowchart TD
    A[关系源数据中的编号 名称或描述] --> B{输入属于哪一类?}

    B -->|完整公开号 申请号 授权号| C[标量倒排索引]
    C --> D[完整字段值精准匹配]

    B -->|关键词 专业术语 IPC CPC| E[Hashed BM25]
    E --> F[bm25_sparse_inverted]
    F --> G[关键词相关候选]

    B -->|中英文标题 摘要或相似描述| H[M3E-small在线服务]
    H --> I[生成512维查询向量]
    I --> J[dense_hnsw语义检索]
    J --> K[语义相似候选]

    G --> L[RRF融合排序]
    K --> L
    D --> M[候选Patent真实VID]
    L --> M
    M --> N[回TRSGraph dev校验VID与Tag]
    N --> O{唯一且证据充分?}
    O -->|是| P[参与关系写入]
    O -->|否| Q[待消歧 不写边]
```

混合检索是查询时联合使用`dense_hnsw`和`bm25_sparse_inverted`并进行RRF融合，不是第9个物理索引。Patent索引只能返回Patent VID，不能用于寻找Person或Organization。

### 3.2 其他实体索引的复用边界

| 终点 | 当前代码使用 | 限制 |
|---|---|---|
| Person | 只读`org_domain_person`的`canonical_name`和`aliases` | 只有姓名不自动写`INVENTED_BY` |
| Organization | 只读`org_domain_organization`的规范名和别名 | 唯一机构命中且人员域无同名时才自动通过 |
| Project | dev中`Project.source_record_id` | 只允许与同项目数据域ID匹配 |
| PatentFamily | `load_patent_graph.py`按同域家族号创建或复用 | 使用确定性VID并校验dev端点 |

当前`load_patent_relations.py`已经实现Person/Organization名称精确候选，但没有调用它们的BM25＋向量检索。文档中的向量流程是安全的候选增强规则，不表示相似度可以直接写边。

### 3.3 置信度规则

| 匹配方式 | confidence | 自动写边 |
|---|---:|---|
| 源关键词、同域家族号直接确定 | 1.00 | 是 |
| 显式属于dev命名空间的`graph_vid`且Tag校验通过 | 1.00 | 是 |
| 标准专利编号唯一命中 | 1.00 | 是 |
| Organization规范名/alias唯一命中且Person域无同名 | 0.98 | 是 |
| 图属性名称唯一匹配 | 0.99 | 是，仍需Tag校验 |
| BM25或M3E相似候选 | 不直接作为最终置信度 | 否，需附加证据 |
| Person只有姓名 | 不赋可写边分值 | 否 |

## 4. 第1条：HAS_KEYWORD

**方向**：Patent → Keyword
**源表字段**：`dwd_patent.patent_id`、`keywords[].zhName/enName/name`
**代码入口**：`script/load_patent_graph.py`

```mermaid
flowchart LR
    A[keywords数组项] --> B[按zhName enName name取值]
    B --> C[NFKC 空白规范化 去重]
    C --> D[生成Keyword确定性VID]
    D --> E[写Keyword]
    E --> F[写HAS_KEYWORD<br/>confidence=1.0]
```

不需要Milvus或跨域消歧。`source_record_id`保存`{patent_id}:keywords:{index}`。

## 5. 第2条：MEMBER_OF_FAMILY

**方向**：Patent → PatentFamily
**源表字段**：`dwd_patent_family.patent_id`、`simple_family_number`

```mermaid
flowchart TD
    A[读取patent_id和simple_family_number] --> B{家族号非空?}
    B -->|否| C[跳过并记录]
    B -->|是| D[同域patent_id定位Patent]
    D --> E[按dev既有规则定位PatentFamily真实VID]
    E --> F{两端存在?}
    F -->|是| G[写MEMBER_OF_FAMILY<br/>confidence=1.0]
    F -->|否| H[记录未匹配]
```

`family_number_inverted`可以查询同族Patent，但不能代替PatentFamily终点实体。由`load_patent_graph.py`随Patent实体批次创建或复用PatentFamily，并幂等写入该关系；`load_patent_relations.py`不重复处理。

## 6. 第3条：CITES

**方向**：Patent → Patent
**源表字段**：`dwd_patent_cited.patent_id`、`patent_citations[]`、`cited_by[]`
**代码入口**：`script/load_patent_relations.py --relation-types CITES`

```mermaid
flowchart TD
    A[展开patent_citations和cited_by] --> B[提取标准专利编号]
    B --> C[规范化大小写 空格 连字符]
    C --> D[查询公开号 申请号 授权号]
    D --> E{唯一Patent命中?}
    E -->|否| F[待审核 不写边]
    E -->|是| G[根据数组确定引用方向]
    G --> H[回dev校验两端VID]
    H --> I[写CITES<br/>confidence=1.0]
```

- `patent_citations[]`：当前Patent引用目标Patent。
- `cited_by[]`：数组中的Patent引用当前Patent，写边方向反转。
- 原始编号保存在`reference_identifier`。
- 当前命令默认关系集合不含`CITES`，必须显式指定，避免在未检查引用覆盖率前批量写入。

## 7. 第4条：OUTPUT_OF

**方向**：Patent → Project
**源表字段**：`dwd_zh_project_output.id`、`output_patents[].patent_number`
**代码入口**：`script/load_patent_relations.py`

```mermaid
flowchart TD
    A[项目产出表id] --> B[匹配Project.source_record_id]
    B --> C{Project唯一命中?}
    C -->|否| D[待审核]
    C -->|是| E[取得Project真实VID]
    E --> F[规范化output_patents中的专利号]
    F --> G[查询三个专利号标量索引或dev属性]
    G --> H{Patent唯一命中?}
    H -->|否| D
    H -->|是| I[写Patent到Project的OUTPUT_OF<br/>confidence=1.0]
```

项目表ID只在项目同域中匹配`source_record_id`；专利编号是跨域标准业务标识。两者都唯一时才写边。

## 8. 第5条：APPLIED_BY

**方向**：Patent → Organization/Person
**源表字段**：`dwd_patent.applicants[].name/sequence`

```mermaid
flowchart TD
    A[申请人名称] --> B{源数据有可信subject_type?}
    B -->|有| C[在指定Person或Organization域查询]
    B -->|无| D[同时查询Organization和Person规范名/alias]
    D --> E{机构唯一且Person无同名?}
    E -->|是| F[Organization真实VID<br/>confidence=0.98]
    E -->|否| G[待消歧]
    C --> H{除姓名外证据充分且唯一?}
    H -->|是| I[取得对应真实VID]
    H -->|否| G
    F --> J[写APPLIED_BY]
    I --> J
```

专利源数据可能无法区分人名和机构名，所以不能只根据“有限公司、大学”等后缀直接判定。若名称同时出现在Person和Organization域，保持待消歧。

## 9. 第6条：OWNED_BY

**方向**：Patent → Organization/Person
**源表字段**：`dwd_patent.assignees[].name/sequence`

```mermaid
flowchart TD
    A[权利人名称] --> B[规范化中英文名称]
    B --> C[Organization和Person规范名/alias精确查询]
    C --> D{实体域明确且唯一?}
    D -->|是| E[取得真实VID<br/>confidence=0.98]
    D -->|否| F[可选名称BM25/M3E候选召回]
    F --> G{有别名表 权威标识<br/>或其他业务证据?}
    G -->|是且唯一| E
    G -->|否| H[待消歧 不写边]
    E --> I[写OWNED_BY<br/>is_current=true]
```

当前专利权利人可能以英文机构名出现，而Organization可能只保存中文名。M3E可以帮助召回跨语言候选，但必须结合别名或权威证据，不能只凭向量相似度写边。

## 10. 第7条：INVENTED_BY

**方向**：Patent → Person
**源表字段**：`dwd_patent.inventors[].name/sequence`

```mermaid
flowchart TD
    A[发明人姓名] --> B[查询Person同名候选]
    B --> C{存在显式dev graph_vid<br/>且Person Tag校验通过?}
    C -->|是| D[confidence=1.0]
    C -->|否| E[可选BM25/M3E召回同名候选]
    E --> F{有机构 项目 邮箱 ORCID<br/>或同命名空间权威ID?}
    F -->|是且唯一| G[计算并记录匹配证据]
    F -->|否| H[待消歧 不写边]
    D --> I[写INVENTED_BY]
    G --> I
```

姓名不具备全局唯一性。当前源数据若只有姓名和顺序，即使Person Collection中只有一个同名记录也不自动写边。

## 11. 写边、幂等与审计

```mermaid
sequenceDiagram
    participant R as 关系抽取脚本
    participant M as Milvus/名称候选
    participant G as TRSGraph dev
    R->>M: 精确或候选检索
    M-->>R: 候选VID及证据
    R->>G: 校验VID与Tag
    G-->>R: 节点状态
    R->>G: 查询同类型同端点rank=0边
    alt 边不存在且证据通过
        R->>G: get_trs_graph_client写边
    else 已存在
        R->>R: 幂等跳过
    else 证据不足
        R->>R: 写待消歧日志
    end
```

每条自动写入关系至少记录：`confidence`、`match_method`、`match_evidence`、`source_table`、`source_record_id`；人员/机构关系还记录`source_name`、`subject_type`和`resolution_status`。

## 12. 代码覆盖与执行

| 关系 | 当前代码状态 |
|---|---|
| `HAS_KEYWORD` | 已实现于`load_patent_graph.py` |
| `MEMBER_OF_FAMILY` | 已实现于`load_patent_graph.py` |
| `CITES` | 已实现，但需显式加入`--relation-types` |
| `OUTPUT_OF` | 已实现，默认启用 |
| `APPLIED_BY` | 已实现精确名称裁决，默认启用 |
| `OWNED_BY` | 已实现精确名称裁决，默认启用 |
| `INVENTED_BY` | 已实现安全拒绝仅姓名匹配，默认启用 |

```bash
cd backend

# 先演练，不写图
uv run python -m script.load_patent_relations \
  --dry-run \
  --batch-size 500 \
  --relation-types INVENTED_BY APPLIED_BY OWNED_BY CITES OUTPUT_OF

# 确认待消歧和命中情况后，再去掉--dry-run
```

关系数量属于运行时状态，不在文档中硬编码。应从dev按`Patent`起点和Edge Type实时统计；建立Milvus索引本身不会自动增加关系，只有关系脚本通过校验并写边后数量才会变化。
