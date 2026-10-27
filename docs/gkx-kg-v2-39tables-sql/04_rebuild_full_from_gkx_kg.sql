-- gkx_kg_v2 全量重建脚本（从源库 gkx_kg 重建全部 39 张表，源库只读零改动）
-- 前提：本机存在 gkx_kg（14 张 kg_* 实体表 + 25 张 ev_* 视图 + kg_scholar_organization）
-- 三档合并口径：①同键 3 行不导（边天然落企业键）②同名不同键 17 行不插行、252 条 affiliated_with 改键 ③纯学术 25 行 INSERT、props 逐字段展开

-- gkx_kg_v2 建库 Part1：库 + 13 实体副本 + Organization 合并版
CREATE DATABASE IF NOT EXISTS gkx_kg_v2 DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci;

CREATE TABLE gkx_kg_v2.v_person LIKE gkx_kg.kg_person;
INSERT INTO gkx_kg_v2.v_person SELECT * FROM gkx_kg.kg_person;
CREATE TABLE gkx_kg_v2.v_paper LIKE gkx_kg.kg_paper;
INSERT INTO gkx_kg_v2.v_paper SELECT * FROM gkx_kg.kg_paper;
CREATE TABLE gkx_kg_v2.v_patent LIKE gkx_kg.kg_patent;
INSERT INTO gkx_kg_v2.v_patent SELECT * FROM gkx_kg.kg_patent;
CREATE TABLE gkx_kg_v2.v_patent_family LIKE gkx_kg.kg_patent_family;
INSERT INTO gkx_kg_v2.v_patent_family SELECT * FROM gkx_kg.kg_patent_family;
CREATE TABLE gkx_kg_v2.v_project LIKE gkx_kg.kg_project;
INSERT INTO gkx_kg_v2.v_project SELECT * FROM gkx_kg.kg_project;
CREATE TABLE gkx_kg_v2.v_news LIKE gkx_kg.kg_news;
INSERT INTO gkx_kg_v2.v_news SELECT * FROM gkx_kg.kg_news;
CREATE TABLE gkx_kg_v2.v_event LIKE gkx_kg.kg_event;
INSERT INTO gkx_kg_v2.v_event SELECT * FROM gkx_kg.kg_event;
CREATE TABLE gkx_kg_v2.v_journal LIKE gkx_kg.kg_journal;
INSERT INTO gkx_kg_v2.v_journal SELECT * FROM gkx_kg.kg_journal;
CREATE TABLE gkx_kg_v2.v_keyword LIKE gkx_kg.kg_keyword;
INSERT INTO gkx_kg_v2.v_keyword SELECT * FROM gkx_kg.kg_keyword;
CREATE TABLE gkx_kg_v2.v_report LIKE gkx_kg.kg_report;
INSERT INTO gkx_kg_v2.v_report SELECT * FROM gkx_kg.kg_report;
CREATE TABLE gkx_kg_v2.v_product LIKE gkx_kg.kg_product;
INSERT INTO gkx_kg_v2.v_product SELECT * FROM gkx_kg.kg_product;
CREATE TABLE gkx_kg_v2.v_industry_chain LIKE gkx_kg.kg_industry_chain;
INSERT INTO gkx_kg_v2.v_industry_chain SELECT * FROM gkx_kg.kg_industry_chain;
CREATE TABLE gkx_kg_v2.v_industry_node LIKE gkx_kg.kg_industry_node;
INSERT INTO gkx_kg_v2.v_industry_node SELECT * FROM gkx_kg.kg_industry_node;

-- Organization 合并版：50 原列 + confidence 新列（props 逐字段展开）
CREATE TABLE gkx_kg_v2.v_organization LIKE gkx_kg.kg_organization;
ALTER TABLE gkx_kg_v2.v_organization
  ADD COLUMN confidence double NULL
  COMMENT '置信度(scholar_affiliation行=dwd_scholar_work_experience物化props.confidence,企业行NULL)';
INSERT INTO gkx_kg_v2.v_organization SELECT o.*, NULL FROM gkx_kg.kg_organization o;
INSERT INTO gkx_kg_v2.v_organization
  (org_id, name_cn, name_en, org_kind, confidence,
   source_table, source_record_id, ingest_batch, ingest_time)
SELECT s.org_id,
       s.name_zh,
       NULLIF(s.name_en, ''),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.org_kind')),
       CAST(JSON_EXTRACT(s.props, '$.confidence') AS DOUBLE),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.source_table')),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.source_record_id')),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.ingest_batch')),
       JSON_UNQUOTE(JSON_EXTRACT(s.props, '$.ingest_time'))
FROM gkx_kg.kg_scholar_organization s
WHERE NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization k WHERE k.org_id = s.org_id)
  AND NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization o WHERE o.name_cn = s.name_zh);

-- gkx_kg_v2 建库 Part2：24 张关系表原样副本 + affiliated_with 键对齐改写版
CREATE TABLE gkx_kg_v2.ev_acquires AS SELECT * FROM gkx_kg.ev_acquires;
CREATE TABLE gkx_kg_v2.ev_actual_controller_of AS SELECT * FROM gkx_kg.ev_actual_controller_of;
CREATE TABLE gkx_kg_v2.ev_applied_by AS SELECT * FROM gkx_kg.ev_applied_by;
CREATE TABLE gkx_kg_v2.ev_authored_by AS SELECT * FROM gkx_kg.ev_authored_by;
CREATE TABLE gkx_kg_v2.ev_belongs_to_node AS SELECT * FROM gkx_kg.ev_belongs_to_node;
CREATE TABLE gkx_kg_v2.ev_beneficial_owner_of AS SELECT * FROM gkx_kg.ev_beneficial_owner_of;
CREATE TABLE gkx_kg_v2.ev_cites AS SELECT * FROM gkx_kg.ev_cites;
CREATE TABLE gkx_kg_v2.ev_coauthor_with AS SELECT * FROM gkx_kg.ev_coauthor_with;
CREATE TABLE gkx_kg_v2.ev_executive_of AS SELECT * FROM gkx_kg.ev_executive_of;
CREATE TABLE gkx_kg_v2.ev_funded_by AS SELECT * FROM gkx_kg.ev_funded_by;
CREATE TABLE gkx_kg_v2.ev_has_keyword AS SELECT * FROM gkx_kg.ev_has_keyword;
CREATE TABLE gkx_kg_v2.ev_has_news AS SELECT * FROM gkx_kg.ev_has_news;
CREATE TABLE gkx_kg_v2.ev_has_node AS SELECT * FROM gkx_kg.ev_has_node;
CREATE TABLE gkx_kg_v2.ev_has_participant AS SELECT * FROM gkx_kg.ev_has_participant;
CREATE TABLE gkx_kg_v2.ev_invented_by AS SELECT * FROM gkx_kg.ev_invented_by;
CREATE TABLE gkx_kg_v2.ev_invests_in AS SELECT * FROM gkx_kg.ev_invests_in;
CREATE TABLE gkx_kg_v2.ev_involved_in AS SELECT * FROM gkx_kg.ev_involved_in;
CREATE TABLE gkx_kg_v2.ev_leads AS SELECT * FROM gkx_kg.ev_leads;
CREATE TABLE gkx_kg_v2.ev_legal_rep_of AS SELECT * FROM gkx_kg.ev_legal_rep_of;
CREATE TABLE gkx_kg_v2.ev_member_of_family AS SELECT * FROM gkx_kg.ev_member_of_family;
CREATE TABLE gkx_kg_v2.ev_produces AS SELECT * FROM gkx_kg.ev_produces;
CREATE TABLE gkx_kg_v2.ev_published_in AS SELECT * FROM gkx_kg.ev_published_in;
CREATE TABLE gkx_kg_v2.ev_shareholder_of AS SELECT * FROM gkx_kg.ev_shareholder_of;
CREATE TABLE gkx_kg_v2.ev_subsidiary_of AS SELECT * FROM gkx_kg.ev_subsidiary_of;

-- affiliated_with 键对齐版：①档 81 条 dst 不变（本就落企业键）
-- ③档 796 条 dst 不变（org_<md5> 已作为合并行进 v_organization）
-- ②档 252 条 dst org_<学者md5> → org_<同名企业键>（唯一匹配已预检）
CREATE TABLE gkx_kg_v2.ev_affiliated_with AS
SELECT e.src_id AS src_id,
       COALESCE(m.new_vid, e.dst_id) AS dst_id,
       e.edge_rank AS edge_rank,
       e.props_json AS props_json
FROM gkx_kg.ev_affiliated_with e
LEFT JOIN (
  SELECT CONCAT('org_', s.org_id COLLATE utf8mb4_general_ci) AS old_vid,
         CONCAT('org_', o.org_id COLLATE utf8mb4_general_ci) AS new_vid
  FROM gkx_kg.kg_scholar_organization s
  JOIN gkx_kg.kg_organization o
    ON o.name_cn COLLATE utf8mb4_general_ci = s.name_zh COLLATE utf8mb4_general_ci
  WHERE NOT EXISTS (SELECT 1 FROM gkx_kg.kg_organization k WHERE k.org_id = s.org_id)
) m ON e.dst_id COLLATE utf8mb4_general_ci = m.old_vid COLLATE utf8mb4_general_ci;
