# gkx_element 主键补齐结果报告（2026-10-11）

## 执行摘要

| 项 | 结果 |
|---|---|
| 目标 | 共享 dev MySQL（`tech-kg-mysql`，宿主机 30306）库 `gkx_element` 中无主键的源表 |
| 范围（第一批） | 75 张 = 文档闭包 69 张 + 6 张本仓库实际使用的额外表（dwd_scholar_papers、dwd_zck_intl_policy、dws_zck_policy、ods_zh_journal、ods_en_journal、ods_en_report） |
| 结果（第一批） | **75 张全部成功，0 失败** |
| 范围（第二批） | 23 张零引用上游层表（10 张 `dwd_*` + 13 张 `ods_*`，用户后续决定全库补齐） |
| 结果（第二批） | **23 张全部成功**（18 张单列键 + 5 张复合键，数据干净零降级；执行器输出曾误报 FAIL，系 mysql 密码警告污染判断，实测 23/23 成功） |
| 最终状态 | **全库 148/148 张表全部有物理主键，无主键表 = 0** |
| 键形分布 | 单列自然键 48 张 / 复合自然键 15 张 / 代理自增键 `row_pk` 35 张（原有主键 50 张不变） |
| 验证 | 库内无 PK 表归零；容器全程健康 |

## 与最初方案的偏差（均有数据依据）

按批准的兜底规则，12 张自然键候选表因**实测数据重复或 NULL** 降级为代理键 `row_pk`：

| 表 | 原候选键 | 校验发现 |
|---|---|---|
| dwd_zh_paper_related | logic_id | 重复组 ≥1000（达查询上限），上游"逻辑主键"实际不唯一 |
| dwd_org_stock_base | stock_code | 62 组重复 |
| dwd_org_company_abnormal | abnormal_id | 150 组重复（"记录id"实为局部序号） |
| dwd_org_company_punish | penalty_id | 20 组重复 |
| dwd_org_company_illegal | sv_id | 229 组重复 |
| dwd_org_risk_tax_punish | tax_vio_id | 20 组重复 |
| dwd_org_opt_judicial_case | case_id | 447 组重复 |
| dwd_org_risk_shixin | dishonest_id | 21 组重复 |
| dwd_org_risk_zhixing | exec_person_id | 20 组重复 |
| dwd_org_bankruptcy_public_cases_list | bankruptcy_party_id | 20 组重复 |
| dwd_org_stock_finance_info | (stock_code, occur_period) | 61 组重复（复合键仍撞） |
| dwd_scholar_papers | id | 1 组重复 + **334,376 行 id 为 NULL**（仅 fixture 造数带 id） |

降级处理是**非破坏性的**：重复数据原样保留，仅改用追加在表尾的 `row_pk BIGINT UNSIGNED AUTO_INCREMENT` 代理键。

## 第二批补齐（原"明确未处理"的 23 张）

应用户决定于同日第二批全部补齐，全部走自然/复合键、零降级：

- **单列键 18 张**：`dwd_en_paper_funding(id)`、`dwd_zh_report_org(org_id)`、`dwd_en_report_author(authors_id)`、`dwd_en_report_org(org_id)`、`dwd_zh_report_project(project_id)`、`dwd_zh_report_scholar(scholar_id)`、`ods_en_author(logic_id)`、`ods_en_paper(pmid)`、其余 10 张单列 `logic_id`
- **复合键 5 张**：`dwd_zh/en_paper_abstract(id, abstract_sequence)`、`dwd_zh/en_paper_title(id, title_sequence)`、`ods_en_paper_abstract(logic_id, abstract_source)`（一文多摘要/多标题/多来源语义）
- 其中 17 张为空表（结构约束先行，数据将来装载时约束即生效）；6 张有数据表查重全部干净

## 执行细节

- 执行通道：`docker exec -i tech-kg-mysql mysql -uroot -pgkx_element gkx_element`（仓库既有惯例）
- 4 条语句因 `ADD COLUMN ... AUTO_INCREMENT` 不支持 `LOCK=NONE` 去掉在线 DDL 子句后重试成功（dwd_zh/en_paper_reference、dwd_zh_paper_citation、dwd_zh_report_paper、ods_en_report，均为秒级完成，无锁表投诉窗口）
- 2 张可空候选列（dwd_zck_intl_policy.recordId、dws_zck_policy.id）由 ADD PRIMARY KEY 隐式转 NOT NULL，列注释无损
- 回滚：`rollback.sql`（N/C 删主键；S 删主键+row_pk 列）

## 对系统代码的影响（已核实）

- **无需改任何代码**：运行时读取全部 `.mappings()` 按列名取值，列序无关；row_pk 追加在表尾，`ORDER BY 1` / `cols[0]` 语义不变
- `_PK_CANDIDATES` 探测与来源绑定 `pk_column` 不受影响（row_pk 不在候选名单内，现有绑定值原样有效）
- fixture 写入方 `manage_expert_modules_e2e_fixture.py` 兼容：配对表键形与其 INSERT 一致（coauthor/paper_relation 复合键）、代理键表自动填 row_pk
- **行为变化（预期内）**：30+10 张自然键表今后 INSERT 重复业务 id 将报 ER_DUP_ENTRY——这正是加键目的，若有其他使用方向这些表重复插数据，需知悉
- 抽取收益：`kg.schema.extract` 的 keyset 模式（`WHERE pk > :cursor`）在 75 张表上语义安全成立，不再依赖 OFFSET 降级

## 产物清单

| 文件 | 说明 |
|---|---|
| apply_pk.sql | 实际执行的 98 条 ALTER（第一批 75 + 第二批 23） |
| rollback.sql | 逐表回滚脚本（98 条） |
| pk_final_map.tsv / pk_final_map_batch2.tsv | 两批最终键映射（表 → 键型/键列） |
| snapshot_before.sql / snapshot_after.sql | 变更前后全库结构（after 为全库补齐后） |
| backup_gkx_element_20261011.sql.gz | 变更前全量数据备份（约 1.5 GB 源库） |
| apply_log.txt / apply_log_batch2.txt | 逐表执行日志 |
