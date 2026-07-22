# 专利实体源表映射（第一阶段）

> 依据：`graph-schema/graph/mapping.md`第5章。  
> 本阶段只映射Patent基本属性，不处理5.2—5.5的实体关系。

## 1. 装载粒度

- 主记录：`dwd_patent`每个`patent_id`生成一个Patent节点。
- VID：`patent_{patent_id}`。
- 关联方式：标题、摘要、法律状态和引用统计分表按`patent_id`左连接。
- 当前数据量：主表2,000条；预期生成2,000个Patent节点。

## 2. 字段级映射

| 序号 | 源表 | 源字段/表达式 | 源类型 | 转换规则 | Patent目标 | 目标类型 | 备注 |
|---:|---|---|---|---|---|---|---|
| 1 | `dwd_patent` | `patent_id` | varchar(64) | `patent_`拼接原值 | VID | fixed string | 图节点主标识 |
| 2 | `dwd_patent` | `publication_number` | varchar(64) | 原值 | `publication_number` | string | 原有属性 |
| 3 | `dwd_patent` | `application_kind` | varchar(1) | 原值 | `application_kind` | string | 原有属性 |
| 4 | `dwd_patent` | `country_code` | varchar(8) | 原值 | `country_code` | string | 原有属性 |
| 5 | `dwd_patent` | `country` | varchar(20) | 原值 | `country` | string | 原有属性 |
| 6 | `dwd_patent_title` | `title_localized` | varchar(1024) | 解析JSON并提取`$.zh`；缺失时回退`title_zh` | `title` | string | 修正旧版`.text`映射 |
| 7 | `dwd_patent_abstract` | `abstract_localized` | text | 解析JSON并提取`$.zh`；缺失时回退`abstract_zh` | `abstract` | string | 修正旧版`.text`映射 |
| 8 | `dwd_patent` | `language` | varchar(16) | 原值 | `language` | string | 原有属性 |
| 9 | `dwd_patent_legal` | `status` | varchar(64) | 原值 | `status` | string | 旧文档误写为主表字段 |
| 10 | `dwd_patent` | `granted_number` | varchar(64) | 原值 | `granted_number` | string | 原有属性 |
| 11 | `dwd_patent` | `application_reference_3` | varchar(10) | 原值 | `application_date` | string | 旧文档JSON字段已拆列 |
| 12 | `dwd_patent` | `publication_reference_2` | varchar(10) | 原值 | `publication_date` | string | 旧文档JSON字段已拆列 |
| 13 | `dwd_patent_legal` | `anticipated_expiration` | varchar(10) | 合法日期转`date()` | `anticipated_expiration` | date | 旧文档未注明分表 |
| 14 | `dwd_patent_cited` | `reference_cited` | int | 空值按0 | `citation_nums` | int64 | 旧字段名`citation_nums`不存在 |
| 15 | `dwd_patent_cited` | `cited_by_nums` | int | 空值按0 | `cited_by_nums` | int64 | 原有属性 |
| 16 | 固定值 | `gkx_element` | — | 固定值 | `source_system` | string | 标准溯源 |
| 17 | 固定值 | `dwd_patent` | — | 固定值 | `source_table` | string | 标准溯源 |
| 18 | `dwd_patent` | `patent_id` | varchar(64) | 原值 | `source_record_id` | string | 标准溯源 |
| 19 | — | 无对应字段 | — | 空字符串 | `source_url` | string | 标准溯源 |
| 20 | ETL | `batch_id` | — | 命令参数或自动生成 | `ingest_batch` | string | 标准溯源 |
| 21 | ETL | 当前时间 | — | UTC+8时间转datetime | `ingest_time` | datetime | 标准溯源 |
| 22 | `dwd_patent` | `update_time` | datetime | 原值 | `source_update_time` | datetime | 标准溯源 |

## 3. 本阶段SQL关联

```sql
SELECT ...
FROM dwd_patent p
LEFT JOIN dwd_patent_title t ON t.patent_id = p.patent_id
LEFT JOIN dwd_patent_abstract a ON a.patent_id = p.patent_id
LEFT JOIN dwd_patent_legal l ON l.patent_id = p.patent_id
LEFT JOIN dwd_patent_cited c ON c.patent_id = p.patent_id
ORDER BY p.id
LIMIT %s OFFSET %s;
```

## 4. 暂缓字段

以下字段不丢弃，但本期不入图：

| 字段组 | 来源 | 后续用途 |
|---|---|---|
| 发明人 | `inventors`、`inventors_2` | Person/INVENTED_BY |
| 申请人和权利人 | `applicants*`、`assignees*` | Organization/APPLIED_BY |
| 引用明细 | `patent_citations`、`cited_by` | CITES/CITED_BY |
| 关键词 | `keywords` | Keyword/HAS_KEYWORD |
| 分类、PCT、优先权 | `dwd_patent`相关字段 | 后续扩展Patent属性或分类实体 |
| 法律事件 | `dwd_patent_legal.legal_events` | 后续事件实体 |
| 家族信息 | `dwd_patent_family` | 后续家族建模 |
| 转移信息 | `dwd_patent_transfer` | 后续转移事件建模 |
| 权利要求、说明书、图片 | 主表JSON字段 | 后续长文本/检索方案 |

## 5. 数据质量说明

- 当前部分分类、代理、价值、PCT及转移字段为样例或推导数据，本期均未映射为Patent基本属性。
- 本期映射的标题、摘要和日期采用当前数据库真实物理列，不使用旧版JSON列假设。
- 关系相关字段将在后续扩展时逐字段补充。
