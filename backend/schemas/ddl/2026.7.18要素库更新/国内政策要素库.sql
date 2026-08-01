-- 国内政策要素库建表 SQL
-- 来源文件：国内政策要素库(1).xlsx
-- 目标数据库：gkx_element
-- 字段注释格式：中文字段名/SQL类型

CREATE DATABASE IF NOT EXISTS `gkx_element`
  DEFAULT CHARACTER SET utf8mb4
  DEFAULT COLLATE utf8mb4_general_ci;

USE `gkx_element`;
SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

-- 国内政策信息表：dws_zck_policy
CREATE TABLE IF NOT EXISTS `dws_zck_policy` (
  `id` VARCHAR(255) NULL COMMENT '唯一ID/varchar(255) ',
  `datatype` DECIMAL(2,0) NOT NULL COMMENT '数据类型/decimal(2,0) ',
  `docstatus` DECIMAL(2,0) NOT NULL COMMENT '状态（20-已发布，30-已撤销）/decimal(2,0) ',
  `title` VARCHAR(1000) NOT NULL COMMENT '标题（纯文本）/varchar(1000) ',
  `titlena` VARCHAR(1000) NOT NULL COMMENT '标题（富文本）/varchar(1000) ',
  `content` LONGTEXT NOT NULL COMMENT '内容（纯文本）/longtext ',
  `contentNa` LONGTEXT NOT NULL COMMENT '内容（富文本）/longtext ',
  `url` VARCHAR(1000) NOT NULL COMMENT '原文链接地址/varchar(1000) ',
  `issueno` VARCHAR(255) NOT NULL COMMENT '发文字号/varchar(255) ',
  `indexno` VARCHAR(255) NOT NULL COMMENT '索引号/varchar(255) ',
  `sitename` VARCHAR(255) NOT NULL COMMENT '站点名称/varchar(255) ',
  `crtime` DATETIME NOT NULL COMMENT '成文日期/datetime ',
  `pubtime` DATETIME NOT NULL COMMENT '发文日期（发布日期）/datetime ',
  `effectivetime` DATETIME NOT NULL COMMENT '实施日期/datetime ',
  `pubyear` VARCHAR(4) NOT NULL COMMENT '发布年份/varchar(4) ',
  `area` VARCHAR(255) NOT NULL COMMENT '地区/varchar(255) ',
  `policylevel` VARCHAR(255) NOT NULL COMMENT '政策层级/varchar(255) ',
  `region` VARCHAR(255) NOT NULL COMMENT '政策地区/varchar(255) ',
  `attachments` LONGTEXT NOT NULL COMMENT '附件信息/longtext ',
  `keywords` VARCHAR(1000) NOT NULL COMMENT '关键词/varchar(1000) ',
  `abs` LONGTEXT NOT NULL COMMENT '摘要/longtext ',
  `maelements` TEXT NOT NULL COMMENT '政策主旨要素/text ',
  `ma_keypoints` TEXT NOT NULL COMMENT '政策要点/text ',
  `allfactors` TEXT NOT NULL COMMENT '政策扶持要素/text ',
  `complextaginfojson` TEXT NOT NULL COMMENT '标签集/text ',
  `pedigree` LONGTEXT NOT NULL COMMENT '政策谱系/longtext ',
  `ma_contenttypenew` VARCHAR(255) NOT NULL COMMENT '文件类型/varchar(255) ',
  `pubdeptname` VARCHAR(255) NOT NULL COMMENT '发布单位名称/varchar(255) ',
  `topic_type` VARCHAR(255) NOT NULL COMMENT '主题分类/varchar(255) ',
  `expiration_date` DATETIME NOT NULL COMMENT '失效日期/datetime ',
  KEY `idx_id` (`id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='国内政策信息表';

SET FOREIGN_KEY_CHECKS = 1;
