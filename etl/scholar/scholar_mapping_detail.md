# 学者领域映射分析文档 (Scholar Domain Mapping)

> 本文档详细分析科技要素数据库中学者相关表的每一个字段，映射到图数据库中的实体/关系属性。

## 目录
- [1. 表概览](#1-表概览)
- [2. dwd_scholar 字段映射](#2-dwd_scholar-字段映射)
- [3. dwd_scholar_talent_flag 字段映射](#3-dwd_scholar_talent_flag-字段映射)
- [4. dwd_scholar_research_direction 字段映射](#4-dwd_scholar_research_direction-字段映射)
- [5. dwd_scholar_coauthor 字段映射](#5-dwd_scholar_coauthor-字段映射)
- [6. dwd_scholar_paper_relation 字段映射](#6-dwd_scholar_paper_relation-字段映射)
- [7. dwd_scholar_papers 字段映射](#7-dwd_scholar_papers-字段映射)
- [8. VID生成规则](#8-vid生成规则)
- [9. 溯源属性映射](#9-溯源属性映射)

---

## 1. 表概览

| 表名 | 中文表名 | 目标实体/边 | 核心用途 |
|-----|---------|------------|---------|
| `dwd_scholar` | 学者主表 | Person Tag | 学者基本信息的核心实体 |
| `dwd_scholar_talent_flag` | 学者人才标识表 | Person.is_academician | 补充学者人才标签 |
| `dwd_scholar_research_direction` | 学者研究方向表 | Person.research_fields | 补充学者研究方向 |
| `dwd_scholar_coauthor` | 学者合作者关系表 | COAUTHOR_WITH Edge | 学者间合作关系 |
| `dwd_scholar_paper_relation` | 学者论文关系表 | AUTHORED_BY Edge | 学者与论文的关联 |
| `dwd_scholar_papers` | 论文信息表 | Paper Tag(补充) | 学者库论文补充信息 |

---

## 2. dwd_scholar 字段映射

**目标实体**: `Person` Tag  
**VID格式**: `person_{scholar_id}`

### 2.1 基本属性映射

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 | 样例值 |
|-----|-----------|-----------|---------|---------|---------|-------|
| 1 | 学者ID | scholar_id | varchar(32) | VID生成 | `person_{scholar_id}` | scholar_001 → person_scholar_001 |
| 2 | 英文姓名 | name_en | varchar(128) | Person.name_en | 直接映射 | Wei Li |
| 3 | 中文姓名 | name_zh | varchar(128) | Person.name_zh | 直接映射 | 李伟 |
| 4 | 头像 | avatar | varchar(256) | Person.avatar | 直接映射 | https://cdn.example.com/avatar.jpg |
| 5 | 英文机构 | scholar_org_name_en | varchar(4096) | Organization + AFFILIATED_WITH | 生成Organization顶点 + AFFILIATED_WITH边 | Institute of Computing Technology, CAS |
| 6 | 中文机构 | scholar_org_name_zh | varchar(1024) | Organization + AFFILIATED_WITH | 同上，优先用于Organization.name_cn | 中国科学院计算技术研究所 |
| 7 | 个人简介 | bio | longtext | Person.bio | 直接映射 | Dr. Wei Li is a professor... |
| 8 | 个人简介(中文) | bio_zh | longtext | Person.bio_zh | 直接映射 | 李伟博士是人工智能领域教授... |

### 2.2 工作经历映射

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 |
|-----|-----------|-----------|---------|---------|---------|
| 9 | 工作经历起止时间 | work_experience_date | varchar(100) | Person.work_experience_date | 直接映射 |
| 10 | 工作经历单位英文 | work_experience_institution_en | varchar(255) | Person.work_experience_institution_en | 直接映射 |
| 11 | 工作经历院系英文 | work_experience_department_en | varchar(255) | Person.work_experience_department_en | 直接映射 |
| 12 | 工作经历职务英文 | work_experience_position_en | varchar(255) | Person.work_experience_position_en | 直接映射 |
| 13 | 工作经历单位中文 | work_experience_institution_zh | varchar(255) | Person.work_experience_institution_zh | 直接映射 |
| 14 | 工作经历院系中文 | work_experience_department_zh | varchar(256) | Person.work_experience_department_zh | 直接映射 |
| 15 | 工作经历职务中文 | work_experience_position_zh | varchar(255) | Person.work_experience_position_zh | 直接映射 |

### 2.3 教育背景映射

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 |
|-----|-----------|-----------|---------|---------|---------|
| 16 | 教育背景起止时间 | education_background_date | varchar(100) | Person.education_background_date | 直接映射 |
| 17 | 教育机构英文 | education_background_institution_en | varchar(500) | Person.education_background_institution_en | 直接映射 |
| 18 | 教育学位英文 | education_background_degree_en | varchar(255) | Person.education_background_degree_en | 直接映射 |
| 19 | 教育机构中文 | education_background_institution_zh | varchar(500) | Person.education_background_institution_zh | 直接映射 |
| 20 | 教育学位中文 | education_background_degree_zh | varchar(255) | Person.education_background_degree_zh | 直接映射 |

### 2.4 学术指标映射

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 | 样例值 |
|-----|-----------|-----------|---------|---------|---------|-------|
| 21 | 论文数量 | paper_nums | int(8) | Person.paper_nums | 直接映射 | 156 |
| 22 | 被引数量 | citation_nums | int(8) | Person.citation_nums | 直接映射 | 8920 |
| 23 | H指数 | h_index | int(8) | Person.h_index | 直接映射 | 42 |
| 24 | 状态 | status | int(1) | Person.status | 直接映射，过滤status=1 | 1 |

### 2.5 溯源属性映射

| 序号 | 字段中文名 | 字段英文名 | 映射目标 | 映射规则 |
|-----|-----------|-----------|---------|---------|
| 25 | 创建时间 | create_time | Person.ingest_time | 首次入图时间 |
| 26 | 更新时间 | update_time | Person.source_update_time | 源记录更新时间 |

### 2.6 关联实体生成

从 `scholar_org_name_en/zh` 字段生成:

```
Person (person_{scholar_id}) 
  -[:AFFILIATED_WITH {affiliation_name, source}]-> 
    Organization (org_{md5(org_name)})
```

**Organization顶点属性**:
- `name_cn` ← scholar_org_name_zh
- `name_en` ← scholar_org_name_en
- `org_type` ← 根据"大学"/"研究所"/"公司"等关键词推断

---

## 3. dwd_scholar_talent_flag 字段映射

**目标实体**: 更新已存在的 `Person` Tag  
**关联条件**: `scholar_id` 匹配

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 | 样例值 |
|-----|-----------|-----------|---------|---------|---------|-------|
| 1 | 学者ID | scholar_id | varchar(32) | Person VID定位 | 匹配已有Person顶点 | scholar_001 |
| 2 | 是否为院士 | academician | varchar(128) | Person.is_academician | 直接更新属性 | 是/否 |
| 3 | 创建时间 | create_time | datetime | - | 不映射 |
| 4 | 更新时间 | update_time | datetime | - | 不映射 |

**nGQL示例**:
```ngql
UPDATE VERTEX ON Person "person_scholar_001" 
SET is_academician = "是";
```

---

## 4. dwd_scholar_research_direction 字段映射

**目标实体**: 更新已存在的 `Person` Tag  
**关联条件**: `scholar_id` 匹配

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 | 样例值 |
|-----|-----------|-----------|---------|---------|---------|-------|
| 1 | 学者ID | scholar_id | varchar(32) | Person VID定位 | 匹配已有Person顶点 | scholar_001 |
| 2 | 研究方向 | fields | text | Person.research_fields | 直接更新属性 | 人工智能；机器学习 |
| 3 | 创建时间 | create_time | datetime | - | 不映射 |
| 4 | 更新时间 | update_time | datetime | - | 不映射 |

**扩展方案**: 研究方向可拆分为Keyword实体，生成HAS_KEYWORD边

```ngql
-- 方案1: 直接存储
UPDATE VERTEX ON Person "person_scholar_001" 
SET research_fields = "人工智能；机器学习；深度学习";

-- 方案2: 拆分为Keyword实体
INSERT VERTEX Keyword (keyword) VALUES "keyword_ai":("人工智能");
INSERT EDGE HAS_KEYWORD () VALUES "person_scholar_001"->"keyword_ai":();
```

---

## 5. dwd_scholar_coauthor 字段映射

**目标实体**: `COAUTHOR_WITH` Edge  
**起点**: `person_{scholar_id}`  
**终点**: `person_{co_scholar_id}`

### 5.1 字段映射

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 | 样例值 |
|-----|-----------|-----------|---------|---------|---------|-------|
| 1 | 学者ID | scholar_id | varchar(32) | 边起点VID | person_{scholar_id} | scholar_001 |
| 2 | 合作学者ID | co_scholar_id | varchar(32) | 边终点VID | person_{co_scholar_id} | scholar_002 |
| 3 | 合作学者英文名 | co_scholar_name_en | varchar(256) | - | 仅用于展示/查询辅助 | Ying Zhang |
| 4 | 合作学者中文名 | co_scholar_name_zh | varchar(128) | - | 仅用于展示/查询辅助 | 张颖 |
| 5 | 合作学者头像 | co_scholar_avatar | varchar(512) | - | 不映射 | - |
| 6 | 合作学者机构英文名 | co_scholar_org_name_en | varchar(2048) | - | 不映射 | - |
| 7 | 合作学者机构中文名 | co_scholar_org_name_zh | varchar(1024) | - | 不映射 | - |
| 8 | 合作论文数量 | co_paper_count | int(8) | COAUTHOR_WITH.co_paper_count | 边属性 | 12 |
| 9 | 状态 | status | int(1) | - | 过滤条件，status=1 | 1 |
| 10 | 创建时间 | create_time | datetime | - | 不映射 |
| 11 | 更新时间 | update_time | datetime | COAUTHOR_WITH.ingest_time | 溯源 |

### 5.2 边生成逻辑

```
Person (scholar_id) -[COAUTHOR_WITH {co_paper_count}]-> Person (co_scholar_id)
```

**注意事项**:
- 合作关系是双向的，但只存储一条边
- 查询时使用双向查询: `MATCH (p1)-[:COAUTHOR_WITH]-(p2)`
- 若co_scholar_id对应的Person顶点不存在，需先创建

### 5.3 nGQL示例

```ngql
INSERT EDGE COAUTHOR_WITH (
    co_paper_count, source_table, source_record_id, ingest_batch, ingest_time
) VALUES 
    "person_scholar_001"->"person_scholar_002":(12, "dwd_scholar_coauthor", "scholar_001_scholar_002", "BATCH_001", NOW());
```

---

## 6. dwd_scholar_paper_relation 字段映射

**目标实体**: `AUTHORED_BY` Edge  
**起点**: `paper_{paper_id}` (Paper顶点)  
**终点**: `person_{scholar_id}` (Person顶点)

### 6.1 字段映射

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 | 样例值 |
|-----|-----------|-----------|---------|---------|---------|-------|
| 1 | 论文ID | paper_id | int64 | 边起点VID | paper_{paper_id} | 1000001 |
| 2 | 论文发表年份 | year | int64 | - | 可用于边属性扩展 | 2024 |
| 3 | 学者ID | scholar_id | varchar(32) | 边终点VID | person_{scholar_id} | scholar_001 |
| 4 | 被引用次数 | citations | int(8) | AUTHORED_BY.citations | 边属性 | 32 |
| 5 | 发布时间 | publish_time | date | - | 不映射 |
| 6 | 状态 | status | int(1) | - | 过滤条件 |
| 7 | 期刊ID | publication_id | int64 | - | 关联dwd_en_journal |
| 8 | 关联论文库ID | related_paper_id | bigint | - | 关联论文库 |

### 6.2 待确认事项

⚠ **关键待确认**: `paper_id` 归属问题

根据mapping.md 2.5节:
- 源表注释: 关联 `dwd_scholar_papers.id`
- 兄弟字段推断: `publication_id` → `dwd_en_journal.id`
- **建议**: 接数后抽样核对 `paper_id` 在 `dwd_zh_paper` / `dwd_en_paper` 中的命中率

**处理逻辑**:
1. 优先匹配 `dwd_zh_paper.id` / `dwd_en_paper.id`
2. 命中: 直接连接已有Paper顶点
3. 未命中: 建桩顶点 `paper_{paper_id}`，后续用SAME_AS合并

### 6.3 nGQL示例

```ngql
-- 假设paper_id在论文库中存在
INSERT EDGE AUTHORED_BY (
    citations, source_table, source_record_id, ingest_batch, ingest_time
) VALUES 
    "paper_1000001"->"person_scholar_001":(45, "dwd_scholar_paper_relation", "1000001_scholar_001", "BATCH_001", NOW());
```

---

## 7. dwd_scholar_papers 字段映射

**目标实体**: 更新/补充已存在的 `Paper` Tag  
**关联条件**: DOI归一化匹配

### 7.1 字段映射

| 序号 | 字段中文名 | 字段英文名 | 数据类型 | 映射目标 | 映射规则 |
|-----|-----------|-----------|---------|---------|---------|
| 1 | 中文题目 | zh_name | varchar(500) | Paper.title_zh | coalesce，不覆盖已有值 |
| 2 | 英文题目 | en_name | varchar(500) | Paper.title_en | coalesce，不覆盖已有值 |
| 3 | 作者列表 | authors | varchar(65535) | - | 不映射（已在其他表处理） |
| 4 | 论文原始链接 | paper_url | varchar(1024) | Paper.source_url | coalesce |
| 5 | 发表时间 | cover_date_start | date | Paper.publication_date | coalesce |
| 6 | 中文摘要 | zh_abstract | varchar(65535) | Paper.abstract_zh | coalesce |
| 7 | 英文摘要 | en_abstract | varchar(65535) | Paper.abstract_en | coalesce |
| 8 | DOI | doi | varchar(512) | 匹配键 | 用于匹配已有Paper顶点 |
| 9 | 期刊/会议英文名 | publication_en_name | varchar(1024) | Journal + PUBLISHED_IN | 生成期刊关联 |

### 7.2 DOI归一化规则

⚠ **待扩展**: 当前规则覆盖:
- 小写化
- 去除 `https://doi.org/` 前缀
- 去除 `doi.org/` 前缀
- trim首尾空格

可能需要扩展的场景:
- `urn:doi:` 前缀
- 全角字符
- 中间含空格
- 带 query/fragment 的变体

### 7.3 处理流程

```
1. 归一化 doi 字段
2. 在 dwd_zh_paper.paper_identifier / dwd_en_paper.paper_unique_id 中查找
3. 命中: UPSERT 补充属性到已有 Paper 顶点
4. 未命中: 建桩顶点 paper_{doi}，source = scholar_paper
```

---

## 8. VID生成规则

### 8.1 Person VID

| 来源表 | VID格式 | 示例 |
|-------|--------|------|
| dwd_scholar | person_{scholar_id} | person_accc1946 |
| dwd_zh_paper_author | person_{author_id} | person_author_001 |
| dwd_en_paper_author | person_{author_id} | person_author_002 |

**注意**: scholar_id 与 author_id 不保证一致，分别生成VID。后续若有对齐表，用SAME_AS边合并。

### 8.2 Organization VID

| 来源 | VID格式 | 示例 |
|-----|--------|------|
| 机构名称 | org_{md5(name)[:16]} | org_a1b2c3d4e5f6g7h8 |
| 机构ID | org_{org_id} | org_123456 |

### 8.3 DataSource VID

| 格式 | 示例 |
|-----|------|
| ds_{table_name} | ds_dwd_scholar |

---

## 9. 溯源属性映射

### 9.1 顶点溯源块（Person Tag）

| 属性 | 来源 | 示例值 |
|-----|------|-------|
| source_system | 固定值 | gkx_element |
| source_table | 表名 | dwd_scholar |
| source_record_id | 主键字段 | scholar_001 |
| source_url | source_url字段 | - |
| ingest_batch | ETL批次号 | BATCH_20260721_001 |
| ingest_time | ETL执行时间 | 2026-07-21 10:30:00 |
| source_update_time | update_time字段 | 2026-07-20 15:00:00 |

### 9.2 边溯源块

| Edge类型 | source_table | source_record_id |
|----------|-------------|-----------------|
| COAUTHOR_WITH | dwd_scholar_coauthor | {scholar_id}_{co_scholar_id} |
| AFFILIATED_WITH | dwd_scholar | {scholar_id} |
| AUTHORED_BY | dwd_scholar_paper_relation | {paper_id}_{scholar_id} |

---

## 10. 完整映射图

```
dwd_scholar
    │
    ├─→ Person (person_{scholar_id})
    │       ├─ name_en, name_zh, avatar, bio, bio_zh
    │       ├─ work_experience_* (7字段)
    │       ├─ education_background_* (5字段)
    │       ├─ paper_nums, citation_nums, h_index
    │       └─ 溯源属性块 (7字段)
    │
    └─→ Organization (org_{hash}) ──[:AFFILIATED_WITH]→ Person

dwd_scholar_talent_flag
    └─→ Person.is_academician (UPDATE)

dwd_scholar_research_direction
    └─→ Person.research_fields (UPDATE)

dwd_scholar_coauthor
    └─→ COAUTHOR_WITH: Person ──→ Person

dwd_scholar_paper_relation
    └─→ AUTHORED_BY: Paper ──→ Person

dwd_scholar_papers
    └─→ Paper (按DOI匹配后UPSERT)
```

---

## 11. 附录

### 11.1 相关文件

| 文件 | 用途 |
|-----|------|
| scholar_fake_data.sql | 假数据SQL |
| scholar_schema.ngql | 图Schema定义 |
| scholar_etl.py | ETL处理脚本 |

### 11.2 参考文档

- [mapping.md](./mapping.md) - 整体映射文档
- [ontology.md](./ontology.md) - 本体设计文档
- [腾讯文档：版权人才、企业机构、政策数据汇总表](https://docs.qq.com/sheet/DWWxaRUF6b1JCakFF)
