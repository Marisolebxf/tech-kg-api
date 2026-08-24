# One Relation Per Script Extractors

关系抽取新实现：**一种边一个入口脚本**，与 `entity_extractors_one_entity/`（实体侧）配套。
不 import 旧 ETL 入口模块（`load_scholar_relations` / `organization_relation_etl` /
`load_patent_relations` / `load_project_graph` / `workflow/paper_journal_chain_etl` /
`industry_chain_etl/load_industry_chain_graph`），匹配器等共享基础设施通过 import 复用。

## 设计原则

1. **边脚本一律不建顶点**：端点缺失跳过并计数（`missing_source`/`missing_target`），
   所有建点由实体脚本承接。两类例外显式声明允许悬空端点：
   - `AFFILIATED_WITH` 的机构名 md5 桩（`org_{md5(name)[:16]}`，待 `SAME_AS` 对齐认领）；
   - 论文 DOI 桩（`paper_ref_`/`paper_cit_`/`paper_rel_`）与 `paper_rp_` 桩。
2. **数据内容与旧脚本严格等价**：端点 VID 公式、边属性集、置信度、匹配决策、
   rank 语义全部沿用旧口径。
3. **两条写入通道**（保留旧机制）：
   - **确定性 rank 模式**（机构域/专利域/论文链路旧口径）：`EdgeRecord.rank` 由
     `edge_rank()`（sha256 确定性公式）或 0（旧多值 INSERT 默认 rank）生成，
     写 nGQL `INSERT EDGE @rank`，重跑同身份覆盖更新；
   - **REST merge 模式**（学者/项目域旧口径）：`merge_edge` 按
     `identityProps`（默认 `source_record_id`）upsert。
4. `--since` 增量、行级异常计 `invalid` 继续、`--dry-run`、虚拟源行过滤（机构域）
   与实体包同口径。

## 有意的统一决策（与旧脚本的差异，均为拆分设计文档声明的修复）

- **Keyword VID 三域统一**为 `keyword_{md5(NFKC+空白折叠+casefold(kw))}` 完整 32 位
  （旧口径：专利=md5(casefold)、项目=md5(lower)、论文=md5(原文)，三处不一致会导致
  同一关键词出现多个顶点）。
- **机构域 person 端点 VID 统一为实体侧公式**（`kind|first(org_id, external_id)|name|birth|country`），
  修复旧关系侧 shareholder/executive 分支与实体点的分叉。
- 不迁移旧 RELATION_SPECS 中 6 条永不执行的死配置
  （dwd_zh/en_project 的 PARTICIPATES_IN/FUNDED_BY、dwd_org_industry_chain_dtl 的
  BELONGS_TO_NODE、dwd_org_industry_chain_prod_dtl 的 PRODUCES——产业链边由本包产业链脚本承接）。
- 专利域的 Milvus 向量提升（`promote_vector_organization_matches`）与项目域对齐增强
  （`align_project_relations`）不在边脚本内，保持独立的对齐修正脚本（见下）。

## 入口脚本

| 边类型 | 脚本 |
| --- | --- |
| `HAS_NODE` / `CHILD_OF` / `DOWNSTREAM_OF` | `has_node_relation.py` / `child_of_relation.py` / `downstream_of_relation.py` |
| `BELONGS_TO_NODE` | `belongs_to_node_relation.py`（org 端存在性过滤） |
| `COVERS_CHAIN` | `covers_chain_relation.py` |
| `HAS_KEYWORD`（Patent） | `patent_has_keyword_relation.py` |
| `MEMBER_OF_FAMILY` | `member_of_family_relation.py` |
| `AUTHORED_BY`（论文工作流） | `authored_by_relation.py` |
| `AUTHORED_BY`（学者域兜底） | `authored_by_fallback_relation.py`（两端验存，0.9） |
| `PUBLISHED_IN` | `published_in_relation.py` |
| `HAS_KEYWORD`（Paper） | `paper_has_keyword_relation.py` |
| `CITES`/`CITED_BY`/`RELATED_TO`（DOI 桩） | `paper_cites_relation.py` |
| `REFERENCED_BY` | `referenced_by_relation.py` |
| `COAUTHOR_WITH` | `coauthor_with_relation.py` |
| `AFFILIATED_WITH` | `affiliated_with_relation.py`（含机构名桩，0.6/1.0 分档） |
| `LEGAL_REP_OF` 等 11 种机构域边 | `legal_rep_of_relation.py` / `shareholder_of_relation.py` / `executive_of_relation.py` / `beneficial_owner_of_relation.py` / `actual_controller_of_relation.py` / `invests_in_relation.py` / `acquires_relation.py` / `subsidiary_of_relation.py` / `has_news_relation.py` / `involved_in_relation.py` / `produces_relation.py` |
| `CITES`（Patent↔Patent） | `patent_cites_relation.py` |
| `INVENTED_BY` | `invented_by_relation.py` |
| `APPLIED_BY` / `OWNED_BY` | `applied_by_relation.py` |
| `FUNDED_BY` / `LEADS` / `HAS_PARTICIPANT` / `HAS_OUTPUT` | `funded_by_relation.py` / `leads_relation.py` / `has_participant_relation.py` / `has_output_relation.py` |
| `HAS_KEYWORD`（Project） | `project_has_keyword_relation.py` |

## 共享模块

- `common.py` — `EdgeRecord`、`edge_rank` 确定性公式、nGQL `INSERT EDGE @rank` 渲染、
  REST `merge_edge` 写层、端点批量验存、`ensure_edge_schema` 幂等 ALTER、
  `run_relation_extractor`（分页/since/容错/dedupe/dry-run）。
- `resolvers.py` — `keyword_vid`（三域统一）、`paper_source_id`（`__数字` 后缀）、
  DOI 桩 VID、`ExactOrganizationResolver`（精确唯一名）、`person_vid_for_row`（实体侧公式）。
- `catalog.py` — 机构域 32 条活跃边 spec（复刻旧 `RELATION_SPECS`）。
- `org_edges.py` — 机构域 spec 驱动引擎（`edge_props`/`extract_edge`/`run_org_relation`）。
- `patent_matching.py` — 专利域匹配类边共享原语（复刻旧 `load_patent_relations.py`
  的 `normalize_*`/`identifier_index`/`patent_candidates`/`canonical_entities`/
  `project_evidence_context`/review 记录等；`CITES`/`INVENTED_BY`/`APPLIED_BY`/
  `OWNED_BY` 四个脚本共用）。旧脚本的 Milvus 向量提升
  （`promote_vector_organization_matches`）为可选对齐步骤，不在边脚本内迁移。

## 对齐修正配套（独立脚本，不并入本包）

- `script/align_scholar_affiliations.py` — 机构名桩 → `SAME_AS`（Milvus 混合检索）。
- `script/paper_milvus/align_paper_relations.py` — 论文 DOI 桩 → `SAME_AS`。
- `script/align_project_relations.py` — 项目边精确 + Milvus 对齐增强。

## 执行顺序（对齐 docs/九个业务服务图谱实体关系依赖分析.md 的入图顺序）

1. 实体脚本全部先行（`entity_extractors_one_entity/`）。
2. 结构边：产业链 5 条、专利 HAS_KEYWORD/MEMBER_OF_FAMILY、论文 AUTHORED_BY/PUBLISHED_IN/HAS_KEYWORD、COAUTHOR_WITH。
3. 机构域 11 种边。
4. 匹配边：AFFILIATED_WITH/AUTHORED_BY 兜底 → 项目 5 条 → 专利 INVENTED_BY/APPLIED_BY/CITES。
5. 对齐修正脚本。
