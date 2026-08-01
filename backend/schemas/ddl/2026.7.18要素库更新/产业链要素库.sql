-- 产业链要素库建表 SQL
-- 来源文件：产业链要素库(1).xlsx
-- 目标数据库：gkx_element
CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 产业链图谱：dwd_industry_chain_info
CREATE TABLE IF NOT EXISTS `dwd_industry_chain_info` (
  `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称/varchar(255) ',
  `node_id` VARCHAR(255) NOT NULL COMMENT '节点代码/varchar(255) ',
  `node_name` VARCHAR(255) NOT NULL COMMENT '节点名称/varchar(255) ',
  `node_type` DECIMAL(20,0) NOT NULL COMMENT '节点类型/decimal(20,0) ',
  `level` DECIMAL(20,0) NOT NULL COMMENT '节点层级/decimal(20,0) ',
  `node_seq` DECIMAL(20,0) NULL COMMENT '节点序号/decimal(20,0) ',
  `parent_id` VARCHAR(255) NULL COMMENT '父级节点代码/varchar(255) ',
  `parent_name` TEXT NULL COMMENT '父级节点名称/text ',
  `node_imp_level` DECIMAL(20,0) NULL COMMENT '节点重要性等级/decimal(20,0) ',
  `downstream_link_code` VARCHAR(255) NULL COMMENT '下游节点代码/varchar(255) ',
  `node_stage` DECIMAL(20,0) NULL COMMENT '节点环节/decimal(20,0) ',
  `node_path` TEXT NULL COMMENT '节点路径/text ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_node_id` (`node_id`),
  KEY `idx_node_imp_level` (`node_imp_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链图谱';

-- 产业关联企业信息：dwd_org_industry_chain_dtl
CREATE TABLE IF NOT EXISTS `dwd_org_industry_chain_dtl` (
  `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称/varchar(255) ',
  `node_id` VARCHAR(255) NOT NULL COMMENT '节点代码/varchar(255) ',
  `node_name` VARCHAR(255) NOT NULL COMMENT '节点名称/varchar(255) ',
  `antitypic` VARCHAR(255) NOT NULL COMMENT '企业id/varchar(255) ',
  `credit_code` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `chain_score` DECIMAL(20,2) NULL COMMENT '产业链评分/decimal(20,2) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_node_id` (`node_id`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业关联企业信息';

-- 产业链企业关联产品信息：dwd_org_industry_chain_prod_dtl
CREATE TABLE IF NOT EXISTS `dwd_org_industry_chain_prod_dtl` (
  `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称/varchar(255) ',
  `antitypic` VARCHAR(255) NOT NULL COMMENT '企业id/varchar(255) ',
  `company_name` VARCHAR(500) NULL COMMENT '企业名称/varchar(500) ',
  `credit_code` VARCHAR(255) NULL COMMENT '统一社会信用代码/varchar(255) ',
  `tech_product` VARCHAR(255) NOT NULL COMMENT '主营产品名称/varchar(255) ',
  `tech_product_seq` DECIMAL(20,0) NULL COMMENT '主营产品排序/decimal(20,0) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`),
  KEY `idx_antitypic` (`antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业链企业关联产品信息';

-- 产业动态资讯：dwd_industry_chain_news_info
CREATE TABLE IF NOT EXISTS `dwd_industry_chain_news_info` (
  `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链代码/varchar(255) ',
  `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称/varchar(255) ',
  `news_id` VARCHAR(255) NOT NULL COMMENT '资讯id/varchar(255) ',
  `title` VARCHAR(255) NULL COMMENT '标题/varchar(255) ',
  `relaese_date` DATETIME NULL COMMENT '发布时间/datetime ',
  `summary` TEXT NULL COMMENT '摘要/text ',
  `source` VARCHAR(255) NULL COMMENT '来源/varchar(255) ',
  `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源/varchar(255) ',
  `created_time` DATETIME NOT NULL COMMENT '创建时间/datetime ',
  `updated_time` DATETIME NOT NULL COMMENT '更新时间/datetime ',
  KEY `idx_chain_code` (`chain_code`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业动态资讯';

SET FOREIGN_KEY_CHECKS = 1;

-- 建表后检查：
-- USE `gkx_element`;
-- SHOW TABLES;
