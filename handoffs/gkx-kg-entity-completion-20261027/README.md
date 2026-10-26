# gkx_kg 实体补全交接

基于 `kgetl` 分支。完整包与解包文件内容一致；本次仅上传文件，没有在开发库执行 SQL。

- `gkx_kg_实体补充与七类关系说明-20261027.zip`：完整包。
- `gkx_kg_entity_completion_20261027.sql`：仅补实体表、字段和有来源的数据，不建关系表。
- `七类关系映射与连接键-20261027.md`：简洁关系说明。
- `开发机执行说明.md`：来源库配置与执行说明。
- `GLM_开发机补全提示词.md`：给开发机 GLM 的简短提示词。

先由 GLM 找到实际 `gkx_kg` 和真实来源、完善 SQL；已补齐的内容跳过，不添加模拟数据。SQL 由用户决定何时执行。

## GLM 开发机执行记录 2026-10-27

已在本机 `tech-kg-mysql`（127.0.0.1:30306）的 `gkx_kg` 执行完成（部分口径）：

- **来源路由**：默认 `gkx_dwd_local`；仅 `dwd_patent`、`dwd_industry_chain_info`、`dwd_forg_stock_fin_info` 三表从 `gkx_element` 取（数组/链编码/财务列只在 element）。执行前整库备份在 `~/deploy/backup-gkx-kg-pre-entity-completion-1027.sql.gz`。
- **会话缓冲**：文件头已加 `sort_buffer_size=64MB / tmp_table_size=max_heap_table_size=256MB`（否则 dwd_forg_base_info 导入报 ERROR 1038）。
- **填列改写**：原 `sp_kg27_fill_from_source` 的多表 UPDATE（持久表 JOIN 持久表）在本实例上两轮卡死在 `Opening tables`（内核线程 R 态自旋，非锁等待）。已把全部填列与快照恢复改成等价的"临时表中转"两步式并回灌进本 SQL（唯一键物化 + 主键探测 UPDATE），实测秒级通过、结果一致。
- **已落库**：机构 6 组导入（含 forg 2,165）、学者补 800（22,077 全量对齐）、中文/英文论文 4,000 篇（含 publication_id）、专利数组/题名/源行 ID（element）、链/节点导入、项目参与者/主持/承担机构列全满（4,008）、项目产出四类数组（journal/conference/patents/reports）、节点 chain_code 180/180（单链节点）、kg_event 快照恢复 organization_id 守卫放行部分 + case_role 674 + exec_person_type 1,988。
- **按规则跳过**：kg_report/kg_data_source（存量已完整，自跳过日志）；output_degree_papers（两来源表均无此列）；scholar_org/work_experience（dwd_scholar 无源列）；快照里 860 条 `MOCK_ORG_*` 机构键被真实性守卫拒绝（不造模拟数据）；**事件 15 表补齐模块未执行**（按"部分数据即可"口径，存量 18,821 条带机构键事件已够 INVOLVED_IN 验证）。
- **七类关系连接键只读验证**（gkx_kg 内，2026-10-27）：

| 关系 | 连接键填充 | 可解析对 |
|---|---|---|
| HAS_NEWS | kg_news.organization_id 1,013/1,489 | 1,013（键全可解析） |
| HAS_NODE | kg_industry_node.chain_code 180/180 | 180 节点落在存量 2 条真实链 |
| HAS_OUTPUT | 产出数组已灌（论文 34,294 项/专利 2,514 项/报告 2,000 项） | 论文题名精确命中 416；报告去后缀归一命中 17；专利号两语料不相交命中 0（已 LIKE 全库核实） |
| HAS_PARTICIPANT | participants 数组 16,786 个人名 | 唯一姓名可解析 1,436（歧义 1,709），覆盖 1,110 个项目 |
| INVENTED_BY | kg_patent.inventors 2,020 人次 | 唯一姓名可解析 86，覆盖 76 件专利 |
| INVESTS_IN | kg_organization.invests 754 家 | 4,069 条投资端点 100% 落在存量机构 |
| INVOLVED_IN | kg_event.organization_id 18,821/24,669 | 13,477 落在存量机构（5,344 幽灵键为历史存量） |

