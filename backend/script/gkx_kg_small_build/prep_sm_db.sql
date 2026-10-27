-- gkx_kg_sm：从 gkx_kg 抽真实小样例（宿主 tech-kg-mysql 上执行）。
-- 用途：dev2 主栈"图谱构建"全流程小数据演练 —— 库、表全部真实行，不造模拟数据。
--
--   docker exec -i tech-kg-mysql mysql -uroot -pgkx_element \
--       --default-character-set=utf8mb4 < prep_sm_db.sql
--
-- 口径：
--   1) 每种边类型从 v_kg_edge（已过滤双端点存在）取前 5 条 → sm_edge；
--   2) 端点 vid 反查回 15 张实体表（全列真实行）；
--   3) 按"有效名"（主名列，空则取步脚本的首个回退列）削减样本内重名/无名实体
--      —— gray-gate 同名候选会 DEFERRED_MERGE_BLOCKED 整链 FAILED；再削掉悬空边；
--   4) 报表：各表行数 + 各边类型行数。若某实体表为 0 行，用文末模板补孤立顶点。
-- 幂等：整库重建（DROP 后 CREATE）。

CREATE DATABASE IF NOT EXISTS gkx_kg_sm DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_0900_ai_ci;
USE gkx_kg_sm;
SET NAMES utf8mb4;

-- ---------- 1) 边采样 ----------
DROP TABLE IF EXISTS sm_edge;
CREATE TABLE sm_edge (
  edge_type VARCHAR(64) NOT NULL,
  src_id    VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL,
  dst_id    VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL,
  edge_rank INT NOT NULL DEFAULT 0,
  props     JSON NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT INTO sm_edge (edge_type, src_id, dst_id, edge_rank, props)
SELECT t.edge_type, t.src_id, t.dst_id, t.edge_rank, t.props
FROM (
  SELECT e.*, ROW_NUMBER() OVER (
           PARTITION BY e.edge_type ORDER BY e.src_id, e.dst_id, e.edge_rank) AS rn
  FROM gkx_kg.v_kg_edge e
) t
WHERE t.rn <= 5;

-- ---------- 1b) 端点无名/同名导致整型被削的边类型：定向重采样 ----------
-- INVOLVED_IN 首批事件是"年报财务信息"等批量同名标题 → 换成全库唯一标题事件；
-- INVESTS_IN/ACQUIRES 首批被投/被购机构 name_cn/name_en 双空 → 换成双端具名机构对；
-- LEGAL_REP_OF 首批人也常无名/重名 → 换成双端具名（人+机构）；
-- CITES 桩 99.96% 无标题且具名桩全是 8899 演示造数 → 不重采样，接受 0 边。
-- 注意：60 万行视图上做 CONCAT..COLLATE 的 IN 子查询会退成嵌套循环，必须先物化具名
-- 端点速查表（带主键）再 JOIN。
DELETE FROM sm_edge WHERE edge_type IN ('INVOLVED_IN', 'INVESTS_IN', 'ACQUIRES', 'LEGAL_REP_OF');

DROP TABLE IF EXISTS sm_h_named_org;
CREATE TABLE sm_h_named_org (
  vid VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
SELECT DISTINCT CONCAT('org_', org_id) COLLATE utf8mb4_general_ci AS vid
FROM gkx_kg.kg_organization
WHERE COALESCE(NULLIF(TRIM(name_cn),''),NULLIF(TRIM(name_en),'')) IS NOT NULL;

DROP TABLE IF EXISTS sm_h_uniq_event;
CREATE TABLE sm_h_uniq_event (
  vid VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
SELECT DISTINCT CONCAT('event_', e.event_id) COLLATE utf8mb4_general_ci AS vid
FROM gkx_kg.kg_event e
JOIN (SELECT title FROM gkx_kg.kg_event
      WHERE title IS NOT NULL AND TRIM(title) <> ''
      GROUP BY title HAVING COUNT(*) = 1) u ON u.title = e.title
WHERE TRIM(e.title) <> '';

DROP TABLE IF EXISTS sm_h_named_stub;
CREATE TABLE sm_h_named_stub (
  vid VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
SELECT DISTINCT CONCAT('paper_ref_', SUBSTRING(id, 5)) COLLATE utf8mb4_general_ci AS vid
FROM gkx_kg.kg_citation_stub
WHERE COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) IS NOT NULL;

INSERT INTO sm_edge (edge_type, src_id, dst_id, edge_rank, props)
SELECT e.edge_type, e.src_id, e.dst_id, e.edge_rank, e.props
FROM gkx_kg.v_kg_edge e
JOIN sm_h_named_org s ON s.vid = e.src_id
JOIN sm_h_uniq_event d ON d.vid = e.dst_id
WHERE e.edge_type = 'INVOLVED_IN'
ORDER BY e.src_id, e.dst_id, e.edge_rank LIMIT 5;

INSERT INTO sm_edge (edge_type, src_id, dst_id, edge_rank, props)
SELECT e.edge_type, e.src_id, e.dst_id, e.edge_rank, e.props
FROM gkx_kg.v_kg_edge e
JOIN sm_h_named_org s ON s.vid = e.src_id
JOIN sm_h_named_org d ON d.vid = e.dst_id
WHERE e.edge_type = 'INVESTS_IN'
ORDER BY e.src_id, e.dst_id, e.edge_rank LIMIT 5;

INSERT INTO sm_edge (edge_type, src_id, dst_id, edge_rank, props)
SELECT e.edge_type, e.src_id, e.dst_id, e.edge_rank, e.props
FROM gkx_kg.v_kg_edge e
JOIN sm_h_named_org s ON s.vid = e.src_id
JOIN sm_h_named_org d ON d.vid = e.dst_id
WHERE e.edge_type = 'ACQUIRES'
ORDER BY e.src_id, e.dst_id, e.edge_rank LIMIT 5;

DROP TABLE IF EXISTS sm_h_named_person;
CREATE TABLE sm_h_named_person (
  vid VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
SELECT DISTINCT CONCAT('person_', person_id) COLLATE utf8mb4_general_ci AS vid
FROM gkx_kg.kg_person
WHERE COALESCE(NULLIF(TRIM(name_zh),''),NULLIF(TRIM(name_en),'')) IS NOT NULL;

INSERT INTO sm_edge (edge_type, src_id, dst_id, edge_rank, props)
SELECT e.edge_type, e.src_id, e.dst_id, e.edge_rank, e.props
FROM gkx_kg.v_kg_edge e
JOIN sm_h_named_person s ON s.vid = e.src_id
JOIN sm_h_named_org d ON d.vid = e.dst_id
WHERE e.edge_type = 'LEGAL_REP_OF'
ORDER BY e.src_id, e.dst_id, e.edge_rank LIMIT 5;

DROP TABLE sm_h_named_org;
DROP TABLE sm_h_uniq_event;
DROP TABLE sm_h_named_stub;
DROP TABLE sm_h_named_person;

-- ---------- 2) 端点 vid 全集 ----------
DROP TABLE IF EXISTS sm_vids;
CREATE TABLE sm_vids (
  vid VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT IGNORE INTO sm_vids SELECT DISTINCT src_id FROM sm_edge;
INSERT IGNORE INTO sm_vids SELECT DISTINCT dst_id FROM sm_edge;

-- ---------- 3) 实体小表（全列，真实行；vid = 前缀 + 主键） ----------
DROP TABLE IF EXISTS sm_person;
CREATE TABLE sm_person AS
SELECT s.* FROM gkx_kg.kg_person s
JOIN sm_vids v ON v.vid = CONCAT('person_', s.person_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_paper;
CREATE TABLE sm_paper AS
SELECT s.* FROM gkx_kg.kg_paper s
JOIN sm_vids v ON v.vid = CONCAT('paper_', s.id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_patent;
CREATE TABLE sm_patent AS
SELECT s.* FROM gkx_kg.kg_patent s
JOIN sm_vids v ON v.vid = CONCAT('patent_', s.patent_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_patent_family;
CREATE TABLE sm_patent_family AS
SELECT s.* FROM gkx_kg.kg_patent_family s
JOIN sm_vids v ON v.vid = CONCAT('patent_family_', s.family_number) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_project;
CREATE TABLE sm_project AS
SELECT s.* FROM gkx_kg.kg_project s
JOIN sm_vids v ON v.vid = CONCAT('project_', s.id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_organization;
CREATE TABLE sm_organization AS
SELECT s.* FROM gkx_kg.kg_organization s
JOIN sm_vids v ON v.vid = CONCAT('org_', s.org_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_news;
CREATE TABLE sm_news AS
SELECT s.* FROM gkx_kg.kg_news s
JOIN sm_vids v ON v.vid = CONCAT('news_', s.news_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_event;
CREATE TABLE sm_event AS
SELECT s.* FROM gkx_kg.kg_event s
JOIN sm_vids v ON v.vid = CONCAT('event_', s.event_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_journal;
CREATE TABLE sm_journal AS
SELECT s.* FROM gkx_kg.kg_journal s
JOIN sm_vids v ON v.vid = CONCAT('journal_', s.publication_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_keyword;
CREATE TABLE sm_keyword AS
SELECT s.* FROM gkx_kg.kg_keyword s
JOIN sm_vids v ON v.vid = CONCAT('keyword_', s.keyword_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_report;
CREATE TABLE sm_report AS
SELECT s.* FROM gkx_kg.kg_report s
JOIN sm_vids v ON v.vid = CONCAT('report_', s.report_id) COLLATE utf8mb4_general_ci;

-- Report 在 25 关系里没有边（HAS_OUTPUT 不在本批），补 3 个全库唯一名孤立真实顶点
INSERT INTO sm_report
SELECT s.* FROM gkx_kg.kg_report s
JOIN (SELECT COALESCE(NULLIF(TRIM(title_cn),''),NULLIF(TRIM(title_en),'')) AS nm
      FROM gkx_kg.kg_report
      GROUP BY COALESCE(NULLIF(TRIM(title_cn),''),NULLIF(TRIM(title_en),''))
      HAVING COUNT(*) = 1) u
  ON u.nm = COALESCE(NULLIF(TRIM(s.title_cn),''),NULLIF(TRIM(s.title_en),''))
ORDER BY s.report_id LIMIT 3;

DROP TABLE IF EXISTS sm_product;
CREATE TABLE sm_product AS
SELECT s.* FROM gkx_kg.kg_product s
JOIN sm_vids v ON v.vid = CONCAT('product_', s.product_id) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_industry_chain;
CREATE TABLE sm_industry_chain AS
SELECT s.* FROM gkx_kg.kg_industry_chain s
JOIN sm_vids v ON v.vid = CONCAT('chain_', s.chain_code) COLLATE utf8mb4_general_ci;

DROP TABLE IF EXISTS sm_industry_node;
CREATE TABLE sm_industry_node AS
SELECT s.* FROM gkx_kg.kg_industry_node s
JOIN sm_vids v ON v.vid = CONCAT('node_', s.node_id) COLLATE utf8mb4_general_ci;

-- 引用桩：vid = paper_ref_ + id[4:]（id 前缀 cit_/ref_/rel_/rp_X 均去前 4 字符）
-- 实测：66,915 条 CITES 边无一落在具名桩上；而全库仅有的 73 个具名桩全部是
-- 889900 演示造数系列（勿当真实用）。按"不造模拟数据"原则，桩表留空（TAG 建而空）。
DROP TABLE IF EXISTS sm_citation_stub;
CREATE TABLE sm_citation_stub AS
SELECT s.* FROM gkx_kg.kg_citation_stub s
JOIN sm_vids v ON v.vid = CONCAT('paper_ref_', SUBSTRING(s.id, 5)) COLLATE utf8mb4_general_ci;

-- ---------- 4) 有效名去重/去空（防 gray-gate 同名候选） ----------
-- 有效名 = 主名列非空则用之，否则取步脚本的第一个回退列；重名组整组删、无名全删。

DELETE p FROM sm_person p JOIN (
  SELECT COALESCE(NULLIF(TRIM(name_zh),''),NULLIF(TRIM(name_en),'')) AS nm FROM sm_person
  GROUP BY COALESCE(NULLIF(TRIM(name_zh),''),NULLIF(TRIM(name_en),'')) HAVING COUNT(*)>1
) d ON COALESCE(NULLIF(TRIM(p.name_zh),''),NULLIF(TRIM(p.name_en),'')) = d.nm;
DELETE FROM sm_person WHERE COALESCE(NULLIF(TRIM(name_zh),''),NULLIF(TRIM(name_en),'')) IS NULL;

DELETE p FROM sm_paper p JOIN (
  SELECT COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) AS nm FROM sm_paper
  GROUP BY COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) HAVING COUNT(*)>1
) d ON COALESCE(NULLIF(TRIM(p.title_zh),''),NULLIF(TRIM(p.title_en),'')) = d.nm;
DELETE FROM sm_paper WHERE COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) IS NULL;

DELETE p FROM sm_patent p JOIN (
  SELECT COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) AS nm FROM sm_patent
  GROUP BY COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) HAVING COUNT(*)>1
) d ON COALESCE(NULLIF(TRIM(p.title_zh),''),NULLIF(TRIM(p.title_en),'')) = d.nm;
DELETE FROM sm_patent WHERE COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) IS NULL;

DELETE p FROM sm_patent_family p JOIN (
  SELECT NULLIF(TRIM(family_number),'') AS nm FROM sm_patent_family
  GROUP BY NULLIF(TRIM(family_number),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.family_number),'') = d.nm;
DELETE FROM sm_patent_family WHERE NULLIF(TRIM(family_number),'') IS NULL;

DELETE p FROM sm_project p JOIN (
  SELECT NULLIF(TRIM(title),'') AS nm FROM sm_project
  GROUP BY NULLIF(TRIM(title),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.title),'') = d.nm;
DELETE FROM sm_project WHERE NULLIF(TRIM(title),'') IS NULL;

DELETE p FROM sm_organization p JOIN (
  SELECT COALESCE(NULLIF(TRIM(name_cn),''),NULLIF(TRIM(name_en),'')) AS nm FROM sm_organization
  GROUP BY COALESCE(NULLIF(TRIM(name_cn),''),NULLIF(TRIM(name_en),'')) HAVING COUNT(*)>1
) d ON COALESCE(NULLIF(TRIM(p.name_cn),''),NULLIF(TRIM(p.name_en),'')) = d.nm;
DELETE FROM sm_organization WHERE COALESCE(NULLIF(TRIM(name_cn),''),NULLIF(TRIM(name_en),'')) IS NULL;

DELETE p FROM sm_news p JOIN (
  SELECT NULLIF(TRIM(title),'') AS nm FROM sm_news
  GROUP BY NULLIF(TRIM(title),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.title),'') = d.nm;
DELETE FROM sm_news WHERE NULLIF(TRIM(title),'') IS NULL;

DELETE p FROM sm_event p JOIN (
  SELECT NULLIF(TRIM(title),'') AS nm FROM sm_event
  GROUP BY NULLIF(TRIM(title),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.title),'') = d.nm;
DELETE FROM sm_event WHERE NULLIF(TRIM(title),'') IS NULL;

DELETE p FROM sm_journal p JOIN (
  SELECT COALESCE(NULLIF(TRIM(name_zh),''),NULLIF(TRIM(name_en),'')) AS nm FROM sm_journal
  GROUP BY COALESCE(NULLIF(TRIM(name_zh),''),NULLIF(TRIM(name_en),'')) HAVING COUNT(*)>1
) d ON COALESCE(NULLIF(TRIM(p.name_zh),''),NULLIF(TRIM(p.name_en),'')) = d.nm;
DELETE FROM sm_journal WHERE COALESCE(NULLIF(TRIM(name_zh),''),NULLIF(TRIM(name_en),'')) IS NULL;

DELETE p FROM sm_keyword p JOIN (
  SELECT NULLIF(TRIM(keyword),'') AS nm FROM sm_keyword
  GROUP BY NULLIF(TRIM(keyword),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.keyword),'') = d.nm;
DELETE FROM sm_keyword WHERE NULLIF(TRIM(keyword),'') IS NULL;

DELETE p FROM sm_report p JOIN (
  SELECT COALESCE(NULLIF(TRIM(title_cn),''),NULLIF(TRIM(title_en),'')) AS nm FROM sm_report
  GROUP BY COALESCE(NULLIF(TRIM(title_cn),''),NULLIF(TRIM(title_en),'')) HAVING COUNT(*)>1
) d ON COALESCE(NULLIF(TRIM(p.title_cn),''),NULLIF(TRIM(p.title_en),'')) = d.nm;
DELETE FROM sm_report WHERE COALESCE(NULLIF(TRIM(title_cn),''),NULLIF(TRIM(title_en),'')) IS NULL;

DELETE p FROM sm_product p JOIN (
  SELECT NULLIF(TRIM(name),'') AS nm FROM sm_product
  GROUP BY NULLIF(TRIM(name),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.name),'') = d.nm;
DELETE FROM sm_product WHERE NULLIF(TRIM(name),'') IS NULL;

DELETE p FROM sm_industry_chain p JOIN (
  SELECT NULLIF(TRIM(chain_name),'') AS nm FROM sm_industry_chain
  GROUP BY NULLIF(TRIM(chain_name),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.chain_name),'') = d.nm;
DELETE FROM sm_industry_chain WHERE NULLIF(TRIM(chain_name),'') IS NULL;

DELETE p FROM sm_industry_node p JOIN (
  SELECT NULLIF(TRIM(node_name),'') AS nm FROM sm_industry_node
  GROUP BY NULLIF(TRIM(node_name),'') HAVING COUNT(*)>1
) d ON NULLIF(TRIM(p.node_name),'') = d.nm;
DELETE FROM sm_industry_node WHERE NULLIF(TRIM(node_name),'') IS NULL;

DELETE p FROM sm_citation_stub p JOIN (
  SELECT COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) AS nm FROM sm_citation_stub
  GROUP BY COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) HAVING COUNT(*)>1
) d ON COALESCE(NULLIF(TRIM(p.title_zh),''),NULLIF(TRIM(p.title_en),'')) = d.nm;
DELETE FROM sm_citation_stub WHERE COALESCE(NULLIF(TRIM(title_zh),''),NULLIF(TRIM(title_en),'')) IS NULL;

-- ---------- 5) 削掉悬空边（端点实体被 4) 删掉的） ----------
DROP TABLE IF EXISTS sm_live;
CREATE TABLE sm_live (
  vid VARCHAR(256) COLLATE utf8mb4_general_ci NOT NULL PRIMARY KEY
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci;

INSERT IGNORE INTO sm_live SELECT CONCAT('person_', person_id) FROM sm_person;
INSERT IGNORE INTO sm_live SELECT CONCAT('paper_', id) FROM sm_paper;
INSERT IGNORE INTO sm_live SELECT CONCAT('patent_', patent_id) FROM sm_patent;
INSERT IGNORE INTO sm_live SELECT CONCAT('patent_family_', family_number) FROM sm_patent_family;
INSERT IGNORE INTO sm_live SELECT CONCAT('project_', id) FROM sm_project;
INSERT IGNORE INTO sm_live SELECT CONCAT('org_', org_id) FROM sm_organization;
INSERT IGNORE INTO sm_live SELECT CONCAT('news_', news_id) FROM sm_news;
INSERT IGNORE INTO sm_live SELECT CONCAT('event_', event_id) FROM sm_event;
INSERT IGNORE INTO sm_live SELECT CONCAT('journal_', publication_id) FROM sm_journal;
INSERT IGNORE INTO sm_live SELECT CONCAT('keyword_', keyword_id) FROM sm_keyword;
INSERT IGNORE INTO sm_live SELECT CONCAT('report_', report_id) FROM sm_report;
INSERT IGNORE INTO sm_live SELECT CONCAT('product_', product_id) FROM sm_product;
INSERT IGNORE INTO sm_live SELECT CONCAT('chain_', chain_code) FROM sm_industry_chain;
INSERT IGNORE INTO sm_live SELECT CONCAT('node_', node_id) FROM sm_industry_node;
INSERT IGNORE INTO sm_live SELECT CONCAT('paper_ref_', SUBSTRING(id, 5)) FROM sm_citation_stub;

DELETE e FROM sm_edge e
LEFT JOIN sm_live l ON l.vid = e.src_id
LEFT JOIN sm_live r ON r.vid = e.dst_id
WHERE l.vid IS NULL OR r.vid IS NULL;

DROP TABLE sm_live;
DROP TABLE sm_vids;

-- ---------- 6) 报表 ----------
SELECT '实体行数' AS what, 'sm_person' AS tbl, COUNT(*) AS c FROM sm_person
UNION ALL SELECT '实体行数', 'sm_paper', COUNT(*) FROM sm_paper
UNION ALL SELECT '实体行数', 'sm_patent', COUNT(*) FROM sm_patent
UNION ALL SELECT '实体行数', 'sm_patent_family', COUNT(*) FROM sm_patent_family
UNION ALL SELECT '实体行数', 'sm_project', COUNT(*) FROM sm_project
UNION ALL SELECT '实体行数', 'sm_organization', COUNT(*) FROM sm_organization
UNION ALL SELECT '实体行数', 'sm_news', COUNT(*) FROM sm_news
UNION ALL SELECT '实体行数', 'sm_event', COUNT(*) FROM sm_event
UNION ALL SELECT '实体行数', 'sm_journal', COUNT(*) FROM sm_journal
UNION ALL SELECT '实体行数', 'sm_keyword', COUNT(*) FROM sm_keyword
UNION ALL SELECT '实体行数', 'sm_report', COUNT(*) FROM sm_report
UNION ALL SELECT '实体行数', 'sm_product', COUNT(*) FROM sm_product
UNION ALL SELECT '实体行数', 'sm_industry_chain', COUNT(*) FROM sm_industry_chain
UNION ALL SELECT '实体行数', 'sm_industry_node', COUNT(*) FROM sm_industry_node
UNION ALL SELECT '实体行数', 'sm_citation_stub', COUNT(*) FROM sm_citation_stub;

SELECT edge_type, COUNT(*) AS c FROM sm_edge GROUP BY edge_type ORDER BY edge_type;

-- ---------- 附：某实体表若为 0 行，补 3 个全库唯一名的孤立真实顶点（示例：Person） ----------
-- INSERT INTO sm_person
-- SELECT s.* FROM gkx_kg.kg_person s
-- WHERE s.name_zh IN (
--   SELECT name_zh FROM gkx_kg.kg_person
--   WHERE name_zh IS NOT NULL AND name_zh <> ''
--   GROUP BY name_zh HAVING COUNT(*) = 1)
--   AND s.person_id NOT IN (SELECT person_id FROM sm_person)
-- ORDER BY s.person_id LIMIT 3;
