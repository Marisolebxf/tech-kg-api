# 专利数据到图谱的完整映射

数据源：2026-07-22 调整后的 gkx_element 七张专利表。
当前执行范围：只装载 Patent 顶点和属性；后续边映射先设计、不执行。

## 1. 七张表的职责

| 表 | 当前阶段 | 后续阶段 |
|---|---|---|
| dwd_patent | Patent 主键、书目、申请/PCT、分类和评价属性 | 展开发明人、申请人、权利人、代理、分类、关键词 |
| dwd_patent_title | 三语标题属性 | 无新实体 |
| dwd_patent_abstract | 三语摘要属性 | 可接全文检索 |
| dwd_patent_legal | 当前法律状态、授权/到期快照 | 法律事件 Event |
| dwd_patent_cited | 引用数量属性 | Patent 引用边及非专利文献边 |
| dwd_patent_transfer | 当前不入 Patent | 转移 Event 和主体边 |
| dwd_patent_family | 家族号属性 | PatentFamily 和成员/家族引用边 |

七表以 patent_id 连接；当前行数为 2000、2000、2000、2000、2000、100、2000。

## 2. 粒度、VID 和关联

- 一条 dwd_patent 生成一个 Patent。
- VID 为 patent_{patent_id}，例如 patent_CN103073024B。
- source_record_id 等于 patent_id。
- title、abstract、legal、cited、family 按 patent_id 左连接。
- 可选值缺失时字符串置空、数值置 0。

## 3. 当前 50 个属性映射

| 分组 | Patent 属性 | SQL 来源 |
|---|---|---|
| 标识 | patent_id、publication_number | 主表 |
| 地域/类型 | application_kind、country_code、country | 主表 |
| 公开 | publication_kind/date/year/month | publication_reference JSON |
| 申请 | application_number/country/date/year/month | application_reference JSON |
| PCT | pct_application_number/date、pct_national_stage_date | filing JSON |
| PCT公开 | pct_publication_number/date | publishing JSON |
| 标题 | title_original/en/zh | titles、title_localized.en、title_zh |
| 摘要 | abstract_original/en/zh | abstracts、abstract_localized.en、abstract_zh |
| 语言 | language | JSON 数组连接 |
| 授权号 | granted_number | 主表 |
| 分类快照 | main_ipcr、further_ipcr、main_cpc、further_cpc | 主表 |
| 关键词快照 | keywords | 主表 JSON 序列化 |
| 法律快照 | status、grant_date/year/month、anticipated_expiration、expiration_year | legal |
| 统计/评价 | citation_nums、cited_by_nums、non_patent_citation_nums、patent_value | cited + 主表 |
| 家族 | simple_family_number | family |
| 溯源 | 7 个标准字段 | 固定值、ETL 参数、update_time |

装载 SQL 不再读取旧版 _2/_3 列，嵌套值统一用 JSON_EXTRACT。

## 4. 后续实体

| 实体 | VID建议 | 来源 |
|---|---|---|
| Person | 已有人员 ID 优先，否则 person_{name_hash} 桩 | inventors、agents、examiners、自然人申请人/权利人 |
| Organization | 机构 ID/信用代码优先，否则 org_{name_hash} 桩 | applicants、assignees、agency |
| Keyword | keyword_{normalized_hash} | keywords |
| Classification | class_{scheme}_{code} | IPCR/CPC/LOC/FI/UPC/F-term |
| PatentFamily | patent_family_{simple_family_number} | family |
| PatentApplication | patent_app_{country}_{apno} | priority_filings、related_documents |
| Event | event_{type}_{source_id}_{sequence} | legal_events、PRS、transfer |
| Document | DOI/标准号优先，否则内容哈希 | non_patent_citations |

名称哈希顶点只是待消歧桩，后续通过对齐或 SAME_AS 与既有 Person/Organization 合并。

## 5. 后续边和边属性

| Edge | 方向 | 来源 | Edge 属性 |
|---|---|---|---|
| INVENTED_BY | Patent→Person | inventors | sequence |
| APPLIED_BY | Patent→主体 | applicants | sequence、role |
| OWNED_BY | Patent→主体 | assignees | sequence、is_current |
| REPRESENTED_BY | Patent→Person | agents | sequence |
| HANDLED_BY | Patent→Organization | agency | sequence |
| EXAMINED_BY | Patent→Person | examiners | level、department |
| CLAIMS_PRIORITY_TO | Patent→PatentApplication | priority_filings | sequence、lang、country、apdt、kind |
| RELATED_DOCUMENT | Patent→申请/专利 | related_documents | date、country、relation_type |
| CITES | Patent→Patent | patent_citations/cited_by | citation_date、country、region、kind |
| CITES_NON_PATENT | Patent→Document | non_patent_citations | citation_date |
| HAS_KEYWORD | Patent→Keyword | keywords | language、source |
| CLASSIFIED_AS | Patent→Classification | 分类字段 | scheme、is_main、sequence |
| MEMBER_OF_FAMILY | Patent→PatentFamily | family | country、status、application_date |
| HAS_LEGAL_EVENT | Patent→Event | legal_events/PRS | date、code |
| HAS_TRANSFER | Patent→Event | transfer | effective_date、country |
| TRANSFER_FROM/TO | Event→主体 | transfer_before/after | sequence |

每条边追加 source_table、source_record_id、ingest_batch、ingest_time。

## 6. 不进入图属性

claims、description、figures、完整法律事件和完整非专利引用文本保留在 MySQL/检索层。它们没有丢失，只是不复制到亿级图存储。

## 7. 数据质量和增量规则

1. patent_id 非空且唯一，七表以它关联。
2. JSON 数组空值统一为 []，JSON 对象使用通知表规定的键名。
3. 日期为 YYYY-MM-DD，年份为整数，年月为 YYYY-MM。
4. 重跑同一专利用同 VID 覆盖；source_update_time 判断增量。
5. 建边前先做 Person、Organization、Patent 引用对象规范化和消歧。
6. 引用或家族成员不在主表时只建最小桩顶点，不伪造业务属性。
