# 国外机构字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `dwd_forg_agg_identifier` | 国外企业代码表 | 3232 | 6 |
| `dwd_forg_base_info` | 国外企业基本信息表 | 1000 | 13 |
| `dwd_forg_beneficiary_info` | 国外企业受益人表 | 5865 | 7 |
| `dwd_forg_contact` | 国外企业联系方式表 | 999 | 5 |
| `dwd_forg_executive_info` | 国外企业高管表 | 4731 | 8 |
| `dwd_forg_industry` | 国外企业行业分类表 | 7674 | 5 |
| `dwd_forg_investment` | 国外企业子公司情况表 | 12523 | 5 |
| `dwd_forg_profile` | 国外企业简介表 | 934 | 3 |
| `dwd_forg_shareholder` | 国外企业股东表 | 20670 | 6 |
| `dwd_forg_ultimate_control` | 国外企业实控人表 | 1027 | 5 |

## `dwd_forg_agg_identifier`

表注释：国外企业代码表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `code_category` | `varchar(100)` | YES |  |  |  | 代码大类 |
| 3 | `code_subcategory` | `varchar(100)` | YES |  |  |  | 代码小类 |
| 4 | `code_cn_name` | `varchar(255)` | YES |  |  |  | 代码中文名称 |
| 5 | `code_name` | `varchar(255)` | YES |  |  |  | 代码名称 |
| 6 | `code_value` | `varchar(255)` | YES |  |  |  | 代码值 |

## `dwd_forg_base_info`

表注释：国外企业基本信息表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `ename_local` | `varchar(500)` | YES |  |  |  | 企业名称（本地语种） |
| 3 | `ename_pv` | `varchar(500)` | YES |  |  |  | 曾用名 |
| 4 | `ipo_status` | `varchar(50)` | YES |  |  |  | 企业状态 |
| 5 | `employees_num` | `varchar(255)` | YES |  |  |  | 员工人数 |
| 6 | `start_year` | `varchar(50)` | YES |  |  |  | 成立年份 |
| 7 | `start_date` | `varchar(50)` | YES |  |  |  | 成立日期 |
| 8 | `address` | `varchar(255)` | YES |  |  |  | 国家或地区 |
| 9 | `reg_city` | `varchar(255)` | YES |  |  |  | 城市 |
| 10 | `address1` | `varchar(255)` | YES |  |  |  | 地址第1行 |
| 11 | `address2` | `varchar(255)` | YES |  |  |  | 地址第2行 |
| 12 | `address3` | `varchar(255)` | YES |  |  |  | 地址第3行 |
| 13 | `address4` | `varchar(255)` | YES |  |  |  | 地址第4行 |

## `dwd_forg_beneficiary_info`

表注释：国外企业受益人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `bo_name` | `varchar(500)` | YES |  |  |  | 受益人名称 |
| 3 | `bo_gender` | `varchar(255)` | YES |  |  |  | 受益人性别 |
| 4 | `bo_birthdate` | `varchar(255)` | YES |  |  |  | 受益人出生日期 |
| 5 | `bo_country_code` | `varchar(255)` | YES |  |  |  | 受益人所在国家代码 |
| 6 | `bo_manager` | `varchar(255)` | YES |  |  |  | 受益人是否同时是管理层 |
| 7 | `path` | `text` | YES |  |  |  | 路径 |

## `dwd_forg_contact`

表注释：国外企业联系方式表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `phone` | `varchar(255)` | YES |  |  |  | 电话 |
| 3 | `domain` | `varchar(255)` | YES |  |  |  | 域名 |
| 4 | `website` | `varchar(255)` | YES |  |  |  | 网址 |
| 5 | `email` | `varchar(255)` | YES |  |  |  | 邮箱 |

## `dwd_forg_executive_info`

表注释：国外企业高管表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `executives_name` | `varchar(500)` | YES |  |  |  | 高管名称 |
| 3 | `dm_age` | `varchar(200)` | YES |  |  |  | 高管年龄 |
| 4 | `dm_sex` | `varchar(500)` | YES |  |  |  | 高管性别 |
| 5 | `executives_position` | `varchar(500)` | YES |  |  |  | 高管职位 |
| 6 | `dm_birthdate` | `varchar(500)` | YES |  |  |  | 高管出生日期 |
| 7 | `dm_nationalities` | `varchar(500)` | YES |  |  |  | 高管国籍 |
| 8 | `dm_biography` | `text` | YES |  |  |  | 高管履历 |

## `dwd_forg_industry`

表注释：国外企业行业分类表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `industry_type` | `varchar(255)` | YES |  |  |  | 行业分类标准 |
| 3 | `industry_level` | `varchar(255)` | YES |  |  |  | 行业分类层级 |
| 4 | `industry_code` | `varchar(255)` | YES |  |  |  | 行业代码 |
| 5 | `industry_label_cn` | `varchar(500)` | YES |  |  |  | 行业描述 |

## `dwd_forg_investment`

表注释：国外企业子公司情况表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `invested_name` | `varchar(500)` | YES |  |  |  | 子公司名称 |
| 3 | `invested_eid` | `varchar(32)` | YES |  |  |  | 子公司国家代码 |
| 4 | `direct_pct` | `varchar(255)` | YES |  |  |  | 直接持股比例（%） |
| 5 | `total_pct` | `varchar(255)` | YES |  |  |  | 总持股比例（%） |

## `dwd_forg_profile`

表注释：国外企业简介表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(1000)` | YES |  |  |  | 企业英文名称 |
| 2 | `business_desc` | `varchar(2000)` | YES |  |  |  | 业务简介 |
| 3 | `products_services` | `varchar(2000)` | YES |  |  |  | 主要产品与服务 |

## `dwd_forg_shareholder`

表注释：国外企业股东表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `sh_name` | `varchar(255)` | YES |  |  |  | 股东名称 |
| 3 | `sh_entity_type` | `varchar(255)` | YES |  |  |  | 股东类型 |
| 4 | `sh_country_code` | `varchar(255)` | YES |  |  |  | 股东所在国家代码 |
| 5 | `sh_direct_pct` | `varchar(50)` | YES |  |  |  | 股东直接持股比例（%） |
| 6 | `sh_total_pct` | `varchar(50)` | YES |  |  |  | 股东总持股比例（%） |

## `dwd_forg_ultimate_control`

表注释：国外企业实控人表

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `ename_en` | `varchar(500)` | YES |  |  |  | 企业英文名称 |
| 2 | `entity_name` | `varchar(255)` | YES |  |  |  | 实控人名称 |
| 3 | `entity_country_code` | `varchar(32)` | YES |  |  |  | 实控人国家代码 |
| 4 | `direct_pct` | `varchar(255)` | YES |  |  |  | 实控人直接持股比例（%） |
| 5 | `total_pct` | `varchar(255)` | YES |  |  |  | 实控人总持股比例（%） |
