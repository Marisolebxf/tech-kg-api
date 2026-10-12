# gkx 外部样例库 vs gkx_element 源库——表结构对比（2026-10-10 实测）

> 结论先行：**两库同名 80 张表的列结构 0 张一致**。外部 gkx 是数仓 DWD 装载层格式
> （`dwd_id bigint` 主键 + 治理列包裹业务列），gkx_element 是业务裸表格式（业务主键 + 中文注释）。
> **现有按 gkx_element 写的 45+ 抽取脚本不能直接换连外部 gkx 跑**——列名、列集、类型三处都动过。
> 密码不入本文档（外部库账号见提供方；本地库即部署 root）。

## 1. 两个库是什么

| | 外部 gkx（本次新给） | gkx_element（e2e 一直用的源库） |
| --- | --- | --- |
| 地址 | `183.240.141.251:3318`（外网） | 宿主 MySQL `127.0.0.1:30306`（容器内 `host.docker.internal:30306`） |
| 账号 | `gkx_reader_zp`（只读） | `root` |
| 服务端 | **9.7.0-commercial**（自报版本，非 8.0；pymysql 1.x 客户端协议兼容实测可连） | MySQL 8.0.46 |
| 库定位 | 厂商 gkx 数仓 DWD 层**样例库**（部分表按 2 万行截断，如 `dwd_corp_basic_info` 恰 20,000 行） | 平台抽取链源库 + yunfei3 业务库混放（36 张平台自有表同库） |
| 表数 | 280 = **185 正式** + 95 张 `_bak_202609xx` 备份表 | 142 = **106 业务**（80 dwd + 10 dwd/dws 其它 + 16 ods）+ 36 平台自有 |
| e2e 关系 | 无 | yft1 e2e 实际绑定的是同实例复制品 `gkx_element_yft1`（73 张，清单见 §4 打√） |

## 2. 顶层格式惯例对比（同名 80 张交集实测）

| 维度 | 外部 gkx | gkx_element |
| --- | --- | --- |
| 首列 / 主键 | `dwd_id`（157/185 表，bigint，**交集 80/80 全有主键**）；少数 `pk_id`(18)/`org_id`/`id` | 业务主键裸放：`id`(53)/`org_id`(31)/`logic_id`(15)/`paper_id`(5)/`scholar_id`(5)/`u_id`(4)/`chain_code`(4)/`report_id`(2)；**交集 80 张里仅 7 张有主键** |
| 审计列 | `created_time/updated_time/creater/updater` 四件套 184/185 表齐 | 仅 54/142 表有 `created_time`；不少表用 `create_time/update_time` |
| 治理列 | 几乎每表追加 `table_data_source`、`is_deleted`、`operator_remarks`、`insert_remark` | 无；个别表有 `data_source`（外部版本反而删掉，换成表级 `table_data_source`） |
| 业务列 | 与 gkx_element 同名但**改版后**的列集：有增有删有改名（见 §5、附录 A） | 平台 45 个脚本面向的列集；DDL 全文见 `docs/图谱ETL源表MySQL建表语句.md`（75 张） |
| 排序规则 | 混用 5 种：utf8mb4_0900_ai_ci(157)/general_ci(47)/unicode_ci(41)/bin(33)/utf8mb3(2) | 基本统一 utf8mb4_general_ci(134) + 0900_ai_ci(8) |
| 索引 | 交集 80 表共 546 个索引 | 交集 80 表共 263 个索引 |
| 特殊表 | 4 张 `*_v3bad`（`dwd_en_report_v3bad` 等，脏数据隔离）；`nums_seq` 序列表；95 张 `_bak_` | 16 张 `ods_*` 贴源层（外部没有 ods 层）；平台自有 36 张 |

## 3. 外部 gkx 正式表清单（185 张，按前缀分组，括号内 information_schema 估算行数）

| 域前缀 | 表数 | 表清单 |
| --- | --- | --- |
| dwd_agg | 1 | `dwd_agg_subsidiary_info`(~19,810) |
| dwd_astock | 1 | `dwd_astock_val_indicators`(~3,019,094) |
| dwd_bid | 4 | `dwd_bid_base_out`(~37,300)、`dwd_bid_purchase_agency_out`(~42,033)、`dwd_bid_target_item_out`(~41,187)、`dwd_bid_win_candidate_out`(~38,352) |
| dwd_calculation | 1 | `dwd_calculation`(~10) |
| dwd_clinical | 2 | `dwd_clinical`(~10)、`dwd_clinical_trial`(~190) |
| dwd_corp | 4 | `dwd_corp_basic_info`(~18,198)、`dwd_corp_his_citic_ic`(~27,677)、`dwd_corp_his_crsc_ic`(~28,556)、`dwd_corp_his_sw_ic`(~76,167) |
| dwd_crystal | 1 | `dwd_crystal_structure`(~351) |
| dwd_deal | 1 | `dwd_deal`(~10) |
| dwd_dim | 5 | `dwd_dim_admin_area`(~19,633)、`dwd_dim_index_attribute`(~867)、`dwd_dim_index_cal`(~3)、`dwd_dim_index_dur`(~7)、`dwd_dim_source_code`(~4) |
| dwd_drug | 3 | `dwd_drug`(~555)、`dwd_drug_profile`(~119)、`dwd_drug_substance`(~222) |
| dwd_en | 17 | `dwd_en_author`(~1,367)、`dwd_en_journal`(~605)、`dwd_en_paper`(~1,356)、`dwd_en_paper_abstract`(~1,192)、`dwd_en_paper_citation`(~1,352)、`dwd_en_paper_cited_by_info`(~74,515)、`dwd_en_paper_classification`(~1,386)、`dwd_en_paper_funding`(~988)、`dwd_en_paper_reference`(~1,330)、`dwd_en_paper_related`(~954)、`dwd_en_paper_title`(~1,387)、`dwd_en_project`(~16,281)、`dwd_en_project_output`(~17,689)、`dwd_en_report`(~10,070)、`dwd_en_report_author`(~18,961)、`dwd_en_report_org`(~961)、`dwd_en_report_v3bad`(~11,384) |
| dwd_event | 1 | `dwd_event`(~20) |
| dwd_foreign | 2 | `dwd_foreign_exchange_info`(~21,732)、`dwd_foreign_org_annual_financial_info`(~51) |
| dwd_forg | 6 | `dwd_forg_base_info`(~19,549)、`dwd_forg_executive_info`(~19,920)、`dwd_forg_product_info`(~19,823)、`dwd_forg_research_org_info`(~19,902)、`dwd_forg_shareholder_info`(~39,494)、`dwd_forg_university_org_info`(~16,790) |
| dwd_fund | 5 | `dwd_fund_basic_info`(~0)、`dwd_fund_bond_allocation`(~0)、`dwd_fund_equity_sector_allocation`(~0)、`dwd_fund_ope_status`(~0)、`dwd_fund_scale_info`(~0) |
| dwd_global | 1 | `dwd_global_policy_base`(~17,526) |
| dwd_heis | 1 | `dwd_heis_info`(~19,215) |
| dwd_high | 1 | `dwd_high_tech_industry_bonds`(~72) |
| dwd_hk | 3 | `dwd_hk_corp_his_sw_ic`(~2,769)、`dwd_hk_sec_daily_quotation`(~1,051,455)、`dwd_hk_stock_val_indicators`(~39,625) |
| dwd_industrial | 5 | `dwd_industrial_fund_basic_info`(~11,586)、`dwd_industrial_fund_investment_project_info`(~9,939)、`dwd_industrial_fund_investment_strategy`(~9,891)、`dwd_industrial_fund_lp_info`(~19,041)、`dwd_industrial_fund_management_institution`(~11,544) |
| dwd_industry | 10 | `dwd_industry_analysis_companies`(~102)、`dwd_industry_analysis_content_types`(~1,000)、`dwd_industry_analysis_countries`(~1,000)、`dwd_industry_analysis_documents`(~827)、`dwd_industry_analysis_industries`(~3,027)、`dwd_industry_analysis_topic_dict`(~92)、`dwd_industry_analysis_topics`(~1,052)、`dwd_industry_chain_info`(~1,296)、`dwd_industry_chain_news_info`(~94,997)、`dwd_industry_code`(~19,855) |
| dwd_information | 1 | `dwd_information`(~32) |
| dwd_job | 1 | `dwd_job`(~10) |
| dwd_ls | 1 | `dwd_ls_stock_daily_quotation`(~4,353,281) |
| dwd_macro | 1 | `dwd_macro_index_data`(~19,857) |
| dwd_main | 3 | `dwd_main_business_composition_area`(~411,731)、`dwd_main_business_composition_industry`(~313,152)、`dwd_main_business_composition_prod`(~522,184) |
| dwd_market | 1 | `dwd_market`(~15) |
| dwd_material | 1 | `dwd_material_virtual_structure`(~10) |
| dwd_medical | 3 | `dwd_medical_company`(~90)、`dwd_medical_company_v3bad`(~90)、`dwd_medical_device`(~9,943) |
| dwd_merger | 1 | `dwd_merger_acquisition_events_party_info`(~19,779) |
| dwd_molecular | 1 | `dwd_molecular_spectrum`(~5) |
| dwd_multi | 1 | `dwd_multi_omics`(~10) |
| dwd_news | 1 | `dwd_news_base`(~19,661) |
| dwd_opt | 1 | `dwd_opt_judicial_case_detail`(~43,911) |
| dwd_option | 2 | `dwd_option_basic_info`(~76)、`dwd_option_daily_quotation`(~14,120) |
| dwd_org | 31 | `dwd_org_annual_financial_info`(~93,945)、`dwd_org_annual_report_asset`(~517,476)、`dwd_org_annual_report_base`(~49,007)、`dwd_org_bankruptcy_public_cases`(~31,141)、`dwd_org_bankruptcy_public_cases_list`(~19,542)、`dwd_org_base_info`(~192,464)、`dwd_org_changerecord_info`(~3,054,575)、`dwd_org_company_abnormal`(~4,979)、`dwd_org_company_illegal`(~247)、`dwd_org_company_punish`(~80,596)、`dwd_org_executive_info`(~385,630)、`dwd_org_financing_info`(~23,662)、`dwd_org_heis_info`(~3,576)、`dwd_org_important_news_info`(~1,371,863)、`dwd_org_income_statement`(~194,054)、`dwd_org_industry_product_tags`(~73,313)、`dwd_org_industry_tags`(~2,197,216)、`dwd_org_invest_info`(~53,758)、`dwd_org_merger_acquisition_info`(~3,565)、`dwd_org_opt_judicial_case`(~3,380,871)、`dwd_org_org_product_info`(~40,612)、`dwd_org_recruit_info`(~6,702,453)、`dwd_org_risk_shixin`(~72,610)、`dwd_org_risk_tax_punish`(~473)、`dwd_org_risk_zhixing`(~535,152)、`dwd_org_sc_info`(~1,716)、`dwd_org_shareholder_info`(~424,496)、`dwd_org_stock_base`(~1,080)、`dwd_org_stock_finance_info`(~42,661)、`dwd_org_subsidiary_info`(~161,341)、`dwd_org_tech_tag`(~196,662) |
| dwd_patent | 13 | `dwd_patent`(~2,690,167)、`dwd_patent_abstract`(~19,247)、`dwd_patent_applicants`(~25,753)、`dwd_patent_assignees`(~19,964)、`dwd_patent_cited`(~20,239)、`dwd_patent_claim`(~10,578)、`dwd_patent_description`(~15,900)、`dwd_patent_family`(~16,235)、`dwd_patent_inventors`(~57,588)、`dwd_patent_legal`(~19,071)、`dwd_patent_priority_filings`(~20,709)、`dwd_patent_title`(~19,420)、`dwd_patent_transfer`(~21,193) |
| dwd_policy | 1 | `dwd_policy_base`(~18,808) |
| dwd_protein | 1 | `dwd_protein`(~9,614) |
| dwd_rd | 1 | `dwd_rd`(~0) |
| dwd_react | 1 | `dwd_react_detail`(~9,825) |
| dwd_rel | 1 | `dwd_rel_reaction_substance`(~7) |
| dwd_research | 1 | `dwd_research_institute_base_info`(~2,012) |
| dwd_safety | 1 | `dwd_safety`(~18,762) |
| dwd_scholar | 9 | `dwd_scholar`(~16,933)、`dwd_scholar_coauthor`(~1,028,293)、`dwd_scholar_education_background`(~42,837)、`dwd_scholar_paper_relation`(~887,927)、`dwd_scholar_papers`(~597,513)、`dwd_scholar_papers_v3bad`(~669,783)、`dwd_scholar_research_direction`(~19,466)、`dwd_scholar_talent_flag`(~16,400)、`dwd_scholar_work_experience`(~56,295) |
| dwd_sci | 1 | `dwd_sci_tech_inno_bonds`(~4,809) |
| dwd_sec | 1 | `dwd_sec_basic_info`(~1,363,254) |
| dwd_similar | 1 | `dwd_similar_substance`(~5) |
| dwd_small | 1 | `dwd_small_molecule_screening`(~10) |
| dwd_special | 3 | `dwd_special_aomen_company`(~792)、`dwd_special_hongkong_company`(~37,736)、`dwd_special_taiwan_company`(~38,106) |
| dwd_substance | 4 | `dwd_substance`(~9,117)、`dwd_substance_paper`(~10)、`dwd_substance_patent`(~10)、`dwd_substance_v3bad`(~9,603) |
| dwd_us | 2 | `dwd_us_sec_daily_quotation`(~1,293)、`dwd_us_stock_val_ind`(~1,740) |
| dwd_zh | 17 | `dwd_zh_author`(~63,260)、`dwd_zh_journal`(~2,326)、`dwd_zh_paper`(~89,214)、`dwd_zh_paper_abstract`(~14,254)、`dwd_zh_paper_citation`(~17,494)、`dwd_zh_paper_classification`(~18,895)、`dwd_zh_paper_reference`(~12,914)、`dwd_zh_paper_reference_content`(~208,125)、`dwd_zh_paper_related`(~18,283)、`dwd_zh_paper_title`(~19,288)、`dwd_zh_project`(~46,455)、`dwd_zh_project_output`(~17,475)、`dwd_zh_report`(~13,699)、`dwd_zh_report_author`(~4,092)、`dwd_zh_report_org`(~1,387)、`dwd_zh_report_paper`(~5,880)、`dwd_zh_report_project`(~653) |
| nums_seq | 1 | `nums_seq`(~200) |

域分布速览：机构 org(31) 专利 patent(13) 学者 scholar(9) 中英文论文 zh/en(各17) 外企 forg(6) 医药 drug/clinical/substance/protein/molecular/crystal(12+) 金融行情 astock/hk/us/ls/option/fund/bond(15+) 产业基金 industrial(5) 行业分析 industry(10) 招投标 bid(4) 政策/新闻/研报若干。

## 4. gkx_element 业务表清单（106 张；表名后打 √ = yft1 e2e 73 张复制品里有）

| 域前缀 | 表数 | 表清单 |
| --- | --- | --- |
| dwd_bid | 4 | `dwd_bid_base_out`√、`dwd_bid_purchase_agency_out`√、`dwd_bid_target_item_out`√、`dwd_bid_win_candidate_out`√ |
| dwd_en | 15 | `dwd_en_author`√、`dwd_en_journal`√、`dwd_en_paper`√、`dwd_en_paper_abstract`、`dwd_en_paper_citation`√、`dwd_en_paper_classification`√、`dwd_en_paper_funding`、`dwd_en_paper_reference`√、`dwd_en_paper_related`√、`dwd_en_paper_title`、`dwd_en_project`√、`dwd_en_project_output`√、`dwd_en_report`√、`dwd_en_report_author`、`dwd_en_report_org` |
| dwd_forg | 8 | `dwd_forg_act_contro_info`√、`dwd_forg_base_info`√、`dwd_forg_beneficiary_info`√、`dwd_forg_executive_info`√、`dwd_forg_product_info`√、`dwd_forg_shareholder_info`√、`dwd_forg_stock_fin_info`√、`dwd_forg_subsidiary_info`√ |
| dwd_industry | 2 | `dwd_industry_chain_info`√、`dwd_industry_chain_news_info`√ |
| dwd_org | 25 | `dwd_org_annual_financial_info`√、`dwd_org_bankruptcy_public_cases`√、`dwd_org_bankruptcy_public_cases_list`√、`dwd_org_base_info`√、`dwd_org_changerecord_info`√、`dwd_org_company_abnormal`√、`dwd_org_company_illegal`√、`dwd_org_company_punish`√、`dwd_org_executive_info`√、`dwd_org_financing_info`√、`dwd_org_heis_info`√、`dwd_org_important_news_info`√、`dwd_org_industry_chain_dtl`√、`dwd_org_industry_chain_prod_dtl`、`dwd_org_invest_info`√、`dwd_org_merger_acquisition_info`√、`dwd_org_opt_judicial_case`√、`dwd_org_org_product_info`√、`dwd_org_recruit_info`√、`dwd_org_risk_shixin`√、`dwd_org_risk_tax_punish`√、`dwd_org_risk_zhixing`√、`dwd_org_shareholder_info`√、`dwd_org_stock_base`√、`dwd_org_stock_finance_info`√ |
| dwd_patent | 7 | `dwd_patent`√、`dwd_patent_abstract`√、`dwd_patent_cited`√、`dwd_patent_family`√、`dwd_patent_legal`√、`dwd_patent_title`√、`dwd_patent_transfer` |
| dwd_research | 1 | `dwd_research_institute_base_info`√ |
| dwd_sample | 1 | `dwd_sample_source` |
| dwd_scholar | 6 | `dwd_scholar`√、`dwd_scholar_coauthor`√、`dwd_scholar_paper_relation`、`dwd_scholar_papers`、`dwd_scholar_research_direction`√、`dwd_scholar_talent_flag`√ |
| dwd_special | 3 | `dwd_special_aomen_company`√、`dwd_special_hongkong_company`√、`dwd_special_taiwan_company`√ |
| dwd_zck | 1 | `dwd_zck_intl_policy` |
| dwd_zh | 16 | `dwd_zh_author`√、`dwd_zh_journal`√、`dwd_zh_paper`√、`dwd_zh_paper_abstract`、`dwd_zh_paper_citation`√、`dwd_zh_paper_classification`√、`dwd_zh_paper_reference`√、`dwd_zh_paper_related`√、`dwd_zh_paper_title`、`dwd_zh_project`√、`dwd_zh_project_output`√、`dwd_zh_report`√、`dwd_zh_report_org`、`dwd_zh_report_paper`√、`dwd_zh_report_project`、`dwd_zh_report_scholar` |
| dws_zck | 1 | `dws_zck_policy` |
| ods_en | 10 | `ods_en_author`、`ods_en_journal`、`ods_en_paper`、`ods_en_paper_abstract`、`ods_en_paper_citation`、`ods_en_paper_classification`、`ods_en_paper_funding`、`ods_en_paper_reference`、`ods_en_paper_title`、`ods_en_report` |
| ods_zh | 6 | `ods_zh_journal`、`ods_zh_paper_abstract`、`ods_zh_paper_author`、`ods_zh_paper_classification`、`ods_zh_paper_reference`、`ods_zh_paper_title` |

yft1 e2e 73 张里有 **5 张外部 gkx 缺表**：`dwd_forg_act_contro_info`、`dwd_forg_beneficiary_info`、`dwd_forg_stock_fin_info`、`dwd_forg_subsidiary_info`、`dwd_org_industry_chain_dtl`——若拿外部库复刻 yft1 口径，这 5 条链路无源。

## 5. 同名 80 张表的结构差异（全部不一致，三种模式）

统一包裹层（几乎所有表）：`+dwd_id bigint PK`、`+created_time/updated_time/creater/updater`、`+table_data_source/is_deleted/operator_remarks/insert_remark`、`-data_source`。在此之上还有业务列改动：

| 模式 | 表数 | 含义 |
| --- | --- | --- |
| 仅加治理列 + 若干类型变化 | 38 | 业务列集合相同但个别类型收窄/放宽（如 varchar(4096)→longtext、varchar→varchar(255)） |
| 加治理列 + 删列 + 类型变化 | 35 | 典型：`-data_source`；`dwd_en_author.email/affiliation` **json→text 且值格式同变**（本地 JSON 数组、外部单值纯文本，见 §6 第 7 条） |
| 加治理列 + 删列 + **业务列改名/换列** | 6 | 如 `dwd_en_journal`：`impact_factor→impact_score`、`jcr_zone→jn_zone`、`self_rate→citation_rate`、`+indexed_databases`；`dwd_en_report_author`：`authors_id→author_id` 等 |
| 仅加治理列 | 1 | `dwd_org_executive_info` |

**结构性演化代表——`dwd_scholar`**（不只是包壳）：

- gkx_element：工作经历/教育背景**扁平化**进主表（`work_experience_*` 7 列 + `education_background_*` 5 列）。
- 外部 gkx：主表删掉这 12 列，**拆出独立表** `dwd_scholar_work_experience`、`dwd_scholar_education_background`（在仅外部有的 105 张里）；主表另加 `scholar_department_name_en/zh`、`scholar_org_id`、`orc_id`、`reference_nums`；`scholar_id` varchar(32)→varchar(255)、`scholar_org_name_en` varchar(4096)→longtext。

**行数不是单向子集**（同一张表两边差很远，方向不一）：

| 表 | gkx_element | 外部 gkx |
| --- | --- | --- |
| `dwd_scholar` | 2,175 | 21,316 |
| `dwd_zh_paper` | 2,000 | 100,900 |
| `dwd_en_paper` | 2,000 | **1,387（反而更少）** |
| `dwd_org_executive_info` | 5,600 | 438,307 |
| `dwd_bid_base_out` | 100 | 39,962 |
| `dwd_forg_product_info` | 1,099 | 20,000（截断） |
| `dwd_en_journal` | 2,126 | 605 |

## 6. 实操影响（拿外部 gkx 接平台抽取前必读）

1. **脚本不可复用**：yft1 45 个脚本面向 gkx_element 列集；外部 0/80 列结构一致，且缺 `data_source` 列、`dwd_en_journal.impact_factor` 等被改名。需按外部列集重写脚本（可参照 kegner→gaoxing 外部库样板，脚本在 `backend/script/kegner_gaoxing/`）。
2. **主键/读取模式利好**：外部表全有 `dwd_id` 主键 → `script/register_platform_extraction.py` 探测得到 pk，可走**水位/keyset** 绑定（querySql 或普通绑定均可）；gkx_element 大多无 PK 只能 LIMIT/OFFSET。
3. **水位时间列**：外部统一 `created_time/updated_time`（datetime），与本地混杂的 `create_time/update_time` 不同，绑水位时注意列名。
4. **collation 混用**：外部一库 5 种排序规则，跨表字符串 join/比较可能报 Illegal mix of collations——querySql 里显式 `COLLATE` 或关联列均加 CONVERT。
5. **排除脏表**：绑定/同步时排除 `_bak_*`（95 张）与 `*_v3bad`（4 张脏数据隔离表）、`nums_seq`。
6. **样本量截断**：外部是样例库（部分表 2 万行封顶、`dwd_en_paper` 仅 1,387），做量级验证时别当全量口径。
7. **JSON→单值文本（实测）**：`dwd_en_author.email/affiliation` 本地存 JSON 数组（`["a@x.com","b@y.com"]`），外部是**单值纯文本**（`quluj@163.com`、`China Agr Univ, ...`；email NULL 711/1387、affiliation NULL 80/1387）。脚本里对这两列的 `json.loads` 在外部库会直接抛错，需按单值口径重写；多值信息在外部被压成单值，属**有损差异**。

## 附录 A：同名 80 张表逐表差异（只列业务列差异；治理列包裹层见 §5）

| 表 | 外部新增业务列 | 外部删除列 | 类型变化 |
| --- | --- | --- | --- |
| `dwd_bid_base_out` | — | — | `project_number` text→varchar(154)；`plan_number` text→varchar(102)；`project_name` text→varchar(358)；`announcement_type_code` decimal(20,0)→double；`procurement_method_code` decimal(20,0)→double；`bidding_stage_code` decimal(20,0)→double；`project_budget_amount` decimal(20,6)→double；`total_amount` decimal(20,6)→double；`contract_num` text→varchar(92)；`tender_document_price_amount` decimal(20,6)→double；`registration_fee_amount` decimal(20,6)→double；`bidding_security_amount` decimal(20,6)→double；`ca_payment_amount` decimal(20,6)→double；`tender_agent_service_fee_amount` decimal(20,6)→double；`performance_security_amount` decimal(20,6)→double；`funding_source` text→varchar(154)；`construction_service_location` text→varchar(216)；`construction_service_period` text→varchar(470)；`allow_joint_bid` decimal(20,0)→double；`bidding_document_sub_style` decimal(20,0)→double；`supplier_qualification_criteria` text→mediumtext |
| `dwd_bid_purchase_agency_out` | — | — | `relate_type` decimal(20,0)→double |
| `dwd_bid_target_item_out` | — | — | `quantity` decimal(20,0)→double；`unit_price_amount` decimal(20,2)→double |
| `dwd_bid_win_candidate_out` | — | — | `amount` decimal(20,6)→double；`ranking` decimal(20,0)→double；`relate_type` decimal(20,0)→double |
| `dwd_en_author` | — | `data_source` | `email` json→text；`affiliation` json→text |
| `dwd_en_journal` | `zh_name`、`impact_score`、`jn_zone`、`citation_rate`、`indexed_databases` | `impact_factor`、`jcr_zone`、`scope_zone`、`self_rate`、`is_sci`、`data_source` | — |
| `dwd_en_paper` | — | `data_source` | `cover_date_start` datetime→date |
| `dwd_en_paper_abstract` | — | `data_source` | `en_abstract` longtext→text；`zh_abstract` longtext→text |
| `dwd_en_paper_citation` | — | `data_source` | — |
| `dwd_en_paper_classification` | — | `data_source`、`created_time_2`、`updated_time_2` | `scope` varchar(20)→varchar(255)；`sub_scope` varchar(20)→varchar(1000)；`keywords` json→text |
| `dwd_en_paper_funding` | — | `data_source` | `funds` longtext→text |
| `dwd_en_paper_reference` | `reference_count` | `data_source` | — |
| `dwd_en_paper_related` | — | `logic_id`、`data_source` | `doi` varchar(512)→text；`en_name` varchar(1024)→text |
| `dwd_en_paper_title` | — | `data_source` | — |
| `dwd_en_project` | `funded_country` | `create_time` | `project_number` varchar(32)→varchar(64)；`project_level` varchar(255)→varchar(64)；`discipline` varchar(256)→varchar(1024)；`participating_institution` json→varchar(128)；`approval_year` int→date；`approval_time` datetime→date；`participants` json→varchar(512)；`keywords` json→varchar(512)；`abstract` longtext→mediumtext；`final_report_abstract` longtext→mediumtext；`project_page_url` text→varchar(255) |
| `dwd_en_project_output` | — | `degree_papers_count`、`books_count`、`awards_count`、`output_degree_papers`、`output_books`、`output_awards`、`create_time` | `output_journal_articles` json→mediumtext；`output_patents` json→mediumtext；`output_conference_papers` json→mediumtext；`output_clinical_trials` json→mediumtext；`output_reports` json→mediumtext；`output_other` json→mediumtext |
| `dwd_en_report` | `category`、`country`、`pub_year`、`file_type`、`related_authors`、`organization`、`related_literature_id`、`related_org_id`、`author_id`、`related_author_id` | `related_scholars`、`literature_id`、`org_id`、`authors_id`、`scholar_id` | `report_number` varchar(64)→varchar(174)；`title_en` varchar(512)→mediumtext；`source_url` varchar(512)→varchar(342)；`document_type` varchar(64)→varchar(212)；`contract_number` varchar(32)→varchar(182)；`updated_time` varchar(8)→datetime；`file_path` json→varchar(260) |
| `dwd_en_report_author` | `author_id`、`author_name`、`author_unit` | `authors_id`、`authors_name`、`authors_unit` | — |
| `dwd_en_report_org` | — | `report_source_2` | `org_name` varchar(200)→text |
| `dwd_forg_base_info` | `state`、`stock_code`、`industry_code` | `industry_class` | `org_id` varchar(255)→varchar(32)；`name_en` varchar(255)→varchar(256)；`name_alias` varchar(255)→varchar(256)；`country_code` varchar(255)→varchar(8)；`country` varchar(255)→varchar(128)；`external_id` varchar(255)→varchar(64)；`city` varchar(255)→varchar(64)；`address` text→varchar(256)；`postal_code` varchar(255)→varchar(16)；`phone` varchar(255)→varchar(32)；`email` varchar(255)→varchar(128)；`company_type` text→varchar(32)；`registration_org` text→varchar(32)；`incorporation_year` decimal(20,0)→bigint；`incorporation_date` datetime→date；`listing_status` varchar(255)→bigint；`registered_capital_value` decimal(20,0)→decimal(20,4)；`registered_capital_currency_code` varchar(255)→varchar(16)；`industry_type` varchar(255)→varchar(32) |
| `dwd_forg_executive_info` | `org_name`、`create_time`、`source_table` | `dm_birthdate`、`dm_nationalities`、`dm_biography` | `org_id` varchar(255)→varchar(64)；`executives_name` varchar(255)→varchar(98)；`executives_position` varchar(255)→varchar(114) |
| `dwd_forg_product_info` | `org_name`、`main_activities`、`create_time`、`source_table` | — | `org_id` varchar(255)→varchar(64)；`description` varchar(368)→mediumtext；`main_products` varchar(1520)→mediumtext |
| `dwd_forg_shareholder_info` | `owners_id`、`org_name`、`create_time`、`source_table` | — | `org_id` varchar(255)→varchar(64)；`owners_name` varchar(255)→varchar(180)；`owners_country_code` varchar(255)→varchar(64)；`owners_country` varchar(255)→varchar(64) |
| `dwd_industry_chain_info` | `pk_id`、`industry_code`、`industry_name`、`industry_link_code`、`industry_link_name`、`parent_code`、`node_company_count` | `chain_code`、`chain_name`、`node_id`、`node_name`、`node_type`、`node_seq`、`parent_id`、`node_imp_level`、`downstream_link_code`、`node_stage`、`node_path`、`data_source` | `level` decimal(20,0)→tinyint |
| `dwd_industry_chain_news_info` | `pk_id`、`industry_code`、`industry_name`、`id`、`publish_date`、`abstract` | `chain_code`、`chain_name`、`news_id`、`relaese_date`、`summary`、`data_source` | `title` varchar(255)→text；`source` varchar(255)→text |
| `dwd_org_annual_financial_info` | `fixed_assets`、`arch_development_am`、`development_employee` | — | `year` decimal(20,0)→double；`total_assets` decimal(20,2)→double；`total_liabilities` decimal(20,2)→double；`operating_revenue` decimal(20,2)→double；`main_business_revenue` decimal(20,2)→double；`total_profit` decimal(20,2)→double；`pure_profit` decimal(20,2)→double；`total_tax_paid` decimal(20,2)→double；`owners_equity` decimal(20,2)→double；`employees_number` decimal(20,0)→double |
| `dwd_org_bankruptcy_public_cases` | — | — | `public_date` datetime→date |
| `dwd_org_bankruptcy_public_cases_list` | — | — | `party_role_type` decimal(20,0)→double；`party_type` decimal(20,0)→double；`public_date` datetime→date |
| `dwd_org_base_info` | `phone_num`、`org_size` | — | `incorporation_year` decimal(20,0)→double；`incorporation_date` datetime→date；`listing_date` datetime→date；`registered_capital_value` decimal(20,2)→double |
| `dwd_org_changerecord_info` | — | — | `update_date` datetime→date |
| `dwd_org_company_abnormal` | — | — | `abn_date` datetime→date；`remove_date` datetime→date |
| `dwd_org_company_illegal` | — | — | `abn_date` datetime→date；`remove_date` datetime→date |
| `dwd_org_company_punish` | — | — | `penalty_date` datetime→date；`public_date` datetime→date；`public_deadline` datetime→date |
| `dwd_org_executive_info` | — | — | — |
| `dwd_org_financing_info` | `pre_valuation`、`after_valuation` | — | `funding_amount` decimal(20,2)→varchar(255)；`completion_date` datetime→date；`investors_name` text→longtext；`data_source` varchar(255)→varchar(500) |
| `dwd_org_heis_info` | — | — | `est_year` decimal(20,0)→double |
| `dwd_org_important_news_info` | — | — | `news_date` datetime→date |
| `dwd_org_invest_info` | — | — | `investment_amount` decimal(20,2)→double；`investment_ratio` decimal(20,2)→double；`data_source` varchar(255)→varchar(500) |
| `dwd_org_merger_acquisition_info` | — | — | `ma_amount` decimal(20,2)→double；`data_source` varchar(255)→varchar(500) |
| `dwd_org_opt_judicial_case` | — | — | `procedure_date` datetime→date |
| `dwd_org_org_product_info` | — | — | `main_prod` varchar(1120)→varchar(255) |
| `dwd_org_recruit_info` | — | — | `release_date` datetime→date |
| `dwd_org_risk_shixin` | — | — | `name_cn` text→varchar(64)；`dishonest_type` decimal(20,0)→double；`exec_basis_no` text→varchar(100)；`legal_obligation` text→longtext；`fulfillment_status` text→varchar(64)；`dishonest_behavior` text→varchar(130)；`publish_date` datetime→date；`filing_date` datetime→date；`exec_part` text→varchar(64)；`unexec_part` text→varchar(90) |
| `dwd_org_risk_tax_punish` | — | — | `publish_date` datetime→date |
| `dwd_org_risk_zhixing` | — | — | `exec_person_type` decimal(20,0)→double；`filing_date` datetime→date；`is_hidden` decimal(20,0)→double |
| `dwd_org_shareholder_info` | — | — | `ownership_percentage` decimal(20,2)→double |
| `dwd_org_stock_base` | — | — | `listed_date` datetime→date |
| `dwd_org_stock_finance_info` | — | — | `total_assets` decimal(20,2)→double；`fixed_assets` decimal(20,2)→double；`total_liabilities` decimal(20,2)→double；`operating_revenue` decimal(20,2)→double；`main_business_revenue` decimal(20,2)→double；`total_profit` decimal(20,2)→double；`pure_profit` decimal(20,2)→double；`total_tax_paid` decimal(20,2)→double；`oper_cash_flow` decimal(20,2)→double；`owners_equity` decimal(20,2)→double；`employees_number` decimal(20,0)→double；`research_development_amount` decimal(20,2)→double |
| `dwd_patent` | `pn`、`kind`、`publication_reference_kind`、`pbdt`、`pbdt_year`、`pbdt_month`、`apno`、`application_country`、`apdt`、`apdt_year`、`apdt_month`、`pct_apno`、`pct_apdt`、`pct_etdt`、`pct_pn`、`pct_pbdt`、`spif_Application_Number`、`spif_Publication_Number`、`prior_Art_Year`、`prior_Art_Date`、`relevants`、`other_Versions` | `id`、`application_kind`、`publication_reference`、`application_reference`、`pct_or_regional_filing_data`、`pct_or_regional_publishing_data`、`priority_filings`、`applicants`、`assignees`、`inventors`、`claims`、`description`、`db_source`、`create_time`、`update_time` | `patent_id` varchar(64)→varchar(255)；`country` varchar(20)→varchar(255)；`first_applicant_name` varchar(255)→varchar(1000)；`first_current_assignee_name` varchar(255)→varchar(1000)；`first_inventor_name` varchar(255)→varchar(1000)；`value` int→bigint |
| `dwd_patent_abstract` | `pn`、`abstract_en`、`abstract_trans_cn` | `id`、`abstract_localized`、`abstract_zh`、`db_source`、`create_time`、`update_time` | `patent_id` varchar(64)→varchar(255) |
| `dwd_patent_cited` | `pn`、`reference_cited_count` | `id`、`reference_cited`、`db_source`、`create_time`、`update_time` | `patent_id` varchar(64)→varchar(255) |
| `dwd_patent_family` | `pn` | `id`、`db_source`、`create_time`、`update_time` | `patent_id` varchar(64)→varchar(255) |
| `dwd_patent_legal` | `pn`、`isdt`、`isdt_year`、`isdt_month`、`patent_legal` | `id`、`dates_of_public_availability`、`patent_legal/prs_data`、`db_source`、`create_time`、`update_time` | `patent_id` varchar(64)→varchar(255) |
| `dwd_patent_title` | `pn`、`title_en`、`title_trans_cn` | `id`、`title_localized`、`title_zh`、`db_source`、`create_time`、`update_time` | `patent_id` varchar(64)→varchar(255) |
| `dwd_patent_transfer` | `patent_transfer_id`、`pn` | `id`、`patent_id`、`db_source`、`create_time`、`update_time` | `country` varchar(8)→varchar(100) |
| `dwd_research_institute_base_info` | — | — | `incorporation_date` datetime→date |
| `dwd_scholar` | `id`、`scholar_department_name_en`、`scholar_department_name_zh`、`scholar_org_id`、`orc_id`、`reference_nums` | `work_experience_date`、`work_experience_institution_en`、`work_experience_department_en`、`work_experience_position_en`、`work_experience_institution_zh`、`work_experience_department_zh`、`work_experience_position_zh`、`education_background_date`、`education_background_institution_en`、`education_background_degree_en`、`education_background_institution_zh`、`education_background_degree_zh`、`create_time`、`update_time` | `scholar_id` varchar(32)→varchar(255)；`name_en` varchar(128)→varchar(255)；`name_zh` varchar(128)→varchar(255)；`avatar` varchar(256)→varchar(255)；`scholar_org_name_en` varchar(4096)→longtext；`scholar_org_name_zh` varchar(1024)→varchar(255) |
| `dwd_scholar_coauthor` | `id`、`co_scholar_department_name_en`、`co_scholar_department_name_zh`、`co_scholar_org_id` | — | `co_scholar_name_en` varchar(256)→varchar(194)；`co_scholar_name_zh` varchar(128)→varchar(64)；`co_scholar_avatar` varchar(512)→varchar(150)；`co_scholar_org_name_en` varchar(2048)→mediumtext；`co_scholar_org_name_zh` varchar(1024)→varchar(132) |
| `dwd_scholar_paper_relation` | `id` | — | `paper_id` bigint→int；`year` bigint→int；`scholar_id` varchar(32)→varchar(255)；`related_paper_id` bigint→int |
| `dwd_scholar_papers` | — | — | `zh_name` varchar(500)→varchar(298)；`en_name` varchar(500)→varchar(414)；`authors` text→mediumtext；`paper_url` varchar(1024)→mediumtext；`status` int→varchar(64)；`zh_abstract` text→mediumtext；`en_abstract` text→mediumtext；`doi` varchar(512)→varchar(80)；`publication_en_name` varchar(1024)→varchar(252) |
| `dwd_scholar_research_direction` | `id` | `update_time` | `scholar_id` varchar(32)→varchar(255)；`fields` text→longtext |
| `dwd_scholar_talent_flag` | `id` | `update_time` | `scholar_id` varchar(32)→varchar(255)；`academician` varchar(128)→int |
| `dwd_special_aomen_company` | — | `incorporation_year`、`incorporation_date`、`person_num`、`company_est_status`、`data_source` | — |
| `dwd_special_hongkong_company` | — | — | `incorporation_date` datetime→date；`cancel_date` datetime→date |
| `dwd_special_taiwan_company` | — | — | `capital_num` decimal(20,6)→double；`realcapital_num` decimal(20,6)→double；`amount_per_share` decimal(20,6)→double；`incorporation_date` datetime→date；`issue_date` datetime→date；`closure_date_begin` datetime→date；`closure_date_end` datetime→date |
| `dwd_zh_author` | `pk_id` | `data_source` | `paper_id` varchar(64)→varchar(91)；`author_id` varchar(32)→varchar(255)；`en_name` varchar(255)→varchar(1024)；`zh_name` varchar(255)→varchar(305)；`email` json→text；`affiliation` json→text |
| `dwd_zh_journal` | `pk_id`、`impact_score`、`jn_zone`、`indexed_databases`、`media_type`、`publisher_id`、`publisher`、`fund_paper_num` | `impact_factor`、`sub_quartile`、`is_sci`、`data_source` | `paper_id` varchar(64)→varchar(1000)；`publication_id` bigint→varchar(16)；`iscn` varchar(16)→varchar(255)；`issn` varchar(16)→varchar(255)；`eissn` varchar(16)→varchar(255)；`founding_time` int→date；`postal_code` varchar(32)→varchar(255)；`chief_editor` varchar(128)→varchar(500)；`publisher_place` varchar(64)→varchar(255)；`publication_cycle` varchar(64)→varchar(255) |
| `dwd_zh_paper` | `pk_id`、`download_num`、`author_info_list`、`rel_paper` | — | `id` varchar(64)→varchar(91)；`publication_id` bigint→varchar(25)；`issn` varchar(16)→varchar(32)；`cover_year_start` varchar(4)→varchar(22)；`abstract_available` varchar(1)→tinyint；`paper_url` text→longtext |
| `dwd_zh_paper_abstract` | `pk_id` | `data_source` | `id` varchar(64)→varchar(91)；`original_abstract` varchar(1)→tinyint |
| `dwd_zh_paper_citation` | `pk_id`、`DOI`、`citation_num`、`citation_content`、`citation_id_list` | `publication_id`、`doi`、`zh_name`、`publication_zh_name`、`data_source` | `id` varchar(64)→varchar(91) |
| `dwd_zh_paper_classification` | `pk_id` | `data_source` | `id` varchar(64)→varchar(91)；`scope` varchar(20)→varchar(255)；`scope_zone` varchar(20)→varchar(255) |
| `dwd_zh_paper_reference` | `pk_id`、`reference_num`、`reference_content`、`reference_id_list` | `publication_id`、`zh_name`、`publication_zh_name`、`cover_year_start`、`volume`、`issue`、`first_page`、`last_page`、`data_source` | `id` varchar(64)→varchar(91) |
| `dwd_zh_paper_related` | `pk_id` | `doi`、`zh_name`、`data_source`、`logic_id` | `id` varchar(64)→varchar(91)；`relevant` json→longtext |
| `dwd_zh_paper_title` | `pk_id` | `data_source` | `id` varchar(64)→varchar(91)；`en_name` varchar(1024)→longtext；`zh_name` varchar(1024)→longtext；`language_code` varchar(12)→varchar(19)；`original_title` varchar(1)→tinyint |
| `dwd_zh_project` | `completion_status`、`project_status` | `create_time` | `id` varchar(255)→varchar(64)；`project_number` varchar(255)→varchar(64)；`title` varchar(255)→varchar(512)；`project_source` varchar(255)→varchar(64)；`funded_institution` varchar(255)→varchar(128)；`project_level` varchar(255)→varchar(32)；`discipline` varchar(255)→varchar(256)；`discipline_code` varchar(255)→varchar(256)；`fund_category` varchar(255)→varchar(64)；`funded_province` varchar(255)→varchar(32)；`participating_institution` json→varchar(128)；`approval_time` datetime→date；`research_period` varchar(255)→varchar(64)；`project_host` varchar(255)→varchar(64)；`participants` json→varchar(512)；`keywords` json→varchar(512)；`abstract` text→varchar(4096)；`final_report_abstract` text→varchar(4096)；`project_page_url` text→varchar(255) |
| `dwd_zh_project_output` | — | `output_degree_papers`、`output_other`、`create_time` | `id` varchar(255)→varchar(64)；`output_journal_articles` json→mediumtext；`output_patents` json→mediumtext；`output_conference_papers` json→mediumtext；`output_books` json→varchar(2048)；`output_awards` json→varchar(2048)；`output_reports` json→varchar(2048) |
| `dwd_zh_report` | `related_authors`、`content`、`file_type`、`related_author_id`、`related_org_id`、`related_paper_id`、`related_project_id` | `related_scholars`、`scholar_id`、`org_id`、`paper_id`、`project_id` | `report_id` varchar(64)→varchar(255)；`report_category` varchar(64)→varchar(255)；`title_cn` varchar(512)→varchar(1500)；`abstract_cn` longtext→text；`report_type` varchar(32)→varchar(255)；`preparation_time` varchar(8)→varchar(10)；`visibility_scope` varchar(16)→varchar(255)；`contact_phone` varchar(64)→varchar(255)；`updated_time` varchar(8)→datetime；`file_path` json→varchar(500) |
| `dwd_zh_report_org` | `report_id` | — | `org_id` varchar(64)→varchar(255)；`org_name` varchar(200)→varchar(255)；`org_xydm` varchar(50)→varchar(255) |
| `dwd_zh_report_paper` | — | — | `paper_id` varchar(64)→varchar(255)；`paper_name` varchar(320)→varchar(1024)；`paper_doi` varchar(100)→varchar(255)；`report_source` varchar(32)→varchar(255)；`paper_source` varchar(32)→varchar(255) |
| `dwd_zh_report_project` | — | — | `project_id` varchar(64)→varchar(255)；`project_name` varchar(200)→varchar(255)；`project_subject` varchar(100)→varchar(255)；`project_type` varchar(100)→varchar(255)；`project_number` varchar(100)→varchar(255)；`report_id` varchar(64)→varchar(255)；`project_source` varchar(32)→varchar(255) |
