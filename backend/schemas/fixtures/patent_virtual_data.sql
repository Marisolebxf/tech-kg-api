-- 专利抽取联调虚拟数据（不自动执行）。
-- 适配当前 gkx_element JSON 嵌套结构；全部业务ID带 VIRTUAL_ 前缀，可独立回滚。
START TRANSACTION;

INSERT INTO dwd_patent (
  id, patent_id, publication_number, application_kind, country_code, country,
  publication_reference, application_reference, applicants, assignees, inventors,
  first_applicant_name, first_current_assignee_name, first_inventor_name,
  main_classification_ipcr, further_classification_ipcr, main_classification_cpc,
  further_classification_cpc, keywords, claims, description, figures, language,
  granted_number, db_source, create_time, update_time, value, agents, agency,
  examiners, related_documents, classification_loc, classification_fi,
  classification_upc, classification_fterm
) VALUES (
  'VIRTUAL_ROW_001', 'VIRTUAL_CN000000001A', 'CN-VIRTUAL-000000001-A', 'A', 'CN', 'China',
  JSON_OBJECT('kind','A','pbdt',20260811,'pbdt_year',2026,'pbdt_month',202608),
  JSON_OBJECT('apno','CN-VIRTUAL-202600000001-A','country','CN','apdt',20260801,'apdt_year',2026,'apdt_month',202608),
  JSON_ARRAY(JSON_OBJECT('sequence',1,'name','北京大学')),
  JSON_ARRAY(JSON_OBJECT('sequence',1,'name','北京大学')),
  JSON_ARRAY(JSON_OBJECT('sequence',1,'name','虚拟发明人')),
  '北京大学', '北京大学', '虚拟发明人',
  'G06F16/36', JSON_ARRAY('G06N5/02'), 'G06F16/36', JSON_ARRAY('G06N5/02'),
  JSON_ARRAY('知识图谱','实体对齐'), JSON_OBJECT('zh',JSON_ARRAY('一种虚拟知识图谱方法')),
  JSON_OBJECT('zh','仅用于专利抽取联调'), JSON_ARRAY(), JSON_ARRAY('zh'),
  NULL, 'virtual_patent_fixture', NOW(), NOW(), 100,
  JSON_ARRAY('虚拟代理人'), JSON_ARRAY('虚拟代理机构'), JSON_ARRAY('虚拟审核员'),
  JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY()
) ON DUPLICATE KEY UPDATE update_time=VALUES(update_time);

INSERT INTO dwd_patent_title
(id, patent_id, titles, title_localized, title_zh, db_source, create_time, update_time)
VALUES (
  'VIRTUAL_TITLE_001', 'VIRTUAL_CN000000001A',
  JSON_ARRAY(JSON_OBJECT('language','zh','text','一种虚拟知识图谱实体对齐方法')),
  JSON_OBJECT('en','A Virtual Knowledge Graph Entity Alignment Method'),
  '一种虚拟知识图谱实体对齐方法', 'virtual_patent_fixture', NOW(), NOW()
) ON DUPLICATE KEY UPDATE update_time=VALUES(update_time);

INSERT INTO dwd_patent_abstract
(id, patent_id, abstracts, abstract_localized, abstract_zh, db_source, create_time, update_time)
VALUES (
  'VIRTUAL_ABSTRACT_001', 'VIRTUAL_CN000000001A',
  JSON_ARRAY(JSON_OBJECT('language','zh','text','用于验证实体、关键词及机构关系抽取。')),
  JSON_OBJECT('en','Fixture for entity and relation extraction.'),
  '用于验证实体、关键词及机构关系抽取。', 'virtual_patent_fixture', NOW(), NOW()
) ON DUPLICATE KEY UPDATE update_time=VALUES(update_time);

INSERT INTO dwd_patent_cited
(id, patent_id, reference_cited, cited_by_nums, cited_by_date, patent_citation_date,
 non_patent_count, non_patent_date, patent_citations_country, patent_citations_region,
 patent_citations_kd, cited_by, patent_citations, non_patent_citations,
 db_source, create_time, update_time)
VALUES (
  'VIRTUAL_CITED_001', 'VIRTUAL_CN000000001A', 1, 0, JSON_ARRAY(), JSON_ARRAY(20260701),
  0, JSON_ARRAY(), JSON_ARRAY('CN'), JSON_ARRAY('China'), JSON_ARRAY('A'),
  JSON_ARRAY(), JSON_ARRAY('CN103073024B'), JSON_ARRAY(),
  'virtual_patent_fixture', NOW(), NOW()
) ON DUPLICATE KEY UPDATE update_time=VALUES(update_time);

INSERT INTO dwd_patent_family
(id, patent_id, simple_family_number, simple_family_pn, simple_family,
 family_citations, cited_by_family, patent_family, db_source, create_time, update_time)
VALUES (
  9900000001, 'VIRTUAL_CN000000001A', 'VIRTUAL_FAMILY_001',
  JSON_ARRAY('VIRTUAL_CN000000001A'), JSON_ARRAY(JSON_OBJECT('sequence',1,'country','CN','kd','A')),
  JSON_ARRAY(), JSON_ARRAY(), JSON_ARRAY(JSON_OBJECT('country','CN','pn','VIRTUAL_CN000000001A')),
  'virtual_patent_fixture', NOW(), NOW()
) ON DUPLICATE KEY UPDATE update_time=VALUES(update_time);

COMMIT;

-- 回滚：
-- DELETE FROM dwd_patent_cited WHERE patent_id='VIRTUAL_CN000000001A';
-- DELETE FROM dwd_patent_family WHERE patent_id='VIRTUAL_CN000000001A';
-- DELETE FROM dwd_patent_title WHERE patent_id='VIRTUAL_CN000000001A';
-- DELETE FROM dwd_patent_abstract WHERE patent_id='VIRTUAL_CN000000001A';
-- DELETE FROM dwd_patent WHERE patent_id='VIRTUAL_CN000000001A';
