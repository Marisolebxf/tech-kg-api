# 中文论文字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `dwd_zh_author` | 深势-中文文献作者详情信息 | 7965 | 7 |
| `dwd_zh_journal` | 深势-中文期刊详情信息 | 1932 | 33 |
| `dwd_zh_paper` | 深势-中文论文详情信息 | 1584 | 19 |
| `ods_zh_journal` | 维普中文报告信息 | 0 | 41 |

## `dwd_zh_author`

表注释：深势-中文文献作者详情信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(32)` | NO | PRI |  |  | 文献作者的唯一主键 id |
| 2 | `paper_id` | `varchar(64)` | NO |  |  |  | 文献记录的唯一主键标识。 |
| 3 | `en_name` | `varchar(255)` | YES |  |  |  | 文献作者的英文名称 |
| 4 | `zh_name` | `varchar(255)` | YES |  |  |  | 文献作者中文名 |
| 5 | `affiliation` | `mediumtext` | YES |  |  |  | 文献作者地址 |
| 6 | `email` | `mediumtext` | YES |  |  |  | 文献作者email |
| 7 | `correspond` | `tinyint` | YES |  |  |  | 是否为通讯作者 |

## `dwd_zh_journal`

表注释：深势-中文期刊详情信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  | 期刊记录的唯一标识。 |
| 2 | `iscn` | `varchar(16)` | YES |  |  |  | 期刊的国内统一刊号。 |
| 3 | `issn` | `varchar(16)` | YES |  |  |  | 期刊的国际标准连续出版物编号。 |
| 4 | `zh_name` | `varchar(1024)` | YES |  |  |  | 期刊的中文名称。 |
| 5 | `en_name` | `varchar(1024)` | YES |  |  |  | 期刊的英文名称。 |
| 6 | `publication_type` | `varchar(255)` | YES |  |  |  | 出版物类别，例如期刊，会议等 |
| 7 | `name_abbr` | `varchar(255)` | YES |  |  |  | 期刊名称的简称或缩写。 |
| 8 | `country` | `varchar(255)` | YES |  |  |  | 期刊所属或出版所在的国家。 |
| 9 | `zh_description` | `mediumtext` | YES |  |  |  | 期刊的中文简介或说明。 |
| 10 | `format` | `varchar(63)` | YES |  |  |  | 期刊的版面开本规格。 |
| 11 | `founding_time` | `int` | YES |  |  |  | 期刊首次创办或发行的时间。 |
| 12 | `language_classify` | `tinyint` | YES |  |  |  | 期刊出版使用的语言类型。 |
| 13 | `eissn` | `varchar(16)` | YES |  |  |  | 期刊电子版的国际标准连续出版物编号。 |
| 14 | `jn_official` | `mediumtext` | YES |  |  |  | 期刊官方网站地址。 |
| 15 | `postal_code` | `varchar(32)` | YES |  |  |  | 期刊邮政发行使用的代号。 |
| 16 | `chief_editor` | `varchar(128)` | YES |  |  |  | 期刊当前或记录中的主编信息。 |
| 17 | `organizer` | `varchar(1024)` | YES |  |  |  | 负责主办该期刊的单位名称。 |
| 18 | `publisher_place` | `varchar(64)` | YES |  |  |  | 期刊出版发行的地点。 |
| 19 | `publication_cycle` | `varchar(64)` | YES |  |  |  | 期刊的出版频率或发行周期。 |
| 20 | `award` | `mediumtext` | YES |  |  |  | 期刊获得的奖项或荣誉信息。 |
| 21 | `cite_nums` | `int` | YES |  |  |  | 期刊或文献的累计被引用次数。 |
| 22 | `paper_nums` | `int` | YES |  |  |  | 期刊已发表论文的数量。 |
| 23 | `review` | `tinyint` | YES |  |  |  | 标识该期刊是否为综述类期刊。 |
| 24 | `annual_publication` | `int` | YES |  |  |  | 期刊每年发表文章的数量。 |
| 25 | `impact_factor` | `decimal(20,10)` | YES |  |  |  | 期刊的影响因子指标。 |
| 26 | `open_access` | `tinyint` | YES |  |  |  | 标识期刊或论文是否为开放获取。 |
| 27 | `scope` | `varchar(20)` | YES |  |  |  | 期刊所属的大类学科领域。 |
| 28 | `scope_zone` | `varchar(20)` | YES |  |  |  | 期刊所属的细分学科领域。 |
| 29 | `warning` | `tinyint` | YES |  |  |  | 标识期刊是否处于预警状态。 |
| 30 | `is_sci` | `tinyint` | YES |  |  |  | 标识期刊是否被 SCI 收录。 |
| 31 | `sub_quartile` | `tinyint` | YES |  |  |  | 期刊在相关评价体系中的分区信息。 |
| 32 | `classify_list` | `mediumtext` | YES |  |  |  | 文献或期刊对应的学科分类编号。 |
| 33 | `updated_time` | `datetime` | NO |  |  |  | 该条数据最近一次更新的时间。 |

## `dwd_zh_paper`

表注释：深势-中文论文详情信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(64)` | NO | PRI |  |  | 文献记录的唯一主键标识。 |
| 2 | `paper_type` | `varchar(255)` | YES |  |  |  | 文献所属出版物的章节名称，栏目等。 |
| 3 | `publication_id` | `bigint` | NO |  |  |  | 关联出版物的id，用于获取期刊详情信息 |
| 4 | `paper_url` | `mediumtext` | YES |  |  |  | 文献数据的原始来源地址。 |
| 5 | `doi` | `varchar(512)` | YES |  |  |  | 论文的唯一标识编码。 |
| 6 | `cover_date_start` | `varchar(255)` | YES |  |  |  | 文献正式发表的日期。 |
| 7 | `ch_name` | `varchar(1024)` | YES |  |  |  | 文献的中文标题名称。 |
| 8 | `ch_abstract` | `mediumtext` | YES |  |  |  | 文献内容的中文摘要信息。 |
| 9 | `keywords` | `mediumtext` | YES |  |  |  | 描述论文主题内容的关键词。 |
| 10 | `volume` | `varchar(128)` | YES |  |  |  | 文献发表所在期刊的卷号。 |
| 11 | `issue` | `varchar(128)` | YES |  |  |  | 文献发表所在期刊的期号。 |
| 12 | `first_page` | `varchar(255)` | YES |  |  |  | 论文在期刊中的起始页码。 |
| 13 | `last_page` | `varchar(255)` | YES |  |  |  | 论文在期刊中的结束页码。 |
| 14 | `reference_nums` | `int` | YES |  |  |  | 论文参考文献的总数量。 |
| 15 | `reference_content` | `mediumtext` | YES |  |  |  | 论文所引用参考文献的具体内容。 |
| 16 | `citation_nums` | `int` | YES |  |  |  | 论文被其他文献引用的数量。 |
| 17 | `citation_content` | `mediumtext` | YES |  |  |  | 引用该论文的相关文献信息。 |
| 18 | `relevant` | `mediumtext` | YES |  |  |  | 与当前文献内容或主题相关的文献信息。 |
| 19 | `authors` | `mediumtext` | YES |  |  |  | 论文作者的结构化id列表。 |

## `ods_zh_journal`

表注释：维普中文报告信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `lngid` | `varchar(50)` | YES |  |  |  |  |
| 2 | `media_c` | `varchar(50)` | YES |  |  |  |  |
| 3 | `media_e` | `varchar(50)` | YES |  |  |  |  |
| 4 | `gch` | `varchar(50)` | YES |  |  |  |  |
| 5 | `gch5` | `varchar(50)` | YES |  |  |  |  |
| 6 | `years` | `int` | YES |  |  |  |  |
| 7 | `vol` | `int` | YES |  |  |  |  |
| 8 | `num` | `int` | YES |  |  |  |  |
| 9 | `title_c` | `text` | YES |  |  |  |  |
| 10 | `title_e` | `text` | YES |  |  |  |  |
| 11 | `keyword_c` | `text` | YES |  |  |  |  |
| 12 | `keyword_e` | `text` | YES |  |  |  |  |
| 13 | `remark_c` | `text` | YES |  |  |  |  |
| 14 | `remark_e` | `text` | YES |  |  |  |  |
| 15 | `firstclass` | `varchar(50)` | YES |  |  |  |  |
| 16 | `class` | `varchar(50)` | YES |  |  |  |  |
| 17 | `beginpage` | `varchar(50)` | YES |  |  |  |  |
| 18 | `endpage` | `varchar(50)` | YES |  |  |  |  |
| 19 | `jumppage` | `varchar(50)` | YES |  |  |  |  |
| 20 | `pagecount` | `int` | YES |  |  |  |  |
| 21 | `firstwriter` | `varchar(50)` | YES |  |  |  |  |
| 22 | `showwriter` | `text` | YES |  |  |  |  |
| 23 | `firstorgan` | `text` | YES |  |  |  |  |
| 24 | `showorgan` | `text` | YES |  |  |  |  |
| 25 | `showwriter_e` | `text` | YES |  |  |  |  |
| 26 | `showorgan_e` | `text` | YES |  |  |  |  |
| 27 | `author_e` | `text` | YES |  |  |  |  |
| 28 | `publishdate` | `int` | YES |  |  |  |  |
| 29 | `doi` | `varchar(50)` | YES |  |  |  |  |
| 30 | `intpdf` | `int` | YES |  |  |  |  |
| 31 | `pdfsize` | `int` | YES |  |  |  |  |
| 32 | `range` | `text` | YES |  |  |  |  |
| 33 | `language` | `int` | YES |  |  |  |  |
| 34 | `type` | `int` | YES |  |  |  |  |
| 35 | `issn` | `varchar(50)` | YES |  |  |  |  |
| 36 | `cnno` | `varchar(50)` | YES |  |  |  |  |
| 37 | `classtypes` | `text` | YES |  |  |  |  |
| 38 | `showclasstypes` | `text` | YES |  |  |  |  |
| 39 | `subject_edu` | `varchar(50)` | YES |  |  |  |  |
| 40 | `corr_author` | `varchar(50)` | YES |  |  |  |  |
| 41 | `fulltextaddress` | `text` | YES |  |  |  |  |
