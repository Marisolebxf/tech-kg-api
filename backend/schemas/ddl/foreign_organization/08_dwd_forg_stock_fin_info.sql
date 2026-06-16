CREATE TABLE IF NOT EXISTS dwd_forg_stock_fin_info (
    `org_id` VARCHAR(255) NOT NULL COMMENT '机构id',
    `occur_period` DATE COMMENT '报告期',
    `total_assets` DECIMAL(20,2) COMMENT '资产总额',
    `fixed_assets` DECIMAL(20,2) COMMENT '固定资产总额',
    `total_liabilities` DECIMAL(20,2) COMMENT '负债总额',
    `operating_revenue` DECIMAL(20,2) COMMENT '营业收入',
    `main_business_revenue` DECIMAL(20,2) COMMENT '主营业务收入',
    `total_profit` DECIMAL(20,2) COMMENT '利润总额',
    `pure_profit` DECIMAL(20,2) COMMENT '净利润',
    `total_tax_paid` DECIMAL(20,2) COMMENT '企业所得税',
    `oper_cash_flow` DECIMAL(20,2) COMMENT '经营活动现金流',
    `owners_equity` DECIMAL(20,2) COMMENT '所有者权益合计',
    `employees_number` DECIMAL(20,2) COMMENT '从业人数',
    `research_development_amount` DECIMAL(20,2) COMMENT '研发投入金额',
    `research_development_employees_number` DECIMAL(20,2) COMMENT '研发人员数（无数据）'
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='海外上市企业财务信息';
