# 专利实体本体设计

依据：2026-07-22 业务确认的全球专利要素库表结构。
当前落地范围：dev 只创建 Patent 顶点及其固有属性，不创建专利相关 Edge；本文同时规划后续边阶段。

## 1. 建模原则

1. dwd_patent.patent_id 是七张表的稳定关联主键，VID 统一为 patent_{patent_id}。
2. 专利自身稳定、单值或适合检索的快照信息作为 Patent 属性。
3. 人员、机构、关键词、分类、家族、事件和引用专利具有独立身份或可复用，后续建为顶点并通过边连接。
4. JSON 数组后续逐元素展开；当前只对少量分类、关键词保留序列化检索快照。
5. 权利要求、说明书、图片和完整法律事件体量大，保留在 MySQL/全文检索层，通过 patent_id 回查。
6. 统计值、法律状态和第一责任主体是可变快照；历史变化后续由 Event 表达。

## 2. 当前实体

| Tag | 来源 | VID | 粒度 |
|---|---|---|---|
| Patent | dwd_patent 联合 title、abstract、legal、cited、family | patent_{patent_id} | 一项专利记录一个顶点 |

## 3. 当前 Patent 属性

### 3.1 标识、公开、申请和 PCT

| 属性 | 类型 | 来源 |
|---|---|---|
| patent_id、publication_number | string | 主表同名字段 |
| application_kind、country_code、country | string | 主表同名字段 |
| publication_kind/date/year/month | string/string/int/string | publication_reference 的 kind/pbdt/pbdt_year/pbdt_month |
| application_number/country/date/year/month | string/string/string/int/string | application_reference 的 apno/country/apdt/apdt_year/apdt_month |
| pct_application_number/date、pct_national_stage_date | string | pct_or_regional_filing_data 的 apno/apdt/etdt |
| pct_publication_number/date | string | pct_or_regional_publishing_data 的 pn/pbdt |
| granted_number | string | 主表 |

### 3.2 文本、分类和检索快照

| 属性 | 类型 | 来源/规则 |
|---|---|---|
| title_original/en/zh | string | titles、title_localized.en、title_zh |
| abstract_original/en/zh | string | abstracts、abstract_localized.en、abstract_zh |
| language | string | JSON 语言数组转逗号分隔字符串 |
| main_ipcr、main_cpc | string | 主分类号 |
| further_ipcr、further_cpc | string | 附加分类 JSON 序列化快照 |
| keywords | string | 关键词 JSON 序列化快照；后续同时生成 Keyword 边 |

### 3.3 法律、评价、统计与溯源

| 属性 | 类型 | 来源 |
|---|---|---|
| status | string | dwd_patent_legal.status |
| grant_date/year/month | string/int/string | dates_of_public_availability |
| anticipated_expiration、expiration_year | date/int | legal 表 |
| citation_nums、cited_by_nums、non_patent_citation_nums | int | cited 表 |
| patent_value | int | dwd_patent.value |
| simple_family_number | string | family 表 |
| source_system/source_table/source_record_id/source_url | string | 标准溯源 |
| ingest_batch/ingest_time/source_update_time | string/datetime/datetime | ETL 与主表 update_time |

当前共 50 个属性。

## 4. 不作为 Patent 固有属性的数据

| 源数据 | 后续顶点 | 后续边 | 主要边属性 |
|---|---|---|---|
| inventors | Person | INVENTED_BY | sequence |
| applicants | Organization 或 Person | APPLIED_BY | sequence、role |
| assignees | Organization 或 Person | OWNED_BY | sequence、is_current |
| agents | Person | REPRESENTED_BY | sequence、role |
| agency | Organization | HANDLED_BY | sequence、role |
| examiners | Person | EXAMINED_BY | level、department |
| priority_filings | PatentApplication/专利桩 | CLAIMS_PRIORITY_TO | sequence、country、apdt、kind、lang |
| related_documents | PatentApplication/专利桩 | RELATED_DOCUMENT | relation_type、date、country |
| patent_citations、cited_by | Patent | CITES | citation_date、country、region、kind |
| non_patent_citations | Document | CITES_NON_PATENT | citation_date |
| keywords | Keyword | HAS_KEYWORD | language、source |
| IPCR/CPC/LOC/FI/UPC/F-term | Classification | CLASSIFIED_AS | scheme、is_main、sequence |
| 家族成员和全球同族 | PatentFamily 与 Patent | MEMBER_OF_FAMILY | country、status、application_date |
| legal_events、PRS | Event(legal_event) | HAS_LEGAL_EVENT | date、code、event |
| dwd_patent_transfer | Event(patent_transfer)与主体 | HAS_TRANSFER、TRANSFER_FROM/TO | effective_date、country、sequence |

first_applicant_name、first_current_assignee_name、first_inventor_name 是关系数组的派生加速字段，不作为独立事实；后续由 sequence=1 的边获得。

## 5. 只留在数据/检索层

| 数据 | 原因 |
|---|---|
| claims | 超长、多语言、数组，亿级图中重复存储成本高 |
| description | 超长说明书，适合 MySQL/Elasticsearch |
| figures | 图片元数据及附件应由对象存储/文档服务管理 |
| 完整法律事件文本 | 多事件且会增长，后续转 Event |
| 完整非专利引用原文 | 需先与文献库消歧 |

## 6. 当前完整性结论

Patent 的标识、申请/公开/PCT、三语标题摘要、分类快照、法律状态、授权与到期、引用统计、价值、家族标识和溯源均已覆盖。没有把未来边的端点数据误当成 Patent 属性，也没有把说明书等超长内容强塞入图数据库。

## 7. 索引策略

- 已知 patent_id 时直接构造 VID；VID 已由 TRSGraph 原生索引，无需 patent_id 二级索引。
- 当前仅建 Patent() 空 Tag 索引 idx_patent_scan，用于 MATCH 全量枚举和统计。
- 只有出现明确的属性检索接口且不能传 patent_id 时，才按查询新增属性索引。
- country_code 等高重复字段不单独建索引，避免亿级写放大和巨大结果集。
