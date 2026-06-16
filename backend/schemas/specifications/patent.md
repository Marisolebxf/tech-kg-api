# 专利数据表规范

本规范依据第三方最新《要素库设计方案》整理。表名、普通字段名、长度、空值要求和索引要求以第三方规范为准。

## 建模约定

第三方规范同时提供“字段英文名称”和“字段英文名称（JSON 解析）”。例如：

```text
publication_reference.kind
publication_reference.date
publication_reference.year
publication_reference.month
```

这些内容在源数据中属于同一个嵌套对象，不能在关系型表中建立多个同名
`publication_reference` 列。因此 DDL 保留顶层字段名，并使用 `JSON` 保存其子字段：

```json
{
  "kind": "A",
  "date": "2013-10-02",
  "year": "2013",
  "month": "2013-10"
}
```

没有 JSON 子字段的普通字段按照第三方给出的英文名直接建列。规范中标记“否”的空值字段使用
`NOT NULL`；明确的主键和普通索引按照规范建立。

## 数据类型映射

| 第三方类型 | MySQL 类型 |
|---|---|
| 字符型 | `VARCHAR(n)`；未提供有效长度时使用 `TEXT` |
| 文本型 | `TEXT` |
| 数字型，精度不超过 11 | `BIGINT` |
| 日期型 | `DATE` 或 `DATETIME` |
| 含 JSON 解析子字段的顶层字段 | `JSON` |

## 1. 专利信息表 `dwd_patent`

### 普通字段

| 字段英文名称 | SQL 类型 | 空值 | 索引/主键 | 数据样例 |
|---|---|---|---|---|
| `patent_id` | `VARCHAR(64)` | 否 | 主键 | `CN103332525A` |
| `publication_number` | `VARCHAR(64)` | 否 | 索引 | `CN-103332525-A` |
| `application_kind` | `VARCHAR(2)` | 是 | - | `A` |
| `country_code` | `VARCHAR(2)` | 是 | - | `CN` |
| `country` | `VARCHAR(20)` | 是 | - | `China` |
| `first_applicant_name` | `VARCHAR(255)` | 是 | - | `中顺洁柔纸业股份有限公司` |
| `first_current_assignee_name` | `VARCHAR(255)` | 是 | - | `C&S PAPER CO., LTD.` |
| `first_inventor_name` | `VARCHAR(255)` | 是 | - | `邓颖忠` |
| `keywords` | `TEXT` | 是 | - | `["纸张","折叠","毫米"]` |
| `claims_localized` | `TEXT` | 是 | - | 多语言权利要求 JSON 文本 |
| `description_localized` | `TEXT` | 是 | - | 多语言说明书 JSON 文本 |
| `figures` | `TEXT` | 是 | - | 附图信息 JSON 文本 |
| `language` | `VARCHAR(16)` | 是 | - | `中文（zh）` |
| `granted_number` | `VARCHAR(64)` | 是 | - | `CN103332525B` |
| `spif_application_number` | `VARCHAR(64)` | 是 | - | `CN201310276148` |
| `spif_publication_number` | `VARCHAR(64)` | 是 | - | `CN103332525A` |
| `prior_art_year` | `VARCHAR(4)` | 是 | - | `2013` |
| `prior_art_date` | `VARCHAR(10)` | 是 | - | `2013-10-02` |
| `relevants` | `TEXT` | 是 | - | 相关专利编号数组 |
| `db_source` | `VARCHAR(64)` | 否 | - | `ods_patent` |
| `create_time` | `DATETIME` | 否 | - | `2026-04-15 14:59:34` |
| `update_time` | `DATETIME` | 否 | - | `2026-04-15 14:59:34` |
| `citation_nums` | `BIGINT` | 是 | - | `20` |
| `cited_by_nums` | `BIGINT` | 是 | - | `6` |
| `non_patent_citations_nums` | `BIGINT` | 是 | - | `1` |
| `status` | `VARCHAR(10)` | 是 | - | `已授权（Granted）` |
| `anticipated_expiration` | `DATE` | 是 | - | `2013-10-02` |
| `expiration_year` | `VARCHAR(10)` | 是 | - | `2033` |
| `family_citations` | `TEXT` | 是 | - | 家族内引用编号数组 |
| `cited_by_family` | `TEXT` | 是 | - | 家族内被引用编号数组 |
| `other_versions` | `TEXT` | 是 | - | 其他版本编号数组 |
| `worldwides` | `TEXT` | 是 | - | 全球同族专利对象数组 |

### JSON 字段

| 顶层字段 | JSON 子字段 | 样例说明 |
|---|---|---|
| `publication_reference` | `kind`, `date`, `year`, `month` | 发布种类、日期、年份和年月 |
| `application_reference` | `apno`, `country`, `date`, `year`, `month` | 申请号、受理局和申请日期 |
| `pct_or_regional_filing_data` | `doc_number`, `date` | PCT 申请号和申请日期 |
| `pct_or_regional_publishing_data` | `doc_number`, `date` | PCT 公布号和公布日期 |
| `priority_filings` | `sequence`, `language`, `application_number`, `publication_number`, `country`, `date`, `year`, `patent_type`, `title` | 优先权对象数组 |
| `applicants` | `sequence`, `name` | 原始申请人对象数组 |
| `assignees` | `sequence`, `name` | 当前申请人/专利权人对象数组 |
| `inventors` | `sequence`, `name` | 发明人对象数组 |
| `classification_ipcr` | `main`, `further` | IPCR/IPC 主分类号和附加分类号 |
| `classification_cpc` | `main`, `further` | CPC 主分类号和附加分类号 |
| `patent_citations` | `publication_number`, `publication_date`, `country`, `kind` | 引用专利对象数组 |
| `cited_by` | `publication_number`, `publication_date`, `country`, `kind` | 被引专利对象数组 |
| `non_patent_citations` | `non_patent_citations_link`, `non_patent_citations_title` | 非专利文献对象数组 |
| `dates_of_public_availability` | `printed_with_granted`, `year`, `month` | 授权日期、年份和年月 |
| `simple_family` | `doc_number` | 简单同族成员文献号数组 |

## 2. 专利标题信息表 `dwd_patent_title`

| 字段英文名称 | SQL 类型 | 空值 | 说明 |
|---|---|---|---|
| `patent_id` | `VARCHAR(64)` | 否 | 主键，关联 `dwd_patent.patent_id` |
| `title_localized` | `JSON` | 是 | 包含 `text` 和 `text[lang=en]` |
| `db_source` | `VARCHAR(64)` | 否 | 数据库来源 |
| `create_time` | `DATETIME` | 否 | 创建时间 |
| `update_time` | `DATETIME` | 否 | 更新时间 |

`title_localized` 样例：

```json
{
  "text": "一种纸手帕折叠加工设备",
  "text[lang=en]": "Paper handkerchief folding machining device"
}
```

## 3. 专利摘要信息表 `dwd_patent_abstract`

| 字段英文名称 | SQL 类型 | 空值 | 说明 |
|---|---|---|---|
| `patent_id` | `VARCHAR(64)` | 否 | 主键，关联 `dwd_patent.patent_id` |
| `abstract_localized` | `JSON` | 是 | 包含 `text` 和 `text[lang=en]` |
| `db_source` | `VARCHAR(64)` | 否 | 数据库来源 |
| `create_time` | `DATETIME` | 否 | 创建时间 |
| `update_time` | `DATETIME` | 否 | 更新时间 |

## 4. 法律状态信息表 `dwd_patent_legal`

| 字段英文名称 | SQL 类型 | 空值 | 说明 |
|---|---|---|---|
| `patent_id` | `VARCHAR(64)` | 否 | 主键，关联 `dwd_patent.patent_id` |
| `legal_events` | `TEXT` | 是 | 法律事件对象数组 |
| `patent_legal/prs_data` | `JSON` | 是 | 包含 `event_date`、`event_code` 和法律状态分类说明 |
| `db_source` | `VARCHAR(64)` | 否 | 数据库来源 |
| `create_time` | `DATETIME` | 否 | 创建时间 |
| `update_time` | `DATETIME` | 否 | 更新时间 |

> `patent_legal/prs_data` 是第三方规范给出的原始字段路径。DDL 使用反引号保留该名称。

## 5. 专利家族信息表 `dwd_patent_family`

| 字段英文名称 | SQL 类型 | 空值 | 索引/主键 | 说明 |
|---|---|---|---|---|
| `patent_id` | `VARCHAR(64)` | 否 | 主键 | 关联 `dwd_patent.patent_id` |
| `simple_family` | `JSON` | 是 | - | 包含 `id`、`country`、`kind` |
| `db_source` | `VARCHAR(64)` | 否 | - | 数据库来源 |
| `create_time` | `DATETIME` | 否 | - | 创建时间 |
| `update_time` | `DATETIME` | 否 | - | 更新时间 |

## 样例数据格式约定

后续统一生成示范数据时：

1. 日期使用 `YYYY-MM-DD`，日期时间使用 `YYYY-MM-DD HH:MM:SS`。
2. 第三方样例 `15/4/2026 14:59:34` 统一转换为 `2026-04-15 14:59:34`。
3. JSON 列使用合法 JSON；数组字段即使只有一个元素也保持数组形式。
4. `claims_localized` 等规范标记为文本型的 JSON 内容仍按字符串保存，不擅自改为 JSON 列。
5. 空值使用 SQL `NULL`，不能使用空字符串代替未知值。

