# 国内机构、国外机构要素库 → TRSGraph 图谱详细映射

> 本文档由 `gkx_element` 当前数据库 `information_schema` 自动生成，覆盖 39 张表及其每一个物理字段。

## 一、统一建模约定

- 国内与国外机构统一为 `Organization`，通过 `org_kind` 区分国内机构、高校、科研院所、港澳台企业和海外机构。
- `Organization` VID 优先为 `org_{org_id}`；超过 dev 空间 `FIXED_STRING(64)` 限制时截断并附加 MD5。Person 按规范化姓名 MD5，Event 按表名与稳定业务键生成。
- 全部节点写入 `source_system/source_table/source_record_id/ingest_batch/ingest_time/source_update_time`；源表全部字段还会进入 `extra_json`，因此未升格为本体属性的字段也不会丢失。
- 物理 DWD 表建为 `DataSource`，业务节点通过 `SOURCED_FROM` 指向它；`data_source` 是真实上游表名时，创建 `原始 DataSource -[DERIVED_FROM]-> DWD DataSource`。
- 关系方向：`Person/Organization -[LEGAL_REP_OF|SHAREHOLDER_OF|EXECUTIVE_OF|BENEFICIAL_OWNER_OF|ACTUAL_CONTROLLER_OF]-> Organization`；`Organization -[INVESTS_IN|ACQUIRES|SUBSIDIARY_OF]-> Organization`；`Organization -[HAS_NEWS]-> News`；`Organization -[INVOLVED_IN]-> Event`。
- 幂等规则：节点 VID、边 rank 均确定性生成；同一源数据重复执行覆盖同一节点/同一条边，不产生重复结构。

## 二、与旧 mapping.md 的名称校正

- `dwd_org_reg_info` 以当前库实际表 `dwd_org_base_info` 为准。
- `dwd_org_hels_info` 以当前库实际表 `dwd_org_heis_info` 为准。
- 旧 `dwd_org_bid_info` 拆分为 `dwd_bid_base_out`、`dwd_bid_win_candidate_out`、`dwd_bid_purchase_agency_out`、`dwd_bid_target_item_out`。
- `DERIVED_FROM` 方向以 ontology.md 为准：原始数据源指向加工后的要素数据源。

## 三、逐表逐字段映射

### 1. `dwd_org_base_info` — 机构基本信息

- 所属领域：国内机构要素库
- 数据库表注释：机构基本信息
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `province` | `varchar(255)` | YES | 所在省份/varchar(255) | Organization.province | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `city` | `varchar(255)` | YES | 所在城市/varchar(255) | Organization.city | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `area` | `varchar(255)` | YES | 所在区县/varchar(255) | Organization.area | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `address` | `text` | YES | 公司地址/text | Organization.address | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `addr_lng` | `varchar(255)` | YES | 地址对应经度/varchar(255) | Organization.extra_json.addr_lng | 本体无独立属性，原样保留以避免信息丢失 |
| `addr_lat` | `varchar(255)` | YES | 地址对应维度/varchar(255) | Organization.extra_json.addr_lat | 本体无独立属性，原样保留以避免信息丢失 |
| `postal_code` | `varchar(255)` | YES | 邮政编码/varchar(255) | Organization.postal_code | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `email` | `text` | YES | 电子邮箱/text | Organization.email | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `lerep` | `varchar(255)` | YES | 法定代表人/varchar(255) | Organization.legal_rep；并创建 Person -[LEGAL_REP_OF]-> Organization | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `reg_status` | `varchar(255)` | YES | 登记状态/varchar(255) | Organization.extra_json.reg_status | 本体无独立属性，原样保留以避免信息丢失 |
| `registration_org` | `varchar(255)` | YES | 登记机关/varchar(255) | Organization.extra_json.registration_org | 本体无独立属性，原样保留以避免信息丢失 |
| `incorporation_year` | `decimal(20,0)` | YES | 成立年份/decimal(20,0) | Organization.founded_year（转 int） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `incorporation_date` | `datetime` | YES | 成立日期/datetime | Organization.extra_json.incorporation_date | 本体无独立属性，原样保留以避免信息丢失 |
| `start_date` | `varchar(255)` | YES | 经营期限自/varchar(255) | Organization.extra_json.start_date | 本体无独立属性，原样保留以避免信息丢失 |
| `end_date` | `varchar(255)` | YES | 经营期限至/varchar(255) | Organization.extra_json.end_date | 本体无独立属性，原样保留以避免信息丢失 |
| `org_type` | `varchar(255)` | YES | 机构类型/varchar(255) | Organization.org_type | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `listing_status` | `varchar(255)` | YES | 上市状态/varchar(255) | Organization.listing_status | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `listing_date` | `datetime` | YES | 上市日期/datetime | Organization.listed_date | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `registered_capital_value` | `decimal(20,2)` | YES | 注册资本(本币元)/decimal(20,2) | Organization.registered_capital（去除单位后转 double） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `capital_currency` | `varchar(255)` | YES | 币种/varchar(255) | Organization.capital_currency | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `industry` | `varchar(255)` | YES | 最深一级的行业名称/varchar(255) | Organization.industry_class | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `industry_l1_name` | `varchar(255)` | YES | 一级行业名称/varchar(255) | Organization.extra_json.industry_l1_name | 本体无独立属性，原样保留以避免信息丢失 |
| `industry_l1_code` | `varchar(255)` | YES | 一级行业编码/varchar(255) | Organization.extra_json.industry_l1_code | 本体无独立属性，原样保留以避免信息丢失 |
| `industry_l2_name` | `varchar(255)` | YES | 二级行业名称/varchar(255) | Organization.extra_json.industry_l2_name | 本体无独立属性，原样保留以避免信息丢失 |
| `industry_l2_code` | `varchar(255)` | YES | 二级行业编码/varchar(255) | Organization.extra_json.industry_l2_code | 本体无独立属性，原样保留以避免信息丢失 |
| `industry_l3_name` | `varchar(255)` | YES | 三级行业名称/varchar(255) | Organization.extra_json.industry_l3_name | 本体无独立属性，原样保留以避免信息丢失 |
| `industry_l3_code` | `varchar(255)` | YES | 三级行业编码/varchar(255) | Organization.extra_json.industry_l3_code | 本体无独立属性，原样保留以避免信息丢失 |
| `industry_l4_name` | `varchar(255)` | YES | 四级行业名称/varchar(255) | Organization.extra_json.industry_l4_name | 本体无独立属性，原样保留以避免信息丢失 |
| `industry_l4_code` | `varchar(255)` | YES | 四级行业编码/varchar(255) | Organization.extra_json.industry_l4_code | 本体无独立属性，原样保留以避免信息丢失 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 2. `dwd_org_heis_info` — 高校基本信息

- 所属领域：国内机构要素库
- 数据库表注释：高校基本信息
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_cn` | `varchar(255)` | NO | 学校名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `school_code` | `varchar(255)` | NO | 学校标识码/varchar(255) | Organization.external_id（同时保留在 extra_json） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_en` | `varchar(255)` | YES | 学校英文名称/varchar(255) | Organization.name_en | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `est_year` | `decimal(20,0)` | YES | 建立时间/decimal(20,0) | Organization.founded_year（转 int） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `address` | `text` | YES | 学校地址/text | Organization.address | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `addr_lng` | `varchar(255)` | YES | 地址对应经度/varchar(255) | Organization.extra_json.addr_lng | 本体无独立属性，原样保留以避免信息丢失 |
| `addr_lat` | `varchar(255)` | YES | 地址对应维度/varchar(255) | Organization.extra_json.addr_lat | 本体无独立属性，原样保留以避免信息丢失 |
| `province` | `varchar(255)` | YES | 地址所在省/varchar(255) | Organization.province | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `city` | `varchar(255)` | YES | 地址所在市/varchar(255) | Organization.city | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `area` | `varchar(255)` | YES | 地址所在区/varchar(255) | Organization.area | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `univ_type` | `varchar(255)` | YES | 学校类型/varchar(255) | Organization.org_type | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `web_link` | `text` | YES | 官方网址/text | Organization.extra_json.web_link | 本体无独立属性，原样保留以避免信息丢失 |
| `comp_dept` | `varchar(255)` | YES | 主管部门/varchar(255) | Organization.extra_json.comp_dept | 本体无独立属性，原样保留以避免信息丢失 |
| `school_nature` | `varchar(255)` | YES | 办学层次/varchar(255) | Organization.extra_json.school_nature | 本体无独立属性，原样保留以避免信息丢失 |
| `postal_code` | `varchar(255)` | YES | 邮政编码/varchar(255) | Organization.postal_code | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 3. `dwd_research_institute_base_info` — 科研机构基本信息

- 所属领域：国内机构要素库
- 数据库表注释：科研机构基本信息
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `lerep` | `varchar(255)` | YES | 法定代表人/varchar(255) | Organization.legal_rep；并创建 Person -[LEGAL_REP_OF]-> Organization | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `reg_status` | `varchar(255)` | YES | 登记状态/varchar(255) | Organization.extra_json.reg_status | 本体无独立属性，原样保留以避免信息丢失 |
| `incorporation_date` | `datetime` | YES | 成立日期/datetime | Organization.extra_json.incorporation_date | 本体无独立属性，原样保留以避免信息丢失 |
| `org_type` | `varchar(255)` | YES | 类型/varchar(255) | Organization.org_type | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `registered_capital_value` | `varchar(255)` | YES | 注册资本(本币元)/varchar(255) | Organization.registered_capital（去除单位后转 double） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `capital_currency` | `varchar(255)` | YES | 币种/varchar(255) | Organization.capital_currency | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `address` | `text` | YES | 登记地址/text | Organization.address | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_en` | `varchar(255)` | YES | 英文名称/varchar(255) | Organization.name_en | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `registration_org` | `varchar(255)` | YES | 登记机关/varchar(255) | Organization.extra_json.registration_org | 本体无独立属性，原样保留以避免信息丢失 |
| `province` | `varchar(255)` | YES | 所在省份/varchar(255) | Organization.province | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `city` | `varchar(255)` | YES | 所在城市/varchar(255) | Organization.city | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `area` | `varchar(255)` | YES | 所在区县/varchar(255) | Organization.area | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `addr_lng` | `varchar(255)` | YES | 地址对应经度/varchar(255) | Organization.extra_json.addr_lng | 本体无独立属性，原样保留以避免信息丢失 |
| `addr_lat` | `varchar(255)` | YES | 地址对应维度/varchar(255) | Organization.extra_json.addr_lat | 本体无独立属性，原样保留以避免信息丢失 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 4. `dwd_special_hongkong_company` — 香港企业

- 所属领域：国内机构要素库
- 数据库表注释：香港企业
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `province_en` | `varchar(255)` | YES | 省份(英文缩写)/varchar(255) | Organization.extra_json.province_en | 本体无独立属性，原样保留以避免信息丢失 |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_en` | `varchar(255)` | YES | 机构英文名称/varchar(255) | Organization.name_en | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `traditional_name` | `varchar(255)` | NO | 机构繁体名称/varchar(255) | Organization.name_cn（name_cn 缺失时） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_code` | `varchar(255)` | YES | 机构编号/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_type` | `varchar(255)` | YES | 机构类别/varchar(255) | Organization.org_type | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `incorporation_date` | `datetime` | YES | 成立日期/datetime | Organization.extra_json.incorporation_date | 本体无独立属性，原样保留以避免信息丢失 |
| `company_status` | `varchar(255)` | YES | 机构现况/varchar(255) | Organization.extra_json.company_status | 本体无独立属性，原样保留以避免信息丢失 |
| `remark` | `varchar(255)` | YES | 备注/varchar(255) | Organization.extra_json.remark | 本体无独立属性，原样保留以避免信息丢失 |
| `liquidation_mode` | `varchar(255)` | YES | 清盘模式/varchar(255) | Organization.extra_json.liquidation_mode | 本体无独立属性，原样保留以避免信息丢失 |
| `cancel_date` | `datetime` | YES | 解散日期/datetime | Organization.extra_json.cancel_date | 本体无独立属性，原样保留以避免信息丢失 |
| `mortgage` | `varchar(255)` | YES | 押记登记册/varchar(255) | Organization.extra_json.mortgage | 本体无独立属性，原样保留以避免信息丢失 |
| `imp_matters` | `varchar(255)` | YES | 重要事项/varchar(255) | Organization.extra_json.imp_matters | 本体无独立属性，原样保留以避免信息丢失 |
| `create_time` | `datetime` | NO | 入库时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `br_code` | `varchar(255)` | YES | 商业登记代码/varchar(255) | Organization.extra_json.br_code | 本体无独立属性，原样保留以避免信息丢失 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 5. `dwd_special_taiwan_company` — 台湾企业

- 所属领域：国内机构要素库
- 数据库表注释：台湾企业
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_name` | `varchar(255)` | YES | 原始机构名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `n_company_name` | `varchar(255)` | YES | 标准机构名称/varchar(255) | Organization.name_cn（name_cn 缺失时） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_code` | `varchar(255)` | YES | 统一编号/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `history_company_code` | `varchar(255)` | YES | 历史统一编号/varchar(255) | Organization.extra_json.history_company_code | 本体无独立属性，原样保留以避免信息丢失 |
| `company_status` | `varchar(255)` | YES | 登记状态/varchar(255) | Organization.extra_json.company_status | 本体无独立属性，原样保留以避免信息丢失 |
| `company_type` | `varchar(255)` | YES | 类型/varchar(255) | Organization.org_type | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_en` | `varchar(255)` | YES | 机构英文名称/varchar(255) | Organization.name_en | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `capital` | `varchar(255)` | YES | 资本总额/varchar(255) | Organization.registered_capital（转 double） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `capital_num` | `decimal(20,6)` | YES | 资本总额_值(万)/decimal(20,6) | Organization.registered_capital（转 double） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `currency` | `varchar(255)` | YES | 资本总额_币种/varchar(255) | Organization.capital_currency | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `real_capital` | `varchar(255)` | YES | 实缴资本额/varchar(255) | Organization.extra_json.real_capital | 本体无独立属性，原样保留以避免信息丢失 |
| `realcapital_num` | `decimal(20,6)` | YES | 实缴资本额_值(万)/decimal(20,6) | Organization.extra_json.realcapital_num | 本体无独立属性，原样保留以避免信息丢失 |
| `realcapital_currency` | `varchar(255)` | YES | 实收资本额_币种/varchar(255) | Organization.extra_json.realcapital_currency | 本体无独立属性，原样保留以避免信息丢失 |
| `amount_per_share` | `decimal(20,6)` | YES | 每股金额/decimal(20,6) | Organization.extra_json.amount_per_share | 本体无独立属性，原样保留以避免信息丢失 |
| `total_shares` | `varchar(255)` | YES | 已发行股份总数/varchar(255) | Organization.extra_json.total_shares | 本体无独立属性，原样保留以避免信息丢失 |
| `legal_person` | `varchar(255)` | YES | 代表人姓名/varchar(255) | Organization.legal_rep；并创建 Person -[LEGAL_REP_OF]-> Organization | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_address` | `varchar(255)` | YES | 机构所在地/varchar(255) | Organization.address | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `registration_org` | `varchar(255)` | YES | 登记机关/varchar(255) | Organization.extra_json.registration_org | 本体无独立属性，原样保留以避免信息丢失 |
| `incorporation_date` | `datetime` | YES | 成立日期/datetime | Organization.extra_json.incorporation_date | 本体无独立属性，原样保留以避免信息丢失 |
| `issue_date` | `datetime` | YES | 核准日期/datetime | Organization.extra_json.issue_date | 本体无独立属性，原样保留以避免信息丢失 |
| `plural_voting_shares` | `varchar(255)` | YES | 是否具有复数表决权特别股/varchar(255) | Organization.extra_json.plural_voting_shares | 本体无独立属性，原样保留以避免信息丢失 |
| `matters_veto_shares` | `varchar(255)` | YES | 是否具有对于特定事项具否决权特别股/varchar(255) | Organization.extra_json.matters_veto_shares | 本体无独立属性，原样保留以避免信息丢失 |
| `special_holder_rights` | `varchar(255)` | YES | 特别股股东被选为董事、监察人的禁止或限制或当选一定名额的权利情况/varchar(255) | Organization.extra_json.special_holder_rights | 本体无独立属性，原样保留以避免信息丢失 |
| `business_scope` | `text` | YES | 经营范围/text | Organization.description | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `history_name` | `varchar(255)` | YES | 历史名称/varchar(255) | Organization.extra_json.history_name | 本体无独立属性，原样保留以避免信息丢失 |
| `equity_status` | `varchar(255)` | YES | 股权状况/varchar(255) | Organization.extra_json.equity_status | 本体无独立属性，原样保留以避免信息丢失 |
| `company_quality` | `varchar(255)` | YES | 机构属性/varchar(255) | Organization.extra_json.company_quality | 本体无独立属性，原样保留以避免信息丢失 |
| `closure_date_begin` | `datetime` | YES | 停业日期(起)/datetime | Organization.extra_json.closure_date_begin | 本体无独立属性，原样保留以避免信息丢失 |
| `closure_date_end` | `datetime` | YES | 停业日期(迄)/datetime | Organization.extra_json.closure_date_end | 本体无独立属性，原样保留以避免信息丢失 |
| `closure_authority` | `varchar(255)` | YES | 停业核准(备)机关/varchar(255) | Organization.extra_json.closure_authority | 本体无独立属性，原样保留以避免信息丢失 |
| `is_history` | `varchar(255)` | YES | 是否历史数据/varchar(255) | Organization.extra_json.is_history | 本体无独立属性，原样保留以避免信息丢失 |
| `create_time` | `datetime` | NO | 入库时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 6. `dwd_special_aomen_company` — 澳门企业

- 所属领域：国内机构要素库
- 数据库表注释：澳门企业
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `org_loc_name` | `varchar(255)` | NO | 机构本地名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `en_name` | `varchar(255)` | YES | 机构英文名称/varchar(255) | Organization.name_en | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `incorporation_year` | `decimal(20,0)` | YES | 成立年份/decimal(20,0) | Organization.founded_year（转 int） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `incorporation_date` | `datetime` | YES | 成立日期/datetime | Organization.extra_json.incorporation_date | 本体无独立属性，原样保留以避免信息丢失 |
| `country_code` | `varchar(255)` | YES | 注册国家代码/varchar(255) | Organization.country_code | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `city` | `varchar(255)` | YES | 注册城市/varchar(255) | Organization.city | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `listing_status` | `varchar(255)` | YES | 上市状态/varchar(255) | Organization.listing_status | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `owners_type` | `varchar(255)` | YES | 机构经济类型/varchar(255) | Organization.extra_json.owners_type | 本体无独立属性，原样保留以避免信息丢失 |
| `person_num` | `decimal(20,0)` | YES | 员工人数/decimal(20,0) | Organization.org_size | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_code` | `varchar(255)` | YES | 统一编号/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_status` | `varchar(255)` | YES | 登记状态/varchar(255) | Organization.extra_json.company_status | 本体无独立属性，原样保留以避免信息丢失 |
| `capital` | `varchar(255)` | YES | 注册资本/varchar(255) | Organization.registered_capital（转 double） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `currency_code` | `varchar(255)` | YES | 注册资本币种/varchar(255) | Organization.capital_currency | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_est_status` | `varchar(255)` | YES | 机构运营状态代码/varchar(255) | Organization.extra_json.company_est_status | 本体无独立属性，原样保留以避免信息丢失 |
| `address` | `varchar(255)` | YES | 地址/varchar(255) | Organization.address | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 7. `dwd_forg_base_info` — 海外机构基本信息

- 所属领域：国外机构要素库
- 数据库表注释：海外机构基本信息
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_en` | `varchar(255)` | NO | 机构名称/varchar(255) | Organization.name_en | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_alias` | `varchar(255)` | YES | 机构本地名称/varchar(255) | Organization.name_cn（本地名称缺失时） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `country_code` | `varchar(255)` | YES | 国家代码/varchar(255) | Organization.country_code | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `country` | `varchar(255)` | YES | 国家/varchar(255) | Organization.country | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `external_id` | `varchar(255)` | YES | 当地官方唯一注册码/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `city` | `varchar(255)` | YES | 所在城市/varchar(255) | Organization.city | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `address` | `text` | YES | 公司地址/text | Organization.address | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `postal_code` | `varchar(255)` | YES | 邮政编码（无数据）/varchar(255) | Organization.postal_code | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `phone` | `varchar(255)` | YES | 联系电话/varchar(255) | Organization.phone | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `email` | `varchar(255)` | YES | 电子邮箱/varchar(255) | Organization.email | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `company_type` | `text` | YES | 企业类型/text | Organization.org_type | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `registration_org` | `text` | YES | 注册机构（无数据）/text | Organization.extra_json.registration_org | 本体无独立属性，原样保留以避免信息丢失 |
| `incorporation_year` | `decimal(20,0)` | YES | 成立年份/decimal(20,0) | Organization.founded_year（转 int） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `incorporation_date` | `datetime` | YES | 成立日期/注册日期/核准日期/datetime | Organization.extra_json.incorporation_date | 本体无独立属性，原样保留以避免信息丢失 |
| `listing_status` | `varchar(255)` | YES | 上市状态/varchar(255) | Organization.listing_status | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `registered_capital_value` | `decimal(20,0)` | YES | 注册资本/decimal(20,0) | Organization.registered_capital（去除单位后转 double） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `registered_capital_currency_code` | `varchar(255)` | YES | 注册资本货币代码/varchar(255) | Organization.capital_currency | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `industry_class` | `varchar(255)` | YES | 公司行业分类/varchar(255) | Organization.industry_class | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `industry_type` | `varchar(255)` | YES | 行业分类标准（新增字段）/varchar(255) | Organization.extra_json.industry_type | 本体无独立属性，原样保留以避免信息丢失 |

### 8. `dwd_org_org_product_info` — 国内机构经营信息

- 所属领域：国内机构要素库
- 数据库表注释：经营信息
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `main_activities` | `text` | YES | 公司经营范围/text | Organization.description | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `description` | `text` | YES | 业务描述/text | Organization.description | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `main_prod` | `varchar(1120)` | YES | — | Organization.main_products | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 9. `dwd_org_stock_base` — 上市企业基本信息

- 所属领域：国内机构要素库
- 数据库表注释：上市企业基本信息
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `stock_code` | `varchar(255)` | NO | 股票代码/varchar(255) | Organization.stock_code | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `stock_noun` | `varchar(255)` | YES | 股票简称/varchar(255) | Organization.stock_noun | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `stock_type` | `varchar(255)` | NO | 上市板块/varchar(255) | Organization.stock_type | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | Organization.name_cn | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Organization.external_id | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `listed_date` | `datetime` | YES | 上市日期/datetime | Organization.listed_date | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `listed_status` | `varchar(255)` | NO | 上市状态/varchar(255) | Organization.listing_status | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Organization.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 10. `dwd_forg_product_info` — 海外机构经营信息

- 所属领域：国外机构要素库
- 数据库表注释：海外机构公司经营信息
- 主图目标：`Organization`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | Organization.org_id（同时用于 VID：org_{org_id}） | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `description` | `varchar(368)` | YES | — | Organization.description | 空值不覆盖已有非空属性；数值字段做容错转换 |
| `main_products` | `varchar(1520)` | YES | — | Organization.main_products | 空值不覆盖已有非空属性；数值字段做容错转换 |

### 11. `dwd_org_shareholder_info` — 国内机构股东信息

- 所属领域：国内机构要素库
- 数据库表注释：股东信息
- 主图目标：`SHAREHOLDER_OF`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | SHAREHOLDER_OF 终点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | SHAREHOLDER_OF.extra_json.name_cn | 本体无独立属性，原样保留在关系/节点 JSON |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | SHAREHOLDER_OF.extra_json.external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `inv_org_id` | `varchar(255)` | YES | 股东id/varchar(255) | SHAREHOLDER_OF 起点 Organization.org_id | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `owners_name` | `varchar(255)` | NO | 股东名称/varchar(255) | SHAREHOLDER_OF 起点 Person.name_cn 或 Organization.name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `owners_type` | `varchar(255)` | YES | 股东类型/varchar(255) | 判定股东节点为 Person 或 Organization | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `ownership_percentage` | `decimal(20,2)` | YES | 所有权占比(%)/decimal(20,2) | SHAREHOLDER_OF.ownership_percentage（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | SHAREHOLDER_OF.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 12. `dwd_forg_shareholder_info` — 海外机构股东信息

- 所属领域：国外机构要素库
- 数据库表注释：海外机构股东股权关联信息
- 主图目标：`SHAREHOLDER_OF`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | SHAREHOLDER_OF 终点 Organization.org_id | 生成 org_{org_id} |
| `owners_name` | `varchar(255)` | YES | 股东名称/varchar(255) | SHAREHOLDER_OF 起点名称；按企业后缀判定 Person/Organization | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `ownership_percentage` | `decimal(20,2)` | YES | 股权占比(%)/decimal(20,2) | SHAREHOLDER_OF.ownership_percentage（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `owners_country_code` | `varchar(255)` | YES | 股东所在国家代码/varchar(255) | SHAREHOLDER_OF.extra_json.owners_country_code | 本体无独立属性，原样保留在关系/节点 JSON |
| `owners_country` | `varchar(255)` | YES | 股东所在国家/varchar(255) | SHAREHOLDER_OF.extra_json.owners_country | 本体无独立属性，原样保留在关系/节点 JSON |

### 13. `dwd_org_executive_info` — 国内机构高管信息

- 所属领域：国内机构要素库
- 数据库表注释：高管信息
- 主图目标：`EXECUTIVE_OF`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | EXECUTIVE_OF 终点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | EXECUTIVE_OF.extra_json.name_cn | 本体无独立属性，原样保留在关系/节点 JSON |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | EXECUTIVE_OF.extra_json.external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `executives_name` | `varchar(255)` | NO | 高管姓名/varchar(255) | EXECUTIVE_OF 起点 Person.name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `executives_position` | `varchar(255)` | YES | 职位名称/varchar(255) | EXECUTIVE_OF.position | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | EXECUTIVE_OF.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 14. `dwd_forg_executive_info` — 海外机构高管信息

- 所属领域：国外机构要素库
- 数据库表注释：海外机构高管信息
- 主图目标：`EXECUTIVE_OF`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | EXECUTIVE_OF 终点 Organization.org_id | 生成 org_{org_id} |
| `executives_name` | `varchar(255)` | YES | 高管姓名/varchar(255) | EXECUTIVE_OF 起点 Person.name_en/name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `executives_position` | `varchar(255)` | YES | 职位名称/varchar(255) | EXECUTIVE_OF.position | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `dm_birthdate` | `datetime` | YES | 高管出生日期(新增字段)/datetime | EXECUTIVE_OF.extra_json.dm_birthdate | 本体无独立属性，原样保留在关系/节点 JSON |
| `dm_nationalities` | `varchar(255)` | YES | 高管国籍(新增字段)/varchar(255) | EXECUTIVE_OF.extra_json.dm_nationalities | 本体无独立属性，原样保留在关系/节点 JSON |
| `dm_biography` | `text` | YES | — | EXECUTIVE_OF.extra_json.dm_biography | 本体无独立属性，原样保留在关系/节点 JSON |

### 15. `dwd_org_invest_info` — 投资事件

- 所属领域：国内机构要素库
- 数据库表注释：投资事件
- 主图目标：`INVESTS_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVESTS_IN 终点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | INVESTS_IN.extra_json.name_cn | 本体无独立属性，原样保留在关系/节点 JSON |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | INVESTS_IN.extra_json.external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `inv_org_id` | `varchar(255)` | NO | 被投企业id/varchar(255) | INVESTS_IN 终点 Organization.org_id | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `inv_name` | `varchar(255)` | NO | 被投资企业名称/varchar(255) | INVESTS_IN 终点 Organization.name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `inv_external_id` | `varchar(255)` | YES | 被投资企业统一社会信用代码/varchar(255) | INVESTS_IN.extra_json.inv_external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `investment_amount` | `decimal(20,2)` | YES | 投资金额(元)/decimal(20,2) | INVESTS_IN.investment_amount（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `investment_ratio` | `decimal(20,2)` | YES | 股权占比(%)/decimal(20,2) | INVESTS_IN.investment_ratio（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | INVESTS_IN.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 16. `dwd_org_merger_acquisition_info` — 并购事件

- 所属领域：国内机构要素库
- 数据库表注释：并购事件
- 主图目标：`ACQUIRES`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `acquiring_org_id` | `varchar(255)` | NO | 发起收购企业id/varchar(255) | ACQUIRES 起点 Organization.org_id | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `acquiring_name` | `varchar(255)` | NO | 发起收购企业名称/varchar(255) | ACQUIRES 起点 Organization.name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `acquiring_external_id` | `varchar(255)` | YES | 发起收购企业统一社会信用代码/varchar(255) | ACQUIRES.extra_json.acquiring_external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `acquired_org_id` | `varchar(255)` | NO | 被收购企业id/varchar(255) | ACQUIRES 终点 Organization.org_id | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `acquired_name` | `varchar(255)` | NO | 被收购企业名称/varchar(255) | ACQUIRES 终点 Organization.name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `acquired_external_id` | `varchar(255)` | YES | 被收购企业统一社会信用代码/varchar(255) | ACQUIRES.extra_json.acquired_external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `ma_amount` | `decimal(20,2)` | YES | 并购金额(元)/decimal(20,2) | ACQUIRES.ma_amount（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `currency_code` | `varchar(255)` | YES | 并购金额币种/varchar(255) | ACQUIRES.currency_code | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | ACQUIRES.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 17. `dwd_forg_subsidiary_info` — 海外机构子公司

- 所属领域：国外机构要素库
- 数据库表注释：海外机构子公司股权关联信息
- 主图目标：`SUBSIDIARY_OF`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | SUBSIDIARY_OF 终点 Organization.org_id | 生成 org_{org_id} |
| `affiliate` | `varchar(255)` | YES | 子公司id/varchar(255) | SUBSIDIARY_OF 终点 Organization.org_id | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `affiliates_name` | `varchar(255)` | YES | 子公司名称/varchar(255) | SUBSIDIARY_OF 终点 Organization.name_en/name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `affiliates_country_code` | `varchar(255)` | YES | 子公司国家代码/varchar(255) | SUBSIDIARY_OF.extra_json.affiliates_country_code | 本体无独立属性，原样保留在关系/节点 JSON |
| `affiliates_country` | `varchar(255)` | YES | 子公司国家/varchar(255) | SUBSIDIARY_OF.extra_json.affiliates_country | 本体无独立属性，原样保留在关系/节点 JSON |
| `affiliates_company_id` | `varchar(255)` | YES | 子公司唯一注册码/varchar(255) | SUBSIDIARY_OF 终点 Organization.external_id/备用标识 | 按字段语义写入端点或关系属性，同时保留在 extra_json |

### 18. `dwd_forg_beneficiary_info` — 海外机构受益人

- 所属领域：国外机构要素库
- 数据库表注释：海外机构受益人信息（新增表）
- 主图目标：`BENEFICIAL_OWNER_OF`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | BENEFICIAL_OWNER_OF 终点 Organization.org_id | 生成 org_{org_id} |
| `bo_name` | `varchar(255)` | YES | 受益人名称/varchar(255) | BENEFICIAL_OWNER_OF 起点 Person.name_en/name_cn | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `bo_gender` | `varchar(255)` | YES | 受益人性别/varchar(255) | BENEFICIAL_OWNER_OF.extra_json.bo_gender | 本体无独立属性，原样保留在关系/节点 JSON |
| `bo_birthdate` | `datetime` | YES | 受益人出生日期/datetime | BENEFICIAL_OWNER_OF.extra_json.bo_birthdate | 本体无独立属性，原样保留在关系/节点 JSON |
| `bo_country_code` | `varchar(255)` | YES | 受益人所在国家代码/varchar(255) | BENEFICIAL_OWNER_OF.extra_json.bo_country_code | 本体无独立属性，原样保留在关系/节点 JSON |
| `path` | `varchar(3296)` | YES | — | BENEFICIAL_OWNER_OF.extra_json.path | 本体无独立属性，原样保留在关系/节点 JSON |
| `bo_manager` | `varchar(255)` | YES | 受益人是否同时是管理层/varchar(255) | BENEFICIAL_OWNER_OF.extra_json.bo_manager | 本体无独立属性，原样保留在关系/节点 JSON |
| `total_percent` | `decimal(20,2)` | YES | 总持股比例/decimal(20,2) | BENEFICIAL_OWNER_OF.total_percent（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `direct_percent` | `decimal(20,2)` | YES | 直接持股比例/decimal(20,2) | BENEFICIAL_OWNER_OF.direct_percent（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `indirect_percent` | `decimal(20,2)` | YES | 间接持股比例/decimal(20,2) | BENEFICIAL_OWNER_OF.indirect_percent（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |

### 19. `dwd_forg_act_contro_info` — 海外机构实际控制人

- 所属领域：国外机构要素库
- 数据库表注释：海外机构实控人信息（新增表）
- 主图目标：`ACTUAL_CONTROLLER_OF`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | ACTUAL_CONTROLLER_OF 终点 Organization.org_id | 生成 org_{org_id} |
| `country_code` | `varchar(255)` | YES | 企业国家代码/varchar(255) | ACTUAL_CONTROLLER_OF.extra_json.country_code | 本体无独立属性，原样保留在关系/节点 JSON |
| `entity_eid` | `varchar(255)` | YES | 实控人ID/varchar(255) | ACTUAL_CONTROLLER_OF 起点标识 | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `entity_name` | `varchar(255)` | YES | 实控人名称/varchar(255) | ACTUAL_CONTROLLER_OF 起点 Person/Organization 名称 | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `entity_type` | `varchar(255)` | YES | 实控人类型/varchar(255) | 判定控制人节点为 Person 或 Organization | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `entity_country_code` | `varchar(255)` | YES | 实控人国家代码/varchar(255) | ACTUAL_CONTROLLER_OF.extra_json.entity_country_code | 本体无独立属性，原样保留在关系/节点 JSON |
| `direct_pct` | `varchar(255)` | YES | 直接持股比例/varchar(255) | ACTUAL_CONTROLLER_OF.direct_pct（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `total_pct` | `varchar(255)` | YES | 总持股比例/varchar(255) | ACTUAL_CONTROLLER_OF.total_pct（转 double） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `direct_pct_num` | `decimal(20,2)` | YES | 直接持股比例数值/decimal(20,2) | ACTUAL_CONTROLLER_OF.direct_pct（数值字段优先） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `total_pct_num` | `decimal(20,2)` | YES | 总持股比例数值/decimal(20,2) | ACTUAL_CONTROLLER_OF.total_pct（数值字段优先） | 按字段语义写入端点或关系属性，同时保留在 extra_json |
| `path` | `varchar(255)` | YES | 路径/varchar(255) | ACTUAL_CONTROLLER_OF.extra_json.path | 本体无独立属性，原样保留在关系/节点 JSON |

### 20. `dwd_org_important_news_info` — 重点资讯

- 所属领域：国内机构要素库
- 数据库表注释：重点资讯
- 主图目标：`News + HAS_NEWS`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | News.extra_json.external_id | 本体无独立属性，原样保留 |
| `news_title` | `text` | NO | 资讯标题/text | News.title | 资讯 VID 由表名和稳定记录键生成 |
| `news_date` | `datetime` | NO | 资讯日期/datetime | News.release_date | 资讯 VID 由表名和稳定记录键生成 |
| `news_content` | `text` | YES | 资讯内容/text | News.content | 资讯 VID 由表名和稳定记录键生成 |
| `original_textlink` | `text` | YES | 咨询原文链接/text | News.original_url、News.source_url | 资讯 VID 由表名和稳定记录键生成 |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | News.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 21. `dwd_org_annual_financial_info` — 年报财务信息

- 所属领域：国内机构要素库
- 数据库表注释：年报财务信息
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `year` | `decimal(20,0)` | NO | 年报年度/decimal(20,0) | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `total_assets` | `decimal(20,2)` | YES | 资产总额/decimal(20,2) | Event.extra_json.total_assets | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_liabilities` | `decimal(20,2)` | YES | 负债总额/decimal(20,2) | Event.extra_json.total_liabilities | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `operating_revenue` | `decimal(20,2)` | YES | 营业收入/decimal(20,2) | Event.extra_json.operating_revenue | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `main_business_revenue` | `decimal(20,2)` | YES | 主营业务收入/decimal(20,2) | Event.extra_json.main_business_revenue | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_profit` | `decimal(20,2)` | YES | 利润总额/decimal(20,2) | Event.extra_json.total_profit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `pure_profit` | `decimal(20,2)` | YES | 净利润/decimal(20,2) | Event.extra_json.pure_profit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_tax_paid` | `decimal(20,2)` | YES | 纳税总额/decimal(20,2) | Event.extra_json.total_tax_paid | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `owners_equity` | `decimal(20,2)` | YES | 所有者权益合计/decimal(20,2) | Event.extra_json.owners_equity | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `employees_number` | `decimal(20,0)` | YES | 从业人数/decimal(20,0) | Event.extra_json.employees_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 22. `dwd_org_stock_finance_info` — 上市企业财务信息

- 所属领域：国内机构要素库
- 数据库表注释：上市企业主要财务指标
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `stock_code` | `varchar(255)` | NO | 股票代码/varchar(255) | Event.extra_json.stock_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `occur_period` | `varchar(255)` | NO | 数据期/varchar(255) | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `total_assets` | `decimal(20,2)` | YES | 资产总额(元)/decimal(20,2) | Event.extra_json.total_assets | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `fixed_assets` | `decimal(20,2)` | YES | 固定资产总额(元)/decimal(20,2) | Event.extra_json.fixed_assets | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_liabilities` | `decimal(20,2)` | YES | 负债总额(元)/decimal(20,2) | Event.extra_json.total_liabilities | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `operating_revenue` | `decimal(20,2)` | YES | 营业收入(元)/decimal(20,2) | Event.extra_json.operating_revenue | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `main_business_revenue` | `decimal(20,2)` | YES | 主营业务收入(元)/decimal(20,2) | Event.extra_json.main_business_revenue | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_profit` | `decimal(20,2)` | YES | 利润总额(元)/decimal(20,2) | Event.extra_json.total_profit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `pure_profit` | `decimal(20,2)` | YES | 净利润(元)/decimal(20,2) | Event.extra_json.pure_profit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_tax_paid` | `decimal(20,2)` | YES | 纳税总额(元)/decimal(20,2) | Event.extra_json.total_tax_paid | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `oper_cash_flow` | `decimal(20,2)` | YES | 经营活动现金流(元)/decimal(20,2) | Event.extra_json.oper_cash_flow | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `owners_equity` | `decimal(20,2)` | YES | 所有者权益合计(元)/decimal(20,2) | Event.extra_json.owners_equity | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `employees_number` | `decimal(20,0)` | YES | 从业人数/decimal(20,0) | Event.extra_json.employees_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `research_development_amount` | `decimal(20,2)` | YES | 研发投入金额(元)/decimal(20,2) | Event.extra_json.research_development_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 23. `dwd_forg_stock_fin_info` — 海外上市企业财务信息

- 所属领域：国外机构要素库
- 数据库表注释：海外上市企业财务信息
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `occur_period` | `datetime` | YES | 报告期/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `total_assets` | `decimal(20,2)` | YES | 资产总额/decimal(20,2) | Event.extra_json.total_assets | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `fixed_assets` | `decimal(20,2)` | YES | 固定资产总额/decimal(20,2) | Event.extra_json.fixed_assets | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_liabilities` | `decimal(20,2)` | YES | 负债总额/decimal(20,2) | Event.extra_json.total_liabilities | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `operating_revenue` | `decimal(20,2)` | YES | 营业收入/decimal(20,2) | Event.extra_json.operating_revenue | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `main_business_revenue` | `decimal(20,2)` | YES | 主营业务收入/decimal(20,2) | Event.extra_json.main_business_revenue | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_profit` | `decimal(20,2)` | YES | 利润总额/decimal(20,2) | Event.extra_json.total_profit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `pure_profit` | `decimal(20,2)` | YES | 净利润/decimal(20,2) | Event.extra_json.pure_profit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `total_tax_paid` | `decimal(20,2)` | YES | 企业所得税/decimal(20,2) | Event.extra_json.total_tax_paid | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `oper_cash_flow` | `decimal(20,2)` | YES | 经营活动现金流/decimal(20,2) | Event.extra_json.oper_cash_flow | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `owners_equity` | `decimal(20,2)` | YES | 所有者权益合计/decimal(20,2) | Event.extra_json.owners_equity | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `employees_number` | `decimal(20,2)` | YES | 从业人数/decimal(20,2) | Event.extra_json.employees_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `research_development_amount` | `decimal(20,2)` | YES | 研发投入金额/decimal(20,2) | Event.extra_json.research_development_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `research_development_employees_number` | `decimal(20,2)` | YES | 研发人员数（无数据）/decimal(20,2) | Event.extra_json.research_development_employees_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |

### 24. `dwd_org_changerecord_info` — 工商变更

- 所属领域：国内机构要素库
- 数据库表注释：工商变更信息
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `update_content` | `varchar(255)` | YES | 变更类型/varchar(255) | Event.content | 同时完整保留在 Event.extra_json/content JSON |
| `current_name` | `text` | YES | 变更前内容/text | Event.extra_json.current_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `update_name` | `text` | YES | 变更后内容/text | Event.extra_json.update_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `update_date` | `datetime` | YES | 变更日期/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 25. `dwd_org_financing_info` — 融资事件

- 所属领域：国内机构要素库
- 数据库表注释：融资事件
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `funding_round` | `varchar(255)` | YES | 融资轮次/varchar(255) | Event.title；同时保留在 Event.extra_json | 同时完整保留在 Event.extra_json/content JSON |
| `funding_amount` | `decimal(20,2)` | YES | 获投金额(元)/decimal(20,2) | Event.amount（转 double） | 同时完整保留在 Event.extra_json/content JSON |
| `funding_currency_code` | `varchar(255)` | YES | 金额币种/varchar(255) | Event.currency | 同时完整保留在 Event.extra_json/content JSON |
| `completion_date` | `datetime` | YES | 融资完成时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `investors_name` | `text` | NO | 投资方列表/text | Event.extra_json.investors_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 26. `dwd_org_recruit_info` — 招聘信息

- 所属领域：国内机构要素库
- 数据库表注释：招聘信息
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `job_title` | `varchar(255)` | YES | 岗位/varchar(255) | Event.title | 同时完整保留在 Event.extra_json/content JSON |
| `job_description` | `text` | YES | 工作描述/text | Event.content | 同时完整保留在 Event.extra_json/content JSON |
| `work_place` | `text` | YES | 工作地点/text | Event.extra_json.work_place | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `release_date` | `datetime` | YES | 发布日期/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `hiring_number` | `varchar(255)` | YES | 招聘人数/varchar(255) | Event.extra_json.hiring_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 27. `dwd_org_company_abnormal` — 经营异常

- 所属领域：国内机构要素库
- 数据库表注释：经营异常
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `abnormal_id` | `varchar(255)` | NO | 经营异常记录id/varchar(255) | Event.extra_json.abnormal_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `abn_reason` | `text` | YES | 列入原因/text | Event.extra_json.abn_reason | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `abn_date` | `datetime` | YES | 列入时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `abn_org` | `varchar(255)` | YES | 列入机关/varchar(255) | Event.extra_json.abn_org | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `remove_reason` | `text` | YES | 移除原因/text | Event.extra_json.remove_reason | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `remove_date` | `datetime` | YES | 移除时间/datetime | Event.extra_json.remove_date | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `remove_org` | `varchar(255)` | YES | 移除机关/varchar(255) | Event.extra_json.remove_org | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 28. `dwd_org_company_punish` — 行政处罚

- 所属领域：国内机构要素库
- 数据库表注释：行政处罚
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `penalty_id` | `varchar(255)` | NO | 行政处罚记录id/varchar(255) | Event.extra_json.penalty_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `decision_no` | `varchar(255)` | YES | 决定书文号/varchar(255) | Event.extra_json.decision_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `violation_type` | `text` | YES | 违法行为类型/text | Event.extra_json.violation_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `penalty_content` | `text` | YES | 行政处罚内容/text | Event.content | 同时完整保留在 Event.extra_json/content JSON |
| `decision_org` | `varchar(255)` | YES | 决定机关/varchar(255) | Event.extra_json.decision_org | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `penalty_date` | `datetime` | YES | 处罚决定日期/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `public_date` | `datetime` | YES | 公示日期/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `penalty_basis` | `text` | YES | 处罚依据/text | Event.extra_json.penalty_basis | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `violation_fact` | `text` | YES | 主要违法事实/text | Event.content | 同时完整保留在 Event.extra_json/content JSON |
| `penalty_type` | `varchar(255)` | YES | 处罚种类/varchar(255) | Event.extra_json.penalty_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `fine_amount` | `varchar(255)` | YES | 罚款金额/varchar(255) | Event.amount（转 double） | 同时完整保留在 Event.extra_json/content JSON |
| `confiscate_amount` | `varchar(255)` | YES | 没收金额/varchar(255) | Event.extra_json.confiscate_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `license_info` | `varchar(255)` | YES | 暂扣或吊销证照名称及编号/varchar(255) | Event.extra_json.license_info | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `validity_period` | `varchar(255)` | YES | 处罚有效期/varchar(255) | Event.extra_json.validity_period | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `public_deadline` | `datetime` | YES | 公示截止日期/datetime | Event.extra_json.public_deadline | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `mark` | `varchar(255)` | YES | 备注/varchar(255) | Event.extra_json.mark | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 29. `dwd_org_company_illegal` — 严重违法

- 所属领域：国内机构要素库
- 数据库表注释：严重违法
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | NO | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `sv_id` | `varchar(255)` | NO | 严重违法记录id/varchar(255) | Event.extra_json.sv_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `category` | `varchar(255)` | YES | 类别/varchar(255) | Event.extra_json.category | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `abn_reason` | `text` | YES | 列入原因/text | Event.extra_json.abn_reason | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `abn_date` | `datetime` | YES | 列入时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `abn_org` | `varchar(255)` | YES | 列入机关/varchar(255) | Event.extra_json.abn_org | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `remove_reason` | `text` | YES | 移除原因/text | Event.extra_json.remove_reason | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `remove_date` | `datetime` | YES | 移除时间/datetime | Event.extra_json.remove_date | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `remove_org` | `varchar(255)` | YES | 移除机关/varchar(255) | Event.extra_json.remove_org | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 30. `dwd_org_risk_tax_punish` — 税收违法

- 所属领域：国内机构要素库
- 数据库表注释：税收违法
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `taxpayer_name` | `varchar(255)` | NO | 纳税人名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `tax_vio_id` | `varchar(255)` | NO | 唯一索引id/varchar(255) | Event.extra_json.tax_vio_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `report_period` | `varchar(255)` | YES | 案件上报期/varchar(255) | Event.extra_json.report_period | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `taxpayer_id` | `varchar(255)` | YES | 纳税人识别码/varchar(255) | Event.extra_json.taxpayer_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `org_code` | `varchar(255)` | YES | 组织机构代码/varchar(255) | Event.extra_json.org_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `reg_address` | `text` | YES | 注册地址/text | Event.extra_json.reg_address | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `publish_date` | `datetime` | YES | 发布日期/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `legal_name` | `varchar(255)` | YES | 法定代表人或者负责人姓名/varchar(255) | Event.extra_json.legal_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `legal_gender` | `varchar(255)` | YES | 法定代表人或者负责人性别/varchar(255) | Event.extra_json.legal_gender | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `legal_id_type` | `varchar(255)` | YES | 法定代表人或者负责人证件类型/varchar(255) | Event.extra_json.legal_id_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `legal_id_no` | `varchar(255)` | YES | 法定代表人或者负责人证件号码/varchar(255) | Event.extra_json.legal_id_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `finance_name` | `varchar(255)` | YES | 负有直接责任的财务负责人姓名/varchar(255) | Event.extra_json.finance_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `finance_gender` | `varchar(255)` | YES | 负有直接责任的财务负责人性别/varchar(255) | Event.extra_json.finance_gender | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `finance_id_type` | `varchar(255)` | YES | 负有直接责任的财务负责人证件类型/varchar(255) | Event.extra_json.finance_id_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `finance_id_no` | `varchar(255)` | YES | 负有直接责任的财务负责人证件号码/varchar(255) | Event.extra_json.finance_id_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `agency_info` | `varchar(255)` | YES | 负有直接责任的中介机构信息及其从业人员信息/varchar(255) | Event.extra_json.agency_info | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `case_type` | `varchar(255)` | YES | 案件性质/varchar(255) | Event.extra_json.case_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `illegal_fact` | `text` | YES | 主要违法事实/text | Event.content | 同时完整保留在 Event.extra_json/content JSON |
| `punish_basis` | `text` | YES | 相关法律依据及税务处理处罚情况/text | Event.extra_json.punish_basis | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `tax_authority` | `varchar(255)` | YES | 所属税务机关/varchar(255) | Event.extra_json.tax_authority | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `original_link` | `text` | YES | 数据原始链接/text | Event.extra_json.original_link | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 31. `dwd_org_opt_judicial_case` — 司法案件

- 所属领域：国内机构要素库
- 数据库表注释：司法案件信息
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `company_name` | `varchar(255)` | NO | 企业名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `case_id` | `varchar(255)` | NO | 司法案件唯一标识/varchar(255) | Event.extra_json.case_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `reg_no` | `varchar(255)` | YES | 注册号/varchar(255) | Event.extra_json.reg_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `case_title` | `text` | YES | 案件标题/text | Event.title | 同时完整保留在 Event.extra_json/content JSON |
| `case_type_tag` | `varchar(255)` | YES | 案件类型标签/varchar(255) | Event.extra_json.case_type_tag | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `case_no` | `text` | YES | 案号/text | Event.case_no；破产表中也作为跨表事件连接键 | 同时完整保留在 Event.extra_json/content JSON |
| `case_cause` | `text` | YES | 案由/text | Event.case_cause | 同时完整保留在 Event.extra_json/content JSON |
| `case_role` | `text` | YES | 案件身份/text | Event.extra_json.case_role | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `current_procedure` | `varchar(255)` | YES | 当前审理程序/varchar(255) | Event.extra_json.current_procedure | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `procedure_date` | `datetime` | YES | 当前审理程序日期/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 32. `dwd_org_risk_shixin` — 失信被执行人

- 所属领域：国内机构要素库
- 数据库表注释：失信被执行人
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `text` | NO | 失信人名称/text | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `dishonest_id` | `varchar(255)` | NO | 失信被执行人id/varchar(255) | Event.extra_json.dishonest_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `official_id` | `varchar(255)` | YES | 官网id/varchar(255) | Event.extra_json.official_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `case_no` | `varchar(255)` | YES | 案号/varchar(255) | Event.case_no；破产表中也作为跨表事件连接键 | 同时完整保留在 Event.extra_json/content JSON |
| `gender` | `varchar(255)` | YES | 性别/varchar(255) | Event.extra_json.gender | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `age` | `varchar(255)` | YES | 年龄/varchar(255) | Event.extra_json.age | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `reg_no` | `varchar(255)` | YES | 企业注册号/varchar(255) | Event.extra_json.reg_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `display_id_no` | `varchar(255)` | YES | 展示用证件号码/varchar(255) | Event.extra_json.display_id_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `legal_person` | `varchar(255)` | YES | 法定代表人或负责人/varchar(255) | Event.extra_json.legal_person | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_court` | `varchar(255)` | YES | 执行法院/varchar(255) | Event.extra_json.exec_court | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `province` | `varchar(255)` | YES | 省份/varchar(255) | Event.extra_json.province | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `dishonest_type` | `decimal(20,0)` | YES | 失信人类型/decimal(20,0) | Event.extra_json.dishonest_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_basis_no` | `text` | YES | 执行依据文号/text | Event.extra_json.exec_basis_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_basis_org` | `varchar(255)` | YES | 做出执行依据单位/varchar(255) | Event.extra_json.exec_basis_org | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `legal_obligation` | `text` | YES | 生效法律文书确定的义务/text | Event.content | 同时完整保留在 Event.extra_json/content JSON |
| `fulfillment_status` | `text` | YES | 被执行人的履行情况/text | Event.extra_json.fulfillment_status | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `dishonest_behavior` | `text` | YES | 失信被执行人行为具体情形/text | Event.extra_json.dishonest_behavior | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `publish_date` | `datetime` | YES | 发布时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `filing_date` | `datetime` | YES | 立案时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `exec_part` | `text` | YES | 执行部分/text | Event.extra_json.exec_part | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `unexec_part` | `text` | YES | 未执行部分/text | Event.extra_json.unexec_part | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 33. `dwd_org_risk_zhixing` — 被执行人

- 所属领域：国内机构要素库
- 数据库表注释：被执行人
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `exec_person_id` | `varchar(255)` | NO | 唯一索引id/varchar(255) | Event.extra_json.exec_person_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_person_type` | `decimal(20,0)` | YES | 被执行人类型/decimal(20,0) | Event.extra_json.exec_person_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_person_name` | `varchar(255)` | NO | 被执行人名称/varchar(255) | Event.extra_json.exec_person_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `gender` | `varchar(255)` | YES | 性别/varchar(255) | Event.extra_json.gender | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `id_no` | `varchar(255)` | YES | 证件号码/varchar(255) | Event.extra_json.id_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_court` | `varchar(255)` | YES | 执行法院/varchar(255) | Event.extra_json.exec_court | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `case_no` | `varchar(255)` | YES | 案号/varchar(255) | Event.case_no；破产表中也作为跨表事件连接键 | 同时完整保留在 Event.extra_json/content JSON |
| `exec_basis_no` | `varchar(255)` | YES | 执行依据文号/varchar(255) | Event.extra_json.exec_basis_no | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_status` | `varchar(255)` | YES | 执行状态/varchar(255) | Event.extra_json.exec_status | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `exec_target` | `varchar(255)` | YES | 执行标的/varchar(255) | Event.extra_json.exec_target | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `web_id` | `varchar(255)` | YES | 执行信息公开网id/varchar(255) | Event.extra_json.web_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `filing_date` | `datetime` | YES | 立案时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `is_hidden` | `decimal(20,0)` | YES | 是否不展示/decimal(20,0) | Event.extra_json.is_hidden | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN/HAS_NEWS 起点 Organization.org_id | 生成 org_{org_id} |
| `name_cn` | `varchar(255)` | YES | 机构名称/varchar(255) | 关联 Organization.name_cn | 仅补全空属性，不覆盖已有机构主数据 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | Event.extra_json.external_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 34. `dwd_org_bankruptcy_public_cases` — 破产案件

- 所属领域：国内机构要素库
- 数据库表注释：破产案件
- 主图目标：`Event + INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `case_no` | `varchar(255)` | NO | 案号/varchar(255) | Event.case_no；破产表中也作为跨表事件连接键 | 同时完整保留在 Event.extra_json/content JSON |
| `case_type` | `varchar(255)` | YES | 案件类型/varchar(255) | Event.extra_json.case_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `handling_court` | `varchar(255)` | YES | 经办法院/varchar(255) | Event.extra_json.handling_court | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `applicant_info` | `text` | YES | 申请人信息/text | Event.extra_json.applicant_info | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `respondent_info` | `text` | YES | 被申请人信息/text | Event.extra_json.respondent_info | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `admin_org` | `varchar(255)` | YES | 管理人机构/varchar(255) | Event.extra_json.admin_org | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `admin_org_id` | `varchar(255)` | NO | 管理人机构id/varchar(255) | Event.extra_json.admin_org_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `admin_principal` | `varchar(255)` | YES | 管理人主要负责人/varchar(255) | Event.extra_json.admin_principal | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `public_date` | `datetime` | YES | 公开时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `link` | `text` | YES | 链接/text | Event.extra_json.link | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `history_status` | `varchar(255)` | YES | 历史状态/varchar(255) | Event.extra_json.history_status | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 35. `dwd_org_bankruptcy_public_cases_list` — 破产案件当事人

- 所属领域：国内机构要素库
- 数据库表注释：破产案件当事人
- 主图目标：`INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `bankruptcy_party_id` | `varchar(255)` | NO | 唯一索引id/varchar(255) | INVOLVED_IN.source_record_id / edge rank 输入 | 按破产案件号跨表关联 |
| `case_no` | `varchar(255)` | YES | 案号/varchar(255) | Event.raw_id（连接 dwd_org_bankruptcy_public_cases） | 按破产案件号跨表关联 |
| `related_person_name` | `varchar(255)` | YES | 相关人名称/varchar(255) | INVOLVED_IN.extra_json.related_person_name | 本体无独立属性，原样保留在关系/节点 JSON |
| `party_role_type` | `decimal(20,0)` | YES | 当事人角色类型/decimal(20,0) | INVOLVED_IN.role | 按破产案件号跨表关联 |
| `party_type` | `decimal(20,0)` | YES | 当事人类型/decimal(20,0) | INVOLVED_IN.extra_json.party_type | 本体无独立属性，原样保留在关系/节点 JSON |
| `org_id` | `varchar(255)` | NO | 机构id/varchar(255) | INVOLVED_IN 起点 Organization.org_id | 按破产案件号跨表关联 |
| `name_cn` | `varchar(255)` | YES | 机构名称/varchar(255) | INVOLVED_IN 起点 Organization.name_cn | 按破产案件号跨表关联 |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | INVOLVED_IN.extra_json.external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `public_date` | `datetime` | YES | 公开时间/datetime | INVOLVED_IN.extra_json.public_date | 本体无独立属性，原样保留在关系/节点 JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | INVOLVED_IN.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 36. `dwd_bid_base_out` — 招投标公告

- 所属领域：国内机构要素库
- 数据库表注释：招投标公告基础表
- 主图目标：`Event`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `u_id` | `varchar(255)` | NO | 公告唯一标识id/varchar(255) | Event.extra_json.u_id | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `publish_time` | `datetime` | YES | 发布时间/datetime | Event.occur_date | 同时完整保留在 Event.extra_json/content JSON |
| `title` | `varchar(255)` | YES | 标题/varchar(255) | Event.title | 同时完整保留在 Event.extra_json/content JSON |
| `project_number` | `text` | YES | 项目编号/text | Event.extra_json.project_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `plan_number` | `text` | YES | 计划编号/text | Event.extra_json.plan_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_name` | `text` | YES | 项目名称/text | Event.title | 同时完整保留在 Event.extra_json/content JSON |
| `announcement_type` | `varchar(255)` | YES | 公告类型/varchar(255) | Event.extra_json.announcement_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `announcement_type_code` | `decimal(20,0)` | YES | 公告类型编号/decimal(20,0) | Event.extra_json.announcement_type_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `industry_type` | `varchar(255)` | YES | 行业分类/varchar(255) | Event.extra_json.industry_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `procurement_method` | `varchar(255)` | YES | 采购方式/varchar(255) | Event.extra_json.procurement_method | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `procurement_method_code` | `decimal(20,0)` | YES | 采购方式编号/decimal(20,0) | Event.extra_json.procurement_method_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bidding_stage` | `varchar(255)` | YES | 招投标阶段/varchar(255) | Event.extra_json.bidding_stage | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `target_item_type` | `varchar(255)` | YES | 标的物类型/varchar(255) | Event.extra_json.target_item_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bidding_stage_code` | `decimal(20,0)` | YES | 招投标阶段编码/decimal(20,0) | Event.extra_json.bidding_stage_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_region_province` | `varchar(255)` | YES | 项目区域-省/varchar(255) | Event.extra_json.project_region_province | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_region_province_code` | `varchar(255)` | YES | 项目区域-省-编码/varchar(255) | Event.extra_json.project_region_province_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_region_city` | `varchar(255)` | YES | 项目区域-市/varchar(255) | Event.extra_json.project_region_city | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_region_city_code` | `varchar(255)` | YES | 项目区域-市-编码/varchar(255) | Event.extra_json.project_region_city_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_region_district` | `varchar(255)` | YES | 项目区域-区县/varchar(255) | Event.extra_json.project_region_district | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_region_district_code` | `varchar(255)` | YES | 项目区域-区县-编码/varchar(255) | Event.extra_json.project_region_district_code | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_budget_amount` | `decimal(20,6)` | YES | 项目预算金额/decimal(20,6) | Event.amount（转 double） | 同时完整保留在 Event.extra_json/content JSON |
| `project_budget_amount_unit` | `varchar(255)` | YES | 项目预算金额单位/varchar(255) | Event.currency | 同时完整保留在 Event.extra_json/content JSON |
| `total_amount` | `decimal(20,6)` | YES | 中标总金额/decimal(20,6) | Event.amount（转 double） | 同时完整保留在 Event.extra_json/content JSON |
| `total_amount_unit` | `varchar(255)` | YES | 中标总金额单位/varchar(255) | Event.currency | 同时完整保留在 Event.extra_json/content JSON |
| `bid_document_start_time` | `datetime` | YES | 标书获取开始时间/datetime | Event.extra_json.bid_document_start_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bid_document_end_time` | `datetime` | YES | 标书获取截止时间/datetime | Event.extra_json.bid_document_end_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `registration_start_time` | `datetime` | YES | 报名开始时间/datetime | Event.extra_json.registration_start_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `registration_end_time` | `datetime` | YES | 报名截止时间/datetime | Event.extra_json.registration_end_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bidding_start_time` | `datetime` | YES | 投标开始时间/datetime | Event.extra_json.bidding_start_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bidding_end_time` | `datetime` | YES | 投标结束时间/datetime | Event.extra_json.bidding_end_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `opening_bid_time` | `datetime` | YES | 开标时间/datetime | Event.extra_json.opening_bid_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `estimated_purchasing_time` | `datetime` | YES | 预计采购时间/datetime | Event.extra_json.estimated_purchasing_time | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `contract_num` | `text` | YES | 合同编号/text | Event.extra_json.contract_num | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `quotation_validity_start` | `datetime` | YES | 报价有效期-起/datetime | Event.extra_json.quotation_validity_start | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `quotation_validity_end` | `datetime` | YES | 报价有效期-止/datetime | Event.extra_json.quotation_validity_end | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `tender_document_price_amount` | `decimal(20,6)` | YES | 标书售价(数值)/decimal(20,6) | Event.extra_json.tender_document_price_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `tender_document_price_unit` | `varchar(255)` | YES | 标书售价(单位)/varchar(255) | Event.extra_json.tender_document_price_unit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `registration_fee_amount` | `decimal(20,6)` | YES | 报名费(数值)/decimal(20,6) | Event.extra_json.registration_fee_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `registration_fee_unit` | `varchar(255)` | YES | 报名费(单位)/varchar(255) | Event.extra_json.registration_fee_unit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bidding_security_amount` | `decimal(20,6)` | YES | 投标保证金(数值)/decimal(20,6) | Event.extra_json.bidding_security_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bidding_security_unit` | `varchar(255)` | YES | 投标保证金(单位)/varchar(255) | Event.extra_json.bidding_security_unit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `ca_payment_amount` | `decimal(20,6)` | YES | CA缴纳费用(数值字)/decimal(20,6) | Event.extra_json.ca_payment_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `ca_payment_unit` | `varchar(255)` | YES | CA缴纳费用(单位)/varchar(255) | Event.extra_json.ca_payment_unit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `tender_agent_service_fee_amount` | `decimal(20,6)` | YES | 招标代理服务费(数值)/decimal(20,6) | Event.extra_json.tender_agent_service_fee_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `tender_agent_service_fee_unit` | `varchar(255)` | YES | 招标代理服务费(单位)/varchar(255) | Event.extra_json.tender_agent_service_fee_unit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `performance_security_amount` | `decimal(20,6)` | YES | 履约保证金(数值)/decimal(20,6) | Event.extra_json.performance_security_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `performance_security_unit` | `varchar(255)` | YES | 履约保证金(单位)/varchar(255) | Event.extra_json.performance_security_unit | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `funding_source` | `text` | YES | 资金来源/text | Event.extra_json.funding_source | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `construction_service_location` | `text` | YES | 建设地点/服务地点/text | Event.extra_json.construction_service_location | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `construction_service_period` | `text` | YES | 工期/服务周期/text | Event.extra_json.construction_service_period | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `allow_joint_bid` | `decimal(20,0)` | YES | 是否允许联合体投标/decimal(20,0) | Event.extra_json.allow_joint_bid | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bidding_document_sub_style` | `decimal(20,0)` | YES | 投标文件递交方式/decimal(20,0) | Event.extra_json.bidding_document_sub_style | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `supplier_qualification_criteria` | `text` | YES | 供应商的准入资质/text | Event.extra_json.supplier_qualification_criteria | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 37. `dwd_bid_win_candidate_out` — 中标候选人

- 所属领域：国内机构要素库
- 数据库表注释：招投标中标候选人表
- 主图目标：`INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `u_id` | `varchar(255)` | NO | 公告唯一标识id/varchar(255) | Event.raw_id（连接 dwd_bid_base_out） | 按 u_id 连接招投标 Event |
| `org_id` | `varchar(255)` | YES | 机构id/varchar(255) | INVOLVED_IN 起点 Organization.org_id | 按 u_id 连接招投标 Event |
| `name_cn` | `varchar(255)` | YES | 机构名称/varchar(255) | INVOLVED_IN 起点 Organization.name_cn | 按 u_id 连接招投标 Event |
| `external_id` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | INVOLVED_IN.extra_json.external_id | 本体无独立属性，原样保留在关系/节点 JSON |
| `project_number` | `varchar(255)` | YES | 项目编号/varchar(255) | INVOLVED_IN.extra_json.project_number | 本体无独立属性，原样保留在关系/节点 JSON |
| `project_name` | `text` | YES | 项目名称/text | INVOLVED_IN.extra_json.project_name | 本体无独立属性，原样保留在关系/节点 JSON |
| `bid_item_name` | `text` | YES | 招标项目名称/text | INVOLVED_IN.extra_json.bid_item_name | 本体无独立属性，原样保留在关系/节点 JSON |
| `bid_section_number` | `varchar(255)` | YES | 标段编号/varchar(255) | INVOLVED_IN.extra_json.bid_section_number | 本体无独立属性，原样保留在关系/节点 JSON |
| `amount` | `decimal(20,6)` | YES | 中标报价(金额)/decimal(20,6) | INVOLVED_IN.extra_json.amount | 本体无独立属性，原样保留在关系/节点 JSON |
| `amount_unit` | `varchar(255)` | YES | 中标报价(单位)/varchar(255) | INVOLVED_IN.extra_json.amount_unit | 本体无独立属性，原样保留在关系/节点 JSON |
| `ranking` | `decimal(20,0)` | YES | 候选人排名/decimal(20,0) | INVOLVED_IN.extra_json.ranking | 按 u_id 连接招投标 Event |
| `relate_type` | `decimal(20,0)` | YES | 关系类型/decimal(20,0) | INVOLVED_IN.extra_json.relate_type | 按 u_id 连接招投标 Event |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | INVOLVED_IN.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 38. `dwd_bid_purchase_agency_out` — 采购代理

- 所属领域：国内机构要素库
- 数据库表注释：招投标采购代理表
- 主图目标：`INVOLVED_IN`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `u_id` | `varchar(255)` | NO | 公告唯一标识id/varchar(255) | Event.raw_id（连接 dwd_bid_base_out） | 按 u_id 连接招投标 Event |
| `company_id` | `varchar(255)` | YES | 机构id/varchar(255) | INVOLVED_IN 起点 Organization.org_id | 按 u_id 连接招投标 Event |
| `company_name` | `varchar(255)` | YES | 机构名称/varchar(255) | INVOLVED_IN 起点 Organization.name_cn | 按 u_id 连接招投标 Event |
| `credit_no` | `varchar(255)` | YES | 统一社会信用代码/varchar(255) | INVOLVED_IN.extra_json.credit_no | 本体无独立属性，原样保留在关系/节点 JSON |
| `project_number` | `varchar(255)` | YES | 项目编号/varchar(255) | INVOLVED_IN.extra_json.project_number | 本体无独立属性，原样保留在关系/节点 JSON |
| `project_name` | `text` | YES | 项目名称/text | INVOLVED_IN.extra_json.project_name | 本体无独立属性，原样保留在关系/节点 JSON |
| `relate_type` | `decimal(20,0)` | YES | 枚举判断/decimal(20,0) | INVOLVED_IN.extra_json.relate_type | 按 u_id 连接招投标 Event |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | INVOLVED_IN.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

### 39. `dwd_bid_target_item_out` — 招投标标的物

- 所属领域：国内机构要素库
- 数据库表注释：招投标标的物表
- 主图目标：`Event.content`

| 源字段 | MySQL 类型 | 可空 | 字段注释 | 图实体/关系属性 | 转换与关联规则 |
|---|---|---|---|---|---|
| `u_id` | `varchar(255)` | NO | 公告唯一标识id/varchar(255) | Event.raw_id（连接 dwd_bid_base_out） | 同一事件 VID，标的物字段整体并入 Event.content JSON |
| `project_number` | `text` | YES | 项目编号/text | Event.extra_json.project_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_name` | `text` | YES | 项目名称/text | Event.title | 同时完整保留在 Event.extra_json/content JSON |
| `amount_unit` | `varchar(255)` | YES | 金额单位/varchar(255) | Event.currency | 同时完整保留在 Event.extra_json/content JSON |
| `bid_item_name` | `text` | YES | 招标项目名称/text | Event.extra_json.bid_item_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `bid_section_number` | `varchar(255)` | YES | 标段编号/varchar(255) | Event.extra_json.bid_section_number | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `brand` | `varchar(255)` | YES | 品牌/varchar(255) | Event.extra_json.brand | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `model` | `varchar(255)` | YES | 型号/varchar(255) | Event.extra_json.model | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `project_content` | `varchar(255)` | YES | 项目内容/varchar(255) | Event.content | 同时完整保留在 Event.extra_json/content JSON |
| `quantity` | `decimal(20,0)` | YES | 数量/decimal(20,0) | Event.extra_json.quantity | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `service_content` | `text` | YES | 服务内容/text | Event.extra_json.service_content | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `standard_product_name` | `varchar(255)` | YES | 标准产品名称/varchar(255) | Event.extra_json.standard_product_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `target_item_name` | `text` | YES | 标的物名称/text | Event.extra_json.target_item_name | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `target_item_type` | `varchar(255)` | YES | 标的物类型/varchar(255) | Event.extra_json.target_item_type | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `unit_price_amount` | `decimal(20,2)` | YES | 单价金额/decimal(20,2) | Event.extra_json.unit_price_amount | 本体无独立属性，原样保留；事件内容类表也进入 content JSON |
| `data_source` | `varchar(255)` | NO | 数据来源/varchar(255) | DataSource.source_table + DERIVED_FROM | 非 MOCK 值建原始 DataSource；方向为原始来源表 -> 当前要素表 |
| `created_time` | `datetime` | NO | 创建时间/datetime | 目标节点/边 extra_json | 保留源值，不作为图写入时间；ingest_time 由 ETL 生成 |
| `updated_time` | `datetime` | NO | 更新时间/datetime | Event.content.source_update_time / 边 extra_json | 统一转 ISO 字符串；关系表保留在 edge.extra_json |

## 四、运行与审计产物

- `manifest.json`：源表行数、各类节点/边数量以及精确 VID/edge rank 清单。
- `load.ngql`：本次批次完整 nGQL，可用于审阅和重放。
- `rollback.ngql`：只删除 manifest 中列出的边和节点，按先边后点生成。
- MySQL 连接在事务级设置为只读；图写入被代码限制为 `dev` 空间。
