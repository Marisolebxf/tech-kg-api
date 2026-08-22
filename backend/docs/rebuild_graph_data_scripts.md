# 重建图谱数据所需脚本

> 在 TRSGraph `dev` 空间重建「国内外论文/期刊」「重点关注科技企业关系」「科技产业链点 TOP-N 事件关系」三类数据需要运行的脚本。统一在 `backend/` 下执行：`cd backend && PYTHONPATH=. .venv/bin/python <脚本>` 或上传到工作流平台由 `workflow(payload)` 调用。

## 一、国内外论文、期刊（Paper / Person 作者 / Journal / Report + AUTHORED_BY / PUBLISHED_IN / CITED_BY 等）

1. 建 schema：`script/init_paper_journal_schema.py`（Paper/Person/Journal/Report tag + 5 条边 DDL，幂等）。
2. 灌实体与边：`script/load_paper_journal_graph.py`（dwd_zh/en_paper、dwd_zh/en_author、dwd_en_journal → Paper/Person/Journal/Report 顶点 + AUTHORED_BY/PUBLISHED_IN/CITED_BY/RELATED_TO/REFERENCED_BY 边）。
3. 置信度 + 溯源（可选，挂 organization_base mixin + 写 edge.confidence）：
   - `script/paper_journal_relation/cleanup_dup_stubs.py`（清 32 字符重复桩）
   - `script/paper_journal_relation/apply_confidence_schema.py`（ALTER EDGE ADD confidence）
   - `script/paper_journal_relation/attach_provenance.py`（挂 organization_base 溯源 tag）
   - `script/paper_journal_relation/backfill_edge_confidence.py`（回填边 confidence）
   - `script/paper_journal_relation/backfill_stub_journals.py`（补桩 Journal + PUBLISHED_IN）
4. 工作流入口（全量/增量，封装上述点边）：`script/workflow/paper_journal_chain_etl.py`，`function_name="workflow"`，`payload={}` 全量、`{"mode":"incremental","since":"2026-07-01"}` 增量。

## 二、重点关注科技企业关系（Organization / Person 任职 / News-Event + EMPLOYED_BY / 治理类边）

1. 建 schema：`python -m script.organization_entity_etl init-schema`（Organization/Person/News/Event 等 tag）。
2. 灌机构域实体（Organization/Person/News/Event/Project/Product 顶点，**只建点不建边**）：`python -m script.organization_entity_etl load --full --write`（可加 `--table dwd_org_base_info` 单表）。
3. 灌机构域关系（EMPLOYED_BY/EXECUTIVE_OF/LEGAL_REP_OF/SHAREHOLDER_OF/AFFILIATED_WITH/INVOLVED_IN 等，**只建边不建点**）：`python -m script.organization_relation_etl --relation all --write`（可 `--relation governance`/`project` 等单类，先 `--dry-run` 预览）。
4. 工作流入口：`script/workflows/organization_ingest_workflow.py`，`function_name="workflow"`（封装实体+关系）。
5. Milvus 索引（向量检索用，可选）：`python -m script.organization_milvus_index`。
- 说明：企业背景（行业地位/经营状况）从 Organization 节点 `extra_json` 摊平读取，无需单独脚本；治理类边无任职起止时间，合作时间仅项目/专利/学者工作经历可取（已知数据现状）。

## 三、科技产业链点 TOP-N 事件关系（IndustryChain / IndustryNode + BELONGS_TO_NODE + News/Event + INVOLVED_IN）

1. 灌产业链节点与边：`script/industry_chain_etl/load_industry_chain_graph.py`（dwd_industry_chain_info → IndustryChain/IndustryNode + HAS_NODE/CHILD_OF/DOWNSTREAM_OF；dwd_org_industry_chain_dtl → BELONGS_TO_NODE(org→node, chain_score)；dwd_industry_chain_news_info → News + COVERS_CHAIN）。建缺失 schema 并加载。
2. 回填链节点关联企业：`script/industry_chain_etl/backfill_chain_org_nodes.py`（补 org_{antitypic} 节点及其 BELONGS_TO_NODE）。
3. 事件与风险（INVOLVED_IN org→Event）：事件顶点来自 `organization_entity_etl load`，INVOLVED_IN 边来自 `organization_relation_etl --relation event`（或 `all`）。TOP-N 服务按 event_type 权重 + chain_score 排序取 TOP-N，无需单独脚本。
- 说明：`paper_journal_chain_etl.py` 工作流的「产业链」部分也覆盖链节点/边，可与论文/期刊一并提交执行。

## 运行顺序建议（三类都要重建时）

1. 各域 schema（init_*）→ 2. 论文/期刊（load_paper_journal_graph + paper_journal_relation/*）→ 3. 机构域（organization_entity_etl load → organization_relation_etl）→ 4. 产业链（load_industry_chain_graph + backfill_chain_org_nodes）。

> 注意：dev 是公共图空间，重建前先确认范围；`--dry-run` 预览，`--write` 落库。`merge_node` 在 live trs-graph 不可靠，实体/边均用 `INSERT VERTEX/EDGE`（rank@0 幂等）。
