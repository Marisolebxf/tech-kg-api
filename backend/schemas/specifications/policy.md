# 政策字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `ods_en_policy` | 拓尔思国外政策信息 | 14 | 31 |
| `ods_zh_policy` | 维普国内政策信息 | 0 | 14 |
| `ods_zh_policy_6` | 拓尔思6月政策样例数据 | 207 | 31 |
| `ods_zh_policy_tuoersi` | 拓尔思国内政策信息5月样例数据 | 0 | 21 |

## `ods_en_policy`

表注释：拓尔思国外政策信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `IR_URLTITLE` | `varchar(256)` | YES |  |  |  |  |
| 2 | `SY_URLTITLE` | `varchar(256)` | YES |  |  |  |  |
| 3 | `FY_URLTITLE` | `varchar(256)` | YES |  |  |  |  |
| 4 | `IR_URLTIME` | `varchar(50)` | YES |  |  |  |  |
| 5 | `IR_SITENAME` | `varchar(50)` | YES |  |  |  |  |
| 6 | `SY_MEDIA_PRODUCT_NAME` | `varchar(50)` | YES |  |  |  |  |
| 7 | `IR_CONTENT` | `mediumtext` | YES |  |  |  |  |
| 8 | `SY_CONTENT` | `mediumtext` | YES |  |  |  |  |
| 9 | `FY_CONTENT` | `mediumtext` | YES |  |  |  |  |
| 10 | `IR_ABSTRACT` | `text` | YES |  |  |  |  |
| 11 | `SY_ABSTRACT` | `text` | YES |  |  |  |  |
| 12 | `IR_URLNAME` | `varchar(1024)` | YES |  |  |  |  |
| 13 | `IR_URLDATE` | `varchar(50)` | YES |  |  |  |  |
| 14 | `IR_ATTACHMENT` | `varchar(1024)` | YES |  |  |  |  |
| 15 | `IR_AUTHORS` | `varchar(256)` | YES |  |  |  |  |
| 16 | `IR_CHANNEL` | `varchar(256)` | YES |  |  |  |  |
| 17 | `IR_LANGUAGE` | `varchar(50)` | YES |  |  |  |  |
| 18 | `IR_URLCONTENT` | `mediumtext` | YES |  |  |  |  |
| 19 | `SY_AREA_LIST` | `varchar(256)` | YES |  |  |  |  |
| 20 | `SY_AREA_LIST_CODE` | `varchar(256)` | YES |  |  |  |  |
| 21 | `SY_KEYWORDS` | `varchar(1024)` | YES |  |  |  |  |
| 22 | `SY_MEDIA_AREA` | `varchar(50)` | YES |  |  |  |  |
| 23 | `SY_MEDIA_AREA_CODE` | `varchar(50)` | YES |  |  |  |  |
| 24 | `SY_MEDIA_DIRECT_UNIT` | `varchar(50)` | YES |  |  |  |  |
| 25 | `SY_MEDIA_INDUSTRY` | `varchar(50)` | YES |  |  |  |  |
| 26 | `SY_MEDIA_RANK_CODE` | `varchar(50)` | YES |  |  |  |  |
| 27 | `SY_MEDIA_TAG` | `varchar(50)` | YES |  |  |  |  |
| 28 | `SY_MEDIA_TYPE1` | `varchar(50)` | YES |  |  |  |  |
| 29 | `SY_MEDIA_TYPE2` | `varchar(50)` | YES |  |  |  |  |
| 30 | `SY_MEDIA_TYPE3` | `varchar(50)` | YES |  |  |  |  |
| 31 | `SY_NAME` | `varchar(256)` | YES |  |  |  |  |

## `ods_zh_policy`

表注释：维普国内政策信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `lngid` | `varchar(50)` | YES |  |  |  |  |
| 2 | `centre_level` | `varchar(50)` | YES |  |  |  |  |
| 3 | `district_level` | `varchar(50)` | YES |  |  |  |  |
| 4 | `fulltext` | `text` | YES |  |  |  |  |
| 5 | `industry` | `varchar(50)` | YES |  |  |  |  |
| 6 | `keyword` | `text` | YES |  |  |  |  |
| 7 | `level` | `varchar(50)` | YES |  |  |  |  |
| 8 | `organ` | `varchar(50)` | YES |  |  |  |  |
| 9 | `policy_type` | `varchar(50)` | YES |  |  |  |  |
| 10 | `publish_time` | `varchar(50)` | YES |  |  |  |  |
| 11 | `issued_number` | `varchar(64)` | YES |  |  |  |  |
| 12 | `pub_year` | `varchar(50)` | YES |  |  |  |  |
| 13 | `url` | `text` | YES |  |  |  |  |
| 14 | `title` | `text` | YES |  |  |  |  |

## `ods_zh_policy_6`

表注释：拓尔思6月政策样例数据

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `id` | `varchar(50)` | YES |  |  |  | 唯一id |
| 2 | `data_type` | `varchar(50)` | YES |  |  |  | 数据类型 |
| 3 | `status` | `varchar(50)` | YES |  |  |  | 政策状态（已发布、已撤销） |
| 4 | `title` | `text` | YES |  |  |  | 标题（纯文本） |
| 5 | `title_na` | `text` | YES |  |  |  | 标题（富文本） |
| 6 | `content` | `mediumtext` | YES |  |  |  | 内容 |
| 7 | `url` | `varchar(256)` | YES |  |  |  | 原文链接地址 |
| 8 | `issue_no` | `varchar(50)` | YES |  |  |  | 发文字号 |
| 9 | `index_no` | `varchar(50)` | YES |  |  |  | 索引号 |
| 10 | `site_name` | `varchar(50)` | YES |  |  |  | 站点名称 |
| 11 | `create_time` | `varchar(50)` | YES |  |  |  | 成文日期 |
| 12 | `publish_time` | `varchar(50)` | YES |  |  |  | 发文日期 |
| 13 | `publish_year` | `varchar(50)` | YES |  |  |  | 发布年份 |
| 14 | `area` | `varchar(50)` | YES |  |  |  | 地区 |
| 15 | `area_code` | `varchar(50)` | YES |  |  |  | 地区编码 |
| 16 | `policy_level` | `varchar(50)` | YES |  |  |  | 政策层级 |
| 17 | `region` | `varchar(200)` | YES |  |  |  | 完整地区 |
| 18 | `platform` | `varchar(50)` | YES |  |  |  | 数据来源平台 |
| 19 | `attachments` | `varchar(512)` | YES |  |  |  | 附件 |
| 20 | `keywords` | `varchar(512)` | YES |  |  |  | 关键词 |
| 21 | `abstracts` | `text` | YES |  |  |  | 摘要 |
| 22 | `elements` | `text` | YES |  |  |  | 主旨要素 |
| 23 | `keypoints` | `varchar(1024)` | YES |  |  |  | 政策要点 |
| 24 | `allfactors` | `varchar(1024)` | YES |  |  |  | 扶持要素 |
| 25 | `tags` | `text` | YES |  |  |  | 标签集 |
| 26 | `pedigree` | `varchar(1024)` | YES |  |  |  | 政策谱系 |
| 27 | `content_type` | `varchar(50)` | YES |  |  |  | 内容分类 |
| 28 | `publish_department` | `varchar(50)` | YES |  |  |  | 发文机构 |
| 29 | `region_origin` | `varchar(50)` | YES |  |  |  | 地区原始信息 |
| 30 | `updated_time` | `varchar(50)` | YES |  |  |  | 更新时间 |
| 31 | `industry` | `varchar(200)` | YES |  |  |  | 产业分类 |

## `ods_zh_policy_tuoersi`

表注释：拓尔思国内政策信息5月样例数据

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `title` | `text` | YES |  |  |  |  |
| 2 | `policy_level` | `varchar(100)` | YES |  |  |  |  |
| 3 | `industry_classify` | `varchar(512)` | YES |  |  |  |  |
| 4 | `create_time` | `varchar(50)` | YES |  |  |  |  |
| 5 | `area` | `varchar(100)` | YES |  |  |  |  |
| 6 | `publish_department` | `varchar(100)` | YES |  |  |  |  |
| 7 | `publish_time` | `varchar(50)` | YES |  |  |  |  |
| 8 | `issue_no` | `varchar(100)` | YES |  |  |  |  |
| 9 | `keywords` | `text` | YES |  |  |  |  |
| 10 | `source` | `varchar(100)` | YES |  |  |  |  |
| 11 | `data_type` | `varchar(50)` | YES |  |  |  |  |
| 12 | `index_no` | `varchar(50)` | YES |  |  |  |  |
| 13 | `content_type` | `varchar(50)` | YES |  |  |  |  |
| 14 | `url` | `varchar(256)` | YES |  |  |  |  |
| 15 | `abstract` | `text` | YES |  |  |  |  |
| 16 | `content` | `mediumtext` | YES |  |  |  |  |
| 17 | `content_na` | `mediumtext` | YES |  |  |  |  |
| 18 | `elements` | `varchar(100)` | YES |  |  |  |  |
| 19 | `attachments` | `varchar(512)` | YES |  |  |  |  |
| 20 | `attachment_url` | `varchar(512)` | YES |  |  |  |  |
| 21 | `labels` | `text` | YES |  |  |  |  |
