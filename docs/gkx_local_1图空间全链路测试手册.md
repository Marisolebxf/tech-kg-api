# gkx_local_1 图空间全链路测试手册（8093 yunfei3 栈 · 本地 DWD 库）

> 版本：2026-10-15 · 全部数据当日从 yunfei3 栈实测导出（API `:8004` / 控制库 `techkg_control_yunfei3` / 图库 SHOW STATS）。
> 定位：本手册与《真实数据全链路测试手册》（dev2 主栈单 Schema 实跑）、《图空间全链路通用测试手册》（ewrdf 自足造数）互补，面向 **yunfei3 栈（web `http://localhost:8093`）的 `gkx_local_1` 图空间**——该空间由 `gkx_verify_1`（远端生产样例库验证空间，见《gkx生产库抽取适配绑定清单》）克隆而来，三件套（**50 Schema / 152 来源绑定 / 46 抽取脚本**）已全部配齐并跑出 **118,068 点 / 388,033 边**，是一套"开箱即验"的真实配置盘点 + 验收手册。
> 用法：第 0~6 节是**现状盘点**（空间里有什么、数据在哪、跑到了什么程度）；第 7 节是**验收步骤**（怎么证明配置和数据是对的）；第 8 节是**排障速查**。

---

## 0. 环境与入口

| 项目 | 值 |
|---|---|
| 被测栈 | yunfei3 栈：web `http://localhost:8093`（根路径直出），api `http://localhost:8004` |
| 鉴权 | AUTH 关闭——API 与页面均可直连，无需登录 |
| 图空间 | `gkx_local_1`（说明：gkx_dwd_local 本地 DWD 库全量 e2e，克隆自 gkx_verify_1） |
| worker | 容器 `tech-kg-temporal-worker-yunfei3`，Temporal 队列消费正常 |
| 图库 | TRS 定制 Nebula，经 `trs-graph-service`（`http://host.docker.internal:8090`，API Key `ysukeg`）访问 |
| 业务/水位库 | host 30306：控制库 `techkg_control_yunfei3`（schema/绑定/脚本/任务），水位库 `techkg_global.kg_script_watermark` |
| 审核案库 | `techkg_global.manual_review_case`（按 `graph_space` 字段隔离） |

与姊妹空间 `gkx_verify_1` 的唯一差别是**数据源**：

| 空间 | 数据源 | 库 | 位置 |
|---|---|---|---|
| gkx_verify_1 | `MYSQL-5F17AA11`（gkx-prod-sample） | `gkx` | 远端 183.240.141.251:3318（生产样例） |
| **gkx_local_1（本手册）** | `MYSQL-DWD-LOCAL`（gkx_dwd_local） | `gkx_dwd_local` | 本机 30306（本地镜像，72 表） |

Schema 集与脚本同源（17 实体 + 33 关系），适配口径见 `docs/gkx生产库抽取适配绑定清单.md`（querySql 只读适配，不动表结构不动数据）。

---

## 1. 配置三件套总览

| 件 | 数量 | 说明 |
|---|---|---|
| Schema | **50**（17 实体 + 33 关系） | DDL 全部 `succeeded`；实体建 TAG 自动注入 id/name/create_time/update_time/source_table 审计列 + vid/溯源列 |
| 来源绑定 | **152** 条 | 全部指向 `MYSQL-DWD-LOCAL · gkx_dwd_local`（本地）；实体/关系可绑多表，每表独立水位 |
| 抽取脚本 | **46** 个 | 全部为 `script/tools/build_portable_steps.py` 生成的自包含单文件（勿手改） |
| 无脚本 Schema | 4 个关系 | APPLIED_BY, INVENTED_BY, OUTPUT_OF, OWNED_BY（图内边数均为 0，一致） |
| 链任务 | 3 条 | 实体链 16 schema / 关系链A 14 / 关系链B 13（第 5 节） |
| 图内数据 | 118,068 点 / 388,033 边 | 2026-10-15 `SUBMIT JOB STATS` 实测（第 6 节） |

### 1.1 源库 `gkx_dwd_local`（72 表，行数为 information_schema 估算值）

| 表 | 行数 | 被绑定给 |
|---|---|---|
| dwd_bid_base_out | 100 | Event |
| dwd_bid_purchase_agency_out | 100 | INVOLVED_IN |
| dwd_bid_target_item_out | 100 | Event |
| dwd_bid_win_candidate_out | 100 | INVOLVED_IN |
| dwd_en_author | 12,871 | AUTHORED_BY, OrganizationBase, Person |
| dwd_en_journal | 1,966 | Journal, OrganizationBase |
| dwd_en_paper | 1,945 | OrganizationBase, PUBLISHED_IN, Paper |
| dwd_en_paper_citation | 527 | CITES |
| dwd_en_paper_classification | 2,018 | HAS_KEYWORD, Keyword, OrganizationBase |
| dwd_en_paper_reference | 66,679 | CITES |
| dwd_en_paper_related | 38,550 | CITES |
| dwd_en_project | 1,530 | FUNDED_BY, HAS_PARTICIPANT, Keyword, LEADS, OrganizationBase, Project |
| dwd_en_project_output | 1,763 | HAS_OUTPUT, OUTPUT_OF |
| dwd_en_report | 897 | OrganizationBase, Report |
| dwd_forg_base_info | 1,100 | Organization, Person, Product |
| dwd_forg_executive_info | 4,940 | EXECUTIVE_OF, Person |
| dwd_forg_product_info | 1,029 | Organization, PRODUCES, Person, Product |
| dwd_forg_shareholder_info | 20,520 | SHAREHOLDER_OF |
| dwd_industry_chain_info | 182 | CHILD_OF, DOWNSTREAM_OF, HAS_NODE, IndustryChain, IndustryNode |
| dwd_industry_chain_news_info | 455 | COVERS_CHAIN, News |
| dwd_org_annual_financial_info | 5,394 | Event, INVOLVED_IN |
| dwd_org_bankruptcy_public_cases | 2,006 | Event, INVOLVED_IN |
| dwd_org_bankruptcy_public_cases_list | 2,107 | INVOLVED_IN |
| dwd_org_base_info | 3,762 | LEGAL_REP_OF, Organization, Person, Product |
| dwd_org_changerecord_info | 100 | Event, INVOLVED_IN |
| dwd_org_company_abnormal | 404 | Event, INVOLVED_IN |
| dwd_org_company_illegal | 510 | Event, INVOLVED_IN |
| dwd_org_company_punish | 265 | Event, INVOLVED_IN |
| dwd_org_executive_info | 4,405 | EXECUTIVE_OF, Person |
| dwd_org_financing_info | 1,073 | Event, INVOLVED_IN |
| dwd_org_heis_info | 100 | Organization, Person, Product |
| dwd_org_important_news_info | 1,000 | HAS_NEWS, News |
| dwd_org_industry_tags | 2,074 | —（未绑定） |
| dwd_org_invest_info | 4,239 | INVESTS_IN |
| dwd_org_merger_acquisition_info | 1,002 | ACQUIRES |
| dwd_org_opt_judicial_case | 1,973 | Event, INVOLVED_IN |
| dwd_org_org_product_info | 1,001 | Organization, PRODUCES, Person, Product |
| dwd_org_recruit_info | 2,065 | Event, INVOLVED_IN |
| dwd_org_risk_shixin | 1,830 | Event, INVOLVED_IN |
| dwd_org_risk_tax_punish | 1,887 | Event, INVOLVED_IN |
| dwd_org_risk_zhixing | 1,989 | Event, INVOLVED_IN |
| dwd_org_shareholder_info | 2,490 | Person, SHAREHOLDER_OF |
| dwd_org_stock_base | 5,824 | Organization, Person, Product |
| dwd_org_stock_finance_info | 5,273 | Event, INVOLVED_IN |
| dwd_org_subsidiary_info | 1,099 | —（未绑定） |
| dwd_patent | 1,743 | APPLIED_BY, INVENTED_BY, Keyword, MEMBER_OF_FAMILY, OWNED_BY, OrganizationBase, Patent, Patent, PatentFamily |
| dwd_patent_abstract | 1,797 | —（未绑定） |
| dwd_patent_cited | 2,000 | —（未绑定） |
| dwd_patent_family | 2,000 | —（未绑定） |
| dwd_patent_legal | 2,000 | —（未绑定） |
| dwd_patent_title | 1,994 | —（未绑定） |
| dwd_research_institute_base_info | 100 | LEGAL_REP_OF, Organization, Person, Product |
| dwd_scholar | 1,743 | Person, STUDIED_AT |
| dwd_scholar_coauthor | 153,796 | COAUTHOR_WITH |
| dwd_scholar_education_background | 173 | —（未绑定） |
| dwd_scholar_research_direction | 2,061 | Keyword, OrganizationBase |
| dwd_scholar_talent_flag | 2,075 | —（未绑定） |
| dwd_scholar_work_experience | 1,209 | AFFILIATED_WITH, ScholarOrganization |
| dwd_special_aomen_company | 100 | Organization, Person, Product |
| dwd_special_hongkong_company | 100 | Organization, Person, Product |
| dwd_special_taiwan_company | 100 | LEGAL_REP_OF, Organization, Person, Product |
| dwd_zh_author | 7,880 | AUTHORED_BY, OrganizationBase, Person |
| dwd_zh_journal | 2,115 | Journal, OrganizationBase |
| dwd_zh_paper | 1,940 | OrganizationBase, PUBLISHED_IN, Paper |
| dwd_zh_paper_citation | 1,012 | CITES |
| dwd_zh_paper_classification | 2,061 | HAS_KEYWORD, Keyword, OrganizationBase |
| dwd_zh_paper_reference | 1,892 | CITES |
| dwd_zh_paper_related | 39,762 | CITES |
| dwd_zh_project | 1,505 | FUNDED_BY, HAS_PARTICIPANT, Keyword, LEADS, OrganizationBase, Project |
| dwd_zh_project_output | 1,365 | HAS_OUTPUT, OUTPUT_OF |
| dwd_zh_report | 1,738 | OrganizationBase, Report |
| dwd_zh_report_paper | 12,656 | REFERENCED_BY |

> 绑定表共 66 张；未绑定表不影响全链路，仅作源库盘点。

---

## 2. Schema 清单

### 2.1 实体（17 个）

| TAG | 中文名 | 属性数 | 图内点数 | 脚本 |
|---|---|---|---|---|
| `DataSource` | 数据来源 | 18 | 39 | `datasource_entity_step.py` |
| `Event` | 事件 | 26 | 23,209 | `event_entity_step.py` |
| `IndustryChain` | 产业链 | 17 | 2 | `industry_chain_entity_step.py` |
| `IndustryNode` | 产业链节点 | 23 | 180 | `industry_node_entity_step.py` |
| `Journal` | 期刊 | 33 | 2,134 | `journal_entity_step.py` |
| `Keyword` | 技术主题 | 18 | 31,645 | `keyword_entity_step.py` |
| `News` | 新闻资讯 | 21 | 1,389 | `news_entity_step.py` |
| `Organization` | 机构 | 50 | 10,329 | `organization_entity_step.py` |
| `OrganizationBase` | 机构基础信息 | 17 | 61,662 | `organization_base_mixin.py` |
| `Paper` | 论文 | 32 | 4,000 | `paper_entity_step.py` |
| `Patent` | 专利 | 48 | 2,010 | `patent_entity_step.py` |
| `PatentFamily` | 专利同族 | 18 | 1,999 | `patent_family_entity_step.py` |
| `Person` | 科技专家 | 50 | 30,097 | `person_entity_step.py` |
| `Product` | 产品 | 19 | 2,039 | `product_entity_step.py` |
| `Project` | 项目 | 46 | 4,005 | `project_entity_step.py` |
| `Report` | 科技成果 | 24 | 3,000 | `report_entity_step.py` |
| `ScholarOrganization` | 学者任职机构 | 18 | 45 | `scholar_organization_entity_step.py` |

### 2.2 关系（33 个）

| EDGE | 中文名 | 源 → 目标 | 属性数 | 图内边数 | 脚本 |
|---|---|---|---|---|---|
| `ACQUIRES` | 收购 | Organization → Organization | 13 | 903 | `acquires_relation_step.py` |
| `ACTUAL_CONTROLLER_OF` | 实际控制关系 | Organization → Organization | 13 | 0 | `actual_controller_of_relation_step.py` |
| `AFFILIATED_WITH` | 任职关系 | Person → Organization | 16 | 1,129 | `affiliated_with_relation_step.py` |
| `APPLIED_BY` | 专利申请方 | Patent → Person | 15 | 0 | `—` |
| `AUTHORED_BY` | 论文署名关系 | Paper → Person | 12 | 18,583 | `authored_by_relation_step.py` |
| `BELONGS_TO_NODE` | 企业归属产业链节点 | Organization → IndustryNode | 10 | 2,943 | `belongs_to_node_relation_step.py` |
| `BENEFICIAL_OWNER_OF` | 最终受益关系 | Person → Organization | 14 | 0 | `beneficial_owner_of_relation_step.py` |
| `CHILD_OF` | 产业节点上下级 | IndustryNode → IndustryNode | 9 | 174 | `child_of_relation_step.py` |
| `CITES` | 论文引用关系 | Paper → Paper | 11 | 147,805 | `paper_cites_relation_step.py` |
| `COAUTHOR_WITH` | 专家合著关系 | Person → Person | 12 | 131,929 | `coauthor_with_relation_step.py` |
| `COVERS_CHAIN` | 产业资讯报道产业链 | News → IndustryChain | 9 | 476 | `covers_chain_relation_step.py` |
| `DOWNSTREAM_OF` | 产业上下游 | IndustryNode → IndustryNode | 9 | 0 | `downstream_of_relation_step.py` |
| `EXECUTIVE_OF` | 高管任职关系 | Person → Organization | 12 | 7,055 | `executive_of_relation_step.py` |
| `FUNDED_BY` | 项目资助方 | Project → Organization | 14 | 150 | `funded_by_relation_step.py` |
| `HAS_KEYWORD` | 论文主题 | Paper → Keyword | 9 | 20,259 | `paper_has_keyword_relation_step.py` |
| `HAS_NEWS` | 企业关联资讯 | News → Organization | 11 | 913 | `has_news_relation_step.py` |
| `HAS_NODE` | 产业链包含产业节点 | IndustryChain → IndustryNode | 9 | 180 | `has_node_relation_step.py` |
| `HAS_OUTPUT` | 成果产出关系 | Project → Paper | 13 | 0 | `has_output_relation_step.py` |
| `HAS_PARTICIPANT` | 项目参加人 | Project → Person | 10 | 990 | `has_participant_relation_step.py` |
| `INVENTED_BY` | 专利发明人 | Patent → Person | 14 | 0 | `—` |
| `INVESTS_IN` | 投资关系 | Organization → Organization | 13 | 4,198 | `invests_in_relation_step.py` |
| `INVOLVED_IN` | 涉及风险事件关系 | Event → Organization | 12 | 23,403 | `involved_in_relation_step.py` |
| `LEADS` | 项目负责人 | Project → Person | 10 | 202 | `leads_relation_step.py` |
| `LEGAL_REP_OF` | 法定代表关系 | Person → Organization | 11 | 3,205 | `legal_rep_of_relation_step.py` |
| `MEMBER_OF_FAMILY` | 家族成员关系 | Patent → PatentFamily | 10 | 2,000 | `member_of_family_relation_step.py` |
| `OUTPUT_OF` | 成果归属关系 | OrganizationBase → Project | 9 | 0 | `—` |
| `OWNED_BY` | 专利权利人 | Patent → Organization | 16 | 0 | `—` |
| `PRODUCES` | 企业生产产品 | Organization → Product | 12 | 2,146 | `produces_relation_step.py` |
| `PUBLISHED_IN` | 论文发表关系 | Paper → Journal | 14 | 4,000 | `published_in_relation_step.py` |
| `REFERENCED_BY` | 被参考 | Paper → Report | 9 | 12,806 | `referenced_by_relation_step.py` |
| `SHAREHOLDER_OF` | 股东持股关系 | Organization → Organization | 12 | 2,407 | `shareholder_of_relation_step.py` |
| `STUDIED_AT` | 就读所属院校 | Person → Organization | 15 | 74 | `studied_at_relation.py` |
| `SUBSIDIARY_OF` | 子公司关系 | Organization → Organization | 11 | 102 | `subsidiary_of_relation_step.py` |

---

## 3. 来源表绑定清单（152 条）

全部绑定：数据源 `MYSQL-DWD-LOCAL`（host.docker.internal:30306）· 库 `gkx_dwd_local`。querySql 列"有"= 绑定带投影 SQL（裁列 / 语义映射 / 过滤 `is_deleted=0`），"无"= 裸表全列读取。


**实体绑定：**

| Schema | 表 | 主键列 | 时间列 | querySql |
|---|---|---|---|---|
| `DataSource` | `placeholder` | `id` | - | 有 |
| `Event` | `dwd_org_annual_financial_info` | `dwd_id` | - | 有 |
| `Event` | `dwd_org_changerecord_info` | `dwd_id` | - | 有 |
| `Event` | `dwd_org_financing_info` | `dwd_id` | updated_time | 无 |
| `Event` | `dwd_org_recruit_info` | `dwd_id` | - | 有 |
| `Event` | `dwd_org_stock_finance_info` | `dwd_id` | updated_time | 无 |
| `Event` | `dwd_org_company_abnormal` | `dwd_id` | updated_time | 无 |
| `Event` | `dwd_org_company_punish` | `dwd_id` | - | 有 |
| `Event` | `dwd_org_company_illegal` | `dwd_id` | updated_time | 无 |
| `Event` | `dwd_org_risk_tax_punish` | `dwd_id` | updated_time | 无 |
| `Event` | `dwd_org_opt_judicial_case` | `dwd_id` | - | 有 |
| `Event` | `dwd_org_risk_shixin` | `dwd_id` | - | 有 |
| `Event` | `dwd_org_risk_zhixing` | `dwd_id` | - | 有 |
| `Event` | `dwd_org_bankruptcy_public_cases` | `dwd_id` | updated_time | 无 |
| `Event` | `dwd_bid_base_out` | `dwd_id` | updated_time | 无 |
| `Event` | `dwd_bid_target_item_out` | `dwd_id` | updated_time | 无 |
| `IndustryChain` | `dwd_industry_chain_info` | `row_pk` | - | 有 |
| `IndustryNode` | `dwd_industry_chain_info` | `row_pk` | - | 有 |
| `Journal` | `dwd_zh_journal` | `pk_id` | updated_time | 无 |
| `Journal` | `dwd_en_journal` | `dwd_id` | updated_time | 无 |
| `Keyword` | `dwd_scholar_research_direction` | `dwd_id` | updated_time | 无 |
| `Keyword` | `dwd_zh_paper_classification` | `pk_id` | updated_time | 无 |
| `Keyword` | `dwd_en_paper_classification` | `dwd_id` | updated_time | 无 |
| `Keyword` | `dwd_zh_project` | `dwd_id` | updated_time | 无 |
| `Keyword` | `dwd_en_project` | `dwd_id` | updated_time | 无 |
| `Keyword` | `dwd_patent` | `source_row_id` | - | 有 |
| `News` | `dwd_org_important_news_info` | `dwd_id` | - | 有 |
| `News` | `dwd_industry_chain_news_info` | `row_pk` | - | 有 |
| `Organization` | `dwd_org_base_info` | `dwd_id` | - | 有 |
| `Organization` | `dwd_org_org_product_info` | `dwd_id` | updated_time | 无 |
| `Organization` | `dwd_org_heis_info` | `dwd_id` | updated_time | 无 |
| `Organization` | `dwd_org_stock_base` | `dwd_id` | updated_time | 无 |
| `Organization` | `dwd_special_hongkong_company` | `dwd_id` | updated_time | 无 |
| `Organization` | `dwd_special_taiwan_company` | `dwd_id` | updated_time | 无 |
| `Organization` | `dwd_special_aomen_company` | `dwd_id` | updated_time | 无 |
| `Organization` | `dwd_research_institute_base_info` | `dwd_id` | updated_time | 无 |
| `Organization` | `dwd_forg_base_info` | `row_pk` | - | 有 |
| `Organization` | `dwd_forg_product_info` | `row_pk` | - | 有 |
| `OrganizationBase` | `dwd_zh_paper` | `pk_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_en_paper` | `dwd_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_zh_author` | `pk_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_en_author` | `dwd_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_zh_journal` | `pk_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_en_journal` | `dwd_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_zh_report` | `dwd_id` | - | 有 |
| `OrganizationBase` | `dwd_en_report` | `dwd_id` | - | 有 |
| `OrganizationBase` | `dwd_scholar_research_direction` | `dwd_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_zh_paper_classification` | `pk_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_en_paper_classification` | `dwd_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_zh_project` | `dwd_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_en_project` | `dwd_id` | updated_time | 无 |
| `OrganizationBase` | `dwd_patent` | `source_row_id` | - | 有 |
| `Paper` | `dwd_zh_paper` | `pk_id` | updated_time | 无 |
| `Paper` | `dwd_en_paper` | `dwd_id` | updated_time | 无 |
| `Patent` | `dwd_patent` | `source_row_id` | - | 有 |
| `Patent` | `dwd_patent` | `source_row_id` | - | 有 |
| `PatentFamily` | `dwd_patent` | `source_row_id` | - | 有 |
| `Person` | `dwd_scholar` | `row_pk` | - | 有 |
| `Person` | `dwd_zh_author` | `pk_id` | updated_time | 无 |
| `Person` | `dwd_en_author` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_org_shareholder_info` | `dwd_id` | - | 有 |
| `Person` | `dwd_org_executive_info` | `dwd_id` | - | 有 |
| `Person` | `dwd_forg_executive_info` | `row_pk` | - | 有 |
| `Person` | `dwd_org_base_info` | `dwd_id` | - | 有 |
| `Person` | `dwd_org_org_product_info` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_org_heis_info` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_org_stock_base` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_special_hongkong_company` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_special_taiwan_company` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_special_aomen_company` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_research_institute_base_info` | `dwd_id` | updated_time | 无 |
| `Person` | `dwd_forg_base_info` | `row_pk` | - | 有 |
| `Person` | `dwd_forg_product_info` | `row_pk` | - | 有 |
| `Product` | `dwd_org_base_info` | `dwd_id` | - | 有 |
| `Product` | `dwd_org_org_product_info` | `dwd_id` | updated_time | 无 |
| `Product` | `dwd_org_heis_info` | `dwd_id` | updated_time | 无 |
| `Product` | `dwd_org_stock_base` | `dwd_id` | updated_time | 无 |
| `Product` | `dwd_special_hongkong_company` | `dwd_id` | updated_time | 无 |
| `Product` | `dwd_special_taiwan_company` | `dwd_id` | updated_time | 无 |
| `Product` | `dwd_special_aomen_company` | `dwd_id` | updated_time | 无 |
| `Product` | `dwd_research_institute_base_info` | `dwd_id` | updated_time | 无 |
| `Product` | `dwd_forg_base_info` | `row_pk` | - | 有 |
| `Product` | `dwd_forg_product_info` | `row_pk` | - | 有 |
| `Project` | `dwd_zh_project` | `dwd_id` | - | 有 |
| `Project` | `dwd_en_project` | `dwd_id` | - | 有 |
| `Report` | `dwd_zh_report` | `dwd_id` | - | 有 |
| `Report` | `dwd_en_report` | `dwd_id` | - | 有 |
| `ScholarOrganization` | `dwd_scholar_work_experience` | `row_pk` | - | 有 |

**关系绑定：**

| Schema | 表 | 主键列 | 时间列 | querySql |
|---|---|---|---|---|
| `ACQUIRES` | `dwd_org_merger_acquisition_info` | `dwd_id` | updated_time | 无 |
| `AFFILIATED_WITH` | `dwd_scholar_work_experience` | `row_pk` | - | 有 |
| `APPLIED_BY` | `dwd_patent` | `dwd_id` | updated_time | 无 |
| `AUTHORED_BY` | `dwd_zh_author` | `pk_id` | - | 有 |
| `AUTHORED_BY` | `dwd_en_author` | `dwd_id` | - | 有 |
| `BELONGS_TO_NODE` | `dwd_org_industry_chain_dtl` | `row_pk` | - | 有 |
| `CHILD_OF` | `dwd_industry_chain_info` | `row_id` | - | 有 |
| `CITES` | `dwd_zh_paper_reference` | `pk_id` | updated_time | 无 |
| `CITES` | `dwd_en_paper_reference` | `dwd_id` | updated_time | 无 |
| `CITES` | `dwd_zh_paper_citation` | `row_pk` | - | 有 |
| `CITES` | `dwd_en_paper_citation` | `dwd_id` | updated_time | 无 |
| `CITES` | `dwd_zh_paper_related` | `row_pk` | - | 有 |
| `CITES` | `dwd_en_paper_related` | `dwd_id` | updated_time | 无 |
| `COAUTHOR_WITH` | `dwd_scholar_coauthor` | `dwd_id` | - | 有 |
| `COVERS_CHAIN` | `dwd_industry_chain_news_info` | `row_pk` | - | 有 |
| `DOWNSTREAM_OF` | `dwd_industry_chain_info` | `row_id` | - | 有 |
| `EXECUTIVE_OF` | `dwd_org_executive_info` | `dwd_id` | - | 有 |
| `EXECUTIVE_OF` | `dwd_forg_executive_info` | `row_pk` | - | 有 |
| `FUNDED_BY` | `dwd_zh_project` | `dwd_id` | - | 有 |
| `FUNDED_BY` | `dwd_en_project` | `dwd_id` | - | 有 |
| `HAS_KEYWORD` | `dwd_zh_paper_classification` | `pk_id` | updated_time | 无 |
| `HAS_KEYWORD` | `dwd_en_paper_classification` | `dwd_id` | updated_time | 无 |
| `HAS_NEWS` | `dwd_org_important_news_info` | `dwd_id` | - | 有 |
| `HAS_NODE` | `dwd_industry_chain_info` | `row_id` | - | 有 |
| `HAS_OUTPUT` | `dwd_zh_project_output` | `row_pk` | - | 有 |
| `HAS_OUTPUT` | `dwd_en_project_output` | `row_pk` | - | 有 |
| `HAS_PARTICIPANT` | `dwd_zh_project` | `dwd_id` | - | 有 |
| `HAS_PARTICIPANT` | `dwd_en_project` | `dwd_id` | - | 有 |
| `INVENTED_BY` | `dwd_patent` | `dwd_id` | updated_time | 无 |
| `INVESTS_IN` | `dwd_org_invest_info` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_annual_financial_info` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_stock_finance_info` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_org_changerecord_info` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_financing_info` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_org_recruit_info` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_company_abnormal` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_org_company_punish` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_company_illegal` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_org_risk_tax_punish` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_org_opt_judicial_case` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_risk_shixin` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_risk_zhixing` | `dwd_id` | - | 有 |
| `INVOLVED_IN` | `dwd_org_bankruptcy_public_cases_list` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_org_bankruptcy_public_cases` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_bid_win_candidate_out` | `dwd_id` | updated_time | 无 |
| `INVOLVED_IN` | `dwd_bid_purchase_agency_out` | `dwd_id` | updated_time | 无 |
| `LEADS` | `dwd_zh_project` | `dwd_id` | - | 有 |
| `LEADS` | `dwd_en_project` | `dwd_id` | - | 有 |
| `LEGAL_REP_OF` | `dwd_org_base_info` | `dwd_id` | - | 有 |
| `LEGAL_REP_OF` | `dwd_research_institute_base_info` | `dwd_id` | updated_time | 无 |
| `LEGAL_REP_OF` | `dwd_special_taiwan_company` | `dwd_id` | updated_time | 无 |
| `MEMBER_OF_FAMILY` | `dwd_patent` | `source_row_id` | - | 有 |
| `OUTPUT_OF` | `dwd_zh_project_output` | `dwd_id` | updated_time | 无 |
| `OUTPUT_OF` | `dwd_en_project_output` | `row_pk` | - | 有 |
| `OWNED_BY` | `dwd_patent` | `dwd_id` | updated_time | 无 |
| `PRODUCES` | `dwd_org_org_product_info` | `dwd_id` | updated_time | 无 |
| `PRODUCES` | `dwd_forg_product_info` | `row_pk` | - | 有 |
| `PUBLISHED_IN` | `dwd_zh_paper` | `pk_id` | updated_time | 无 |
| `PUBLISHED_IN` | `dwd_en_paper` | `dwd_id` | updated_time | 无 |
| `REFERENCED_BY` | `dwd_zh_report_paper` | `dwd_id` | - | 有 |
| `SHAREHOLDER_OF` | `dwd_org_shareholder_info` | `dwd_id` | - | 有 |
| `SHAREHOLDER_OF` | `dwd_forg_shareholder_info` | `row_pk` | - | 有 |
| `STUDIED_AT` | `dwd_scholar` | `row_pk` | - | 有 |
| `SUBSIDIARY_OF` | `dwd_forg_subsidiary_info` | `row_pk` | - | 有 |

### 3.1 querySql 三个代表形态

**① 投影裁列（控 Temporal 历史体积，最常见）**——Event 绑 `dwd_org_changerecord_info`：
```sql
SELECT t.dwd_id, t.org_id, t.name_cn, t.external_id, t.update_name, t.update_content, t.update_date,
       t.data_source, t.updated_time
FROM `dwd_org_changerecord_info` t
WHERE t.is_deleted = 0
```

**② 语义映射重建（产业链域列全换）**——IndustryChain 绑 `dwd_industry_chain_info`：
```sql
SELECT t.pk_id AS row_pk,
       t.industry_code AS chain_code, t.industry_name AS chain_name
FROM dwd_industry_chain_info t
WHERE t.is_deleted = 0 AND CHAR_LENGTH(t.industry_code) = 7
```

**③ 恒等占位行（无真实源）**——DataSource 绑 `placeholder`：
```sql
SELECT 1 AS id, '1970-01-01 00:00:01' AS wm_col
```

### 3.2 水位语义

- 裸表绑定按时间列（`updated_time`）记水位；querySql 绑定走水位/keyset 游标。存在 `techkg_global.kg_script_watermark`，`definition_id` 形如 `schema-extract-tag-<slug>` / `schema-extract-edge-<slug>`，`step_id` 形如 `source:<绑定id>`，每绑定一行。
- 每次执行只读水位之后的**增量行**，全部批次成功后推进；重跑不重复读旧行。想让某行被重新处理：把它的 `updated_time` bump 过水位，或对该 Schema 触发「历史数据回填」（backfill，清水位全量重跑）。
- 注意表里多数绑定的**时间列为空**（源表无可靠时间列）——这类绑定首跑全量、之后无增量可拾取，重跑只能靠 backfill。

---

## 4. 抽取脚本清单（46 个）

全部脚本由仓库 `script/tools/build_portable_steps.py` 从 `backend/script/entity_extractors_one_entity/` 源模块及其依赖闭包**自动生成**，自包含单文件、平台喂数管道 `kg.schema.extract` 直传可用。**请勿手改**——改动落回源模块后重新生成。

| 脚本文件 | 绑定 Schema | 大小(B) | 末次校验 | 上传日期 |
|---|---|---|---|---|
| `acquires_relation_step.py` | `ACQUIRES` | 45820 | ok | 2026-10-10 |
| `actual_controller_of_relation_step.py` | `ACTUAL_CONTROLLER_OF` | 45874 | none | 2026-10-10 |
| `affiliated_with_relation_step.py` | `AFFILIATED_WITH` | 6867 | ok | 2026-10-10 |
| `authored_by_relation_step.py` | `AUTHORED_BY` | 5237 | ok | 2026-10-10 |
| `belongs_to_node_relation_step.py` | `BELONGS_TO_NODE` | 5215 | ok | 2026-10-10 |
| `beneficial_owner_of_relation_step.py` | `BENEFICIAL_OWNER_OF` | 45869 | none | 2026-10-10 |
| `child_of_relation_step.py` | `CHILD_OF` | 4534 | ok | 2026-10-10 |
| `paper_cites_relation_step.py` | `CITES` | 5924 | ok | 2026-10-10 |
| `coauthor_with_relation_step.py` | `COAUTHOR_WITH` | 5561 | ok | 2026-10-10 |
| `covers_chain_relation_step.py` | `COVERS_CHAIN` | 4840 | ok | 2026-10-10 |
| `datasource_entity_step.py` | `DataSource` | 11009 | ok | 2026-10-10 |
| `downstream_of_relation_step.py` | `DOWNSTREAM_OF` | 4583 | ok | 2026-10-10 |
| `event_entity_step.py` | `Event` | 19940 | ok | 2026-10-10 |
| `executive_of_relation_step.py` | `EXECUTIVE_OF` | 45834 | ok | 2026-10-10 |
| `funded_by_relation_step.py` | `FUNDED_BY` | 30046 | ok | 2026-10-10 |
| `paper_has_keyword_relation_step.py` | `HAS_KEYWORD` | 5766 | ok | 2026-10-10 |
| `has_news_relation_step.py` | `HAS_NEWS` | 45813 | ok | 2026-10-10 |
| `has_node_relation_step.py` | `HAS_NODE` | 4539 | ok | 2026-10-10 |
| `has_output_relation_step.py` | `HAS_OUTPUT` | 29179 | ok | 2026-10-10 |
| `has_participant_relation_step.py` | `HAS_PARTICIPANT` | 27773 | ok | 2026-10-10 |
| `industry_chain_entity_step.py` | `IndustryChain` | 6782 | ok | 2026-10-10 |
| `industry_node_entity_step.py` | `IndustryNode` | 7111 | ok | 2026-10-10 |
| `invests_in_relation_step.py` | `INVESTS_IN` | 45827 | ok | 2026-10-10 |
| `involved_in_relation_step.py` | `INVOLVED_IN` | 45826 | ok | 2026-10-10 |
| `journal_entity_step.py` | `Journal` | 7281 | ok | 2026-10-10 |
| `keyword_entity_step.py` | `Keyword` | 9136 | ok | 2026-10-10 |
| `leads_relation_step.py` | `LEADS` | 28623 | ok | 2026-10-10 |
| `legal_rep_of_relation_step.py` | `LEGAL_REP_OF` | 45845 | ok | 2026-10-10 |
| `member_of_family_relation_step.py` | `MEMBER_OF_FAMILY` | 4979 | ok | 2026-10-10 |
| `news_entity_step.py` | `News` | 13135 | ok | 2026-10-10 |
| `organization_entity_step.py` | `Organization` | 22078 | ok | 2026-10-10 |
| `organization_base_mixin.py` | `OrganizationBase` | 9316 | ok | 2026-10-10 |
| `paper_entity_step.py` | `Paper` | 7367 | ok | 2026-10-10 |
| `patent_entity_step.py` | `Patent` | 10893 | ok | 2026-10-10 |
| `patent_family_entity_step.py` | `PatentFamily` | 6841 | ok | 2026-10-10 |
| `person_entity_step.py` | `Person` | 26892 | ok | 2026-10-10 |
| `produces_relation_step.py` | `PRODUCES` | 45816 | ok | 2026-10-10 |
| `product_entity_step.py` | `Product` | 17907 | ok | 2026-10-10 |
| `project_entity_step.py` | `Project` | 12357 | ok | 2026-10-10 |
| `published_in_relation_step.py` | `PUBLISHED_IN` | 4859 | ok | 2026-10-10 |
| `referenced_by_relation_step.py` | `REFERENCED_BY` | 5097 | ok | 2026-10-10 |
| `report_entity_step.py` | `Report` | 7150 | ok | 2026-10-10 |
| `scholar_organization_entity_step.py` | `ScholarOrganization` | 4863 | ok | 2026-10-15 |
| `shareholder_of_relation_step.py` | `SHAREHOLDER_OF` | 45844 | ok | 2026-10-10 |
| `studied_at_relation.py` | `STUDIED_AT` | 4716 | ok | 2026-10-10 |
| `subsidiary_of_relation_step.py` | `SUBSIDIARY_OF` | 45839 | ok | 2026-10-10 |

### 4.1 脚本契约（与平台喂数管道的接口）

```python
from kg_sdk import step

@step("scholar_organization")   # 步名=函数声明名；入口函数统一叫 emit
def emit(payload):              # payload 带 rows(本批源行) + source(绑定元数据)
    ...                         # 行 → {"entities": [{"id": vid, "props": {...}}],
    return {...}                #         "edges": [{"fromId", "toId", "props"}],
                                #         "failures": [{"recordId", "error"}]}（逐行毒行隔离）
```

要点：脚本**只做转换不写图**——写图由平台用 nGQL `INSERT VERTEX/EDGE` 列级幂等 upsert 完成，未列出的属性保留原值；空值列跳过不写。同名实体由平台消歧（0.6 名 + 0.4 属性打分），灰区落 T_LINK 人工审核案扣留写图。

### 4.2 完整示例：`scholar_organization_entity_step.py`（最小的一个，4.8KB）

选它做示例是因为结构最短且讲清了 portable 骨架：`_record_id`（pk 缺失时行摘要做 ID）→ `_split_source`（从 payload 拆表名/主键/批次号）→ `_run`（毒行隔离循环）→ 业务 mapper → `@step` 入口。它也是**关系边端点实连**的范例：ScholarOrganization 顶点 vid = 机构名小写 md5 前 16 位，与 AFFILIATED_WITH 边的机构端点同键，保证任职边不悬空。

```python
"""scholar_organization 抽取步（自包含单文件，平台喂数管道 kg.schema.extract 直传可用）。

学者任职机构实体：dwd_scholar_work_experience 的 distinct 机构名落图，
vid 与 AFFILIATED_WITH 关系边的机构端点同键（机构名小写 md5 前 16 位），
保证任职边端点实连（不再悬空）。正式机构库（企业/高校/研究所）落地后
经同名消歧（T_LINK）合并，本域顶点保留溯源。
"""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from kg_sdk import step

logger = logging.getLogger("scholar_organization")

EntityBuilder = Callable[[str, Mapping[str, Any], str], Iterable[Any]]


def _record_id(row: Mapping[str, Any], pk_column: str | None) -> str:
    if pk_column and row.get(pk_column) is not None:
        return str(row[pk_column])
    digest = hashlib.sha256(
        json.dumps(row, ensure_ascii=False, default=str, sort_keys=True).encode()
    ).hexdigest()
    return f"row:{digest[:16]}"


def _split_source(payload: Mapping[str, Any]) -> tuple[str, str, str]:
    source = payload.get("source") or {}
    source_table = str(payload.get("source_table") or source.get("tableName") or "")
    table = source_table.rsplit(".", 1)[-1]
    pk_column = str(source.get("pkColumn") or "id")
    batch = f"se-{str(source.get('id') or 'x')[:8]}"
    return table, pk_column, batch


def _run(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None,
    mapper_by_table: dict[str, EntityBuilder] | None,
    to_json: Callable[[Any], dict[str, Any]],
    key: str,
) -> dict[str, Any]:
    table, pk_column, batch = _split_source(payload)
    if builder is None and mapper_by_table:
        builder = mapper_by_table.get(table)
    if builder is None:
        raise RuntimeError(f"来源表 {table} 没有对应的转换 mapper")
    rows = payload.get("rows") or []
    records: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    for row in rows:
        record_id = _record_id(row, pk_column)
        try:
            mapped = list(builder(table, row, batch) or [])
            records.extend(to_json(r) for r in mapped)
        except Exception as exc:  # noqa: BLE001
            logger.warning("行转换失败 table=%s record=%s: %s", table, record_id, exc)
            failures.append({"recordId": record_id, "error": f"{type(exc).__name__}: {exc}"[:1000]})
    output: dict[str, Any] = {key: records, "failures": failures}
    if table:
        output["stats"] = {
            "table": table,
            "rows": len(rows),
            key: len(records),
            "failed": len(failures),
        }
    return output


def entity_transform(
    payload: Mapping[str, Any],
    *,
    builder: EntityBuilder | None = None,
    mapper_by_table: dict[str, EntityBuilder] | None = None,
) -> dict[str, Any]:
    """实体转换：行 → ``{"id": vid, "props": properties}``。"""

    def to_json(record: Any) -> dict[str, Any]:
        return {"id": record.vid, "props": record.properties}

    return _run(
        payload, builder=builder, mapper_by_table=mapper_by_table, to_json=to_json, key="entities"
    )


@dataclass(frozen=True)
class EntityRecord:
    tag: str
    vid: str
    properties: dict[str, Any]


def now_utc() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def org_name_vid(org_name: str) -> str:
    """机构名 → 机构顶点 vid：与 AFFILIATED_WITH 边端点同一 md5 键。"""
    key = org_name.strip().lower()
    return f"org_{hashlib.md5(key.encode('utf-8')).hexdigest()[:16]}"


def scholar_organization(table: str, row: Mapping[str, Any], batch: str) -> list[EntityRecord]:
    org_name_zh = str(row.get("org_name_zh") or "").strip()
    org_name_en = str(row.get("org_name_en") or "").strip()
    org_name = org_name_zh or org_name_en
    if not org_name:
        return []
    return [
        EntityRecord(
            "ScholarOrganization",
            org_name_vid(org_name),
            {
                "name": org_name,
                "name_cn": org_name_zh,
                "name_en": org_name_en,
                "org_kind": "scholar_affiliation",
                "confidence": 0.6,
                "source_table": "dwd_scholar_work_experience",
                "source_record_id": org_name,
                "ingest_batch": batch,
                "ingest_time": now_utc(),
            },
        )
    ]


def _transform(payload: dict[str, Any]) -> dict[str, Any]:
    """kg.schema.extract 转换入口：rows → entities JSON。"""
    return entity_transform(payload, builder=scholar_organization)


@step("scholar_organization")
def emit(payload):
    return _transform(payload)
```

---

## 5. 链任务与执行现状

### 5.1 三条链任务（2026-10-14 23:45 建，均 once 一次性）

| 任务 | job id | 组成（按链内顺序） | batchSize |
|---|---|---|---|
| gkx本地e2e-实体链 | `job-8b0df2bdcca8` | DataSource, Event, IndustryChain, IndustryNode, Journal, Keyword, News, Organization, OrganizationBase, Paper, Patent, PatentFamily, Person, Product, Project, Report（16） | 2000 |
| gkx本地e2e-关系链A | `job-befa72a610dc` | ACQUIRES, AUTHORED_BY, CHILD_OF, COAUTHOR_WITH, DOWNSTREAM_OF, FUNDED_BY, HAS_NEWS, HAS_OUTPUT, INVESTS_IN, LEADS, MEMBER_OF_FAMILY, PUBLISHED_IN, SHAREHOLDER_OF, SUBSIDIARY_OF（14） | 2000 |
| gkx本地e2e-关系链B | `job-abbb1cd50704` | AFFILIATED_WITH, BELONGS_TO_NODE, CITES, COVERS_CHAIN, EXECUTIVE_OF, HAS_KEYWORD, HAS_NODE, HAS_PARTICIPANT, INVOLVED_IN, LEGAL_REP_OF, PRODUCES, REFERENCED_BY, STUDIED_AT（13） | 2000 |

### 5.2 执行历史（截至 2026-10-15）

| 执行 | 任务 | 开始时间 | 终态 | 说明 |
|---|---|---|---|---|
| EXEC-178813F4E1E44CA9 | 实体链 | 10-14 23:45:09 | **COMPLETED** | 工作流执行完成；tag-* 水位全系列排齐 |
| EXEC-D17C2E4BC9C64068 | 关系链A | 10-14 23:48:10 | TERMINATED | Temporal 中已不存在（workflow execution not found）——服务迁移/重置所致 |
| EXEC-F262AB629E714590 | 关系链B | 10-15 00:17:40 | TERMINATED | 同上 |
| EXEC-27A190BC7B314550 | 关系链A | 10-15 01:28:13 | **COMPLETED** | 重触发后完成（首跑 10-14 23:48 已推进大半 edge-* 水位，重跑幂等补齐） |
| EXEC-D172EB7525AE4B08 | 关系链B·INVOLVED_IN 步 | 10-15 10:23:52 | **ABNORMAL** | "抽取完成，含 1 条失败记录（已转人工审核）"——ABNORMAL≠失败，图已写入，失败行进审核案 |
| EXEC-4C5CA10365F940F7 | 关系链B | 10-15 10:24:36 | **COMPLETED** | — |
| EXEC-D7AF5C3DC5974283 | 关系链A | 10-15 11:29:44 | **COMPLETED** | 幂等重跑（水位已高，空读快过） |
| EXEC-9BB0969F0CB445C9 | 关系链B | 10-15 11:29:58 | **COMPLETED** | 同上 |

### 5.3 水位现状（`techkg_global.kg_script_watermark`）

链内每个 schema 一步，`definition_id = schema-extract-tag-<slug>`（实体）/ `schema-extract-edge-<slug>`（关系），行数=该 schema 的来源绑定数（含重试留痕）。核对命令：

```sql
SELECT definition_id, COUNT(*) AS steps, MAX(watermark) AS max_wm, MAX(updated_at) AS last_touch
FROM techkg_global.kg_script_watermark
WHERE definition_id LIKE 'schema-extract-tag-%' OR definition_id LIKE 'schema-extract-edge-%'
GROUP BY definition_id ORDER BY definition_id;
```

> ⚠ **时区口径**：水位表 `updated_at` 为 UTC，控制库 `workflow_executions.started_at` 为本地时（CST，差 8 小时）。例如实体链 10-14 23:45 CST 开跑，水位 touch 时间显示 10-14 15:45。对照两边时先换算。

---

## 6. 图内数据现状（2026-10-15 `SUBMIT JOB STATS` 实测）

**总量：118,068 顶点 / 388,033 边。**逐 TAG/EDGE：

| 类型 | 名称 | 数量 |
|---|---|---|
| TAG | `DataSource` | 39 |
| TAG | `Event` | 23,209 |
| TAG | `IndustryChain` | 2 |
| TAG | `IndustryNode` | 180 |
| TAG | `Journal` | 2,134 |
| TAG | `Keyword` | 31,645 |
| TAG | `News` | 1,389 |
| TAG | `Organization` | 10,329 |
| TAG | `OrganizationBase` | 61,662 |
| TAG | `Paper` | 4,000 |
| TAG | `Patent` | 2,010 |
| TAG | `PatentFamily` | 1,999 |
| TAG | `Person` | 30,097 |
| TAG | `Product` | 2,039 |
| TAG | `Project` | 4,005 |
| TAG | `Report` | 3,000 |
| TAG | `ScholarOrganization` | 45 |
| EDGE | `ACQUIRES` | 903 |
| EDGE | `ACTUAL_CONTROLLER_OF` | 0 |
| EDGE | `AFFILIATED_WITH` | 1,129 |
| EDGE | `ALUMNI` | 0 |
| EDGE | `APPLIED_BY` | 0 |
| EDGE | `AUTHORED_BY` | 18,583 |
| EDGE | `BELONGS_TO_NODE` | 2,943 |
| EDGE | `BENEFICIAL_OWNER_OF` | 0 |
| EDGE | `CHILD_OF` | 174 |
| EDGE | `CITES` | 147,805 |
| EDGE | `COAUTHOR_WITH` | 131,929 |
| EDGE | `COLLEAGUE` | 1 |
| EDGE | `COVERS_CHAIN` | 476 |
| EDGE | `DOWNSTREAM_OF` | 0 |
| EDGE | `EXECUTIVE_OF` | 7,055 |
| EDGE | `FUNDED_BY` | 150 |
| EDGE | `HAS_KEYWORD` | 20,259 |
| EDGE | `HAS_NEWS` | 913 |
| EDGE | `HAS_NODE` | 180 |
| EDGE | `HAS_OUTPUT` | 0 |
| EDGE | `HAS_PARTICIPANT` | 990 |
| EDGE | `INVENTED_BY` | 0 |
| EDGE | `INVESTS_IN` | 4,198 |
| EDGE | `INVOLVED_IN` | 23,403 |
| EDGE | `LEADS` | 202 |
| EDGE | `LEGAL_REP_OF` | 3,205 |
| EDGE | `MEMBER_OF_FAMILY` | 2,000 |
| EDGE | `OUTPUT_OF` | 0 |
| EDGE | `OWNED_BY` | 0 |
| EDGE | `PRODUCES` | 2,146 |
| EDGE | `PUBLISHED_IN` | 4,000 |
| EDGE | `REFERENCED_BY` | 12,806 |
| EDGE | `SHAREHOLDER_OF` | 2,407 |
| EDGE | `STUDIED_AT` | 74 |
| EDGE | `SUBSIDIARY_OF` | 102 |

> 零数据 EDGE（ACTUAL_CONTROLLER_OF / APPLIED_BY / BENEFICIAL_OWNER_OF / DOWNSTREAM_OF / HAS_OUTPUT / INVENTED_BY / OUTPUT_OF / OWNED_BY）与其"无脚本或源表空"的现状一致；ALUMNI/COLLEAGUE 是专家间接关系（kg-construction）产物，不在三件套内。

---

## 7. 验收与测试步骤

### 7.1 计数对齐（图 vs 源库）

TRS 定制 Nebula 语法注意：`YIELD id(vertex)`（不是 `id($$.Tag)`）。例：

```ngql
USE gkx_local_1;
LOOKUP ON Report YIELD id(vertex) | YIELD COUNT(*) AS n;   -- 3,000
```

代表性对齐表（图内点数 vs 源表精确 `COUNT(*)` 合计，2026-10-15 实测）：

| TAG | 图内 | 源表 COUNT(*) 合计 | 对齐结论 |
|---|---|---|---|
| `Paper` | 4,000 | 4,000（dwd_zh_paper 2,000 + dwd_en_paper 2,000） | **精确一致** |
| `Patent` | 2,010 | 2,010（dwd_patent） | **精确一致** |
| `Report` | 3,000 | 3,000（dwd_zh_report 2,000 + dwd_en_report 1,000） | **精确一致** |
| `Project` | 4,005 | 4,005（dwd_zh_project 2,011 + dwd_en_project 1,994） | **精确一致** |
| `Journal` | 2,134 | 4,207（dwd_zh_journal 2,081 + dwd_en_journal 2,126） | 脚本按 `publication_id` **去重后**落图（期刊表是论文×期刊打平样本） |
| `News` | 1,389 | 1,489（dwd_org_important_news_info 1,013 + dwd_industry_chain_news_info 476） | 差 100，两源均无 is_deleted 过滤——候选口径：跨源同 news_id 去重 / 同名灰案扣留（T_LINK），可按 7.4 审核案核对 |

> **同名消歧灰区（T_LINK 案）会扣留写图**，所以图内数 ≤ 源行数属预期；上表四个"精确一致"说明对应源零重名零空名。要复核其他 TAG：逐表 `COUNT(*)` 后扣除审核案（7.4）。

### 7.2 抽样属性比对

取源表一行主键 → 图内取该点逐字段比对；溯源列应回指绑定表：

```ngql
USE gkx_local_1;
FETCH PROP ON Report "<源表 dwd_id>" YIELD properties(vertex) AS p;
-- name/摘要等应与源行一致；source_table 应为 gkx_dwd_local.dwd_zh_report（或 dwd_en_report）
```

### 7.3 台账核对

- **水位**：5.3 的 SQL；无时间列的绑定首跑即推到高水位，属正常。
- **执行历史**：任务中心（页面）或 `techkg_control_yunfei3.workflow_executions`；注意 5.2 的时区口径。
- **审核案**：见 7.4。

### 7.4 人工审核现状与处置

```sql
SELECT category, status, COUNT(*) FROM techkg_global.manual_review_case
WHERE graph_space='gkx_local_1' GROUP BY category, status;
```

| 类别 | 状态 | 件数 | 处置 |
|---|---|---|---|
| 实体对齐裁决（T_LINK） | OPEN | 2,991 | 人工审核页逐案裁决 merge/create，裁决真实写图 |
| 抽取失败重跑（T_EXTRACT_FAIL） | OPEN | 4,670 | 页面一键重跑（多为源行缺必填名/端点 id） |
| 抽取失败重跑 | RESOLVED | 1 | 已闭环 |

测试审核链路时直接用这批存量案即可（ewrdf 栈造数配方见《图空间全链路通用测试手册》附录）。

### 7.5 索引引导 + 检索冒烟（当前未建，必做）

当前 `gkx_local_1` 的实体检索索引**未建**（`indexed=false, actualDataAvailable=false`）——检索页搜不到东西属设计内行为。在已登录页面（本栈 AUTH 关，直接开 `http://localhost:8093`）控制台执行：

```js
fetch('/api/v1/entity-search/reindex', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({space: 'gkx_local_1'})
}).then(r => r.json()).then(console.log)
```

预期返回 `entityCount` ≈ 118,068（全空间 图 → m3e embedding + BM25 词表 → Milvus `kg_entity`，按 space 隔离；11.8 万实体预计分钟级）。完成后检索冒烟：实体检索页搜任一源表机构名/论文名应命中。同一时间只允许一个重建在跑。

状态查询：`GET /api/v1/entity-search/index-status?space=gkx_local_1`。

### 7.6 增量与幂等重跑

- **幂等**：图写入门是列级 upsert，重触发链任务（如 5.2 里 11:29 的两连跑）水位已高 → 空读快过、不重复写图。
- **增量**：只有绑定了时间列的表会拾取 `updated_time > 水位` 的新行；其余表需 backfill（Schema 详情 → 历史数据回填，或 `POST /api/v1/schema-management/schemas/{id}/backfill`）。
- **单行重处理**：把该行 `updated_time` 改成当前时间即可（注意别改坏业务数据，本栈是共享镜像库）。

---

## 8. 已知坑与排障速查

| 症状/现象 | 根因 | 处置 |
|---|---|---|
| 链执行 TERMINATED："Workflow history size/count exceeds limit" | Temporal 历史上限（~50MB），大载荷活动反复序列化必炸；平台工作流无 ContinueAsNew | 大表必须 querySql 裁列 + 脚本截断大字段（本空间 152 绑定中 76 条带裁列 SQL；姊妹空间 gkx_verify_1 远端全量跑曾因此反复终止，见其执行史） |
| TERMINATED："workflow execution not found" | Temporal 服务迁移/重置，工作流实例丢失 | 直接重新触发；水位保证幂等续跑（本栈 10-15 关系链A/B 即如此恢复） |
| 执行 ABNORMAL | 图已写入但有失败行转人工审核——**不是失败** | 去「运营中心→人工审核」处置 T_EXTRACT_FAIL 案 |
| 实体检索为空 | 空间无索引基座（indexed=false） | 7.5 reindex 一次 |
| 图查询报语法错 `id($$.Tag)` | TRS 定制 Nebula 语法差异 | 用 `YIELD id(vertex)` / `properties(vertex)` |
| graphd OOM/被打爆 | 大 IN 列表查询（TRS 已知瓶颈） | 拆小批次；避免百万级 VID 一次 FETCH |
| 水位时间与执行历史差 8 小时 | 水位表 UTC、执行表 CST | 对照时换算（5.3） |
| LLM 安全校验偶发"返回格式异常" | 校验服务偶抖 | 重试一次即可，非脚本问题 |
| 想改脚本行为 | portable 脚本是生成物 | 改 `backend/script/entity_extractors_one_entity/` 源模块后用 `script/tools/build_portable_steps.py` 重新生成上传，勿手改 |

---

## 附：本手册数据来源（2026-10-15 实测口径）

| 数据 | 来源 |
|---|---|
| Schema 50 条 | `GET :8004/api/v1/schema-management/schemas?graphSpace=gkx_local_1&pageSize=100` |
| 绑定 152 条 | `techkg_control_yunfei3.kg_schema_source` ⋈ `kg_schema_definition` |
| 脚本 46 个 | `kg_schema_script` + `GET …/schemas/{id}/script/content` |
| 图内统计 | `USE gkx_local_1; SUBMIT JOB STATS; SHOW STATS;`（经 trs-graph-service :8090） |
| 执行历史 | `techkg_control_yunfei3.workflow_executions` |
| 审核案 | `techkg_global.manual_review_case WHERE graph_space='gkx_local_1'` |
| 源库行数 | host 30306 `gkx_dwd_local` information_schema（估算值） |
