# 专利实体本体设计（第一阶段）

> 依据：`graph-schema/ontology.md` 与 `graph-schema/graph/ddl.ngql`。  
> 范围：仅创建 `Patent` 实体及原设计中的基本属性；不创建 Person、Organization、Keyword 等关联实体，不创建任何 Edge。

## 1. 实体定义

| Tag | 来源表 | VID格式 | 说明 |
|---|---|---|---|
| `Patent` | `gkx_element.dwd_patent`及其标题、摘要、法律、引用分表 | `patent_{patent_id}` | 全球专利基本实体 |

VID示例：`patent_CN103073024B`。

## 2. 原有业务属性

属性名称和类型与原`Patent` Tag保持一致，本阶段不新增业务属性。

| 属性 | nGQL类型 | 当前正确来源 | 说明 |
|---|---|---|---|
| `publication_number` | `string` | `dwd_patent.publication_number` | 专利公布号 |
| `application_kind` | `string` | `dwd_patent.application_kind` | 专利申请类型 |
| `country_code` | `string` | `dwd_patent.country_code` | 国家/地区/组织代码 |
| `country` | `string` | `dwd_patent.country` | 国家名称 |
| `title` | `string` | `dwd_patent_title.title_localized.$.zh` | 中文优先展示标题 |
| `abstract` | `string` | `dwd_patent_abstract.abstract_localized.$.zh` | 中文优先展示摘要 |
| `language` | `string` | `dwd_patent.language` | 原文语言 |
| `status` | `string` | `dwd_patent_legal.status` | 当前法律状态 |
| `granted_number` | `string` | `dwd_patent.granted_number` | 授权号 |
| `application_date` | `string` | `dwd_patent.application_reference_3` | 申请日期，`YYYY-MM-DD` |
| `publication_date` | `string` | `dwd_patent.publication_reference_2` | 发布日期，`YYYY-MM-DD` |
| `anticipated_expiration` | `date` | `dwd_patent_legal.anticipated_expiration` | 预计到期日 |
| `citation_nums` | `int64` | `dwd_patent_cited.reference_cited` | 引用专利数量 |
| `cited_by_nums` | `int64` | `dwd_patent_cited.cited_by_nums` | 被其他专利引用数量 |

## 3. 原有溯源属性

| 属性 | nGQL类型 | 取值规则 |
|---|---|---|
| `source_system` | `string` | 固定为`gkx_element` |
| `source_table` | `string` | 主实体固定为`dwd_patent` |
| `source_record_id` | `string` | `dwd_patent.patent_id` |
| `source_url` | `string` | 当前源表无URL，写空字符串 |
| `ingest_batch` | `string` | ETL批次号 |
| `ingest_time` | `datetime` | ETL写入时间 |
| `source_update_time` | `datetime` | `dwd_patent.update_time` |

## 4. 本阶段不处理的本体内容

以下属于实体关系抽取，留待后续阶段：

- `inventors` → `Person` + `INVENTED_BY`
- `applicants`/`assignees` → `Organization` + `APPLIED_BY`
- `patent_citations`/`cited_by` → `Patent` + `CITES`/`CITED_BY`
- `keywords` → `Keyword` + `HAS_KEYWORD`
- 专利家族、法律事件、转移事件等复杂对象建模

## 5. 新增项

本阶段没有新增Tag、业务属性或Edge。仅修正原映射中的真实字段来源，不改变既有属性名称和类型。
