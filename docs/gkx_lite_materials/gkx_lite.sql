-- gkx_lite：轻量测试库（2026-10-18）
-- 目的：《亿级科技知识图谱引擎测试文档》专用的小数据源，7 张表共 64 行，
--       全链路（Paper/Journal/Person/Organization/IndustryChain/IndustryNode +
--       PUBLISHED_IN/AUTHORED_BY/BELONGS_TO_NODE）端到端可对账。
-- 口径：
--   * dwd_zh_paper / dwd_zh_journal / dwd_org_base_info / dwd_scholar / dwd_zh_author
--     结构照抄 gkx_dwd_local 同名表（列名与脚本 mapper 逐列对齐）；
--   * dwd_industry_chain_info 用老结构（chain_code/node_id/...）——gkx_dwd_local 里这张表
--     2026-10-14 重建后列名改成 industry_code/industry_link_code，现行脚本读 chain_code/node_id，
--     绑新结构表会抽出 0 个产业链/节点实体；gkx_element 里的同名表仍是老结构；
--   * dwd_org_industry_chain_dtl 结构照抄 gkx_element 同名表（gkx_dwd_local 中已不存在）。
-- 幂等：DROP + CREATE，可重复执行。
-- 预期产出（对账用）：
--   Paper 10 | Journal 5 | Person 6 | Organization 6 | IndustryChain 2 | IndustryNode 10
--   PUBLISHED_IN 10 | AUTHORED_BY 19 | BELONGS_TO_NODE 8

DROP DATABASE IF EXISTS gkx_lite;
CREATE DATABASE gkx_lite CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE gkx_lite;

-- 1. 中文论文（Paper 实体 + PUBLISHED_IN 边源表）
CREATE TABLE `dwd_zh_paper` (
  `pk_id` bigint NOT NULL AUTO_INCREMENT,
  `id` varchar(91) NOT NULL COMMENT '文献记录的唯一主键标识',
  `doi` varchar(512) DEFAULT NULL,
  `en_name` varchar(1024) DEFAULT NULL,
  `zh_name` varchar(1024) DEFAULT NULL,
  `publication_id` varchar(25) DEFAULT NULL COMMENT '关联出版物的id',
  `paper_type` varchar(255) DEFAULT NULL,
  `publication_type` varchar(255) DEFAULT NULL,
  `publication_zh_name` varchar(1024) DEFAULT NULL COMMENT '期刊中文名',
  `issn` varchar(32) DEFAULT NULL,
  `volume` varchar(128) DEFAULT NULL,
  `issue` varchar(128) DEFAULT NULL,
  `first_page` varchar(255) DEFAULT NULL,
  `last_page` varchar(255) DEFAULT NULL,
  `cover_year_start` varchar(22) DEFAULT NULL COMMENT '发表年份',
  `cover_date_start` varchar(255) DEFAULT NULL COMMENT '发表日期',
  `language_classify` tinyint DEFAULT NULL,
  `abstract_available` tinyint DEFAULT NULL,
  `open_access` tinyint DEFAULT NULL,
  `paper_url` longtext,
  `data_source` varchar(255) DEFAULT NULL,
  `download_num` bigint DEFAULT NULL,
  `created_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` datetime NOT NULL,
  `is_deleted` smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (`pk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文论文详情信息(轻量测试)';

INSERT INTO `dwd_zh_paper`
(id, doi, en_name, zh_name, publication_id, paper_type, publication_type, publication_zh_name, issn, volume, issue, first_page, last_page, cover_year_start, cover_date_start, language_classify, abstract_available, open_access, paper_url, data_source, download_num, updated_time) VALUES
('P2026L001', '10.3724/lite.2026.001', 'A Survey of Lightweight Knowledge Graph Construction', '轻量级知识图谱构建综述', 'J001', '期刊论文', '学术期刊', '中国科学:信息科学', '1674-7267', '56', '1', '1', '18', '2026', '2026-01-15', 1, 1, 1, 'https://example.org/p/P2026L001', 'lite_manual', 320, '2026-10-12 10:00:00'),
('P2026L002', '10.3724/lite.2026.002', 'Incremental Extraction of Entities from Large Tables', '大规模表格实体的增量抽取方法', 'J001', '期刊论文', '学术期刊', '中国科学:信息科学', '1674-7267', '56', '2', '19', '31', '2026', '2026-02-20', 1, 1, 0, 'https://example.org/p/P2026L002', 'lite_manual', 154, '2026-10-12 10:05:00'),
('P2026L003', '10.3724/lite.2026.003', 'Graph Storage Benchmark on Heterogeneous Clusters', '异构集群下图存储基准测试', 'J001', '期刊论文', '学术期刊', '中国科学:信息科学', '1674-7267', '56', '3', '32', '45', '2025', '2025-03-11', 1, 0, 0, 'https://example.org/p/P2026L003', 'lite_manual', 88, '2026-10-12 10:10:00'),
('P2026L004', '10.3724/lite.2026.004', 'Batched Upsert Strategies for Property Graphs', '属性图的批量 Upsert 策略', 'J002', '期刊论文', '学术期刊', '计算机学报', '0254-4164', '49', '4', '101', '116', '2026', '2026-04-08', 1, 1, 1, 'https://example.org/p/P2026L004', 'lite_manual', 265, '2026-10-12 10:15:00'),
('P2026L005', '10.3724/lite.2026.005', 'Entity Disambiguation with Multi-way Recall', '多路召回的实体消歧方法', 'J002', '期刊论文', '学术期刊', '计算机学报', '0254-4164', '49', '5', '117', '130', '2025', '2025-05-22', 1, 1, 0, 'https://example.org/p/P2026L005', 'lite_manual', 401, '2026-10-12 10:20:00'),
('P2026L006', '10.3724/lite.2026.006', 'A Sandbox for ETL Script Verification', '面向 ETL 脚本校验的沙箱设计', 'J003', '期刊论文', '学术期刊', '软件学报', '1000-9825', '37', '6', '601', '615', '2026', '2026-06-30', 1, 1, 1, 'https://example.org/p/P2026L006', 'lite_manual', 177, '2026-10-12 10:25:00'),
('P2026L007', '10.3724/lite.2026.007', 'Provenance Tracking in Knowledge Graph Pipelines', '知识图谱流水线中的溯源追踪', 'J003', '期刊论文', '学术期刊', '软件学报', '1000-9825', '37', '7', '616', '628', '2025', '2025-07-19', 1, 0, 0, 'https://example.org/p/P2026L007', 'lite_manual', 96, '2026-10-12 10:30:00'),
('P2026L008', '10.3724/lite.2026.008', 'Edge Index Selection for Labeled Property Graphs', '标签属性图的边索引选择', 'J004', '期刊论文', '学术期刊', '电子学报', '0372-2112', '54', '8', '1201', '1212', '2026', '2026-08-05', 1, 1, 0, 'https://example.org/p/P2026L008', 'lite_manual', 143, '2026-10-12 10:35:00'),
('P2026L009', '10.3724/lite.2026.009', 'Watermark-based Idempotent Rerun of Extract Jobs', '基于水位线的抽取任务幂等复跑', 'J005', '期刊论文', '学术期刊', '计算机研究与发展', '1000-1239', '63', '9', '1501', '1514', '2026', '2026-09-14', 1, 1, 1, 'https://example.org/p/P2026L009', 'lite_manual', 210, '2026-10-12 10:40:00'),
('P2026L010', '10.3724/lite.2026.010', 'Visual Exploration of Industry Chain Graphs', '产业链图谱的可视化探索', 'J005', '期刊论文', '学术期刊', '计算机研究与发展', '1000-1239', '63', '10', '1515', '1527', '2025', '2025-10-26', 1, 1, 0, 'https://example.org/p/P2026L010', 'lite_manual', 58, '2026-10-12 10:45:00');

-- 2. 中文期刊（Journal 实体）
CREATE TABLE `dwd_zh_journal` (
  `pk_id` bigint NOT NULL AUTO_INCREMENT,
  `publication_id` varchar(16) NOT NULL COMMENT '期刊id',
  `publication_type` varchar(255) DEFAULT NULL,
  `country` varchar(255) DEFAULT NULL,
  `zh_name` varchar(1024) DEFAULT NULL,
  `name_abbr` varchar(255) DEFAULT NULL,
  `en_name` varchar(1024) DEFAULT NULL,
  `iscn` varchar(255) DEFAULT NULL,
  `issn` varchar(255) DEFAULT NULL,
  `eissn` varchar(255) DEFAULT NULL,
  `founding_time` date DEFAULT NULL,
  `jn_official` text,
  `zh_description` text,
  `chief_editor` varchar(500) DEFAULT NULL,
  `organizer` varchar(1024) DEFAULT NULL,
  `publisher_place` varchar(255) DEFAULT NULL,
  `cite_nums` int DEFAULT NULL,
  `annual_publication` int DEFAULT NULL,
  `impact_score` double DEFAULT NULL,
  `jn_zone` varchar(255) DEFAULT NULL,
  `publication_cycle` varchar(255) DEFAULT NULL,
  `paper_nums` int DEFAULT NULL,
  `publisher` varchar(500) DEFAULT NULL,
  `created_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` datetime NOT NULL,
  `is_deleted` smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (`pk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文期刊详情信息(轻量测试)';

INSERT INTO `dwd_zh_journal`
(publication_id, publication_type, country, zh_name, name_abbr, en_name, issn, eissn, founding_time, jn_official, zh_description, chief_editor, organizer, publisher_place, cite_nums, annual_publication, impact_score, jn_zone, publication_cycle, paper_nums, publisher, updated_time) VALUES
('J001', '学术期刊', '中国', '中国科学:信息科学', '中国科学', 'SCIENTIA SINICA Informationis', '1674-7267', '1674-732X', '1950-01-01', 'https://example.org/j/J001', '信息科学领域综合性学术期刊', '主编甲', '中国科学杂志社', '北京', 52000, 200, 3.12, '1区', '月刊', 4000, '中国科学杂志社', '2026-10-11 09:00:00'),
('J002', '学术期刊', '中国', '计算机学报', '计学', 'Chinese Journal of Computers', '0254-4164', '0254-4324', '1978-01-01', 'https://example.org/j/J002', '中国计算机学会会刊', '主编乙', '中国计算机学会', '北京', 41000, 180, 2.86, '1区', '月刊', 3600, '中国计算机学会', '2026-10-11 09:05:00'),
('J003', '学术期刊', '中国', '软件学报', '软学', 'Journal of Software', '1000-9825', '1000-982X', '1990-01-01', 'https://example.org/j/J003', '软件工程领域核心期刊', '主编丙', '中国科学院软件研究所', '北京', 38000, 190, 2.65, '1区', '月刊', 3800, '中国科学院软件研究所', '2026-10-11 09:10:00'),
('J004', '学术期刊', '中国', '电子学报', '电学', 'Acta Electronica Sinica', '0372-2112', '0372-2120', '1962-01-01', 'https://example.org/j/J004', '电子与信息领域综合性期刊', '主编丁', '中国电子学会', '北京', 26000, 160, 2.05, '2区', '月刊', 3000, '中国电子学会', '2026-10-11 09:15:00'),
('J005', '学术期刊', '中国', '计算机研究与发展', '研发', 'Journal of Computer Research and Development', '1000-1239', '1000-1247', '1963-01-01', 'https://example.org/j/J005', '计算技术领域核心期刊', '主编戊', '中国计算机学会', '北京', 29000, 170, 2.21, '2区', '月刊', 3200, '中国计算机学会', '2026-10-11 09:20:00');

-- 3. 产业链图谱（IndustryChain + IndustryNode 实体）——老结构（chain_code/node_id）
CREATE TABLE `dwd_industry_chain_info` (
  `pk_id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `chain_code` varchar(255) NOT NULL COMMENT '产业链代码',
  `chain_name` varchar(255) NOT NULL COMMENT '产业链名称',
  `node_id` varchar(255) NOT NULL COMMENT '节点代码',
  `node_name` varchar(255) NOT NULL COMMENT '节点名称',
  `node_type` decimal(20,0) NOT NULL COMMENT '节点类型',
  `level` decimal(20,0) NOT NULL COMMENT '级别',
  `node_seq` decimal(20,0) DEFAULT NULL COMMENT '节点顺序',
  `parent_id` varchar(255) DEFAULT NULL COMMENT '父级编码',
  `parent_name` text COMMENT '父级名称',
  `node_imp_level` decimal(20,0) DEFAULT NULL COMMENT '节点重要度',
  `downstream_link_code` varchar(255) DEFAULT NULL COMMENT '下游节点编码',
  `node_stage` decimal(20,0) DEFAULT NULL COMMENT '节点阶段',
  `node_path` text COMMENT '节点路径',
  `data_source` varchar(255) NOT NULL,
  `created_time` datetime NOT NULL,
  `updated_time` datetime NOT NULL,
  PRIMARY KEY (`pk_id`),
  UNIQUE KEY `uk_chain_node` (`chain_code`, `node_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='市场研究-产业链-产业链图谱(轻量测试)';

INSERT INTO `dwd_industry_chain_info`
(chain_code, chain_name, node_id, node_name, node_type, level, node_seq, parent_id, parent_name, node_imp_level, downstream_link_code, node_stage, node_path, data_source, created_time, updated_time) VALUES
('IC0101', '集成电路产业链', 'IC0101001', '芯片设计', 1, 2, 1, 'IC0101', '集成电路产业链', 1, 'IC0101002', 1, '集成电路产业链>芯片设计', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0101', '集成电路产业链', 'IC0101002', '晶圆制造', 1, 2, 2, 'IC0101', '集成电路产业链', 1, 'IC0101003', 2, '集成电路产业链>晶圆制造', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0101', '集成电路产业链', 'IC0101003', '封装测试', 1, 2, 3, 'IC0101', '集成电路产业链', 0, 'IC0101004', 3, '集成电路产业链>封装测试', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0101', '集成电路产业链', 'IC0101004', '半导体材料', 1, 2, 4, 'IC0101', '集成电路产业链', 0, NULL, 3, '集成电路产业链>半导体材料', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0101', '集成电路产业链', 'IC0101005', 'EDA工具', 1, 2, 5, 'IC0101', '集成电路产业链', 1, NULL, 1, '集成电路产业链>EDA工具', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0202', '人工智能产业链', 'IC0202001', '算力基础设施', 1, 2, 1, 'IC0202', '人工智能产业链', 1, 'IC0202002', 1, '人工智能产业链>算力基础设施', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0202', '人工智能产业链', 'IC0202002', '大模型', 1, 2, 2, 'IC0202', '人工智能产业链', 1, 'IC0202003', 1, '人工智能产业链>大模型', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0202', '人工智能产业链', 'IC0202003', '行业应用', 1, 2, 3, 'IC0202', '人工智能产业链', 0, NULL, 3, '人工智能产业链>行业应用', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0202', '人工智能产业链', 'IC0202004', '智能传感器', 1, 2, 4, 'IC0202', '人工智能产业链', 0, NULL, 2, '人工智能产业链>智能传感器', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00'),
('IC0202', '人工智能产业链', 'IC0202005', '数据服务', 1, 2, 5, 'IC0202', '人工智能产业链', 0, NULL, 2, '人工智能产业链>数据服务', 'lite_manual', '2026-10-10 08:00:00', '2026-10-10 08:00:00');

-- 4. 机构基本信息（Organization 实体）
CREATE TABLE `dwd_org_base_info` (
  `dwd_id` bigint NOT NULL AUTO_INCREMENT COMMENT 'dwd_id',
  `org_id` varchar(255) NOT NULL COMMENT '机构id',
  `name_cn` varchar(255) NOT NULL COMMENT '机构名称',
  `incorporation_date` date DEFAULT NULL,
  `lerep` varchar(255) DEFAULT NULL COMMENT '法定代表人',
  `org_type` varchar(255) DEFAULT NULL,
  `registered_capital_value` double DEFAULT NULL,
  `address` text,
  `province` varchar(255) DEFAULT NULL,
  `city` varchar(255) DEFAULT NULL,
  `external_id` varchar(255) DEFAULT NULL COMMENT '统一社会信用代码',
  `area` varchar(255) DEFAULT NULL,
  `postal_code` varchar(255) DEFAULT NULL,
  `reg_status` varchar(255) DEFAULT NULL,
  `incorporation_year` double DEFAULT NULL,
  `industry` varchar(255) DEFAULT NULL,
  `data_source` varchar(255) NOT NULL,
  `org_size` varchar(255) DEFAULT NULL,
  `created_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` datetime NOT NULL,
  `is_deleted` smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (`dwd_id`),
  UNIQUE KEY `uk_org_id` (`org_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='企业机构-机构基本信息(轻量测试)';

INSERT INTO `dwd_org_base_info`
(org_id, name_cn, incorporation_date, lerep, org_type, registered_capital_value, address, province, city, external_id, area, postal_code, reg_status, incorporation_year, industry, data_source, org_size, updated_time) VALUES
('O2026L001', '中科天玑科技有限公司', '2016-03-18', '张守拙', '有限责任公司', 12000.0, '北京市海淀区知春路甲1号', '北京市', '北京市', '91110108MA01LITE01', '海淀区', '100190', '存续', 2016, '软件和信息技术服务业', 'lite_manual', '100-499人', '2026-10-11 11:00:00'),
('O2026L002', '华清智能装备（南京）有限公司', '2018-07-09', '李慎行', '有限责任公司', 8000.0, '江苏省南京市江宁区天元东路66号', '江苏省', '南京市', '91320115MA02LITE02', '江宁区', '211100', '存续', 2018, '专用设备制造业', 'lite_manual', '100-499人', '2026-10-11 11:05:00'),
('O2026L003', '深圳市量子芯半导体有限公司', '2015-11-30', '王铸精', '有限责任公司', 30000.0, '广东省深圳市南山区科苑南路8号', '广东省', '深圳市', '91440300MA03LITE03', '南山区', '518057', '存续', 2015, '计算机、通信和其他电子设备制造业', 'lite_manual', '500-999人', '2026-10-11 11:10:00'),
('O2026L004', '杭州云枢数据技术有限公司', '2020-05-20', '赵驭数', '有限责任公司', 5000.0, '浙江省杭州市西湖区文三路90号', '浙江省', '杭州市', '91330106MA04LITE04', '西湖区', '310012', '存续', 2020, '互联网和相关服务', 'lite_manual', '50-99人', '2026-10-11 11:15:00'),
('O2026L005', '武汉光谷激光工程有限公司', '2013-09-12', '钱聚光', '有限责任公司', 20000.0, '湖北省武汉市东湖新技术开发区光谷大道1号', '湖北省', '武汉市', '91420100MA05LITE05', '洪山区', '430074', '存续', 2013, '仪器仪表制造业', 'lite_manual', '500-999人', '2026-10-11 11:20:00'),
('O2026L006', '北京星图导航技术有限公司', '2019-12-05', '孙引航', '有限责任公司', 6600.0, '北京市朝阳区北辰西路8号', '北京市', '北京市', '91110105MA06LITE06', '朝阳区', '100101', '存续', 2019, '铁路、船舶、航空航天和其他运输设备制造业', 'lite_manual', '100-499人', '2026-10-11 11:25:00');

-- 5. 学者信息（Person 实体属性增强源）
CREATE TABLE `dwd_scholar` (
  `dwd_id` bigint NOT NULL AUTO_INCREMENT,
  `scholar_id` varchar(255) DEFAULT NULL,
  `name_en` varchar(255) DEFAULT NULL,
  `name_zh` varchar(255) DEFAULT NULL,
  `avatar` varchar(255) DEFAULT NULL,
  `scholar_org_name_en` longtext,
  `scholar_org_name_zh` varchar(255) DEFAULT NULL,
  `scholar_org_id` varchar(255) DEFAULT NULL,
  `orc_id` varchar(255) DEFAULT NULL,
  `bio_zh` longtext,
  `paper_nums` int DEFAULT NULL,
  `citation_nums` int DEFAULT NULL,
  `h_index` int DEFAULT NULL,
  `status` int DEFAULT NULL,
  `created_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` datetime NOT NULL,
  `is_deleted` smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (`dwd_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='学者信息表(轻量测试)';

INSERT INTO `dwd_scholar`
(scholar_id, name_en, name_zh, scholar_org_name_zh, scholar_org_id, orc_id, bio_zh, paper_nums, citation_nums, h_index, status, updated_time) VALUES
('A2026L001', 'ZHANG Shouzhuo', '张守拙', '中科天玑科技有限公司', 'O2026L001', '0000-0002-2026-0001', '知识图谱构建与大规模图数据管理方向研究员', 46, 1820, 18, 1, '2026-10-11 12:00:00'),
('A2026L002', 'LI Shenxing', '李慎行', '华清智能装备（南京）有限公司', 'O2026L002', '0000-0002-2026-0002', '智能装备与工业知识工程方向高级工程师', 32, 960, 14, 1, '2026-10-11 12:05:00'),
('A2026L003', 'WANG Zhujing', '王铸精', '深圳市量子芯半导体有限公司', 'O2026L003', '0000-0002-2026-0003', '半导体工艺与产业链建模方向研究员', 58, 3100, 24, 1, '2026-10-11 12:10:00'),
('A2026L004', 'ZHAO Yushu', '赵驭数', '杭州云枢数据技术有限公司', 'O2026L004', '0000-0002-2026-0004', '数据治理与实体消歧方向工程师', 21, 430, 10, 1, '2026-10-11 12:15:00'),
('A2026L005', 'QIAN Juguang', '钱聚光', '武汉光谷激光工程有限公司', 'O2026L005', '0000-0002-2026-0005', '激光装备与产业图谱方向研究员', 39, 1280, 16, 1, '2026-10-11 12:20:00'),
('A2026L006', 'SUN Yinhang', '孙引航', '北京星图导航技术有限公司', 'O2026L006', '0000-0002-2026-0006', '导航定位与图可视化方向工程师', 27, 710, 12, 1, '2026-10-11 12:25:00');

-- 6. 中文文献作者（AUTHORED_BY 边 + Person 实体源）
CREATE TABLE `dwd_zh_author` (
  `pk_id` bigint NOT NULL AUTO_INCREMENT,
  `paper_id` varchar(91) DEFAULT NULL,
  `author_sequence` int DEFAULT NULL,
  `author_id` varchar(255) DEFAULT NULL,
  `en_name` varchar(1024) DEFAULT NULL,
  `zh_name` varchar(305) DEFAULT NULL,
  `email` text,
  `correspond` tinyint DEFAULT NULL,
  `institution` text,
  `created_time` datetime NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_time` datetime NOT NULL,
  `is_deleted` smallint NOT NULL DEFAULT 0,
  PRIMARY KEY (`pk_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='中文文献作者详情信息(轻量测试)';

INSERT INTO `dwd_zh_author`
(paper_id, author_sequence, author_id, en_name, zh_name, email, correspond, institution, updated_time) VALUES
('P2026L001', 1, 'A2026L001', 'ZHANG Shouzhuo', '张守拙', '["zhangsz@lite.org"]', 1, '中科天玑科技有限公司', '2026-10-12 11:00:00'),
('P2026L001', 2, 'A2026L002', 'LI Shenxing', '李慎行', '["lisx@lite.org"]', 0, '华清智能装备（南京）有限公司', '2026-10-12 11:00:00'),
('P2026L001', 3, 'A2026L003', 'WANG Zhujing', '王铸精', '["wangzj@lite.org"]', 0, '深圳市量子芯半导体有限公司', '2026-10-12 11:00:00'),
('P2026L002', 1, 'A2026L001', 'ZHANG Shouzhuo', '张守拙', '["zhangsz@lite.org"]', 1, '中科天玑科技有限公司', '2026-10-12 11:05:00'),
('P2026L002', 2, 'A2026L004', 'ZHAO Yushu', '赵驭数', '["zhaoys@lite.org"]', 0, '杭州云枢数据技术有限公司', '2026-10-12 11:05:00'),
('P2026L003', 1, 'A2026L003', 'WANG Zhujing', '王铸精', '["wangzj@lite.org"]', 0, '深圳市量子芯半导体有限公司', '2026-10-12 11:10:00'),
('P2026L003', 2, 'A2026L005', 'QIAN Juguang', '钱聚光', '["qianjg@lite.org"]', 1, '武汉光谷激光工程有限公司', '2026-10-12 11:10:00'),
('P2026L004', 1, 'A2026L002', 'LI Shenxing', '李慎行', '["lisx@lite.org"]', 1, '华清智能装备（南京）有限公司', '2026-10-12 11:15:00'),
('P2026L004', 2, 'A2026L006', 'SUN Yinhang', '孙引航', '["sunyh@lite.org"]', 0, '北京星图导航技术有限公司', '2026-10-12 11:15:00'),
('P2026L005', 1, 'A2026L004', 'ZHAO Yushu', '赵驭数', '["zhaoys@lite.org"]', 1, '杭州云枢数据技术有限公司', '2026-10-12 11:20:00'),
('P2026L006', 1, 'A2026L001', 'ZHANG Shouzhuo', '张守拙', '["zhangsz@lite.org"]', 0, '中科天玑科技有限公司', '2026-10-12 11:25:00'),
('P2026L006', 2, 'A2026L005', 'QIAN Juguang', '钱聚光', '["qianjg@lite.org"]', 1, '武汉光谷激光工程有限公司', '2026-10-12 11:25:00'),
('P2026L006', 3, 'A2026L006', 'SUN Yinhang', '孙引航', '["sunyh@lite.org"]', 0, '北京星图导航技术有限公司', '2026-10-12 11:25:00'),
('P2026L007', 1, 'A2026L003', 'WANG Zhujing', '王铸精', '["wangzj@lite.org"]', 1, '深圳市量子芯半导体有限公司', '2026-10-12 11:30:00'),
('P2026L008', 1, 'A2026L002', 'LI Shenxing', '李慎行', '["lisx@lite.org"]', 0, '华清智能装备（南京）有限公司', '2026-10-12 11:35:00'),
('P2026L008', 2, 'A2026L004', 'ZHAO Yushu', '赵驭数', '["zhaoys@lite.org"]', 1, '杭州云枢数据技术有限公司', '2026-10-12 11:35:00'),
('P2026L009', 1, 'A2026L006', 'SUN Yinhang', '孙引航', '["sunyh@lite.org"]', 1, '北京星图导航技术有限公司', '2026-10-12 11:40:00'),
('P2026L010', 1, 'A2026L005', 'QIAN Juguang', '钱聚光', '["qianjg@lite.org"]', 1, '武汉光谷激光工程有限公司', '2026-10-12 11:45:00'),
('P2026L010', 2, 'A2026L001', 'ZHANG Shouzhuo', '张守拙', '["zhangsz@lite.org"]', 0, '中科天玑科技有限公司', '2026-10-12 11:45:00');

-- 7. 产业关联企业（BELONGS_TO_NODE 边）——结构照抄 gkx_element 同名表
CREATE TABLE `dwd_org_industry_chain_dtl` (
  `chain_code` varchar(255) NOT NULL,
  `chain_name` varchar(255) NOT NULL,
  `node_id` varchar(255) NOT NULL,
  `node_name` varchar(255) NOT NULL,
  `antitypic` varchar(255) NOT NULL COMMENT '企业id(=dwd_org_base_info.org_id)',
  `credit_code` varchar(255) DEFAULT NULL,
  `chain_score` decimal(20,2) DEFAULT NULL,
  `data_source` varchar(255) NOT NULL,
  `created_time` datetime NOT NULL,
  `updated_time` datetime NOT NULL,
  PRIMARY KEY (`chain_code`, `node_id`, `antitypic`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='产业关联企业信息(轻量测试)';

INSERT INTO `dwd_org_industry_chain_dtl`
(chain_code, chain_name, node_id, node_name, antitypic, credit_code, chain_score, data_source, created_time, updated_time) VALUES
('IC0101', '集成电路产业链', 'IC0101001', '芯片设计', 'O2026L001', '91110108MA01LITE01', 0.92, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00'),
('IC0101', '集成电路产业链', 'IC0101003', '封装测试', 'O2026L001', '91110108MA01LITE01', 0.85, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00'),
('IC0101', '集成电路产业链', 'IC0101002', '晶圆制造', 'O2026L003', '91440300MA03LITE03', 0.95, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00'),
('IC0101', '集成电路产业链', 'IC0101004', '半导体材料', 'O2026L003', '91440300MA03LITE03', 0.80, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00'),
('IC0101', '集成电路产业链', 'IC0101005', 'EDA工具', 'O2026L005', '91420100MA05LITE05', 0.70, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00'),
('IC0202', '人工智能产业链', 'IC0202001', '算力基础设施', 'O2026L002', '91320115MA02LITE02', 0.75, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00'),
('IC0202', '人工智能产业链', 'IC0202003', '行业应用', 'O2026L002', '91320115MA02LITE02', 0.88, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00'),
('IC0202', '人工智能产业链', 'IC0202005', '数据服务', 'O2026L004', '91330106MA04LITE04', 0.90, 'lite_manual', '2026-10-11 13:00:00', '2026-10-11 13:00:00');
