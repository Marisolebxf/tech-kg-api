# 外文论文字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `dwd_en_author` | 深势-英文文献作者详情信息 | 12930 | 7 |
| `dwd_en_journal` | 深势-英文期刊详情信息 | 1905 | 28 |
| `dwd_en_paper` | 深势-英文论文详情信息 | 990 | 21 |
| `dwd_en_paper_cited_by` | 爱思唯尔外文论文引用关系表 | 227477 | 5 |
| `dwd_en_paper_info` | 爱思唯尔外文文献基础信息 | 9236 | 40 |
| `ods_en_journal` | 万方外文期刊信息 | 708 | 53 |

## `dwd_en_author`

表注释：深势-英文文献作者详情信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(32)` | NO | PRI |  |  | 文献作者的唯一主键 id |
| 2 | `paper_id` | `varchar(64)` | NO |  |  |  | 文献记录的唯一主键标识。 |
| 3 | `en_name` | `varchar(255)` | NO |  |  |  | 文献作者的英文名称 |
| 4 | `zh_name` | `varchar(255)` | YES |  |  |  | 文献作者中文名 |
| 5 | `affiliation` | `mediumtext` | YES |  |  |  | 文献作者地址 |
| 6 | `email` | `mediumtext` | YES |  |  |  | 文献作者email |
| 7 | `correspond` | `tinyint` | YES |  |  |  | 是否为通讯作者。否=0，是=1，未知=Null |

## `dwd_en_journal`

表注释：深势-英文期刊详情信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  | 期刊、会议或预印本记录的唯一标识。 |
| 2 | `issn` | `varchar(16)` | YES |  |  |  | 期刊的国际标准连续出版物编号。 |
| 3 | `zh_name` | `varchar(1024)` | YES |  |  |  | 期刊、顶会或预印本平台的中文名称。 |
| 4 | `en_name` | `varchar(1024)` | YES |  |  |  | 期刊、顶会或预印本平台的英文名称。 |
| 5 | `name_abbr` | `varchar(255)` | YES |  |  |  | 期刊、会议或预印本名称的简称或缩写。 |
| 6 | `publication_type` | `varchar(255)` | YES |  |  |  | 标识出版载体的类型，如期刊、会议或预印本等。journal，conference |
| 7 | `en_description` | `mediumtext` | YES |  |  |  | 期刊、会议或预印本平台的英文简介或说明。 |
| 8 | `establish_time` | `int` | YES |  |  |  | 期刊首次创办或发行的时间。 |
| 9 | `language` | `varchar(255)` | YES |  |  |  | 文献或期刊出版使用的语言类型。 |
| 10 | `country` | `varchar(255)` | YES |  |  |  | 期刊、会议或出版机构所属的国家或地区。 |
| 11 | `eissn` | `varchar(16)` | YES |  |  |  | 期刊电子版的国际标准连续出版物编号。 |
| 12 | `annual_publication` | `int` | YES |  |  |  | 期刊或会议每年发表文章的数量。 |
| 13 | `review` | `tinyint` | YES |  |  |  | 标识该期刊是否为综述类期刊。否=0，是=1，未知=2 |
| 14 | `impact_factor` | `decimal(20,10)` | YES |  |  |  | 期刊或会议的影响力评价指标。 |
| 15 | `jcr_zone` | `varchar(2)` | YES |  |  |  | 期刊在 JCR 等评价体系中的分区信息。Q1,Q2,Q3,Q4 |
| 16 | `open_access` | `tinyint` | YES |  |  |  | 标识期刊或论文是否为开放获取。否=0，是=1，未知=2 |
| 17 | `review_period` | `varchar(255)` | YES |  |  |  | 期刊从投稿到审稿完成的平均周期。 |
| 18 | `scope` | `varchar(20)` | YES |  |  |  | 期刊或会议所属的大类学科领域。 |
| 19 | `sub_scope` | `varchar(20)` | YES |  |  |  | 期刊或会议所属的细分学科主题。 |
| 20 | `self_rate` | `decimal(20,10)` | YES |  |  |  | 期刊文献中自我引用所占的比例。 |
| 21 | `top` | `tinyint` | YES |  |  |  | 标识期刊或会议是否为所在领域的顶级刊物。否=0，是=1 |
| 22 | `warning` | `tinyint` | YES |  |  |  | 标识期刊是否处于预警状态。否=0，是=1，未知=Null |
| 23 | `is_sci` | `tinyint` | YES |  |  |  | 标识期刊是否被 SCI 收录。否=0，是=1，未知=Null |
| 24 | `publish_period` | `varchar(64)` | YES |  |  |  | 期刊的出版频率或发行周期。 |
| 25 | `jn_official` | `mediumtext` | YES |  |  |  | 期刊官方网站地址。 |
| 26 | `layout_cost` | `varchar(15)` | YES |  |  |  | 期刊发表论文所需的版面费用。 |
| 27 | `paper_nums` | `int` | YES |  |  |  | 期刊、会议或平台已发表论文的数量。 |
| 28 | `updated_time` | `datetime` | NO |  |  |  | 该条数据最近一次更新的时间。 |

## `dwd_en_paper`

表注释：深势-英文论文详情信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(64)` | NO | PRI |  |  | 文献记录的唯一主键标识。 |
| 2 | `publisher` | `varchar(1024)` | YES |  |  |  | 文献或期刊所属的出版商信息。 |
| 3 | `publication_id` | `bigint` | NO |  |  |  | 关联出版物的id，用于获取期刊详情信息 |
| 4 | `paper_type` | `varchar(255)` | YES |  |  |  | 文献所属出版物的章节名称，栏目等。 |
| 5 | `paper_url` | `mediumtext` | YES |  |  |  | 文献在官网或来源平台中的访问链接。 |
| 6 | `doi` | `varchar(512)` | NO | UNI |  |  | 论文的唯一标识编码。 |
| 7 | `cover_date_start` | `varchar(255)` | YES |  |  |  | 文献正式发表的时间。 |
| 8 | `funds` | `mediumtext` | YES |  |  |  | 支持该论文研究的基金或资助项目信息。 |
| 9 | `en_name` | `varchar(1024)` | YES |  |  |  | 文献的英文标题名称。 |
| 10 | `en_abstract` | `mediumtext` | YES |  |  |  | 文献内容的英文摘要信息。 |
| 11 | `keywords` | `mediumtext` | YES |  |  |  | 描述论文主题内容的关键词。 |
| 12 | `volume` | `varchar(128)` | YES |  |  |  | 文献发表所在期刊的卷号。 |
| 13 | `issue` | `varchar(128)` | YES |  |  |  | 文献发表所在期刊的期号。 |
| 14 | `first_page` | `varchar(255)` | YES |  |  |  | 论文在期刊中的起始页码。 |
| 15 | `last_page` | `varchar(255)` | YES |  |  |  | 论文在期刊中的结束页码。 |
| 16 | `reference_nums` | `int` | YES |  |  |  | 论文参考文献的总数量。 |
| 17 | `reference_content` | `mediumtext` | YES |  |  |  | 论文所引用参考文献的具体内容。 |
| 18 | `citation_nums` | `int` | YES |  |  |  | 论文被其他文献引用的数量。 |
| 19 | `citation_content` | `mediumtext` | YES |  |  |  | 引用该论文的相关文献信息。 |
| 20 | `relevant` | `mediumtext` | YES |  |  |  | 与当前文献内容或主题相关的文献信息。 |
| 21 | `authors` | `mediumtext` | YES |  |  |  | 论文作者的结构化id列表。 |

## `dwd_en_paper_cited_by`

表注释：爱思唯尔外文论文引用关系表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  | auto_increment | 主键ID |
| 2 | `paper_eid` | `varchar(64)` | NO | MUL |  |  | 被引文献EID（指向dwd_paper_info_qh.eid） |
| 3 | `citing_eid` | `varchar(64)` | NO |  |  |  | 引用文献EID |
| 4 | `citing_year` | `int` | YES |  |  |  | 引用文献发表年份 |
| 5 | `create_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 记录创建时间 |

## `dwd_en_paper_info`

表注释：爱思唯尔外文文献基础信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  | auto_increment | 自增主键ID |
| 2 | `eid` | `varchar(64)` | NO | UNI |  |  | Scopus文献唯一标识 |
| 3 | `doi` | `varchar(128)` | YES |  |  |  | 文献数字对象唯一标识符 |
| 4 | `online_status` | `varchar(32)` | YES |  |  |  | 文献在线状态 |
| 5 | `pui` | `varchar(64)` | YES |  |  |  | 出版商唯一标识 |
| 6 | `sdfullavail` | `tinyint` | YES |  | 0 |  | 全文可获取状态，0-不可获取，1-可获取 |
| 7 | `issn` | `varchar(32)` | YES |  |  |  | 期刊国际标准刊号 |
| 8 | `volume` | `varchar(16)` | YES |  |  |  | 期刊卷号 |
| 9 | `issue` | `varchar(16)` | YES |  |  |  | 期刊期号 |
| 10 | `first_page` | `varchar(16)` | YES |  |  |  | 文献起始页码 |
| 11 | `last_page` | `varchar(16)` | YES |  |  |  | 文献结束页码 |
| 12 | `sort_year` | `int` | YES |  |  |  | 数据排序年份 |
| 13 | `sort_yyyymm` | `varchar(8)` | YES |  |  |  | 数据排序年月 |
| 14 | `pub_year` | `int` | YES |  |  |  | 文献正式出版年份 |
| 15 | `timestamp` | `datetime` | YES |  |  |  | 文献数据更新时间戳 |
| 16 | `orig_load_date` | `date` | YES |  |  |  | 数据原始入库日期 |
| 17 | `datesort` | `varchar(16)` | YES |  |  |  | 日期排序字符串 |
| 18 | `indexeddate` | `datetime` | YES |  |  |  | Scopus索引收录时间 |
| 19 | `absavail` | `tinyint` | YES |  | 0 |  | 摘要可获取状态，0-不可获取，1-可获取 |
| 20 | `suppressdummy` | `varchar(16)` | YES |  | no |  | 是否隐藏虚拟数据 |
| 21 | `srctype` | `char(1)` | YES |  |  |  | 文献来源类型，j-期刊 |
| 22 | `subj_area` | `varchar(255)` | YES |  |  |  | 文献所属学科领域，多学科逗号分隔 |
| 23 | `srctitle` | `varchar(512)` | YES |  |  |  | 期刊来源全称 |
| 24 | `country` | `varchar(64)` | YES |  |  |  | 文献所属国家 |
| 25 | `language` | `varchar(64)` | YES |  |  |  | 文献语种 |
| 26 | `is_open_access` | `tinyint` | YES |  | 0 |  | 是否开放获取，0-否，1-是 |
| 27 | `oa_article_status` | `varchar(64)` | YES |  |  |  | 开放获取状态描述 |
| 28 | `doctype` | `varchar(16)` | YES |  |  |  | 文献文档类型 |
| 29 | `group_id` | `varchar(64)` | YES |  |  |  | 文献分组ID |
| 30 | `author_count` | `int` | YES |  | 0 |  | 文献作者总数量 |
| 31 | `author_list` | `text` | YES |  |  |  | 作者完整信息列表，多作者分号分隔，含姓名、职称、作者ID等 |
| 32 | `author_surname` | `varchar(64)` | YES |  |  |  | 第一作者姓氏 |
| 33 | `author_initials` | `varchar(32)` | YES |  |  |  | 第一作者首字母缩写 |
| 34 | `author_id` | `varchar(64)` | YES |  |  |  | 作者唯一标识 |
| 35 | `title` | `varchar(1024)` | YES |  |  |  | 文献中文/英文标题 |
| 36 | `source_id` | `varchar(64)` | YES |  |  |  | 期刊来源唯一ID |
| 37 | `source_title_abbrev` | `varchar(512)` | YES |  |  |  | 期刊来源简称 |
| 38 | `asjc_code` | `varchar(255)` | YES |  |  |  | ASJC学科分类编码，多编码逗号分隔 |
| 39 | `cited_by_count` | `int` | YES |  | 0 |  | 被引用次数 |
| 40 | `create_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 数据入库时间 |

## `ods_en_journal`

表注释：万方外文期刊信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `F_ID` | `varchar(50)` | YES |  |  |  |  |
| 2 | `F_PaperID` | `text` | YES |  |  |  |  |
| 3 | `F_Title` | `text` | YES |  |  |  |  |
| 4 | `F_title_alternative` | `text` | YES |  |  |  |  |
| 5 | `F_abbrev_title` | `text` | YES |  |  |  |  |
| 6 | `F_author` | `text` | YES |  |  |  |  |
| 7 | `F_author_alternative` | `text` | YES |  |  |  |  |
| 8 | `F_affiliation` | `text` | YES |  |  |  |  |
| 9 | `F_affiliation_alternative` | `text` | YES |  |  |  |  |
| 10 | `F_Abstract` | `text` | YES |  |  |  |  |
| 11 | `F_Abstract_alternative` | `text` | YES |  |  |  |  |
| 12 | `F_Keyword` | `text` | YES |  |  |  |  |
| 13 | `F_Keyword_alternative` | `text` | YES |  |  |  |  |
| 14 | `F_Language` | `text` | YES |  |  |  |  |
| 15 | `F_Other_language` | `text` | YES |  |  |  |  |
| 16 | `F_year` | `varchar(10)` | YES |  |  |  |  |
| 17 | `F_volume` | `varchar(10)` | YES |  |  |  |  |
| 18 | `F_issue` | `varchar(10)` | YES |  |  |  |  |
| 19 | `F_Paper_type` | `varchar(50)` | YES |  |  |  |  |
| 20 | `F_Classification` | `text` | YES |  |  |  |  |
| 21 | `F_DOI` | `varchar(50)` | YES |  |  |  |  |
| 22 | `F_Start_page` | `varchar(10)` | YES |  |  |  |  |
| 23 | `F_End_page` | `varchar(10)` | YES |  |  |  |  |
| 24 | `F_page` | `varchar(50)` | YES |  |  |  |  |
| 25 | `F_Total_page_number` | `varchar(10)` | YES |  |  |  |  |
| 26 | `F_Journal` | `text` | YES |  |  |  |  |
| 27 | `F_Journal_alternative` | `text` | YES |  |  |  |  |
| 28 | `F_journal_abbrev` | `text` | YES |  |  |  |  |
| 29 | `F_journal_id` | `text` | YES |  |  |  |  |
| 30 | `F_ISSNp` | `varchar(50)` | YES |  |  |  |  |
| 31 | `F_ISSNe` | `varchar(50)` | YES |  |  |  |  |
| 32 | `F_DateReceived` | `varchar(50)` | YES |  |  |  |  |
| 33 | `F_DateSubmitted` | `varchar(50)` | YES |  |  |  |  |
| 34 | `F_DatePublish` | `varchar(50)` | YES |  |  |  |  |
| 35 | `F_DateRevision` | `varchar(50)` | YES |  |  |  |  |
| 36 | `F_Updatedtime` | `varchar(50)` | YES |  |  |  |  |
| 37 | `F_Content` | `text` | YES |  |  |  |  |
| 38 | `F_Subject` | `text` | YES |  |  |  |  |
| 39 | `F_column` | `text` | YES |  |  |  |  |
| 40 | `F_column_alternative` | `text` | YES |  |  |  |  |
| 41 | `F_AbstractUrl` | `text` | YES |  |  |  |  |
| 42 | `F_FulltextUrl` | `text` | YES |  |  |  |  |
| 43 | `F_PaperUrlContent` | `text` | YES |  |  |  |  |
| 44 | `F_issue_url` | `text` | YES |  |  |  |  |
| 45 | `F_journal_url` | `text` | YES |  |  |  |  |
| 46 | `yn_free` | `text` | YES |  |  |  |  |
| 47 | `F_Fund` | `text` | YES |  |  |  |  |
| 48 | `F_Fundid` | `text` | YES |  |  |  |  |
| 49 | `F_Fundaffiliation` | `text` | YES |  |  |  |  |
| 50 | `F_refrences` | `text` | YES |  |  |  |  |
| 51 | `F_publiser` | `text` | YES |  |  |  |  |
| 52 | `F_batchid` | `text` | YES |  |  |  |  |
| 53 | `F_article_id` | `text` | YES |  |  |  |  |
