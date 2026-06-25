# 人才专家字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `dwd_scholar` | 深势-学者表 | 1551 | 20 |
| `dwd_scholar_coauthor` | 深势-学者合作者关系表 | 154140 | 13 |
| `dwd_scholar_paper_relation` | 深势-学者论文关系表 | 342878 | 11 |
| `dwd_scholar_papers` | 深势-论文信息表 | 256767 | 13 |
| `dwd_scholar_research_direction` | 深势-学者研究方向表 | 2044 | 5 |
| `dwd_scholar_talent_flag` | 深势-学者人才标签表 | 2000 | 5 |

## `dwd_scholar`

表注释：深势-学者表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  | 主键 |
| 2 | `scholar_id` | `varchar(32)` | NO |  |  |  | 学者id |
| 3 | `name_en` | `varchar(128)` | NO |  |  |  | 英文姓名 |
| 4 | `name_zh` | `varchar(128)` | NO |  |  |  | 中文姓名 |
| 5 | `avatar` | `varchar(256)` | NO |  |  |  | 头像 |
| 6 | `scholar_org_name_en` | `text` | YES |  |  |  | 英文机构 |
| 7 | `scholar_org_name_zh` | `varchar(1024)` | YES |  |  |  | 中文机构 |
| 8 | `scholar_org_id` | `varchar(64)` | YES |  |  |  | 所属机构id，学者所属机构id |
| 9 | `bio` | `mediumtext` | YES |  |  |  | 个人简介/学术简介，学者的个人或学术简介信息 |
| 10 | `bio_zh` | `mediumtext` | YES |  |  |  | 个人简介/学术简介（中文），学者的中文个人或学术简介信息 |
| 11 | `work_experience_en` | `mediumtext` | YES |  |  |  | 工作经历英文（包含机构和职务） |
| 12 | `work_experience_zh` | `mediumtext` | YES |  |  |  | 工作经历中文（包含机构和职务） |
| 13 | `education_background_en` | `mediumtext` | YES |  |  |  | 教育背景（英文），学者的英文教育经历信息 |
| 14 | `education_background_zh` | `mediumtext` | YES |  |  |  | 教育背景（中文），学者的中文教育经历信息 |
| 15 | `paper_nums` | `int` | NO |  | 0 |  | 论文数量 |
| 16 | `citation_nums` | `int` | NO |  | 0 |  | 被引数量 |
| 17 | `h_index` | `int` | NO |  | 0 |  | H指数 |
| 18 | `status` | `int` | NO |  | 1 |  | 状态：0:无效,1:有效 |
| 19 | `create_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 20 | `update_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 记录最后更新时间 |

## `dwd_scholar_coauthor`

表注释：深势-学者合作者关系表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  | 自增主键ID |
| 2 | `scholar_id` | `varchar(32)` | NO |  |  |  | 学者ID，当前学者记录的业务唯一标识 |
| 3 | `co_scholar_id` | `varchar(32)` | NO |  |  |  | 合作学者ID，合作学者记录的业务唯一标识 |
| 4 | `co_scholar_name_en` | `varchar(256)` | YES |  |  |  | 合作学者英文名 |
| 5 | `co_scholar_name_zh` | `varchar(128)` | YES |  |  |  | 合作学者中文名 |
| 6 | `co_scholar_avatar` | `varchar(512)` | YES |  |  |  | 合作学者头像URL |
| 7 | `co_scholar_org_name_en` | `text` | YES |  |  |  | 合作学者所属机构英文名 |
| 8 | `co_scholar_org_name_zh` | `varchar(1024)` | YES |  |  |  | 合作学者所属机构中文名 |
| 9 | `co_scholar_org_id` | `varchar(64)` | YES |  |  |  | 合作学者所属机构ID |
| 10 | `co_paper_count` | `int` | NO |  | 0 |  | 合作论文数量 |
| 11 | `status` | `int` | NO |  | 1 |  | 状态：0:无效,1:有效 |
| 12 | `create_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 记录创建时间 |
| 13 | `update_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 记录最后更新时间 |

## `dwd_scholar_paper_relation`

表注释：深势-学者论文关系表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  | 主键 |
| 2 | `paper_id` | `bigint` | NO |  | 0 |  | 论文id |
| 3 | `related_paper_id` | `bigint` | YES |  |  |  | 关联论文库的唯一标识 |
| 4 | `year` | `bigint` | NO |  | 0 |  | 论文发表年份 |
| 5 | `scholar_id` | `varchar(32)` | NO |  |  |  | 学者id |
| 6 | `citations` | `int` | NO |  | 0 |  | 被引用次数 |
| 7 | `publish_time` | `datetime` | YES |  |  |  | 发布时间 |
| 8 | `status` | `int` | NO |  | 1 |  | 状态：0:无效,1:有效 |
| 9 | `create_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 10 | `update_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 记录最后更新时间 |
| 11 | `publication_id` | `bigint` | NO |  | 0 |  | 期刊id |

## `dwd_scholar_papers`

表注释：深势-论文信息表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  |  |
| 2 | `zh_name` | `varchar(500)` | NO |  |  |  | 中文题目 |
| 3 | `en_name` | `varchar(500)` | NO |  |  |  | 英文题目 |
| 4 | `authors` | `mediumtext` | YES |  |  |  | 作者列表 |
| 5 | `paper_url` | `varchar(1024)` | NO |  |  |  | 论文原始链接 |
| 6 | `cover_date_start` | `datetime` | YES |  |  |  | 发表时间 |
| 7 | `create_time` | `datetime` | YES |  |  |  | 创建时间 |
| 8 | `update_time` | `datetime` | YES |  |  |  | 记录最后更新时间 |
| 9 | `status` | `tinyint` | YES |  | 1 |  | 状态：0:无效,1:有效 |
| 10 | `zh_abstract` | `mediumtext` | YES |  |  |  | 中文摘要 |
| 11 | `en_abstract` | `mediumtext` | YES |  |  |  | 英文摘要 |
| 12 | `doi` | `varchar(512)` | NO |  |  |  |  |
| 13 | `publication_en_name` | `varchar(1024)` | NO |  | 期刊/会议英文名 |  |  |

## `dwd_scholar_research_direction`

表注释：深势-学者研究方向表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  | 逻辑ID |
| 2 | `scholar_id` | `varchar(32)` | NO | UNI |  |  | 学者ID |
| 3 | `fields` | `mediumtext` | YES |  |  |  | 研究方向 |
| 4 | `create_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 5 | `update_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 记录最后更新时间 |

## `dwd_scholar_talent_flag`

表注释：深势-学者人才标签表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  |  | 逻辑ID |
| 2 | `scholar_id` | `varchar(32)` | NO | UNI |  |  | 学者ID |
| 3 | `academician` | `int` | NO |  | 0 |  | 是否为院士：0:否,1:是 |
| 4 | `create_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 5 | `update_time` | `datetime` | NO |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 记录最后更新时间 |
