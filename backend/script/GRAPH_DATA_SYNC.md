# 科技知识图谱 ETL 部署指南（MySQL → trs-graph）

本指南让部署人员在新环境（已 mysqldump 导入 `gkx_element`）从 0 搭建一个与 `dev` 同构的 trs 图空间，支持**全量**与**增量**导入。

> 数据只从 MySQL（`gkx_element`，只读 SELECT）走流程；**禁止从 `dev` 克隆/复制**。`dev` / `gkx` 全程只读。

## 0. 前置

- **trs-graph-service**（默认 `http://localhost:8090`，`X-API-Key` 鉴权，`X-Graph-Space` 选空间）
- **MySQL**：`gkx_element` 已 mysqldump 导入（学者/机构/论文/专利/项目/产业链/事件等 dwd 表）
- **Milvus**（默认 `http://127.0.0.1:19531`，db `default`）
- **Python 3.11 + uv**：`cd backend && uv sync --dev`

## 1. 配置（写进 `backend/.env` 或 shell env）

```
TRS_GRAPH_BASE_URL=http://localhost:8090
TRS_GRAPH_SPACE=<目标空间,如 test>     # 默认 dev；dev 含 demo 数据,techkg 是空壳勿用
TRS_GRAPH_API_KEY=<key>
TRS_GRAPH_TIMEOUT=60
MYSQL_HOST=127.0.0.1  MYSQL_PORT=3306  MYSQL_USERNAME=xxx  MYSQL_PASSWORD=xxx   # gkx_element 只读
MILVUS_URI=http://127.0.0.1:19531  MILVUS_DB_NAME=default
# 后端运行参数(可选):
BUSINESS_API_BASE=http://127.0.0.1:<后端端口>   # 必须=后端自身端口,否则 key-enterprise 自调用失败
RESULT_CACHE_TTL=600  PREWARM_BUSINESS=true
```

> 所有 ETL 脚本与服务都读 `TRS_GRAPH_SPACE`（默认 dev 向后兼容）。设成目标空间即整体指向它。

## 2. 建空间 + schema（顺序重要：最全的 CREATE 先跑,空空间上才生效）

```bash
cd backend && export PYTHONPATH=. TRS_GRAPH_SPACE=<space>
# 建空间(CREATE SPACE 有传播延迟,后续 DDL 瞬态 500/400 重试)
.venv/bin/python -c "from infra.graph_db import get_trs_graph_client as f; g=f(); g.execute_write('CREATE SPACE IF NOT EXISTS <space>(vid_type=FIXED_STRING(64),partition_num=10,replica_factor=1);'); g.close()"
sleep 12
# schema(按序):
.venv/bin/python script/init_paper_journal_schema.py                         # Paper/Journal/Person(4字段,含name_zh)/Keyword/organization_base + 论文边
.venv/bin/python -m script.organization_entity_etl init-schema --space <space>   # Organization全字段/Event/News/Project/Product/DataSource + 治理/风险边 + reconcile Person
.venv/bin/python -m script.init_graph_schema                               # Scholar/EMPLOYED_BY(Organization 已存在则 no-op)
.venv/bin/python -c "from script.industry_chain_etl.load_industry_chain_graph import get_graph_client,ensure_schema; g=get_graph_client(); ensure_schema(g); g.close()"  # IndustryChain/IndustryNode/HAS_NODE/CHILD_OF/DOWNSTREAM_OF/COVERS_CHAIN
.venv/bin/python -m script.init_project_schema                             # 项目边 FUNDED_BY/LEADS/HAS_PARTICIPANT/PARTICIPATES_IN + 索引
```

> `organization_entity_etl init-schema` 的 `reconcile_existing_schema` 在全新空间可能抛 `TagNotFound`（非致命——CREATE 已含 organization_id/confidence 字段，reconcile 的 ALTER 是冗余的）。若 Organization/Person 字段不全，见排错 §5。

## 3. 全量导入（按依赖序）

```bash
export PYTHONPATH=. TRS_GRAPH_SPACE=<space> ORGANIZATION_ETL_LOCK_FILE=/tmp/org_etl.lock
.venv/bin/python -m script.organization_entity_etl load --full --write          # 机构/法人Person/事件/资讯/项目/产品/DataSource 顶点
.venv/bin/python -m script.organization_relation_etl --write                  # 治理/风险/资讯边(注意:无 load 子命令,直接 --write)
.venv/bin/python -m script.load_scholar_entities                              # 学者 Person(nGQL INSERT,自适应 tag 字段)
.venv/bin/python -m script.load_scholar_relations                             # AFFILIATED_WITH + COAUTHOR_WITH
.venv/bin/python -m script.load_paper_journal_graph      # 论文/期刊/作者Person/AUTHORED_BY/PUBLISHED_IN/CITES/CITED_BY/报告(默认灌全;专家论文合作/单节点学术关联需灌)
.venv/bin/python -m script.industry_chain_etl.load_industry_graph             # 产业链节点 + BELONGS_TO_NODE(只连已存在 org) + News
# 可选域(本套件已支持,按需):
.venv/bin/python -m script.load_patent_graph             # 专利 + APPLIED_BY/INVENTED_BY
# load_project_graph 仍用 merge_node 且 dev-gated,尚未改写(见 §6),按需另行处理
```

所有写入 `rank@0` 幂等，可安全重跑。

## 4. 建 Milvus 索引

```bash
export PYTHONPATH=. TRS_GRAPH_SPACE=<space>
.venv/bin/python -m script.organization_milvus_index        # org_domain_* collection
.venv/bin/python -m script.build_scholar_milvus_index        # scholar_person
.venv/bin/python -m script.build_paper_journal_milvus_index # paper/journal
.venv/bin/python -m script.build_project_milvus_index
.venv/bin/python -m script.build_patent_milvus_indexes
```

> Milvus collection 按域命名、**不按图空间分**；多空间共享同一 Milvus 实例时 collection 共用（upsert by vid）。独立环境用自己的 Milvus。两个业务页面（重点科技企业 / topn）不读 Milvus，此步为检索类接口与完整度。

## 5. 切后端 + 验证

```bash
# 后端指向目标空间(BUSINESS_API_BASE 必须=后端自身端口)
env TRS_GRAPH_SPACE=<space> BUSINESS_API_BASE=http://127.0.0.1:8000 \
    PREWARM_BUSINESS=true RESULT_CACHE_TTL=600 \
    .venv/bin/python -m uvicorn main:app --host 0.0.0.0 --port 8000 --workers 4

# 验证两个 demo 用例(应与 dev 一致):
curl -X POST http://127.0.0.1:8000/api/v1/kg-service/key-enterprise-relation \
  -H 'Content-Type: application/json' -d '{"expert_id":"person_855924f1"}'   # 期望:郭佳佳→新智认知,governance 任职
curl -X POST http://127.0.0.1:8000/api/v1/kg-service/industry-node-top-events \
  -H 'Content-Type: application/json' -d '{"chain_node_id":"IC0007007","top_n":10}'  # 期望:集成电路设计,10事件
```

## 6. 增量（周期）

已接 `--mode incremental`（读 `script/.etl_watermark/<域>.txt` 水位,只灌 `update_time/updated_time > 水位` 的行,整批成功后才前进水位,原子写,丢失/损坏→退化全量）:

```bash
.venv/bin/python -m script.load_scholar_entities --mode incremental          # 水位域:scholar(dwd_scholar.update_time)
.venv/bin/python -m script.organization_entity_etl load --full --write --mode incremental   # 水位域:org_entity(各表 updated_time;无该列的退化全量)
.venv/bin/python -m script.organization_relation_etl --write --mode incremental            # 水位域:org_relation(治理/风险/资讯边,各 spec 源表 updated_time)
.venv/bin/python -m script.load_paper_journal_graph --mode incremental      # 水位域:paper_journal(zh/en_paper/author 的 updated_time;journal/refs/cites/reports 增量时全量)
```

未接 `--mode`(数据较静态或无 argparse,暂走全量,重跑幂等):
- `load_industry_chain_graph`(产业链节点,数据静态;无 argparse,暂全量)
- `load_project_graph`(仍 merge_node+dev-gate,见 §7 排错)

cron 示例:`0 3 * * * cd backend && TRS_GRAPH_SPACE=<space> PYTHONPATH=. .venv/bin/python -m script.load_scholar_entities --mode incremental`

- 水位文件 `backend/script/.etl_watermark/<域>.txt`：整批成功后才前进、原子写；丢失/损坏→退化全量（只慢不丢）。水位别删；删了即退化全量。

> Person 数说明:`dwd_scholar` 仅 ~2163 条 status=1 学者(非 3.3 万);学者 ETL 全量写入这 2163;图中 Person 总数 = 学者 + 机构域法人/股东/控制人等。dev Person 多是因源库或机构域行更多,非学者 ETL 漏写。

## 7. 排错

- **CREATE SPACE 后 DDL 500/400**：传播延迟，等 10-20s 重试。
- **`merge_node` 在 trs-graph 上不可靠（400）**：`load_scholar_entities` 已改 nGQL `INSERT`（自适应 tag 字段：DESCRIBE 取实有字段，只写交集，数字不加引号）。`load_project_graph`/`load_graph` 仍用 merge_node 且 `load_project_graph` 有 dev-gate（`TRS_GRAPH_SPACE != dev` 即抛错），尚未改写——按需用 `load_scholar_entities`(Person) + `organization_entity_etl`(Org) + `organization_relation_etl`(EMPLOYED_BY) 替代。
- **`graph-search/filtered-subgraph` 400 `/traversal/{vid}/edges`**：请求的 edge_type 在目标空间不存在。重点科技企业页请求 `EXECUTIVE_OF/LEGAL_REP_OF/.../HAS_PARTICIPANT/LEADS/PARTICIPATES_IN/FUNDED_BY` 等——确保 `init_project_schema` 跑过（项目边存在），缺哪个 `CREATE EDGE IF NOT EXISTS X(...)` 补哪个。
- **`dwd_scholar` 无 `scholar_org_id` 列**：`load_scholar_relations` 的 `AFFILIATED_WITH` 走机构名 md5 桩兜底 `org_{md5(name)[:16]}`，边照样建（`merge_edge` 到虚拟 dst 成功、顶点虚拟无属性，coverage 优先）；dev 源表有该列时直指真实 `org_{org_id}`。真实机构对齐交给 `align_scholar_affiliations`（机构域 Milvus 混合检索写 `SAME_AS`，不改原边）。**禁止把这里改成 name-join 跳过**——会让 AFFILIATED_WITH 覆盖率从 ~全量跌到个位数（见 commit ed1ffdb 回归）；已有单元测试 `test_affiliation_uses_md5_stub_when_no_org_id` 锁定桩兜底行为，CI 拦截。
- **COAUTHOR_WITH 合作边覆盖率低（已知局限,非 bug）**：`dwd_scholar_coauthor` 的 co_scholar_id 多为外部学者（`dwd_scholar` 无记录,无源数据灌 Person）,这些合作边 `merge_edge` 写了但 dst Person 顶点不存在 → 遍历查不到（同 AFFILIATED_WITH 模式）。库内学者间合作（两端 Person 都在）正常入库（test 实测 1528 条）。专家直接关系/同事/校友/论文合作模块读此边,查外部学者合作会空属数据局限,非脚本问题；若需合作网络完整,可建 id-only 桩 Person 或改 `load_coauthors` 只写两端存在。
- **`Person` tag 字段不全**（org_entity 写 Person 报 400 `Duplicate column`/缺 name_cn 等）：`dev_organization_schema.ngql` 曾有 `confidence`/`organization_id` 重复列（已修）；CREATE IF NOT EXISTS 对已存在 tag 为 no-op，故最全的 CREATE 必须在空空间先跑（见 §2 顺序）。缺字段可 `ALTER TAG Person ADD (...)` 补。
- **key-enterprise 返回 `专家不存在`**：① `BUSINESS_API_BASE` 没指向后端自身端口（自调用 graph-search 失败）；② 上面 §的 edge_type 缺失导致 filtered-subgraph 400 取不到 seed；③ 结果缓存了旧的 404（`RESULT_CACHE_TTL`），重启后端清缓存。
- **`/tmp/tech_kg_organization_etl.lock` Permission denied**：设 `ORGANIZATION_ETL_LOCK_FILE=/tmp/<自己>.lock`。
- **`.env` 的 `TRS_GRAPH_SPACE`**：曾误设为 `techkg`（空壳，0 人）；应设 `dev`（含 demo 数据）或目标空间。
- **gkx / gkx_element 只读**，禁止写；**dev 不作数据源**（只读对照/基线）。

## 8. 本次（test 空间）已验证

- test 空间从 0 搭建，schema 齐全（Organization 39 字段含 stock_code/external_id；Person 45 字段；IndustryNode/IndustryChain/Event/News；治理+风险+产业链边；项目边补建）。
- demo 用例入库：`person_855924f1`（郭佳佳）+ AFFILIATED_WITH→`org_000213e718b09bd45e71789553cc53d7`（新智认知,stock 603869.SH)；`node_IC0007007`（集成电路设计）+ 82 企业 BELONGS_TO_NODE + 13463 INVOLVED_IN 事件。
- AFFILIATED_WITH 任职边覆盖率:回退 md5 桩兜底(`org_{md5(name)[:16]}`)+ 建 md5 桩 Organization 顶点(trs-graph 对指向"不存在顶点"的边做遍历过滤,桩顶点必须先建,否则边虽存但 `get_node_edges`/`get_edges_by_type` 遍历查不到)。test 实测 2163 学者→2164 条 AFFILIATED_WITH(795 个不同机构 md5 桩顶点),边可遍历、机构名正确;dev 有 scholar_org_id 走真实 org(organization_entity_etl 已建顶点)不触发建桩,不影响 BWNNN602 的 `rebuild_scholar_graph` 流程。
- 后端 `TRS_GRAPH_SPACE=test` 后，两页面返回与 dev 一致：重点科技企业=郭佳佳→新智认知 governance 任职 2019-01~2024-12；topn=集成电路设计 10 事件 82 企业 风险中。
- dev 基线比对不变（写保护 OK）。Milvus builder 对 test 可跑、产出 collection。

## 9. 部署后任职边覆盖率自检（防回归）

部署后跑一遍,确认 AFFILIATED_WITH 覆盖率,防 ed1ffdb 式 name-join 跳过回归:

```bash
PYTHONPATH=. TRS_GRAPH_SPACE=<space> .venv/bin/python -c "
from infra.graph_db import get_trs_graph_client
g=get_trs_graph_client(); g.connect()
n=g.get_edges_by_type('AFFILIATED_WITH', limit=1).total
print('AFFILIATED_WITH:', n)
assert n > 100, '任职边过少,疑似 name-join 跳过回归——见 load_scholar_relations 桩兜底'
g.close()"
```

> 单元测试 `test_affiliation_uses_md5_stub_when_no_org_id`(锁定无 org_id 时走 md5 桩不跳过) + `test_affiliation_builds_stub_org_vertex_when_no_org_id`(锁定建 md5 桩 Organization 顶点) 已在 CI 拦截代码层回归;本 smoke 为部署后运行时校验。
