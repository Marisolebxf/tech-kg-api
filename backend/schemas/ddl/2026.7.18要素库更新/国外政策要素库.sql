-- 国外政策要素库建表 SQL
-- 来源文件：国外政策要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 国际政策信息表：dwd_zck_intl_policy
CREATE TABLE IF NOT EXISTS `dwd_zck_intl_policy` (
  `recordId` VARCHAR(255) NULL COMMENT '唯一ID/varchar(255) ',
  `sy_urltitle` VARCHAR(1000) NOT NULL COMMENT '标题原文/varchar(1000) ',
  `fy_urltitle` VARCHAR(1000) NOT NULL COMMENT '标题译文/varchar(1000) ',
  `sy_content` LONGTEXT NOT NULL COMMENT '正文原文/longtext ',
  `fy_content` LONGTEXT NOT NULL COMMENT '正文译文/longtext ',
  `sy_abstract` VARCHAR(2000) NOT NULL COMMENT '摘要原文/varchar(2000) ',
  `sy_media_area` VARCHAR(255) NOT NULL COMMENT '所属区域/varchar(255) ',
  `ir_urldate` VARCHAR(255) NOT NULL COMMENT '发布时间/varchar(255) ',
  `sy_media_product_name` VARCHAR(255) NOT NULL COMMENT '媒体名称/varchar(255) ',
  `ir_urlname` VARCHAR(1000) NOT NULL COMMENT 'URL链接/varchar(1000) ',
  `ir_language` VARCHAR(255) NOT NULL COMMENT '语种/varchar(255) ',
  `media_type` VARCHAR(255) NOT NULL COMMENT '媒体类型/varchar(255) ',
  KEY `idx_recordId` (`recordId`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国际政策信息表';

SET FOREIGN_KEY_CHECKS = 1;
