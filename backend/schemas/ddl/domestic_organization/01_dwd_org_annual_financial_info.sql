CREATE TABLE `dwd_org_annual_financial_info` (
  `org_id` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '机构id',
  `name_cn` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '机构名称',
  `social_credit_code` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '统一社会信用代码',
  `year` int DEFAULT NULL COMMENT '年报年度',
  `total_assets` double DEFAULT NULL COMMENT '资产总额',
  `total_fixed_assets` double DEFAULT NULL COMMENT '固定资产总额',
  `total_liabilities` double DEFAULT NULL COMMENT '负债总额',
  `operating_revenue` double DEFAULT NULL COMMENT '营业收入',
  `main_business_revenue` double DEFAULT NULL COMMENT '主营业务收入',
  `total_profit` double DEFAULT NULL COMMENT '利润总额',
  `pure_profit` double DEFAULT NULL COMMENT '净利润',
  `total_tax_paid` double DEFAULT NULL COMMENT '纳税总额',
  `data_source` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '数据来源',
  `created_time` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '创建时间',
  `updated_time` varchar(50) CHARACTER SET utf8mb3 COLLATE utf8mb3_general_ci DEFAULT NULL COMMENT '更新时间'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb3 COMMENT='前海数据机构年报财务信息';
