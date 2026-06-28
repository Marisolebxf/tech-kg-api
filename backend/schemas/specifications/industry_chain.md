# 产业链字段规范

来源数据库：`gkx`
生成日期：`2026-06-25`

| 表名 | 表注释 | 估算行数 | 字段数 |
|---|---|---:|---:|
| `dwd_industry_chain_info` | 产业链图谱 | 180 | 16 |
| `dwd_industry_chain_news_info` | 产业动态资讯 | 461 | 10 |
| `dwd_org_industry_chain_dtl` | 产业关联企业信息 | 2888 | 10 |
| `dwd_org_industry_chain_pat_dtl` | 产业链关联专利信息 | 888 | 14 |
| `dwd_org_industry_chain_prod_dtl` | 产业链企业关联产品信息 | 6080 | 10 |

## `dwd_industry_chain_info`

表注释：产业链图谱

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `chain_code` | `varchar(255)` | YES |  |  |  | 产业链代码 |
| 2 | `chain_name` | `varchar(255)` | YES |  |  |  | 产业链名称 |
| 3 | `node_id` | `varchar(255)` | YES |  |  |  | 节点代码 |
| 4 | `node_name` | `varchar(255)` | YES |  |  |  | 节点名称 |
| 5 | `node_type` | `int` | YES |  |  |  | 节点类型 |
| 6 | `level` | `int` | YES |  |  |  | 节点层级 |
| 7 | `node_seq` | `int` | YES |  |  |  | 节点序号 |
| 8 | `parent_id` | `varchar(255)` | YES |  |  |  | 父级节点代码 |
| 9 | `parent_name` | `varchar(255)` | YES |  |  |  | 父级节点名称 |
| 10 | `node_imp_level` | `int` | YES |  |  |  | 节点重要性等级 |
| 11 | `downstream_lin` | `varchar(255)` | YES |  |  |  | 下游节点代码 |
| 12 | `node_stage` | `int` | YES |  |  |  | 节点环节 |
| 13 | `node_path` | `text` | YES |  |  |  | 节点路径 |
| 14 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 15 | `created_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 16 | `updated_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP | 更新时间 |

## `dwd_industry_chain_news_info`

表注释：产业动态资讯

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `chain_code` | `varchar(255)` | YES |  |  |  | 产业链代码 |
| 2 | `chain_name` | `varchar(255)` | YES |  |  |  | 产业链名称 |
| 3 | `news_id` | `varchar(255)` | YES |  |  |  | 资讯id |
| 4 | `title` | `varchar(255)` | YES |  |  |  | 标题 |
| 5 | `relaese_date` | `date` | YES |  |  |  | 发布时间 |
| 6 | `summary` | `text` | YES |  |  |  | 摘要 |
| 7 | `source` | `varchar(255)` | YES |  |  |  | 来源 |
| 8 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 10 | `updated_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP | 更新时间 |

## `dwd_org_industry_chain_dtl`

表注释：产业关联企业信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `chain_code` | `varchar(255)` | YES |  |  |  | 产业链代码 |
| 2 | `chain_name` | `varchar(255)` | YES |  |  |  | 产业链名称 |
| 3 | `node_id` | `varchar(255)` | YES |  |  |  | 节点代码 |
| 4 | `node_name` | `varchar(255)` | YES |  |  |  | 节点名称 |
| 5 | `antitypic` | `varchar(255)` | YES |  |  |  | 企业id |
| 6 | `credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 7 | `chain_score` | `decimal(20,2)` | YES |  |  |  | 产业链评分 |
| 8 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 10 | `updated_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP | 更新时间 |

## `dwd_org_industry_chain_pat_dtl`

表注释：产业链关联专利信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `chain_code` | `varchar(255)` | YES |  |  |  | 产业链代码 |
| 2 | `chain_name` | `varchar(255)` | YES |  |  |  | 产业链名称 |
| 3 | `node_id` | `varchar(255)` | YES |  |  |  | 节点代码 |
| 4 | `node_name` | `varchar(255)` | YES |  |  |  | 节点名称 |
| 5 | `apno` | `varchar(255)` | YES |  |  |  | 申请号 |
| 6 | `apdt` | `date` | YES |  |  |  | 申请日 |
| 7 | `pat_name` | `varchar(500)` | YES |  |  |  | 专利名称 |
| 8 | `pn` | `varchar(255)` | YES |  |  |  | 公布(公告)号 |
| 9 | `pbdt` | `date` | YES |  |  |  | 公布(公告)日 |
| 10 | `current_assign` | `text` | YES |  |  |  | 申请(专利权)人 |
| 11 | `inventors` | `text` | YES |  |  |  | 发明(设计)人 |
| 12 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 13 | `created_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 14 | `updated_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP | 更新时间 |

## `dwd_org_industry_chain_prod_dtl`

表注释：产业链企业关联产品信息

| 序号 | 字段名 | 类型 | 可空 | 键 | 默认值 | 额外信息 | 字段注释 |
|---:|---|---|---|---|---|---|---|
| 1 | `chain_code` | `varchar(255)` | YES |  |  |  | 产业链代码 |
| 2 | `chain_name` | `varchar(255)` | YES |  |  |  | 产业链名称 |
| 3 | `antitypic` | `varchar(255)` | YES |  |  |  | 企业id |
| 4 | `company_name` | `varchar(500)` | YES |  |  |  | 企业名称 |
| 5 | `credit_code` | `varchar(255)` | YES |  |  |  | 统一社会信用代码 |
| 6 | `tech_product` | `varchar(255)` | YES |  |  |  | 主营产品名称 |
| 7 | `tech_product_s` | `int` | YES |  |  |  | 主营产品排序 |
| 8 | `data_source` | `varchar(255)` | YES |  |  |  | 数据来源 |
| 9 | `created_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED | 创建时间 |
| 10 | `updated_time` | `datetime` | YES |  | CURRENT_TIMESTAMP | DEFAULT_GENERATED on update CURRENT_TIMESTAMP | 更新时间 |
