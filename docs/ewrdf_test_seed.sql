-- ewrdf 图空间全链路测试专用库:把 gkx_element 数仓的白名单行搬进独立小库(共 104 行)。
-- 执行(必须带 --default-character-set=utf8mb4,缺省字符集会把中文比较/中文数据弄坏,实测中文全变 ??):
--   docker exec -i tech-kg-mysql mysql --default-character-set=utf8mb4 -uroot -pgkx_element < docs/ewrdf_test_seed.sql
-- 核对行数(预期 t_org 12 / t_executive 27 / t_expert 25 / t_paper 10 / t_journal 4 / t_author_paper 20 / t_shareholder 6):
--   docker exec tech-kg-mysql mysql --default-character-set=utf8mb4 -uroot -pgkx_element -N -e "
--     SELECT 't_org',COUNT(*) FROM ewrdf_test.t_org UNION ALL SELECT 't_executive',COUNT(*) FROM ewrdf_test.t_executive
--     UNION ALL SELECT 't_expert',COUNT(*) FROM ewrdf_test.t_expert UNION ALL SELECT 't_paper',COUNT(*) FROM ewrdf_test.t_paper
--     UNION ALL SELECT 't_journal',COUNT(*) FROM ewrdf_test.t_journal UNION ALL SELECT 't_author_paper',COUNT(*) FROM ewrdf_test.t_author_paper
--     UNION ALL SELECT 't_shareholder',COUNT(*) FROM ewrdf_test.t_shareholder;"
-- 清理:DROP DATABASE IF EXISTS ewrdf_test;

CREATE DATABASE IF NOT EXISTS ewrdf_test DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;
USE ewrdf_test;

-- ---------- 实体源表 ----------

-- 机构(12 行)→ 绑定给 Organization
-- 列名与抽取脚本读取字段同名;主键列放第一列(UI 自动选中),时间列命名 update_time(UI 自动选中)
CREATE TABLE t_org (
  org_id varchar(255) NOT NULL,
  name_cn varchar(255) NOT NULL,
  province varchar(255) DEFAULT NULL,
  city varchar(255) DEFAULT NULL,
  industry_l1_name varchar(255) DEFAULT NULL,
  reg_status varchar(255) DEFAULT NULL,
  registered_capital_value decimal(20,2) DEFAULT NULL,
  update_time datetime DEFAULT NULL,
  PRIMARY KEY (org_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO t_org
SELECT org_id, name_cn, province, city, industry_l1_name, reg_status, registered_capital_value, updated_time
FROM gkx_element.dwd_org_base_info
WHERE org_id IN ('6316ee16a50a0a093a5859d8b5cc67a8','98e68fdf64b81709249dc23816a89c66',
 '6c25d2e2c852ba5a81d733cefaf5fe7b','69c0d92da4105991cedee6335fb44412',
 '0a14fdb97eb7d2892654ee2ef180b527','cbeac662cf32b19dcdb872790e4df8da',
 '8e04394509161ebbdf63c1813b948955','71aa92091eda2d2b872ca903d05d6d5d',
 'f21c867cb7a12e7f175c422de0e939a4','3d9ba778337dba72db8cc12a1bbb92be',
 'e9f6a720f02bb2143dd0f926b82f07f3','6ed1fec4b9de17f467edc5dd0af0c89a');

-- 高管(27 行)→ 绑定给 Officer、EXECUTIVE_OF(两 schema 共用此表)
-- row_id 已物化(原表 org_id+executives_name 复合才唯一),主键列真实唯一
CREATE TABLE t_executive (
  row_id varchar(600) NOT NULL,
  org_id varchar(255) NOT NULL,
  executives_name varchar(255) NOT NULL,
  executives_position varchar(255) DEFAULT NULL,
  update_time datetime DEFAULT NULL,
  PRIMARY KEY (row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO t_executive
SELECT CONCAT(org_id,'__',executives_name), org_id, executives_name, executives_position, updated_time
FROM gkx_element.dwd_org_executive_info
WHERE org_id IN ('6316ee16a50a0a093a5859d8b5cc67a8','6c25d2e2c852ba5a81d733cefaf5fe7b',
 '0a14fdb97eb7d2892654ee2ef180b527','8e04394509161ebbdf63c1813b948955',
 'f21c867cb7a12e7f175c422de0e939a4','e9f6a720f02bb2143dd0f926b82f07f3');

-- 专家(25 行)→ 绑定给 Expert
-- 含樊杰同名组(消歧灰区素材)与 2 条空名行(抽取失败素材),与手册方案 A 同一白名单
CREATE TABLE t_expert (
  author_id varchar(32) NOT NULL,
  zh_name varchar(255) DEFAULT NULL,
  institution text,
  update_time datetime DEFAULT NULL,
  PRIMARY KEY (author_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO t_expert
SELECT author_id, zh_name, institution, updated_time
FROM gkx_element.dwd_zh_author
WHERE author_id IN ('cafb9c466b2d74de158d995bef134639','36e40fcc42d2bec87f7c423211213dfb',
 '59dce19adb29701688a1ce9a63069aea','134066be56583f1327557f7898825a18',
 '50ef5f551c4a7fad56dcd82b2bdf6da2','d2b9bda08f8130b8dab54e1aa6ae6b98',
 '0f2f8f6e8903effb92ff99d39f936787','a7b0e09a0ff6d3337a5fee9ba4434844',
 'ff60369aa3eb6daad43d30000fa43e4b','fb9e2948f22da487fb3338ba1f4e072a',
 '73fdfa939f5bc499b86582316981b1db','53e7d89bd0f34628b6ef2f7055d8eec4',
 '24db008db3d0781a7bd6cd35a4f3922c','47330a8c229cc0b1f03129685eaa4763',
 '717546ccc349b6d95a2050122c6a7664','eb01531ab783e0f19a7fe36aad02c5cc',
 '264fb2e63afff07020233920a4d7a11b','8f7a5550dc2be9517d371be0448804f2',
 '12aea370e3b46b1dc7e6570a6cd639b9','eb7e28ffc6a0edf21580dddc0aced796',
 '2c3dfa15fa2b0f1adac5b7c835ca00dc','170795a90339520c3673f72508b5ba6f',
 'da151fbcb5e621d9b2ce6754a0859f63',
 '80960999b7bfd9f089b86c88796b3bcb','792f74d99a0bd137118b239fac5047ef');

-- 论文(10 行)→ 绑定给 Paper、PUBLISHED_IN(两 schema 共用此表)
CREATE TABLE t_paper (
  id varchar(64) NOT NULL,
  zh_name varchar(1024) DEFAULT NULL,
  doi varchar(512) DEFAULT NULL,
  cover_year_start varchar(4) DEFAULT NULL,
  publication_id bigint DEFAULT NULL,
  update_time datetime DEFAULT NULL,
  PRIMARY KEY (id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO t_paper
SELECT id, zh_name, doi, cover_year_start, publication_id, updated_time
FROM gkx_element.dwd_zh_paper
WHERE id IN ('1002153099575427075','1002153099575427078','1002153099575427082','1002153099575427088',
 '1002153099575427093','1002613259049631753','1005773515376295936','1005773515376295942',
 '1012001490740445188','1012001490740445198');

-- 期刊(4 行,已按 publication_id 预去重)→ 绑定给 Journal
-- 源表 dwd_zh_journal 按论文一行(4 刊合计 2000 行),这里 GROUP BY 物化去重,
-- 免去抽取时翻 2000 行(方案 A 的量控瑕疵在此根治);脚本内按 publication_id 去重逻辑变为空转,兼容
CREATE TABLE t_journal (
  row_id varchar(64) NOT NULL,
  publication_id bigint NOT NULL,
  zh_name varchar(1024) DEFAULT NULL,
  issn varchar(16) DEFAULT NULL,
  update_time datetime DEFAULT NULL,
  PRIMARY KEY (row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO t_journal
SELECT CONCAT(publication_id,'__journal'), publication_id,
       MAX(NULLIF(zh_name,'')), MAX(NULLIF(issn,'')), MAX(updated_time)
FROM gkx_element.dwd_zh_journal
WHERE publication_id IN ('1009219','1006062','1004427','1004798')
GROUP BY publication_id;

-- ---------- 关系源表 ----------

-- 论文-作者对(20 行,前 2 作者)→ 绑定给 AUTHORED_BY、COAUTHOR_WITH(两 schema 共用此表)
CREATE TABLE t_author_paper (
  row_id varchar(160) NOT NULL,
  paper_id varchar(64) NOT NULL,
  author_id varchar(32) NOT NULL,
  author_sequence int DEFAULT NULL,
  zh_name varchar(255) DEFAULT NULL,
  update_time datetime DEFAULT NULL,
  PRIMARY KEY (row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO t_author_paper
SELECT CONCAT(paper_id,'__',author_id), paper_id, author_id, author_sequence, zh_name, updated_time
FROM gkx_element.dwd_zh_author
WHERE author_sequence<=2 AND paper_id IN ('1002153099575427075','1002153099575427078','1002153099575427082',
 '1002153099575427088','1002153099575427093','1002613259049631753','1005773515376295936',
 '1005773515376295942','1012001490740445188','1012001490740445198');

-- 单位持股对(6 行,双端均在 t_org 内的闭合对)→ 绑定给 SHAREHOLDER_OF
CREATE TABLE t_shareholder (
  row_id varchar(600) NOT NULL,
  org_id varchar(255) NOT NULL,
  inv_org_id varchar(255) NOT NULL,
  owners_name varchar(255) DEFAULT NULL,
  ownership_percentage decimal(20,2) DEFAULT NULL,
  update_time datetime DEFAULT NULL,
  PRIMARY KEY (row_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

INSERT INTO t_shareholder
SELECT CONCAT(org_id,'__',inv_org_id), org_id, inv_org_id, owners_name, ownership_percentage, updated_time
FROM gkx_element.dwd_org_shareholder_info
WHERE owners_type='单位'
  AND org_id IN ('6316ee16a50a0a093a5859d8b5cc67a8','6c25d2e2c852ba5a81d733cefaf5fe7b',
   '0a14fdb97eb7d2892654ee2ef180b527','8e04394509161ebbdf63c1813b948955',
   'f21c867cb7a12e7f175c422de0e939a4','e9f6a720f02bb2143dd0f926b82f07f3')
  AND inv_org_id IN ('98e68fdf64b81709249dc23816a89c66','69c0d92da4105991cedee6335fb44412',
   'cbeac662cf32b19dcdb872790e4df8da','71aa92091eda2d2b872ca903d05d6d5d',
   '3d9ba778337dba72db8cc12a1bbb92be','6ed1fec4b9de17f467edc5dd0af0c89a');
