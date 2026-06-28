# 论文通用字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `dwd_author_affiliation` | 作者-机构关联表 | 1619 | 17 |
| `dwd_author_info` | Scopus作者元数据表 | 0 | 30 |

## `dwd_author_affiliation`

表注释：作者-机构关联表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  | auto_increment | 主键ID |
| 2 | `auid` | `bigint` | NO |  |  |  | 作者ID |
| 3 | `affiliation_id` | `bigint` | YES |  |  |  | 机构ID |
| 4 | `afid` | `bigint` | YES |  |  |  | 机构显示ID |
| 5 | `affiliation_id_parent` | `bigint` | YES |  |  |  | 父机构ID |
| 6 | `preferred_name` | `varchar(500)` | YES |  |  |  | 机构标准名称 |
| 7 | `afdispname` | `varchar(500)` | YES |  |  |  | 机构显示名称 |
| 8 | `sort_name` | `varchar(500)` | YES |  |  |  | 机构排序名称 |
| 9 | `address_part` | `varchar(500)` | YES |  |  |  | 详细地址 |
| 10 | `city` | `varchar(100)` | YES |  |  |  | 城市 |
| 11 | `state` | `varchar(100)` | YES |  |  |  | 州/省份 |
| 12 | `country` | `varchar(100)` | YES |  |  |  | 国家 |
| 13 | `country_tag` | `varchar(32)` | YES |  |  |  | 国家编码 |
| 14 | `postal_code` | `varchar(64)` | YES |  |  |  | 邮政编码 |
| 15 | `type_afid` | `varchar(32)` | YES |  |  |  | 机构类型：dept/parent |
| 16 | `relationship` | `varchar(32)` | YES |  |  |  | 关系：author/derived |
| 17 | `create_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 入库时间 |

## `dwd_author_info`

表注释：Scopus作者元数据表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `bigint` | NO | PRI |  | auto_increment | 主键ID |
| 2 | `auid` | `bigint` | NO | UNI |  |  | 作者唯一ID |
| 3 | `orcid` | `varchar(64)` | YES |  |  |  | ORCID 标识 |
| 4 | `orcid_matching_type` | `varchar(64)` | YES |  |  |  | ORCID匹配类型 |
| 5 | `given_name` | `varchar(255)` | YES |  |  |  | 名 |
| 6 | `surname` | `varchar(255)` | YES |  |  |  | 姓 |
| 7 | `indexed_name` | `varchar(255)` | YES |  |  |  | 索引名称 |
| 8 | `initials` | `varchar(32)` | YES |  |  |  | 姓名缩写 |
| 9 | `alias_status` | `varchar(32)` | YES |  |  |  | 别名状态 |
| 10 | `name_variants` | `varchar(500)` | YES |  |  |  | 姓名别名列表（逗号分隔） |
| 11 | `history_ids` | `varchar(500)` | YES |  |  |  | 历史ID列表（逗号分隔） |
| 12 | `email` | `varchar(255)` | YES |  |  |  | 邮箱 |
| 13 | `email_type` | `varchar(32)` | YES |  |  |  | 邮箱类型 |
| 14 | `asjc_list` | `varchar(500)` | YES |  |  |  | ASJC学科代码列表，逗号分隔 |
| 15 | `asjc_freq_list` | `varchar(500)` | YES |  |  |  | ASJC频次列表，逗号分隔 |
| 16 | `subjabbr_list` | `varchar(500)` | YES |  |  |  | 学科缩写列表，逗号分隔 |
| 17 | `subjabbr_freq_list` | `varchar(500)` | YES |  |  |  | 学科缩写频次，逗号分隔 |
| 18 | `n_affiliation_current` | `int` | YES |  | 0 |  | 当前机构数量 |
| 19 | `current_affiliations` | `varchar(500)` | YES |  |  |  | 当前有效机构ID列表，逗号分隔 |
| 20 | `current_affiliations_parent` | `varchar(500)` | YES |  |  |  | 父机构ID列表，逗号分隔 |
| 21 | `corrupt_xml` | `tinyint` | YES |  | 0 |  | XML文件是否损坏（1=损坏，0=正常） |
| 22 | `xmlsize` | `int` | YES |  |  |  | XML文件大小 |
| 23 | `datetime_max` | `varchar(32)` | YES |  |  |  | 数据最新日期 |
| 24 | `suppress` | `tinyint` | YES |  | 0 |  | 是否隐藏 |
| 25 | `type` | `varchar(32)` | YES |  |  |  | 作者类型 |
| 26 | `curated` | `tinyint` | YES |  | 0 |  | 是否经过人工校准 |
| 27 | `curtype` | `varchar(255)` | YES |  |  |  | 校准类型 |
| 28 | `cur_source` | `varchar(255)` | YES |  |  |  | 校准来源 |
| 29 | `cur_timestamp` | `varchar(255)` | YES |  |  |  | 校准时间戳 |
| 30 | `create_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 入库时间 |
