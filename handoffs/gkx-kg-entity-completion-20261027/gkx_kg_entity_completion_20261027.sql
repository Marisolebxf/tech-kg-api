-- gkx_kg: one entity type per table; source-backed field completion only.
-- MySQL 8.0.21+; run with the mysql CLI (DELIMITER is a client command).
-- Restore the supplied gkx_kg backup first. Change USE and @source_db if needed.
-- This file does not import the backup, delete rows, or rewrite primary keys.
-- DDL commits implicitly. Take a backup first; review the final per-step log.
USE `gkx_kg`;
SET NAMES utf8mb4;
SET @target_db = DATABASE();
-- 2026-10-27 GLM dev-machine revision (real layout verified on tech-kg-mysql, 127.0.0.1:30306):
--   primary source = gkx_dwd_local (dev2 data plane; dwd_scholar 22,077 / dwd_org_base_info 3,739,
--   event fact tables match existing kg_event provenance);
--   routed to gkx_element for the three tables gkx_dwd_local lacks or stores with a different schema:
--     dwd_patent               (only element has inventors/applicants/assignees/application_reference/id;
--                               local copy only has first_*_name singles),
--     dwd_industry_chain_info  (element holds the chain_code/node_id design that matches kg_industry_*;
--                               local copy is a different industry_code layout, 182 rows),
--     dwd_forg_stock_fin_info  (absent in gkx_dwd_local, 100 rows in element).
-- Routing is done by flipping @source_db around the affected CALLs; every procedure reads it at call time.
SET @source_db = 'gkx_dwd_local';
-- Session buffers: GROUP BY over long company names / JSON staging docs needs more than the
-- 256KB default sort buffer (first run died with ERROR 1038 on dwd_forg_base_info import).
SET SESSION sort_buffer_size = 67108864;
SET SESSION tmp_table_size = 268435456;
SET SESSION max_heap_table_size = 268435456;

DROP TEMPORARY TABLE IF EXISTS tmp_kg_patch_log;
CREATE TEMPORARY TABLE tmp_kg_patch_log (
  step VARCHAR(255) NOT NULL,
  status VARCHAR(40) NOT NULL,
  affected_rows BIGINT NOT NULL DEFAULT 0,
  detail TEXT
) ENGINE=InnoDB;

DELIMITER $$
DROP FUNCTION IF EXISTS fn_kg27_is_real_json$$
CREATE FUNCTION fn_kg27_is_real_json(p_document LONGTEXT)
RETURNS TINYINT DETERMINISTIC NO SQL
BEGIN
  DECLARE v_matches JSON;
  DECLARE v_value LONGTEXT;
  DECLARE v_i INT DEFAULT 0;
  IF p_document IS NULL OR TRIM(p_document) = '' THEN RETURN 1; END IF;
  IF JSON_VALID(p_document) = 0 THEN RETURN 0; END IF;
  SET v_matches = JSON_EXTRACT(p_document,
    '$**.data_source', '$**.source_system', '$**.source',
    '$**.id', '$**.join_key', '$**.source_record_id',
    '$**.organization_id', '$**.org_id', '$**.company_id', '$**.entity_eid',
    '$**.inv_org_id', '$**.admin_org_id', '$**.report_id', '$**.scholar_id',
    '$**.person_id', '$**.patent_id', '$**.event_id', '$**.news_id',
    '$**.product_id', '$**.project_id', '$**.project_number', '$**.contract_num',
    '$**.case_id','$**.u_id','$**.abnormal_id','$**.penalty_id','$**.sv_id',
    '$**.tax_vio_id','$**.dishonest_id','$**.exec_person_id','$**.bankruptcy_party_id',
    '$**.family_number','$**.simple_family_number','$**.chain_code','$**.node_id');
  WHILE v_i < COALESCE(JSON_LENGTH(v_matches), 0) DO
    SET v_value = LOWER(REPLACE(JSON_UNQUOTE(JSON_EXTRACT(v_matches, CONCAT('$[',v_i,']'))), '-', '_'));
    IF REGEXP_LIKE(v_value, '(^|_)(mock|stub|virtual|placeholder|test|synthetic)(_|$)') THEN
      RETURN 0;
    END IF;
    SET v_i = v_i + 1;
  END WHILE;
  RETURN 1;
END$$

DROP PROCEDURE IF EXISTS sp_kg27_assert_base$$
CREATE PROCEDURE sp_kg27_assert_base()
BEGIN
  DECLARE v_missing INT;
  IF @source_db IS NULL OR @source_db NOT REGEXP '^[0-9A-Za-z_]+$' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid @source_db';
  END IF;
  SELECT COUNT(*) INTO v_missing
  FROM JSON_TABLE('["kg_person","kg_organization","kg_paper","kg_patent","kg_project","kg_journal","kg_keyword","kg_industry_chain","kg_industry_node","kg_event","kg_news","kg_product","kg_patent_family"]',
    '$[*]' COLUMNS(table_name VARCHAR(64) PATH '$')) expected
  LEFT JOIN information_schema.tables t
    ON t.table_schema=@target_db AND t.table_name=expected.table_name AND t.table_type='BASE TABLE'
  WHERE t.table_name IS NULL;
  IF v_missing > 0 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Missing base entity tables: restore gkx_kg backup before running';
  END IF;
  INSERT INTO tmp_kg_patch_log VALUES ('base_tables','OK',13,'Existing 13 entity types use their existing primary keys; no separate scholar/author/company entity table is created.');
END$$

DROP PROCEDURE IF EXISTS sp_kg27_add_column$$
CREATE PROCEDURE sp_kg27_add_column(IN p_table VARCHAR(64), IN p_column VARCHAR(64), IN p_ddl TEXT)
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_table AND column_name=p_column) THEN
    SET @kg27_sql=CONCAT('ALTER TABLE `',@target_db,'`.`',p_table,'` ADD COLUMN `',p_column,'` ',p_ddl);
    PREPARE kg27_stmt FROM @kg27_sql; EXECUTE kg27_stmt; DEALLOCATE PREPARE kg27_stmt;
    INSERT INTO tmp_kg_patch_log VALUES (CONCAT('column:',p_table,'.',p_column),'ADDED',0,p_ddl);
  ELSE
    INSERT INTO tmp_kg_patch_log VALUES (CONCAT('column:',p_table,'.',p_column),'EXISTS',0,'Existing definition preserved.');
  END IF;
END$$

-- p_map is [{target, sources:[candidate_column,...]}]. Only exact, unique source keys are used.
DROP PROCEDURE IF EXISTS sp_kg27_fill_from_source$$
CREATE PROCEDURE sp_kg27_fill_from_source(
  IN p_target VARCHAR(64), IN p_key VARCHAR(64),
  IN p_source VARCHAR(64), IN p_source_key VARCHAR(64),
  IN p_affinity VARCHAR(128), IN p_map JSON)
fill_block: BEGIN
  DECLARE v_i INT DEFAULT 0;
  DECLARE v_j INT DEFAULT 0;
  DECLARE v_name VARCHAR(64);
  DECLARE v_target_col VARCHAR(64);
  DECLARE v_type VARCHAR(64);
  DECLARE v_maxlen BIGINT;
  DECLARE v_expr LONGTEXT;
  DECLARE v_assign LONGTEXT DEFAULT '';
  DECLARE v_guard LONGTEXT DEFAULT '';
  DECLARE v_source_json LONGTEXT DEFAULT '';
  DECLARE v_target_json LONGTEXT DEFAULT '';
  DECLARE v_affinity LONGTEXT DEFAULT '';
  DECLARE v_filter LONGTEXT DEFAULT '';
  DECLARE v_metadata JSON;
  DECLARE v_rows BIGINT DEFAULT 0;
  DECLARE v_step VARCHAR(255);
  SET v_step=CONCAT('fill:',p_target,'<-',@source_db,'.',p_source);
  IF NOT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema=@source_db AND table_name=p_source AND table_type='BASE TABLE') THEN
    INSERT INTO tmp_kg_patch_log VALUES(v_step,'SKIPPED_SOURCE',0,'Source table not present; no records fabricated.'); LEAVE fill_block;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_source AND column_name=p_source_key) THEN
    INSERT INTO tmp_kg_patch_log VALUES(v_step,'SKIPPED_KEY',0,CONCAT('Missing exact source key ',p_source_key)); LEAVE fill_block;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name=p_key) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Unexpected target primary-key column';
  END IF;
  WHILE v_i < JSON_LENGTH(p_map) DO
    SET v_target_col=JSON_UNQUOTE(JSON_EXTRACT(p_map,CONCAT('$[',v_i,'].target')));
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name=v_target_col) THEN
      SET v_expr=''; SET v_j=0;
      WHILE v_j < JSON_LENGTH(JSON_EXTRACT(p_map,CONCAT('$[',v_i,'].sources'))) DO
        SET v_name=JSON_UNQUOTE(JSON_EXTRACT(p_map,CONCAT('$[',v_i,'].sources[',v_j,']')));
        IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_source AND column_name=v_name) THEN
          SET v_expr=CONCAT(v_expr,IF(v_expr='','',','),'NULLIF(TRIM(CAST(s.`',v_name,'` AS CHAR CHARACTER SET utf8mb4)),'''')');
        END IF;
        SET v_j=v_j+1;
      END WHILE;
      IF v_expr<>'' THEN
        SET v_expr=CONCAT('COALESCE(',v_expr,',NULL)');
        SELECT data_type,character_maximum_length INTO v_type,v_maxlen FROM information_schema.columns
        WHERE table_schema=@target_db AND table_name=p_target AND column_name=v_target_col;
        IF v_type IN ('varchar','char') THEN
          -- Do not truncate a source value. Oversize values stay unfilled and are logged.
          SET @kg27_sql=CONCAT('SELECT COUNT(*) INTO @kg27_oversize FROM `',@source_db,'`.`',p_source,'` s WHERE CHAR_LENGTH(',v_expr,')>',v_maxlen);
          PREPARE kg27_stmt FROM @kg27_sql; EXECUTE kg27_stmt; DEALLOCATE PREPARE kg27_stmt;
          IF COALESCE(@kg27_oversize,0)>0 THEN
            INSERT INTO tmp_kg_patch_log VALUES(CONCAT(v_step,':',v_target_col),'OVERSIZE_SOURCE',@kg27_oversize,'Source values exceeding target width are not truncated. Count covers the source table.');
          END IF;
          SET v_expr=CONCAT('IF(CHAR_LENGTH(',v_expr,')<=',v_maxlen,',',v_expr,',NULL)');
        END IF;
        SET v_assign=CONCAT(v_assign,IF(v_assign='','',','),'t.`',v_target_col,'`=CASE WHEN t.`',v_target_col,'` IS NULL OR TRIM(CAST(t.`',v_target_col,'` AS CHAR))='''' THEN ',v_expr,' ELSE t.`',v_target_col,'` END');
      ELSE
        INSERT INTO tmp_kg_patch_log VALUES(CONCAT(v_step,':',v_target_col),'SKIPPED_COLUMN',0,'None of the configured source columns exist.');
      END IF;
    END IF;
    SET v_i=v_i+1;
  END WHILE;
  IF v_assign='' THEN
    INSERT INTO tmp_kg_patch_log VALUES(v_step,'NO_COLUMNS',0,'No mapped source columns available.'); LEAVE fill_block;
  END IF;
  -- Construct filters only from metadata and structural IDs, never from arbitrary prose.
  SET v_metadata=JSON_ARRAY('data_source','source_system','source','id','source_record_id','organization_id','org_id','company_id','entity_eid','inv_org_id','admin_org_id','report_id','scholar_id','person_id','patent_id','project_id','project_number');
  SET v_i=0;
  SET v_source_json=CONCAT('JSON_OBJECT(''join_key'',s.`',p_source_key,'`');
  SET v_target_json=CONCAT('JSON_OBJECT(''join_key'',t.`',p_key,'`');
  WHILE v_i<JSON_LENGTH(v_metadata) DO
    SET v_name=JSON_UNQUOTE(JSON_EXTRACT(v_metadata,CONCAT('$[',v_i,']')));
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_source AND column_name=v_name) THEN
      SET v_source_json=CONCAT(v_source_json,',''',v_name,''',s.`',v_name,'`');
    END IF;
    IF EXISTS (SELECT 1 FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name=v_name) THEN
      SET v_target_json=CONCAT(v_target_json,',''',v_name,''',t.`',v_name,'`');
    END IF;
    SET v_i=v_i+1;
  END WHILE;
  IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_source AND column_name='extra_json') THEN
    SET v_source_json=CONCAT(v_source_json,',''extra_json'',CAST(IF(JSON_VALID(s.extra_json),s.extra_json,''null'') AS JSON)');
  END IF;
  IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name='extra_json') THEN
    SET v_target_json=CONCAT(v_target_json,',''extra_json'',CAST(IF(JSON_VALID(t.extra_json),t.extra_json,''null'') AS JSON)');
  END IF;
  SET v_source_json=CONCAT(v_source_json,')'); SET v_target_json=CONCAT(v_target_json,')');
  IF p_affinity IS NOT NULL AND p_affinity<>'' AND EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name='source_table') THEN
    SET v_affinity=CONCAT(' AND (t.source_table IS NULL OR TRIM(t.source_table)='''' OR BINARY t.source_table=BINARY ',QUOTE(p_affinity),')');
  END IF;
  IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_source AND column_name='is_deleted') THEN
    SET v_filter=' AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0';
  END IF;
  SET @kg27_sql=CONCAT('SELECT COUNT(*) INTO @kg27_duplicates FROM (SELECT BINARY CAST(`',p_source_key,'` AS CHAR) k FROM `',@source_db,'`.`',p_source,'` WHERE `',p_source_key,'` IS NOT NULL GROUP BY BINARY CAST(`',p_source_key,'` AS CHAR) HAVING COUNT(*)>1) d');
  PREPARE kg27_stmt FROM @kg27_sql; EXECUTE kg27_stmt; DEALLOCATE PREPARE kg27_stmt;
  IF COALESCE(@kg27_duplicates,0)>0 THEN
    INSERT INTO tmp_kg_patch_log VALUES(v_step,'AMBIGUOUS_SOURCE_KEYS',@kg27_duplicates,'All source keys with multiple rows are excluded, even if their payloads look similar.');
  END IF;
  SET @kg27_sql=CONCAT('UPDATE `',@target_db,'`.`',p_target,'` t JOIN `',@source_db,'`.`',p_source,'` s ON BINARY CAST(t.`',p_key,'` AS CHAR)=BINARY CAST(s.`',p_source_key,'` AS CHAR) JOIN (SELECT BINARY CAST(`',p_source_key,'` AS CHAR) k FROM `',@source_db,'`.`',p_source,'` WHERE `',p_source_key,'` IS NOT NULL GROUP BY BINARY CAST(`',p_source_key,'` AS CHAR) HAVING COUNT(*)=1) uniq ON uniq.k=BINARY CAST(s.`',p_source_key,'` AS CHAR) SET ',v_assign,' WHERE fn_kg27_is_real_json(',v_source_json,')=1 AND fn_kg27_is_real_json(',v_target_json,')=1',v_affinity,v_filter);
  PREPARE kg27_stmt FROM @kg27_sql; EXECUTE kg27_stmt; SET v_rows=ROW_COUNT(); DEALLOCATE PREPARE kg27_stmt;
  INSERT INTO tmp_kg_patch_log VALUES(v_step,'UPDATED',v_rows,'Exact unique source-key match; existing nonempty target values preserved; explicit test markers excluded.');
END$$
DELIMITER ;

CALL sp_kg27_assert_base();
CALL sp_kg27_add_column('kg_project','participants','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','project_host','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','funded_institution','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','participating_institution','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','output_journal_articles','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','output_conference_papers','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','output_degree_papers','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','output_patents','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_project','output_reports','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_patent','inventors','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_patent','applicants','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_patent','assignees','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_patent','source_patent_row_id','VARCHAR(255) NULL');
CALL sp_kg27_add_column('kg_person','scholar_org_name_zh','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_person','scholar_org_name_en','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_industry_node','chain_code','VARCHAR(255) NULL');
CALL sp_kg27_add_column('kg_industry_node','source_system','VARCHAR(64) NULL');
CALL sp_kg27_add_column('kg_industry_node','source_record_id','VARCHAR(255) NULL');
CALL sp_kg27_add_column('kg_industry_chain','source_system','VARCHAR(64) NULL');
CALL sp_kg27_add_column('kg_industry_chain','source_record_id','VARCHAR(255) NULL');
CALL sp_kg27_add_column('kg_event','case_role','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_event','exec_person_type','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_event','party_role_type','MEDIUMTEXT NULL');
CALL sp_kg27_add_column('kg_event','u_id','VARCHAR(255) NULL');


-- Full seven-relation completion: no business sample rows are embedded.
SET @kg27_batch=CONCAT('kg27:',DATE_FORMAT(UTC_TIMESTAMP(6),'%Y%m%dT%H%i%s.%f'),':',CONNECTION_ID());
SET SESSION group_concat_max_len=16777216;
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_issues;
CREATE TEMPORARY TABLE tmp_kg27_issues(
 relation_type VARCHAR(64),source_table VARCHAR(128),source_record_id VARCHAR(512),
 issue_code VARCHAR(64),detail MEDIUMTEXT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_source_rows;
CREATE TEMPORARY TABLE tmp_kg27_source_rows(
 source_table VARCHAR(128) NOT NULL,source_key VARCHAR(512),row_hash CHAR(64) NOT NULL,doc JSON NOT NULL,
 PRIMARY KEY(source_table,row_hash)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

DELIMITER $$
DROP FUNCTION IF EXISTS fn_kg27_json_text$$
CREATE FUNCTION fn_kg27_json_text(p_doc LONGTEXT,p_path VARCHAR(255))
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN
 IF p_doc IS NULL OR JSON_VALID(p_doc)=0 THEN RETURN NULL; END IF;
 RETURN NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(p_doc,p_path))),'null'),'');
END$$
DROP FUNCTION IF EXISTS fn_kg27_norm_text$$
CREATE FUNCTION fn_kg27_norm_text(p_text LONGTEXT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN RETURN LOWER(TRIM(REGEXP_REPLACE(COALESCE(p_text,''),'[[:space:]]+',' '))); END$$
DROP FUNCTION IF EXISTS fn_kg27_norm_name$$
CREATE FUNCTION fn_kg27_norm_name(p_text LONGTEXT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN RETURN REGEXP_REPLACE(fn_kg27_norm_text(p_text),'[^0-9a-z一-龥]',''); END$$
DROP FUNCTION IF EXISTS fn_kg27_norm_doi$$
CREATE FUNCTION fn_kg27_norm_doi(p_text LONGTEXT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN RETURN REGEXP_REPLACE(fn_kg27_norm_text(p_text),'^(https?://(dx[.])?doi[.]org/|doi:[[:space:]]*)',''); END$$
DROP FUNCTION IF EXISTS fn_kg27_norm_patent$$
CREATE FUNCTION fn_kg27_norm_patent(p_text LONGTEXT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN RETURN UPPER(REGEXP_REPLACE(TRIM(COALESCE(p_text,'')),'[[:space:]./-]+','')); END$$
DROP FUNCTION IF EXISTS fn_kg27_confidence_doc$$
CREATE FUNCTION fn_kg27_confidence_doc(p_doc LONGTEXT,p_source VARCHAR(128))
RETURNS DOUBLE DETERMINISTIC NO SQL
BEGIN
 DECLARE v_score DOUBLE DEFAULT 0.45;
 DECLARE v_ids INT DEFAULT 0; DECLARE v_i INT DEFAULT 0; DECLARE v_fields JSON;
 IF p_source LIKE 'dwd\_%' THEN SET v_score=0.55; END IF;
 SET v_fields=JSON_ARRAY('organization_id','org_id','company_id','entity_eid','inv_org_id','acquiring_org_id','acquired_org_id','affiliate','affiliates_company_id','admin_org_id','antitypic');
 WHILE v_i<JSON_LENGTH(v_fields) DO
  IF fn_kg27_json_text(p_doc,CONCAT('$.',JSON_UNQUOTE(JSON_EXTRACT(v_fields,CONCAT('$[',v_i,']'))))) IS NOT NULL THEN SET v_ids=v_ids+1; END IF;
  SET v_i=v_i+1;
 END WHILE;
 IF v_ids>=1 THEN SET v_score=v_score+0.25; END IF;
 IF v_ids>=2 THEN SET v_score=v_score+0.10; END IF;
 SET v_fields=JSON_KEYS(p_doc); SET v_i=0; SET v_ids=0;
 WHILE v_i<COALESCE(JSON_LENGTH(v_fields),0) DO
  IF fn_kg27_json_text(p_doc,CONCAT('$."',REPLACE(JSON_UNQUOTE(JSON_EXTRACT(v_fields,CONCAT('$[',v_i,']'))),'"','\\"'),'"')) IS NOT NULL THEN SET v_ids=v_ids+1; END IF;
  SET v_i=v_i+1;
 END WHILE;
 IF v_ids>=3 THEN SET v_score=v_score+0.05; END IF;
 IF COALESCE(fn_kg27_json_text(p_doc,'$.external_id'),fn_kg27_json_text(p_doc,'$.credit_no')) IS NOT NULL THEN SET v_score=v_score+0.05; END IF;
 RETURN ROUND(LEAST(1.0,v_score),4);
END$$

DROP PROCEDURE IF EXISTS sp_kg27_stage_source$$
CREATE PROCEDURE sp_kg27_stage_source(IN p_table VARCHAR(128))
stage_block: BEGIN
 DECLARE v_json LONGTEXT; DECLARE v_key LONGTEXT DEFAULT 'NULL'; DECLARE v_filter TEXT DEFAULT '';
 DECLARE v_n BIGINT;
 IF p_table NOT REGEXP '^[0-9A-Za-z_]+$' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='Invalid source identifier'; END IF;
 IF NOT EXISTS(SELECT 1 FROM information_schema.tables WHERE table_schema=@source_db AND table_name=p_table AND table_type='BASE TABLE') THEN
  INSERT INTO tmp_kg_patch_log VALUES(CONCAT('stage:',p_table),'MISSING_SOURCE',0,'Required real source table is absent; no placeholder rows created.'); LEAVE stage_block;
 END IF;
 IF EXISTS(SELECT 1 FROM tmp_kg27_source_rows WHERE source_table=p_table LIMIT 1) THEN LEAVE stage_block; END IF;
 SELECT CONCAT('JSON_OBJECT(',GROUP_CONCAT(CONCAT(QUOTE(column_name),',',
  IF(column_name='extra_json',CONCAT('CAST(IF(JSON_VALID(s.`',REPLACE(column_name,'`','``'),'`),s.`',REPLACE(column_name,'`','``'),'`,''null'') AS JSON)'),CONCAT('s.`',REPLACE(column_name,'`','``'),'`')))
  ORDER BY ordinal_position SEPARATOR ','),')') INTO v_json
 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_table;
 IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_table AND column_name='id') THEN SET v_key='NULLIF(TRIM(CAST(s.id AS CHAR)),'''')'; END IF;
 IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@source_db AND table_name=p_table AND column_name='is_deleted') THEN SET v_filter=' AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0'; END IF;
 SET @kg27_stage_sql=CONCAT('INSERT IGNORE INTO tmp_kg27_source_rows(source_table,source_key,row_hash,doc) SELECT ',QUOTE(p_table),',IF(CHAR_LENGTH(',v_key,')<=512,',v_key,',CONCAT(''sha256:'',SHA2(',v_key,',256))),SHA2(CAST(',v_json,' AS CHAR),256),',v_json,' FROM `',@source_db,'`.`',p_table,'` s WHERE fn_kg27_is_real_json(',v_json,')=1',v_filter);
 PREPARE kg27_stage_stmt FROM @kg27_stage_sql; EXECUTE kg27_stage_stmt; SET v_n=ROW_COUNT(); DEALLOCATE PREPARE kg27_stage_stmt;
 INSERT INTO tmp_kg_patch_log VALUES(CONCAT('stage:',p_table),'STAGED',v_n,'Exact source rows; explicit test markers/deleted rows excluded. Identical complete rows deduplicated by fingerprint.');
END$$

DROP PROCEDURE IF EXISTS sp_kg27_import_entity$$
CREATE PROCEDURE sp_kg27_import_entity(IN p_target VARCHAR(64),IN p_key VARCHAR(64),IN p_source VARCHAR(128),IN p_key_expr LONGTEXT,IN p_required LONGTEXT,IN p_map JSON)
import_block: BEGIN
 DECLARE v_i INT DEFAULT 0; DECLARE v_col VARCHAR(64); DECLARE v_expr LONGTEXT;
 DECLARE v_cols LONGTEXT DEFAULT ''; DECLARE v_values LONGTEXT DEFAULT ''; DECLARE v_updates LONGTEXT DEFAULT '';
 DECLARE v_type VARCHAR(64); DECLARE v_max BIGINT; DECLARE v_keymax BIGINT; DECLARE v_n BIGINT;
 DECLARE v_origin TEXT DEFAULT ''; DECLARE v_guard LONGTEXT;
 DECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN SELECT @kg27_import_sql AS failed_dynamic_sql; RESIGNAL; END;
 IF NOT EXISTS(SELECT 1 FROM tmp_kg27_source_rows WHERE source_table=p_source LIMIT 1) THEN LEAVE import_block; END IF;
 SELECT character_maximum_length INTO v_keymax FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name=p_key;
 SET v_cols=CONCAT('`',p_key,'`'); SET v_values=CONCAT('MAX(',p_key_expr,')');
 WHILE v_i<JSON_LENGTH(p_map) DO
  SET v_col=JSON_UNQUOTE(JSON_EXTRACT(p_map,CONCAT('$[',v_i,'].target')));
  SET v_expr=JSON_UNQUOTE(JSON_EXTRACT(p_map,CONCAT('$[',v_i,'].expr')));
  IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name=v_col) AND v_col<>p_key THEN
   SELECT data_type,character_maximum_length INTO v_type,v_max FROM information_schema.columns WHERE table_schema=@target_db AND table_name=p_target AND column_name=v_col;
   IF v_type IN('varchar','char') THEN SET v_expr=CONCAT('IF(CHAR_LENGTH(',v_expr,')<=',v_max,',',v_expr,',NULL)'); END IF;
   IF v_type IN('int','bigint','tinyint','smallint','mediumint','double','float','decimal') THEN
    SET v_expr=CONCAT('IF((CONVERT((',v_expr,') USING utf8mb4) COLLATE utf8mb4_bin) REGEXP (_utf8mb4''^-?[0-9]+([.][0-9]+)?([eE][+-]?[0-9]+)?$'' COLLATE utf8mb4_bin),',v_expr,',NULL)');
   END IF;
   SET @kg27_import_sql=CONCAT('INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail) SELECT ',QUOTE(p_target),',',QUOTE(p_source),',IF(CHAR_LENGTH(MAX(',p_key_expr,'))<=512,MAX(',p_key_expr,'),CONCAT(''sha256:'',SHA2(MAX(',p_key_expr,'),256))),''CONFLICTING_SOURCE_FIELD'',',QUOTE(CONCAT('Conflicting values for ',v_col,'; the field is not chosen arbitrarily.')),' FROM tmp_kg27_source_rows r WHERE source_table=',QUOTE(p_source),' AND ',p_key_expr,' IS NOT NULL GROUP BY ',p_key_expr,' HAVING COUNT(DISTINCT BINARY (',v_expr,'))>1');
   PREPARE kg27_import_stmt FROM @kg27_import_sql; EXECUTE kg27_import_stmt; DEALLOCATE PREPARE kg27_import_stmt;
   -- Multiple source rows may assert the same entity key. Conflicting field values are not chosen arbitrarily.
   SET v_values=CONCAT(v_values,',IF(COUNT(DISTINCT BINARY (',v_expr,'))<=1,MAX(',v_expr,'),NULL)');
   SET v_cols=CONCAT(v_cols,',`',v_col,'`');
   SET v_updates=CONCAT(v_updates,IF(v_updates='','',','),'`',v_col,'`=IF(',p_target,'.`',v_col,'` IS NULL OR TRIM(CAST(',p_target,'.`',v_col,'` AS CHAR))='''',VALUES(`',v_col,'`),',p_target,'.`',v_col,'`)');
  END IF;
  SET v_i=v_i+1;
 END WHILE;
 SET v_cols=CONCAT(v_cols,',source_table,source_record_id,source_system,ingest_batch,ingest_time,extra_json');
 SET v_values=CONCAT(v_values,',',QUOTE(p_source),',MAX(',p_key_expr,'),',QUOTE(CONCAT('mysql:',@source_db)),',@kg27_batch,DATE_FORMAT(UTC_TIMESTAMP(),''%Y-%m-%dT%H:%i:%sZ''),JSON_OBJECT(''source_table'',',QUOTE(p_source),',''source_records'',JSON_ARRAYAGG(r.doc))');
 SET v_updates=CONCAT(v_updates,',source_table=COALESCE(NULLIF(',p_target,'.source_table,''''),VALUES(source_table)),source_record_id=COALESCE(NULLIF(',p_target,'.source_record_id,''''),VALUES(source_record_id)),source_system=COALESCE(NULLIF(',p_target,'.source_system,''''),VALUES(source_system)),extra_json=COALESCE(NULLIF(',p_target,'.extra_json,''''),VALUES(extra_json))');
 DROP TEMPORARY TABLE IF EXISTS tmp_kg27_import_rows;
 -- Reuse the real target schema to preserve types and avoid expression-column name ambiguity.
 SET @kg27_import_sql=CONCAT('CREATE TEMPORARY TABLE tmp_kg27_import_rows LIKE `',@target_db,'`.`',p_target,'`');
 PREPARE kg27_import_stmt FROM @kg27_import_sql; EXECUTE kg27_import_stmt; DEALLOCATE PREPARE kg27_import_stmt;
 -- Preserve an existing business PK when its source_table/source_record_id already identify this source entity.
 DROP TEMPORARY TABLE IF EXISTS tmp_kg27_import_key_map;
 SET @kg27_import_sql=CONCAT('CREATE TEMPORARY TABLE tmp_kg27_import_key_map AS SELECT s.`',p_key,'` incoming_key,MIN(t.`',p_key,'`) resolved_key,COUNT(DISTINCT BINARY t.`',p_key,'`) n FROM tmp_kg27_import_rows s JOIN `',@target_db,'`.`',p_target,'` t ON BINARY t.source_table=BINARY ',QUOTE(p_source),' AND BINARY t.source_record_id=BINARY s.source_record_id GROUP BY s.`',p_key,'`');
 PREPARE kg27_import_stmt FROM @kg27_import_sql; EXECUTE kg27_import_stmt; DEALLOCATE PREPARE kg27_import_stmt;
 INSERT INTO tmp_kg27_issues SELECT p_target,p_source,incoming_key,'AMBIGUOUS_EXISTING_ENTITY','Several entity IDs have the same exact source identity; this source row is skipped.' FROM tmp_kg27_import_key_map WHERE n>1;
 SET @kg27_import_sql=CONCAT('DELETE s FROM tmp_kg27_import_rows s JOIN tmp_kg27_import_key_map m ON BINARY m.incoming_key=BINARY s.`',p_key,'` WHERE m.n>1');
 PREPARE kg27_import_stmt FROM @kg27_import_sql; EXECUTE kg27_import_stmt; DEALLOCATE PREPARE kg27_import_stmt;
 SET @kg27_import_sql=CONCAT('UPDATE tmp_kg27_import_rows s JOIN tmp_kg27_import_key_map m ON BINARY m.incoming_key=BINARY s.`',p_key,'` SET s.`',p_key,'`=m.resolved_key WHERE m.n=1');
 PREPARE kg27_import_stmt FROM @kg27_import_sql; EXECUTE kg27_import_stmt; DEALLOCATE PREPARE kg27_import_stmt;
 SET @kg27_import_sql=CONCAT('INSERT INTO tmp_kg27_import_rows(',v_cols,') SELECT ',v_values,' FROM tmp_kg27_source_rows r WHERE r.source_table=',QUOTE(p_source),' AND ',p_key_expr,' IS NOT NULL AND CHAR_LENGTH(',p_key_expr,')<=',COALESCE(v_keymax,255),' AND (',p_required,') IS NOT NULL GROUP BY ',p_key_expr);
 PREPARE kg27_import_stmt FROM @kg27_import_sql; EXECUTE kg27_import_stmt; DEALLOCATE PREPARE kg27_import_stmt;
 SET v_guard=CONCAT('fn_kg27_is_real_json(JSON_OBJECT(''join_key'',t.`',p_key,'`,''source_system'',t.source_system,''source_record_id'',t.source_record_id,''extra_json'',CAST(IF(JSON_VALID(t.extra_json),t.extra_json,''null'') AS JSON)))=1');
 IF p_target IN('kg_person','kg_paper','kg_project') THEN SET v_origin=CONCAT(' AND (t.source_table IS NULL OR t.source_table='''' OR BINARY t.source_table=BINARY ',QUOTE(p_source),')'); END IF;
 SET @kg27_import_sql=CONCAT('INSERT INTO `',@target_db,'`.`',p_target,'`(',v_cols,') SELECT ',REPLACE(CONCAT('s.',REPLACE(v_cols,',',',s.')),'s.','s.'),' FROM tmp_kg27_import_rows s LEFT JOIN `',@target_db,'`.`',p_target,'` t ON BINARY t.`',p_key,'`=BINARY s.`',p_key,'` WHERE (t.`',p_key,'` IS NULL OR ',v_guard,')',v_origin,' ON DUPLICATE KEY UPDATE ',v_updates);
 PREPARE kg27_import_stmt FROM @kg27_import_sql; EXECUTE kg27_import_stmt; SET v_n=ROW_COUNT(); DEALLOCATE PREPARE kg27_import_stmt;
 INSERT INTO tmp_kg_patch_log VALUES(CONCAT('entity:',p_target,'<-',p_source),'UPSERTED',v_n,'Real source keys only; insert missing entities and fill empty fields; conflicting non-key source fields stay NULL.');
 DROP TEMPORARY TABLE IF EXISTS tmp_kg27_import_rows;
 DROP TEMPORARY TABLE IF EXISTS tmp_kg27_import_key_map;
END$$
DELIMITER ;
CALL sp_kg27_stage_source('dwd_org_base_info');
CALL sp_kg27_stage_source('dwd_org_heis_info');
CALL sp_kg27_stage_source('dwd_research_institute_base_info');
CALL sp_kg27_stage_source('dwd_special_hongkong_company');
CALL sp_kg27_stage_source('dwd_special_taiwan_company');
CALL sp_kg27_stage_source('dwd_special_aomen_company');
CALL sp_kg27_stage_source('dwd_forg_base_info');
CALL sp_kg27_stage_source('dwd_scholar');
CALL sp_kg27_stage_source('dwd_zh_project');
CALL sp_kg27_stage_source('dwd_en_project');
CALL sp_kg27_stage_source('dwd_zh_project_output');
CALL sp_kg27_stage_source('dwd_en_project_output');
CALL sp_kg27_stage_source('dwd_zh_paper');
CALL sp_kg27_stage_source('dwd_en_paper');
SET @source_db='gkx_element'; -- element-only schema: inventors/applicants/assignees/application_reference/id
CALL sp_kg27_stage_source('dwd_patent');
SET @source_db='gkx_dwd_local';
CALL sp_kg27_stage_source('dwd_patent_title');
CALL sp_kg27_stage_source('dwd_patent_abstract');
CALL sp_kg27_stage_source('dwd_patent_family');
SET @source_db='gkx_element'; -- local copy is a different industry_code layout; element has chain_code/node_id
CALL sp_kg27_stage_source('dwd_industry_chain_info');
SET @source_db='gkx_dwd_local';
CALL sp_kg27_stage_source('dwd_org_important_news_info');
CALL sp_kg27_stage_source('dwd_org_annual_financial_info');
CALL sp_kg27_stage_source('dwd_org_stock_finance_info');
SET @source_db='gkx_element'; -- absent in gkx_dwd_local (the later idempotent re-stage call becomes a no-op)
CALL sp_kg27_stage_source('dwd_forg_stock_fin_info');
SET @source_db='gkx_dwd_local';
CALL sp_kg27_stage_source('dwd_org_changerecord_info');
CALL sp_kg27_stage_source('dwd_org_financing_info');
CALL sp_kg27_stage_source('dwd_org_recruit_info');
CALL sp_kg27_stage_source('dwd_org_company_abnormal');
CALL sp_kg27_stage_source('dwd_org_company_punish');
CALL sp_kg27_stage_source('dwd_org_company_illegal');
CALL sp_kg27_stage_source('dwd_org_risk_tax_punish');
CALL sp_kg27_stage_source('dwd_org_opt_judicial_case');
CALL sp_kg27_stage_source('dwd_org_risk_shixin');
CALL sp_kg27_stage_source('dwd_org_risk_zhixing');
CALL sp_kg27_stage_source('dwd_org_bankruptcy_public_cases');
CALL sp_kg27_stage_source('dwd_bid_base_out');

-- Missing source-backed entities needed by the seven relations.
CALL sp_kg27_import_entity('kg_organization','org_id','dwd_org_base_info','CONVERT((COALESCE(fn_kg27_json_text(r.doc,''$.org_id''),fn_kg27_json_text(r.doc,''$.company_id''),fn_kg27_json_text(r.doc,''$.entity_eid''))) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_cn","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.n_company_name''),fn_kg27_json_text(r.doc,''$.traditional_name''),fn_kg27_json_text(r.doc,''$.name_alias''),fn_kg27_json_text(r.doc,''$.name_en''))"},{"target":"name_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_en''),fn_kg27_json_text(r.doc,''$.en_name''))"},{"target":"external_id","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.external_id''),fn_kg27_json_text(r.doc,''$.company_code''),fn_kg27_json_text(r.doc,''$.school_code''),fn_kg27_json_text(r.doc,''$.credit_no''))"},{"target":"province","expr":"fn_kg27_json_text(r.doc,''$.province'')"},{"target":"city","expr":"fn_kg27_json_text(r.doc,''$.city'')"},{"target":"country","expr":"fn_kg27_json_text(r.doc,''$.country'')"},{"target":"address","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.address''),fn_kg27_json_text(r.doc,''$.company_address''),fn_kg27_json_text(r.doc,''$.reg_address''))"},{"target":"legal_rep","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.lerep''),fn_kg27_json_text(r.doc,''$.legal_person''),fn_kg27_json_text(r.doc,''$.legal_name''))"},{"target":"org_type","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.org_type''),fn_kg27_json_text(r.doc,''$.univ_type''),fn_kg27_json_text(r.doc,''$.company_type''),fn_kg27_json_text(r.doc,''$.industry_type''))"}]');
CALL sp_kg27_import_entity('kg_organization','org_id','dwd_org_heis_info','CONVERT((COALESCE(fn_kg27_json_text(r.doc,''$.org_id''),fn_kg27_json_text(r.doc,''$.company_id''),fn_kg27_json_text(r.doc,''$.entity_eid''))) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_cn","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.n_company_name''),fn_kg27_json_text(r.doc,''$.traditional_name''),fn_kg27_json_text(r.doc,''$.name_alias''),fn_kg27_json_text(r.doc,''$.name_en''))"},{"target":"name_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_en''),fn_kg27_json_text(r.doc,''$.en_name''))"},{"target":"external_id","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.external_id''),fn_kg27_json_text(r.doc,''$.company_code''),fn_kg27_json_text(r.doc,''$.school_code''),fn_kg27_json_text(r.doc,''$.credit_no''))"},{"target":"province","expr":"fn_kg27_json_text(r.doc,''$.province'')"},{"target":"city","expr":"fn_kg27_json_text(r.doc,''$.city'')"},{"target":"country","expr":"fn_kg27_json_text(r.doc,''$.country'')"},{"target":"address","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.address''),fn_kg27_json_text(r.doc,''$.company_address''),fn_kg27_json_text(r.doc,''$.reg_address''))"},{"target":"legal_rep","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.lerep''),fn_kg27_json_text(r.doc,''$.legal_person''),fn_kg27_json_text(r.doc,''$.legal_name''))"},{"target":"org_type","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.org_type''),fn_kg27_json_text(r.doc,''$.univ_type''),fn_kg27_json_text(r.doc,''$.company_type''),fn_kg27_json_text(r.doc,''$.industry_type''))"}]');
CALL sp_kg27_import_entity('kg_organization','org_id','dwd_research_institute_base_info','CONVERT((COALESCE(fn_kg27_json_text(r.doc,''$.org_id''),fn_kg27_json_text(r.doc,''$.company_id''),fn_kg27_json_text(r.doc,''$.entity_eid''))) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_cn","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.n_company_name''),fn_kg27_json_text(r.doc,''$.traditional_name''),fn_kg27_json_text(r.doc,''$.name_alias''),fn_kg27_json_text(r.doc,''$.name_en''))"},{"target":"name_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_en''),fn_kg27_json_text(r.doc,''$.en_name''))"},{"target":"external_id","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.external_id''),fn_kg27_json_text(r.doc,''$.company_code''),fn_kg27_json_text(r.doc,''$.school_code''),fn_kg27_json_text(r.doc,''$.credit_no''))"},{"target":"province","expr":"fn_kg27_json_text(r.doc,''$.province'')"},{"target":"city","expr":"fn_kg27_json_text(r.doc,''$.city'')"},{"target":"country","expr":"fn_kg27_json_text(r.doc,''$.country'')"},{"target":"address","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.address''),fn_kg27_json_text(r.doc,''$.company_address''),fn_kg27_json_text(r.doc,''$.reg_address''))"},{"target":"legal_rep","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.lerep''),fn_kg27_json_text(r.doc,''$.legal_person''),fn_kg27_json_text(r.doc,''$.legal_name''))"},{"target":"org_type","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.org_type''),fn_kg27_json_text(r.doc,''$.univ_type''),fn_kg27_json_text(r.doc,''$.company_type''),fn_kg27_json_text(r.doc,''$.industry_type''))"}]');
CALL sp_kg27_import_entity('kg_organization','org_id','dwd_special_hongkong_company','CONVERT((COALESCE(fn_kg27_json_text(r.doc,''$.org_id''),fn_kg27_json_text(r.doc,''$.company_id''),fn_kg27_json_text(r.doc,''$.entity_eid''))) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_cn","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.n_company_name''),fn_kg27_json_text(r.doc,''$.traditional_name''),fn_kg27_json_text(r.doc,''$.name_alias''),fn_kg27_json_text(r.doc,''$.name_en''))"},{"target":"name_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_en''),fn_kg27_json_text(r.doc,''$.en_name''))"},{"target":"external_id","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.external_id''),fn_kg27_json_text(r.doc,''$.company_code''),fn_kg27_json_text(r.doc,''$.school_code''),fn_kg27_json_text(r.doc,''$.credit_no''))"},{"target":"province","expr":"fn_kg27_json_text(r.doc,''$.province'')"},{"target":"city","expr":"fn_kg27_json_text(r.doc,''$.city'')"},{"target":"country","expr":"fn_kg27_json_text(r.doc,''$.country'')"},{"target":"address","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.address''),fn_kg27_json_text(r.doc,''$.company_address''),fn_kg27_json_text(r.doc,''$.reg_address''))"},{"target":"legal_rep","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.lerep''),fn_kg27_json_text(r.doc,''$.legal_person''),fn_kg27_json_text(r.doc,''$.legal_name''))"},{"target":"org_type","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.org_type''),fn_kg27_json_text(r.doc,''$.univ_type''),fn_kg27_json_text(r.doc,''$.company_type''),fn_kg27_json_text(r.doc,''$.industry_type''))"}]');
CALL sp_kg27_import_entity('kg_organization','org_id','dwd_special_taiwan_company','CONVERT((COALESCE(fn_kg27_json_text(r.doc,''$.org_id''),fn_kg27_json_text(r.doc,''$.company_id''),fn_kg27_json_text(r.doc,''$.entity_eid''))) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_cn","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.n_company_name''),fn_kg27_json_text(r.doc,''$.traditional_name''),fn_kg27_json_text(r.doc,''$.name_alias''),fn_kg27_json_text(r.doc,''$.name_en''))"},{"target":"name_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_en''),fn_kg27_json_text(r.doc,''$.en_name''))"},{"target":"external_id","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.external_id''),fn_kg27_json_text(r.doc,''$.company_code''),fn_kg27_json_text(r.doc,''$.school_code''),fn_kg27_json_text(r.doc,''$.credit_no''))"},{"target":"province","expr":"fn_kg27_json_text(r.doc,''$.province'')"},{"target":"city","expr":"fn_kg27_json_text(r.doc,''$.city'')"},{"target":"country","expr":"fn_kg27_json_text(r.doc,''$.country'')"},{"target":"address","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.address''),fn_kg27_json_text(r.doc,''$.company_address''),fn_kg27_json_text(r.doc,''$.reg_address''))"},{"target":"legal_rep","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.lerep''),fn_kg27_json_text(r.doc,''$.legal_person''),fn_kg27_json_text(r.doc,''$.legal_name''))"},{"target":"org_type","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.org_type''),fn_kg27_json_text(r.doc,''$.univ_type''),fn_kg27_json_text(r.doc,''$.company_type''),fn_kg27_json_text(r.doc,''$.industry_type''))"}]');
CALL sp_kg27_import_entity('kg_organization','org_id','dwd_special_aomen_company','CONVERT((COALESCE(fn_kg27_json_text(r.doc,''$.org_id''),fn_kg27_json_text(r.doc,''$.company_id''),fn_kg27_json_text(r.doc,''$.entity_eid''))) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_cn","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.n_company_name''),fn_kg27_json_text(r.doc,''$.traditional_name''),fn_kg27_json_text(r.doc,''$.name_alias''),fn_kg27_json_text(r.doc,''$.name_en''))"},{"target":"name_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_en''),fn_kg27_json_text(r.doc,''$.en_name''))"},{"target":"external_id","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.external_id''),fn_kg27_json_text(r.doc,''$.company_code''),fn_kg27_json_text(r.doc,''$.school_code''),fn_kg27_json_text(r.doc,''$.credit_no''))"},{"target":"province","expr":"fn_kg27_json_text(r.doc,''$.province'')"},{"target":"city","expr":"fn_kg27_json_text(r.doc,''$.city'')"},{"target":"country","expr":"fn_kg27_json_text(r.doc,''$.country'')"},{"target":"address","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.address''),fn_kg27_json_text(r.doc,''$.company_address''),fn_kg27_json_text(r.doc,''$.reg_address''))"},{"target":"legal_rep","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.lerep''),fn_kg27_json_text(r.doc,''$.legal_person''),fn_kg27_json_text(r.doc,''$.legal_name''))"},{"target":"org_type","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.org_type''),fn_kg27_json_text(r.doc,''$.univ_type''),fn_kg27_json_text(r.doc,''$.company_type''),fn_kg27_json_text(r.doc,''$.industry_type''))"}]');
CALL sp_kg27_import_entity('kg_organization','org_id','dwd_forg_base_info','CONVERT((COALESCE(fn_kg27_json_text(r.doc,''$.org_id''),fn_kg27_json_text(r.doc,''$.company_id''),fn_kg27_json_text(r.doc,''$.entity_eid''))) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_cn","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_cn''),fn_kg27_json_text(r.doc,''$.org_loc_name''),fn_kg27_json_text(r.doc,''$.company_name''),fn_kg27_json_text(r.doc,''$.n_company_name''),fn_kg27_json_text(r.doc,''$.traditional_name''),fn_kg27_json_text(r.doc,''$.name_alias''),fn_kg27_json_text(r.doc,''$.name_en''))"},{"target":"name_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.name_en''),fn_kg27_json_text(r.doc,''$.en_name''))"},{"target":"external_id","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.external_id''),fn_kg27_json_text(r.doc,''$.company_code''),fn_kg27_json_text(r.doc,''$.school_code''),fn_kg27_json_text(r.doc,''$.credit_no''))"},{"target":"province","expr":"fn_kg27_json_text(r.doc,''$.province'')"},{"target":"city","expr":"fn_kg27_json_text(r.doc,''$.city'')"},{"target":"country","expr":"fn_kg27_json_text(r.doc,''$.country'')"},{"target":"address","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.address''),fn_kg27_json_text(r.doc,''$.company_address''),fn_kg27_json_text(r.doc,''$.reg_address''))"},{"target":"legal_rep","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.lerep''),fn_kg27_json_text(r.doc,''$.legal_person''),fn_kg27_json_text(r.doc,''$.legal_name''))"},{"target":"org_type","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.org_type''),fn_kg27_json_text(r.doc,''$.univ_type''),fn_kg27_json_text(r.doc,''$.company_type''),fn_kg27_json_text(r.doc,''$.industry_type''))"}]');
CALL sp_kg27_import_entity('kg_person','person_id','dwd_scholar','CONVERT((fn_kg27_json_text(r.doc,''$.scholar_id'')) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.name_zh''),fn_kg27_json_text(r.doc,''$.name_en''))','[{"target":"name_zh","expr":"fn_kg27_json_text(r.doc,''$.name_zh'')"},{"target":"name_en","expr":"fn_kg27_json_text(r.doc,''$.name_en'')"},{"target":"scholar_org_name_zh","expr":"fn_kg27_json_text(r.doc,''$.scholar_org_name_zh'')"},{"target":"scholar_org_name_en","expr":"fn_kg27_json_text(r.doc,''$.scholar_org_name_en'')"},{"target":"work_experience_institution_zh","expr":"fn_kg27_json_text(r.doc,''$.work_experience_institution_zh'')"},{"target":"work_experience_institution_en","expr":"fn_kg27_json_text(r.doc,''$.work_experience_institution_en'')"},{"target":"scholar_org","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.scholar_org_name_zh''),fn_kg27_json_text(r.doc,''$.scholar_org_name_en''))"}]');
CALL sp_kg27_import_entity('kg_project','id','dwd_zh_project','CONVERT((fn_kg27_json_text(r.doc,''$.id'')) USING utf8mb4) COLLATE utf8mb4_bin','fn_kg27_json_text(r.doc,''$.title'')','[{"target":"project_number","expr":"fn_kg27_json_text(r.doc,''$.project_number'')"},{"target":"title","expr":"fn_kg27_json_text(r.doc,''$.title'')"},{"target":"participants","expr":"fn_kg27_json_text(r.doc,''$.participants'')"},{"target":"project_host","expr":"fn_kg27_json_text(r.doc,''$.project_host'')"},{"target":"funded_institution","expr":"fn_kg27_json_text(r.doc,''$.funded_institution'')"},{"target":"participating_institution","expr":"fn_kg27_json_text(r.doc,''$.participating_institution'')"},{"target":"funded_amount","expr":"fn_kg27_json_text(r.doc,''$.funded_amount'')"},{"target":"discipline","expr":"fn_kg27_json_text(r.doc,''$.discipline'')"},{"target":"abstract","expr":"fn_kg27_json_text(r.doc,''$.abstract'')"}]');
CALL sp_kg27_import_entity('kg_paper','id','dwd_zh_paper','CONVERT((fn_kg27_json_text(r.doc,''$.id'')) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.zh_name''),fn_kg27_json_text(r.doc,''$.en_name''),fn_kg27_json_text(r.doc,''$.title_zh''),fn_kg27_json_text(r.doc,''$.title_en''),fn_kg27_json_text(r.doc,''$.doi''))','[{"target":"title_zh","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.zh_name''),fn_kg27_json_text(r.doc,''$.title_zh''))"},{"target":"title_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.en_name''),fn_kg27_json_text(r.doc,''$.title_en''))"},{"target":"doi","expr":"fn_kg27_json_text(r.doc,''$.doi'')"},{"target":"publication_id","expr":"fn_kg27_json_text(r.doc,''$.publication_id'')"},{"target":"publication_year","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.cover_year_start''),fn_kg27_json_text(r.doc,''$.publication_year''))"},{"target":"publication_date","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.cover_date_start''),fn_kg27_json_text(r.doc,''$.publication_date''))"}]');
CALL sp_kg27_import_entity('kg_project','id','dwd_en_project','CONVERT((fn_kg27_json_text(r.doc,''$.id'')) USING utf8mb4) COLLATE utf8mb4_bin','fn_kg27_json_text(r.doc,''$.title'')','[{"target":"project_number","expr":"fn_kg27_json_text(r.doc,''$.project_number'')"},{"target":"title","expr":"fn_kg27_json_text(r.doc,''$.title'')"},{"target":"participants","expr":"fn_kg27_json_text(r.doc,''$.participants'')"},{"target":"project_host","expr":"fn_kg27_json_text(r.doc,''$.project_host'')"},{"target":"funded_institution","expr":"fn_kg27_json_text(r.doc,''$.funded_institution'')"},{"target":"participating_institution","expr":"fn_kg27_json_text(r.doc,''$.participating_institution'')"},{"target":"funded_amount","expr":"fn_kg27_json_text(r.doc,''$.funded_amount'')"},{"target":"discipline","expr":"fn_kg27_json_text(r.doc,''$.discipline'')"},{"target":"abstract","expr":"fn_kg27_json_text(r.doc,''$.abstract'')"}]');
CALL sp_kg27_import_entity('kg_paper','id','dwd_en_paper','CONVERT((fn_kg27_json_text(r.doc,''$.id'')) USING utf8mb4) COLLATE utf8mb4_bin','COALESCE(fn_kg27_json_text(r.doc,''$.zh_name''),fn_kg27_json_text(r.doc,''$.en_name''),fn_kg27_json_text(r.doc,''$.title_zh''),fn_kg27_json_text(r.doc,''$.title_en''),fn_kg27_json_text(r.doc,''$.doi''))','[{"target":"title_zh","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.zh_name''),fn_kg27_json_text(r.doc,''$.title_zh''))"},{"target":"title_en","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.en_name''),fn_kg27_json_text(r.doc,''$.title_en''))"},{"target":"doi","expr":"fn_kg27_json_text(r.doc,''$.doi'')"},{"target":"publication_id","expr":"fn_kg27_json_text(r.doc,''$.publication_id'')"},{"target":"publication_year","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.cover_year_start''),fn_kg27_json_text(r.doc,''$.publication_year''))"},{"target":"publication_date","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.cover_date_start''),fn_kg27_json_text(r.doc,''$.publication_date''))"}]');
SET @source_db='gkx_element'; -- patent arrays/application_reference only exist in element
CALL sp_kg27_import_entity('kg_patent','patent_id','dwd_patent','CONVERT((fn_kg27_json_text(r.doc,''$.patent_id'')) USING utf8mb4) COLLATE utf8mb4_bin','fn_kg27_json_text(r.doc,''$.patent_id'')','[{"target":"publication_number","expr":"fn_kg27_json_text(r.doc,''$.publication_number'')"},{"target":"application_number","expr":"COALESCE(fn_kg27_json_text(r.doc,''$.application_number''),fn_kg27_json_text(fn_kg27_json_text(r.doc,''$.application_reference''),''$.apno''))"},{"target":"inventors","expr":"fn_kg27_json_text(r.doc,''$.inventors'')"},{"target":"applicants","expr":"fn_kg27_json_text(r.doc,''$.applicants'')"},{"target":"assignees","expr":"fn_kg27_json_text(r.doc,''$.assignees'')"},{"target":"simple_family_number","expr":"fn_kg27_json_text(r.doc,''$.simple_family_number'')"},{"target":"title_zh","expr":"fn_kg27_json_text(r.doc,''$.title_zh'')"},{"target":"title_en","expr":"fn_kg27_json_text(r.doc,''$.title_en'')"},{"target":"source_patent_row_id","expr":"fn_kg27_json_text(r.doc,''$.id'')"}]');
CALL sp_kg27_import_entity('kg_industry_chain','chain_code','dwd_industry_chain_info','CONVERT((fn_kg27_json_text(r.doc,''$.chain_code'')) USING utf8mb4) COLLATE utf8mb4_bin','fn_kg27_json_text(r.doc,''$.chain_code'')','[{"target":"chain_name","expr":"fn_kg27_json_text(r.doc,''$.chain_name'')"}]');
CALL sp_kg27_import_entity('kg_industry_node','node_id','dwd_industry_chain_info','CONVERT((fn_kg27_json_text(r.doc,''$.node_id'')) USING utf8mb4) COLLATE utf8mb4_bin','fn_kg27_json_text(r.doc,''$.node_id'')','[{"target":"node_name","expr":"fn_kg27_json_text(r.doc,''$.node_name'')"},{"target":"node_type","expr":"fn_kg27_json_text(r.doc,''$.node_type'')"},{"target":"level","expr":"fn_kg27_json_text(r.doc,''$.level'')"},{"target":"node_seq","expr":"fn_kg27_json_text(r.doc,''$.node_seq'')"},{"target":"node_imp_level","expr":"fn_kg27_json_text(r.doc,''$.node_imp_level'')"},{"target":"node_stage","expr":"fn_kg27_json_text(r.doc,''$.node_stage'')"},{"target":"node_path","expr":"fn_kg27_json_text(r.doc,''$.node_path'')"}]');
SET @source_db='gkx_dwd_local';


-- Restore project people/institutions and outputs by exact unique project id; preserve zh/en origin.
-- DEV-NOTE 20261027: the original sp_kg27_fill_from_source shape (multi-table UPDATE joining two
-- persistent tables) spins in state "Opening tables" on the tech-kg-mysql instance (CPU-bound,
-- killed after 20+ min twice). The equivalent two-step relay below was executed instead and
-- verified: materialize unique-key source rows into a session temp table, then UPDATE the target
-- joined to that temp table only. Semantics preserved: unique source key (HAVING COUNT(*)=1),
-- is_deleted filter, fill-empty-only, affinity filter on target source_table, oversize values are
-- never truncated (guarded to NULL and left for the log). Temp tables are session-local.

-- ---- kg_project people/institutions from dwd_zh_project
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_zhp;
CREATE TEMPORARY TABLE tmp_kg27_zhp (k VARBINARY(64) PRIMARY KEY, participants MEDIUMTEXT, project_host VARCHAR(255), funded_institution MEDIUMTEXT, participating_institution MEDIUMTEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_zhp
SELECT BINARY CAST(s.id AS CHAR),
  MAX(NULLIF(TRIM(CAST(s.participants AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.project_host AS CHAR CHARACTER SET utf8mb4)),''))<=255,NULLIF(TRIM(CAST(s.project_host AS CHAR CHARACTER SET utf8mb4)),''),NULL)),
  MAX(NULLIF(TRIM(CAST(s.funded_institution AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.participating_institution AS CHAR CHARACTER SET utf8mb4)),''))
FROM gkx_dwd_local.dwd_zh_project s
WHERE s.id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_project t JOIN tmp_kg27_zhp f ON f.k=BINARY CAST(t.id AS CHAR)
SET t.participants=CASE WHEN t.participants IS NULL OR TRIM(CAST(t.participants AS CHAR))='' THEN f.participants ELSE t.participants END,
    t.project_host=CASE WHEN t.project_host IS NULL OR TRIM(CAST(t.project_host AS CHAR))='' THEN f.project_host ELSE t.project_host END,
    t.funded_institution=CASE WHEN t.funded_institution IS NULL OR TRIM(CAST(t.funded_institution AS CHAR))='' THEN f.funded_institution ELSE t.funded_institution END,
    t.participating_institution=CASE WHEN t.participating_institution IS NULL OR TRIM(CAST(t.participating_institution AS CHAR))='' THEN f.participating_institution ELSE t.participating_institution END
WHERE (t.source_table IS NULL OR TRIM(t.source_table)='' OR BINARY t.source_table=BINARY 'dwd_zh_project');
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_project.people_zh','UPDATED',ROW_COUNT(),'Relay fill from dwd_zh_project by exact unique id; empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_zhp;

-- ---- kg_project people/institutions from dwd_en_project
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_enp;
CREATE TEMPORARY TABLE tmp_kg27_enp (k VARBINARY(64) PRIMARY KEY, participants MEDIUMTEXT, project_host VARCHAR(255), funded_institution MEDIUMTEXT, participating_institution MEDIUMTEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_enp
SELECT BINARY CAST(s.id AS CHAR),
  MAX(NULLIF(TRIM(CAST(s.participants AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.project_host AS CHAR CHARACTER SET utf8mb4)),''))<=255,NULLIF(TRIM(CAST(s.project_host AS CHAR CHARACTER SET utf8mb4)),''),NULL)),
  MAX(NULLIF(TRIM(CAST(s.funded_institution AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.participating_institution AS CHAR CHARACTER SET utf8mb4)),''))
FROM gkx_dwd_local.dwd_en_project s
WHERE s.id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_project t JOIN tmp_kg27_enp f ON f.k=BINARY CAST(t.id AS CHAR)
SET t.participants=CASE WHEN t.participants IS NULL OR TRIM(CAST(t.participants AS CHAR))='' THEN f.participants ELSE t.participants END,
    t.project_host=CASE WHEN t.project_host IS NULL OR TRIM(CAST(t.project_host AS CHAR))='' THEN f.project_host ELSE t.project_host END,
    t.funded_institution=CASE WHEN t.funded_institution IS NULL OR TRIM(CAST(t.funded_institution AS CHAR))='' THEN f.funded_institution ELSE t.funded_institution END,
    t.participating_institution=CASE WHEN t.participating_institution IS NULL OR TRIM(CAST(t.participating_institution AS CHAR))='' THEN f.participating_institution ELSE t.participating_institution END
WHERE (t.source_table IS NULL OR TRIM(t.source_table)='' OR BINARY t.source_table=BINARY 'dwd_en_project');
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_project.people_en','UPDATED',ROW_COUNT(),'Relay fill from dwd_en_project by exact unique id; empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_enp;

-- ---- kg_project outputs from dwd_zh_project_output / dwd_en_project_output
-- (output_degree_papers has no source column in either output table; logged, not invented.)
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_zho;
CREATE TEMPORARY TABLE tmp_kg27_zho (k VARBINARY(64) PRIMARY KEY, ja MEDIUMTEXT, cp MEDIUMTEXT, pt MEDIUMTEXT, rp MEDIUMTEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_zho
SELECT BINARY CAST(s.id AS CHAR),
  MAX(NULLIF(TRIM(CAST(s.output_journal_articles AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.output_conference_papers AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.output_patents AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.output_reports AS CHAR CHARACTER SET utf8mb4)),''))
FROM gkx_dwd_local.dwd_zh_project_output s
WHERE s.id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_project t JOIN tmp_kg27_zho f ON f.k=BINARY CAST(t.id AS CHAR)
SET t.output_journal_articles=CASE WHEN t.output_journal_articles IS NULL OR TRIM(CAST(t.output_journal_articles AS CHAR))='' THEN f.ja ELSE t.output_journal_articles END,
    t.output_conference_papers=CASE WHEN t.output_conference_papers IS NULL OR TRIM(CAST(t.output_conference_papers AS CHAR))='' THEN f.cp ELSE t.output_conference_papers END,
    t.output_patents=CASE WHEN t.output_patents IS NULL OR TRIM(CAST(t.output_patents AS CHAR))='' THEN f.pt ELSE t.output_patents END,
    t.output_reports=CASE WHEN t.output_reports IS NULL OR TRIM(CAST(t.output_reports AS CHAR))='' THEN f.rp ELSE t.output_reports END
WHERE (t.source_table IS NULL OR TRIM(t.source_table)='' OR BINARY t.source_table=BINARY 'dwd_zh_project');
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_project.outputs_zh','UPDATED',ROW_COUNT(),'Relay fill from dwd_zh_project_output by exact unique id; empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_zho;

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_eno;
CREATE TEMPORARY TABLE tmp_kg27_eno (k VARBINARY(64) PRIMARY KEY, ja MEDIUMTEXT, cp MEDIUMTEXT, pt MEDIUMTEXT, rp MEDIUMTEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_eno
SELECT BINARY CAST(s.id AS CHAR),
  MAX(NULLIF(TRIM(CAST(s.output_journal_articles AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.output_conference_papers AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.output_patents AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.output_reports AS CHAR CHARACTER SET utf8mb4)),''))
FROM gkx_dwd_local.dwd_en_project_output s
WHERE s.id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_project t JOIN tmp_kg27_eno f ON f.k=BINARY CAST(t.id AS CHAR)
SET t.output_journal_articles=CASE WHEN t.output_journal_articles IS NULL OR TRIM(CAST(t.output_journal_articles AS CHAR))='' THEN f.ja ELSE t.output_journal_articles END,
    t.output_conference_papers=CASE WHEN t.output_conference_papers IS NULL OR TRIM(CAST(t.output_conference_papers AS CHAR))='' THEN f.cp ELSE t.output_conference_papers END,
    t.output_patents=CASE WHEN t.output_patents IS NULL OR TRIM(CAST(t.output_patents AS CHAR))='' THEN f.pt ELSE t.output_patents END,
    t.output_reports=CASE WHEN t.output_reports IS NULL OR TRIM(CAST(t.output_reports AS CHAR))='' THEN f.rp ELSE t.output_reports END
WHERE (t.source_table IS NULL OR TRIM(t.source_table)='' OR BINARY t.source_table=BINARY 'dwd_en_project');
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_project.outputs_en','UPDATED',ROW_COUNT(),'Relay fill from dwd_en_project_output by exact unique id; empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_eno;
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_project.output_degree_papers','SKIPPED',0,'No output_degree_papers column exists in dwd_zh_project_output or dwd_en_project_output; nothing invented.');

-- ---- kg_patent arrays / source row id / family number from gkx_element.dwd_patent
-- (inventors/applicants/assignees exist only in element's dwd_patent)
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_pat;
CREATE TEMPORARY TABLE tmp_kg27_pat (k VARBINARY(64) PRIMARY KEY, inventors MEDIUMTEXT, applicants MEDIUMTEXT, assignees MEDIUMTEXT, src_row VARCHAR(255), fam VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_pat
SELECT BINARY CAST(s.patent_id AS CHAR),
  MAX(NULLIF(TRIM(CAST(s.inventors AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.applicants AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.assignees AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.id AS CHAR)),''))<=255,NULLIF(TRIM(CAST(s.id AS CHAR)),''),NULL)),
  MAX(IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.simple_family_number AS CHAR CHARACTER SET utf8mb4)),''))<=64,NULLIF(TRIM(CAST(s.simple_family_number AS CHAR CHARACTER SET utf8mb4)),''),NULL))
FROM gkx_element.dwd_patent s
WHERE s.patent_id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.patent_id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_patent t JOIN tmp_kg27_pat f ON f.k=BINARY CAST(t.patent_id AS CHAR)
SET t.inventors=CASE WHEN t.inventors IS NULL OR TRIM(CAST(t.inventors AS CHAR))='' THEN f.inventors ELSE t.inventors END,
    t.applicants=CASE WHEN t.applicants IS NULL OR TRIM(CAST(t.applicants AS CHAR))='' THEN f.applicants ELSE t.applicants END,
    t.assignees=CASE WHEN t.assignees IS NULL OR TRIM(CAST(t.assignees AS CHAR))='' THEN f.assignees ELSE t.assignees END,
    t.source_patent_row_id=CASE WHEN t.source_patent_row_id IS NULL OR TRIM(t.source_patent_row_id)='' THEN f.src_row ELSE t.source_patent_row_id END,
    t.simple_family_number=CASE WHEN t.simple_family_number IS NULL OR TRIM(t.simple_family_number)='' THEN f.fam ELSE t.simple_family_number END;
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_patent.arrays_element','UPDATED',ROW_COUNT(),'Relay fill from gkx_element.dwd_patent by exact unique patent_id; empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_pat;

-- ---- kg_patent family number from dwd_patent_family (local copy)
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_fam;
CREATE TEMPORARY TABLE tmp_kg27_fam (k VARBINARY(64) PRIMARY KEY, fam VARCHAR(64)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_fam
SELECT BINARY CAST(s.patent_id AS CHAR),
  MAX(IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.simple_family_number AS CHAR CHARACTER SET utf8mb4)),''))<=64,NULLIF(TRIM(CAST(s.simple_family_number AS CHAR CHARACTER SET utf8mb4)),''),NULL))
FROM gkx_dwd_local.dwd_patent_family s
WHERE s.patent_id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.patent_id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_patent t JOIN tmp_kg27_fam f ON f.k=BINARY CAST(t.patent_id AS CHAR)
SET t.simple_family_number=CASE WHEN t.simple_family_number IS NULL OR TRIM(t.simple_family_number)='' THEN f.fam ELSE t.simple_family_number END;
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_patent.family_local','UPDATED',ROW_COUNT(),'Relay fill from dwd_patent_family by exact unique patent_id; empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_fam;

-- ---- kg_patent titles from dwd_patent_title
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_ttl;
CREATE TEMPORARY TABLE tmp_kg27_ttl (k VARBINARY(64) PRIMARY KEY, tz VARCHAR(1024), te VARCHAR(1024)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_ttl
SELECT BINARY CAST(s.patent_id AS CHAR),
  MAX(IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.title_zh AS CHAR CHARACTER SET utf8mb4)),''))<=1024,NULLIF(TRIM(CAST(s.title_zh AS CHAR CHARACTER SET utf8mb4)),''),NULL)),
  MAX(COALESCE(
    IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.title_en AS CHAR CHARACTER SET utf8mb4)),''))<=1024,NULLIF(TRIM(CAST(s.title_en AS CHAR CHARACTER SET utf8mb4)),''),NULL),
    IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.title_localized AS CHAR CHARACTER SET utf8mb4)),''))<=1024,NULLIF(TRIM(CAST(s.title_localized AS CHAR CHARACTER SET utf8mb4)),''),NULL)))
FROM gkx_dwd_local.dwd_patent_title s
WHERE s.patent_id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.patent_id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_patent t JOIN tmp_kg27_ttl f ON f.k=BINARY CAST(t.patent_id AS CHAR)
SET t.title_zh=CASE WHEN t.title_zh IS NULL OR TRIM(CAST(t.title_zh AS CHAR))='' THEN f.tz ELSE t.title_zh END,
    t.title_en=CASE WHEN t.title_en IS NULL OR TRIM(CAST(t.title_en AS CHAR))='' THEN f.te ELSE t.title_en END;
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_patent.titles','UPDATED',ROW_COUNT(),'Relay fill from dwd_patent_title (title_en falls back to title_localized); empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_ttl;

-- ---- kg_person scholar org names from dwd_scholar (only existing scholar-origin rows, keyed by source_record_id)
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_sch;
CREATE TEMPORARY TABLE tmp_kg27_sch (k VARBINARY(64) PRIMARY KEY, oz MEDIUMTEXT, oe MEDIUMTEXT) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_sch
SELECT BINARY CAST(s.scholar_id AS CHAR),
  MAX(NULLIF(TRIM(CAST(s.scholar_org_name_zh AS CHAR CHARACTER SET utf8mb4)),'')),
  MAX(NULLIF(TRIM(CAST(s.scholar_org_name_en AS CHAR CHARACTER SET utf8mb4)),''))
FROM gkx_dwd_local.dwd_scholar s
WHERE s.scholar_id IS NOT NULL AND COALESCE(CAST(s.is_deleted AS SIGNED),0)=0
GROUP BY BINARY CAST(s.scholar_id AS CHAR) HAVING COUNT(*)=1;
UPDATE kg_person t JOIN tmp_kg27_sch f ON f.k=BINARY CAST(t.source_record_id AS CHAR)
SET t.scholar_org_name_zh=CASE WHEN t.scholar_org_name_zh IS NULL OR TRIM(CAST(t.scholar_org_name_zh AS CHAR))='' THEN f.oz ELSE t.scholar_org_name_zh END,
    t.scholar_org_name_en=CASE WHEN t.scholar_org_name_en IS NULL OR TRIM(CAST(t.scholar_org_name_en AS CHAR))='' THEN f.oe ELSE t.scholar_org_name_en END
WHERE (t.source_table IS NULL OR TRIM(t.source_table)='' OR BINARY t.source_table=BINARY 'dwd_scholar');
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_person.scholar_org','UPDATED',ROW_COUNT(),'Only existing scholar-origin people enriched; empty targets only.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_sch;
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_person.scholar_org','SKIPPED',0,'kg_person has no scholar_org or work_experience source columns in dwd_scholar; nothing invented.');

-- ---- kg_industry_node.chain_code from gkx_element.dwd_industry_chain_info (single-chain nodes only)
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_chn;
CREATE TEMPORARY TABLE tmp_kg27_chn (k VARBINARY(64) PRIMARY KEY, cc VARCHAR(255)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_chn
SELECT BINARY CAST(s.node_id AS CHAR),
  MAX(IF(CHAR_LENGTH(NULLIF(TRIM(CAST(s.chain_code AS CHAR CHARACTER SET utf8mb4)),''))<=255,NULLIF(TRIM(CAST(s.chain_code AS CHAR CHARACTER SET utf8mb4)),''),NULL))
FROM gkx_element.dwd_industry_chain_info s
WHERE s.node_id IS NOT NULL AND s.chain_code IS NOT NULL AND TRIM(s.chain_code)<>''
GROUP BY BINARY CAST(s.node_id AS CHAR) HAVING COUNT(DISTINCT BINARY s.chain_code)=1;
UPDATE kg_industry_node t JOIN tmp_kg27_chn f ON f.k=BINARY CAST(t.node_id AS CHAR)
SET t.chain_code=CASE WHEN t.chain_code IS NULL OR TRIM(t.chain_code)='' THEN f.cc ELSE t.chain_code END;
INSERT INTO tmp_kg_patch_log VALUES('fill:kg_industry_node.chain_code','UPDATED',ROW_COUNT(),'Single-chain nodes only; multi-chain nodes not collapsed.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_chn;

-- Recover existing news/event provenance from stored raw snapshots. No transformed-row hash is recomputed.
-- Same relay form: stage empty-organization_id rows whose snapshot carries an org_id candidate,
-- resolve the candidate against kg_organization, then apply. Only exact existing organization IDs;
-- conflicting snapshot IDs and explicit test markers excluded (fn_kg27_is_real_json guard).
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_norg;
CREATE TEMPORARY TABLE tmp_kg27_norg (k VARBINARY(64) PRIMARY KEY, oc VARBINARY(64), oke TINYINT NOT NULL DEFAULT 0, extra_json MEDIUMTEXT) ENGINE=InnoDB;
INSERT INTO tmp_kg27_norg (k, oc, extra_json)
SELECT BINARY CAST(t.news_id AS CHAR),
       BINARY COALESCE(NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(t.extra_json),t.extra_json,'null') AS JSON),'$.org_id'))),'null'),''),
                       NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(t.extra_json),t.extra_json,'null') AS JSON),'$.existing_payload.org_id'))),'null'),'')),
       t.extra_json
FROM kg_news t
WHERE (t.organization_id IS NULL OR TRIM(t.organization_id)='')
  AND fn_kg27_is_real_json(JSON_OBJECT('join_key',t.news_id,'source_system',t.source_system,'source_record_id',t.source_record_id,'organization_id',t.organization_id,'extra_json',CAST(IF(JSON_VALID(t.extra_json),t.extra_json,'null') AS JSON)))=1;
UPDATE tmp_kg27_norg f JOIN kg_organization o ON BINARY o.org_id=BINARY f.oc
SET f.oke=CASE WHEN fn_kg27_is_real_json(JSON_OBJECT('org_id',o.org_id,'source_system',o.source_system,'extra_json',CAST(IF(JSON_VALID(o.extra_json),o.extra_json,'null') AS JSON)))=1 THEN 1 ELSE 0 END
WHERE f.oc IS NOT NULL;
UPDATE tmp_kg27_norg f SET f.oke=0
WHERE f.oke=1 AND JSON_VALID(f.extra_json)
  AND BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.org_id'))),'null'),'') IS NOT NULL
  AND BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.existing_payload.org_id'))),'null'),'') IS NOT NULL
  AND BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.org_id'))),'null'),'')
   <> BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.existing_payload.org_id'))),'null'),'');
UPDATE kg_news t JOIN tmp_kg27_norg f ON BINARY f.k=BINARY CAST(t.news_id AS CHAR)
SET t.organization_id=CONVERT(f.oc USING utf8mb4)
WHERE f.oke=1 AND (t.organization_id IS NULL OR TRIM(t.organization_id)='');
INSERT INTO tmp_kg_patch_log VALUES('snapshot:kg_news.organization_id','UPDATED',ROW_COUNT(),'Only exact existing organization IDs; conflicting snapshot IDs and explicit test markers excluded.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_norg;

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_eorg;
CREATE TEMPORARY TABLE tmp_kg27_eorg (k VARBINARY(64) PRIMARY KEY, oc VARBINARY(64), oke TINYINT NOT NULL DEFAULT 0, extra_json MEDIUMTEXT) ENGINE=InnoDB;
INSERT INTO tmp_kg27_eorg (k, oc, extra_json)
SELECT BINARY CAST(t.event_id AS CHAR),
       BINARY COALESCE(NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(t.extra_json),t.extra_json,'null') AS JSON),'$.org_id'))),'null'),''),
                       NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(t.extra_json),t.extra_json,'null') AS JSON),'$.existing_payload.org_id'))),'null'),'')),
       t.extra_json
FROM kg_event t
WHERE (t.organization_id IS NULL OR TRIM(t.organization_id)='')
  AND fn_kg27_is_real_json(JSON_OBJECT('join_key',t.event_id,'source_system',t.source_system,'source_record_id',t.source_record_id,'organization_id',t.organization_id,'extra_json',CAST(IF(JSON_VALID(t.extra_json),t.extra_json,'null') AS JSON)))=1;
UPDATE tmp_kg27_eorg f JOIN kg_organization o ON BINARY o.org_id=BINARY f.oc
SET f.oke=CASE WHEN fn_kg27_is_real_json(JSON_OBJECT('org_id',o.org_id,'source_system',o.source_system,'extra_json',CAST(IF(JSON_VALID(o.extra_json),o.extra_json,'null') AS JSON)))=1 THEN 1 ELSE 0 END
WHERE f.oc IS NOT NULL;
UPDATE tmp_kg27_eorg f SET f.oke=0
WHERE f.oke=1 AND JSON_VALID(f.extra_json)
  AND BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.org_id'))),'null'),'') IS NOT NULL
  AND BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.existing_payload.org_id'))),'null'),'') IS NOT NULL
  AND BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.org_id'))),'null'),'')
   <> BINARY NULLIF(NULLIF(TRIM(JSON_UNQUOTE(JSON_EXTRACT(CAST(f.extra_json AS JSON),'$.existing_payload.org_id'))),'null'),'');
UPDATE kg_event t JOIN tmp_kg27_eorg f ON BINARY f.k=BINARY CAST(t.event_id AS CHAR)
SET t.organization_id=CONVERT(f.oc USING utf8mb4)
WHERE f.oke=1 AND (t.organization_id IS NULL OR TRIM(t.organization_id)='');
INSERT INTO tmp_kg_patch_log VALUES('snapshot:kg_event.organization_id','UPDATED',ROW_COUNT(),'Only exact existing organization IDs; conflicting snapshot IDs and explicit test markers excluded.');
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_eorg;

UPDATE kg_event SET `case_role`=COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.case_role')),'null'),''),NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.existing_payload.case_role')),'null'),'')) WHERE (`case_role` IS NULL OR TRIM(`case_role`)='') AND fn_kg27_is_real_json(JSON_OBJECT('event_id',event_id,'organization_id',organization_id,'source_system',source_system,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT INTO tmp_kg_patch_log VALUES('snapshot:kg_event.case_role','UPDATED',ROW_COUNT(),'Copies an explicit role/key only; no participant role is invented.');
UPDATE kg_event SET `exec_person_type`=COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.exec_person_type')),'null'),''),NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.existing_payload.exec_person_type')),'null'),'')) WHERE (`exec_person_type` IS NULL OR TRIM(`exec_person_type`)='') AND fn_kg27_is_real_json(JSON_OBJECT('event_id',event_id,'organization_id',organization_id,'source_system',source_system,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT INTO tmp_kg_patch_log VALUES('snapshot:kg_event.exec_person_type','UPDATED',ROW_COUNT(),'Copies an explicit role/key only; no participant role is invented.');
UPDATE kg_event SET `party_role_type`=COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.party_role_type')),'null'),''),NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.existing_payload.party_role_type')),'null'),'')) WHERE (`party_role_type` IS NULL OR TRIM(`party_role_type`)='') AND fn_kg27_is_real_json(JSON_OBJECT('event_id',event_id,'organization_id',organization_id,'source_system',source_system,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT INTO tmp_kg_patch_log VALUES('snapshot:kg_event.party_role_type','UPDATED',ROW_COUNT(),'Copies an explicit role/key only; no participant role is invented.');
UPDATE kg_event SET `u_id`=IF(CHAR_LENGTH(COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.u_id')),'null'),''),NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.existing_payload.u_id')),'null'),'')))<=255,COALESCE(NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.u_id')),'null'),''),NULLIF(NULLIF(JSON_UNQUOTE(JSON_EXTRACT(CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON),'$.existing_payload.u_id')),'null'),'')),NULL) WHERE (`u_id` IS NULL OR TRIM(`u_id`)='') AND fn_kg27_is_real_json(JSON_OBJECT('event_id',event_id,'organization_id',organization_id,'source_system',source_system,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT INTO tmp_kg_patch_log VALUES('snapshot:kg_event.u_id','UPDATED',ROW_COUNT(),'Copies an explicit role/key only; no participant role is invented.');

-- Missing family entities may be created only from an explicit family number on a source-backed patent.
INSERT INTO kg_patent_family (family_number,source_table,source_record_id,ingest_batch,ingest_time)
SELECT p.simple_family_number,'kg_patent',p.simple_family_number,'real_source_patch_20261027',DATE_FORMAT(UTC_TIMESTAMP(),'%Y-%m-%dT%H:%i:%sZ')
FROM kg_patent p LEFT JOIN kg_patent_family f ON f.family_number=p.simple_family_number
WHERE f.family_number IS NULL AND NULLIF(TRIM(p.simple_family_number),'') IS NOT NULL
AND CHAR_LENGTH(p.simple_family_number)<=64
AND fn_kg27_is_real_json(JSON_OBJECT('join_key',p.simple_family_number,'patent_id',p.patent_id,'organization_id',p.organization_id,'source_system',p.source_system,'source_record_id',p.source_record_id,'extra_json',CAST(IF(JSON_VALID(p.extra_json),p.extra_json,'null') AS JSON)))=1
GROUP BY p.simple_family_number HAVING COUNT(DISTINCT BINARY p.simple_family_number)=1;
INSERT INTO tmp_kg_patch_log VALUES('PatentFamily:explicit_patent_reference','INSERTED',ROW_COUNT(),'Distinct family numbers already asserted by eligible patent rows; no family number generated.');

-- MySQL 8.0: Report / DataSource entity completion.
-- Required context: USE target database; @source_db, @target_db;
-- tmp_kg_patch_log(step,status,affected_rows,detail);
-- fn_kg27_is_real_json(LONGTEXT), returning 1 for rows without explicit test markers.
-- No facts are embedded in this file. All Report rows come from source tables.

DELIMITER $$

DROP PROCEDURE IF EXISTS sp_kg27_report_expr$$
CREATE PROCEDURE sp_kg27_report_expr(
    IN p_table VARCHAR(128), IN p_columns VARCHAR(512), OUT p_expression LONGTEXT
)
BEGIN
    DECLARE v_list VARCHAR(512);
    DECLARE v_column VARCHAR(128);
    DECLARE v_count INT DEFAULT 0;
    SET v_list = p_columns;
    SET p_expression = 'NULL';
    choose_column: WHILE CHAR_LENGTH(v_list) > 0 DO
        SET v_column = SUBSTRING_INDEX(v_list, ',', 1);
        SELECT COUNT(*) INTO v_count
        FROM information_schema.columns
        WHERE table_schema = @source_db AND table_name = p_table AND column_name = v_column;
        IF v_count > 0 THEN
            IF p_expression = 'NULL' THEN
                SET p_expression = CONCAT('NULLIF(TRIM(CAST(s.`', REPLACE(v_column, '`', '``'), '` AS CHAR)), '''')');
            ELSE
                SET p_expression = CONCAT('COALESCE(', p_expression, ',NULLIF(TRIM(CAST(s.`', REPLACE(v_column, '`', '``'), '` AS CHAR)), ''''))');
            END IF;
        END IF;
        IF INSTR(v_list, ',') = 0 THEN
            SET v_list = '';
        ELSE
            SET v_list = SUBSTRING(v_list, INSTR(v_list, ',') + 1);
        END IF;
    END WHILE;
END$$

DROP PROCEDURE IF EXISTS sp_kg27_one_report$$
CREATE PROCEDURE sp_kg27_one_report(IN p_table VARCHAR(128))
load_source: BEGIN
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_before BIGINT DEFAULT 0;
    DECLARE v_after BIGINT DEFAULT 0;
    DECLARE v_rejected BIGINT DEFAULT 0;
    DECLARE v_json LONGTEXT;
    DECLARE v_id LONGTEXT;
    DECLARE v_title_cn LONGTEXT;
    DECLARE v_title_en LONGTEXT;
    DECLARE v_abstract_cn LONGTEXT;
    DECLARE v_abstract_en LONGTEXT;
    DECLARE v_publication_date LONGTEXT;
    DECLARE v_keywords LONGTEXT;
    DECLARE v_source_url LONGTEXT;
    DECLARE v_update_time LONGTEXT;
    SELECT COUNT(*) INTO v_count
    FROM information_schema.tables WHERE table_schema = @source_db AND table_name = p_table;
    IF v_count = 0 THEN
        INSERT INTO tmp_kg_patch_log VALUES (CONCAT('Report:', p_table), 'SKIPPED', 0, 'Source table is absent; no placeholder data created.');
        LEAVE load_source;
    END IF;
    SELECT COUNT(*) INTO v_count
    FROM information_schema.columns WHERE table_schema = @source_db AND table_name = p_table AND column_name = 'report_id';
    IF v_count = 0 THEN
        INSERT INTO tmp_kg_patch_log VALUES (CONCAT('Report:', p_table), 'SKIPPED', 0, 'Required source column report_id is absent.');
        LEAVE load_source;
    END IF;
    CALL sp_kg27_report_expr(p_table, 'report_id', v_id);
    CALL sp_kg27_report_expr(p_table, 'title_cn', v_title_cn);
    CALL sp_kg27_report_expr(p_table, 'title_en', v_title_en);
    CALL sp_kg27_report_expr(p_table, 'abstract_cn', v_abstract_cn);
    CALL sp_kg27_report_expr(p_table, 'abstract_en', v_abstract_en);
    CALL sp_kg27_report_expr(p_table, 'publication_date', v_publication_date);
    CALL sp_kg27_report_expr(p_table, 'keywords', v_keywords);
    CALL sp_kg27_report_expr(p_table, 'source_url,report_url,url', v_source_url);
    CALL sp_kg27_report_expr(p_table, 'updated_time,update_time', v_update_time);
    IF v_title_cn = 'NULL' AND v_title_en = 'NULL' THEN
        INSERT INTO tmp_kg_patch_log VALUES (CONCAT('Report:', p_table), 'SKIPPED', 0, 'Neither title_cn nor title_en exists; source identity cannot be checked conservatively.');
        LEAVE load_source;
    END IF;
    -- JSON_OBJECT contains the actual source columns, including report_id and marker columns.
    -- Valid extra_json is embedded as JSON instead of an escaped JSON string.
    SELECT CONCAT('JSON_OBJECT(', GROUP_CONCAT(
        CONCAT(QUOTE(column_name), ',',
            CASE WHEN column_name = 'extra_json' THEN
                CONCAT('IF(JSON_VALID(s.`', REPLACE(column_name, '`', '``'), '`), JSON_EXTRACT(s.`', REPLACE(column_name, '`', '``'), '`, ''$''), NULL)')
            ELSE CONCAT('s.`', REPLACE(column_name, '`', '``'), '`') END)
        ORDER BY ordinal_position SEPARATOR ','), ')') INTO v_json
    FROM information_schema.columns
    WHERE table_schema = @source_db AND table_name = p_table;
    SELECT COUNT(*) INTO v_before FROM tmp_kg27_report_stage;
    SET @kg27_report_sql = CONCAT(
        'INSERT INTO tmp_kg27_report_stage ',
        '(report_id,title_cn,title_en,abstract_cn,abstract_en,publication_date,keywords,source_url,source_table,source_update_time,extra_json) ',
        'SELECT ', v_id, ',', v_title_cn, ',', v_title_en, ',', v_abstract_cn, ',', v_abstract_en, ',',
        'IF(CHAR_LENGTH(', v_publication_date, ')<=64,', v_publication_date, ',NULL),',
        v_keywords, ',', v_source_url, ',', QUOTE(p_table), ',',
        'IF(CHAR_LENGTH(', v_update_time, ')<=64,', v_update_time, ',NULL),', v_json,
        ' FROM `', REPLACE(@source_db, '`', '``'), '`.`', REPLACE(p_table, '`', '``'), '` s ',
        'WHERE ', v_id, ' IS NOT NULL AND CHAR_LENGTH(', v_id, ')<=255 ',
        'AND COALESCE(', v_title_cn, ',', v_title_en, ') IS NOT NULL ',
        'AND fn_kg27_is_real_json(', v_json, ')=1'
    );
    PREPARE kg27_report_stmt FROM @kg27_report_sql;
    EXECUTE kg27_report_stmt;
    DEALLOCATE PREPARE kg27_report_stmt;
    SELECT COUNT(*) INTO v_after FROM tmp_kg27_report_stage;
    SET @kg27_report_sql = CONCAT(
        'SELECT COUNT(*) INTO @kg27_rejected FROM `', REPLACE(@source_db, '`', '``'), '`.`', REPLACE(p_table, '`', '``'), '` s ',
        'WHERE ', v_id, ' IS NULL OR CHAR_LENGTH(', v_id, ')>255 OR COALESCE(', v_title_cn, ',', v_title_en, ') IS NULL ',
        'OR fn_kg27_is_real_json(', v_json, ')<>1'
    );
    PREPARE kg27_report_stmt FROM @kg27_report_sql;
    EXECUTE kg27_report_stmt;
    DEALLOCATE PREPARE kg27_report_stmt;
    SET v_rejected = COALESCE(@kg27_rejected, 0);
    INSERT INTO tmp_kg_patch_log VALUES (CONCAT('Report:', p_table), 'STAGED', v_after-v_before,
        CONCAT('Eligible source rows staged; excluded invalid/untitled/explicit test rows: ', v_rejected, '. Optional absent columns remain NULL.'));
END$$

DROP PROCEDURE IF EXISTS sp_kg27_reports_and_sources$$
CREATE PROCEDURE sp_kg27_reports_and_sources()
module_main: BEGIN
    DECLARE v_count INT DEFAULT 0;
    DECLARE v_conflicts BIGINT DEFAULT 0;
    DECLARE v_affected BIGINT DEFAULT 0;
    DECLARE v_key_count INT DEFAULT 0;
    DECLARE v_target LONGTEXT;
    SET SESSION group_concat_max_len=1048576;
    SET v_target = CONCAT('`', REPLACE(@target_db, '`', '``'), '`');
    SET @kg27_report_sql = CONCAT(
        'CREATE TABLE IF NOT EXISTS ', v_target, '.`kg_report` (',
        '`report_id` VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,',
        '`title` MEDIUMTEXT,`title_cn` MEDIUMTEXT,`title_en` MEDIUMTEXT,',
        '`abstract_cn` MEDIUMTEXT,`abstract_en` MEDIUMTEXT,`publication_date` VARCHAR(64),',
        '`keywords` MEDIUMTEXT,`source_url` TEXT,`source_system` VARCHAR(128),',
        '`source_table` VARCHAR(128),`source_record_id` VARCHAR(255),',
        '`source_update_time` VARCHAR(64),`ingest_batch` VARCHAR(128),`ingest_time` VARCHAR(64),',
        '`extra_json` MEDIUMTEXT,PRIMARY KEY (`report_id`)',
        ') ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT=''报告实体；真实来源 report_id 为业务键'''
    );
    PREPARE kg27_report_stmt FROM @kg27_report_sql;
    EXECUTE kg27_report_stmt;
    DEALLOCATE PREPARE kg27_report_stmt;
    SELECT COUNT(*) INTO v_count FROM information_schema.columns
    WHERE table_schema=@target_db AND table_name='kg_report'
      AND column_name IN ('report_id','title','title_cn','title_en','abstract_cn','abstract_en','publication_date',
        'keywords','source_url','source_system','source_table','source_record_id','source_update_time','ingest_batch','ingest_time','extra_json');
    SELECT COUNT(*) INTO v_key_count FROM information_schema.key_column_usage
    WHERE table_schema=@target_db AND table_name='kg_report' AND constraint_name='PRIMARY';
    IF v_count <> 16 OR v_key_count <> 1 OR NOT EXISTS (
        SELECT 1 FROM information_schema.key_column_usage
        WHERE table_schema=@target_db AND table_name='kg_report' AND constraint_name='PRIMARY' AND column_name='report_id'
    ) THEN
        INSERT INTO tmp_kg_patch_log VALUES ('Report:target_schema','SKIPPED',0,'Existing kg_report has a different schema; no source data was merged. Required columns are listed in the module DDL.');
    ELSE
        DROP TEMPORARY TABLE IF EXISTS tmp_kg27_report_stage;
        CREATE TEMPORARY TABLE tmp_kg27_report_stage (
            report_id VARCHAR(255) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
            title_cn MEDIUMTEXT,title_en MEDIUMTEXT,abstract_cn MEDIUMTEXT,abstract_en MEDIUMTEXT,
            publication_date VARCHAR(64),keywords MEDIUMTEXT,source_url TEXT,source_table VARCHAR(128),
            source_update_time VARCHAR(64),extra_json MEDIUMTEXT,KEY (report_id)
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
        CALL sp_kg27_one_report('dwd_zh_report');
        CALL sp_kg27_one_report('dwd_en_report');
        DROP TEMPORARY TABLE IF EXISTS tmp_kg27_report_conflict;
        CREATE TEMPORARY TABLE tmp_kg27_report_conflict AS
        SELECT report_id FROM tmp_kg27_report_stage GROUP BY report_id
        HAVING COUNT(DISTINCT BINARY LOWER(TRIM(COALESCE(NULLIF(title_cn,''),NULLIF(title_en,''))))) > 1;
        SELECT COUNT(*) INTO v_conflicts FROM tmp_kg27_report_conflict;
        INSERT INTO tmp_kg_patch_log VALUES ('Report:source_id_conflicts','CONFLICT',v_conflicts,
            'These report_id groups have different nonempty preferred titles and are skipped. Different-language titles are not assumed to identify the same report.');
        DROP TEMPORARY TABLE IF EXISTS tmp_kg27_report_best;
        CREATE TEMPORARY TABLE tmp_kg27_report_best AS
        SELECT report_id,title_cn,title_en,abstract_cn,abstract_en,publication_date,keywords,source_url,
            source_table,source_update_time,extra_json
        FROM (
            SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.report_id ORDER BY s.source_table, SHA2(s.extra_json,256)) AS rn
            FROM tmp_kg27_report_stage s LEFT JOIN tmp_kg27_report_conflict c ON c.report_id=s.report_id
            WHERE c.report_id IS NULL
        ) ranked WHERE rn=1;
        -- Target conflicts are checked before the upsert. Existing nonempty values are never replaced.
        SET @kg27_report_sql = CONCAT(
            'SELECT COUNT(*) INTO @kg27_target_conflicts FROM tmp_kg27_report_best s JOIN ', v_target, '.kg_report t ON t.report_id=s.report_id ',
            'WHERE NULLIF(TRIM(COALESCE(NULLIF(t.title_cn,''''),NULLIF(t.title_en,''''),NULLIF(t.title,''''))),'''') IS NOT NULL ',
            'AND BINARY LOWER(TRIM(COALESCE(NULLIF(t.title_cn,''''),NULLIF(t.title_en,''''),NULLIF(t.title,'''')))) <> ',
            'BINARY LOWER(TRIM(COALESCE(NULLIF(s.title_cn,''''),NULLIF(s.title_en,''''))))'
        );
        PREPARE kg27_report_stmt FROM @kg27_report_sql;
        EXECUTE kg27_report_stmt;
        DEALLOCATE PREPARE kg27_report_stmt;
        INSERT INTO tmp_kg_patch_log VALUES ('Report:target_id_conflicts','CONFLICT',COALESCE(@kg27_target_conflicts,0),
            'Existing target titles disagree with source preferred titles; these report_id values are skipped.');
        SET @kg27_report_sql = CONCAT(
            'INSERT INTO ', v_target, '.kg_report ',
            '(report_id,title,title_cn,title_en,abstract_cn,abstract_en,publication_date,keywords,source_url,source_system,',
            'source_table,source_record_id,source_update_time,ingest_batch,ingest_time,extra_json) ',
            'SELECT s.report_id,COALESCE(s.title_cn,s.title_en),s.title_cn,s.title_en,s.abstract_cn,s.abstract_en,s.publication_date,',
            's.keywords,s.source_url,', QUOTE(CONCAT('mysql:',@source_db)), ',s.source_table,s.report_id,s.source_update_time,',
            '''real_source_patch_20261027'',DATE_FORMAT(UTC_TIMESTAMP(),''%Y-%m-%dT%H:%i:%sZ''),s.extra_json ',
            'FROM tmp_kg27_report_best s LEFT JOIN ', v_target, '.kg_report t ON t.report_id=s.report_id ',
            'WHERE (t.report_id IS NULL OR NULLIF(TRIM(COALESCE(NULLIF(t.title_cn,''''),NULLIF(t.title_en,''''),NULLIF(t.title,''''))),'''') IS NULL ',
            'OR BINARY LOWER(TRIM(COALESCE(NULLIF(t.title_cn,''''),NULLIF(t.title_en,''''),NULLIF(t.title,'''')))) = ',
            'BINARY LOWER(TRIM(COALESCE(NULLIF(s.title_cn,''''),NULLIF(s.title_en,''''))))) ',
            'AND (t.report_id IS NULL OR fn_kg27_is_real_json(JSON_OBJECT(',
            '''report_id'',t.report_id,''source_system'',t.source_system,''source_table'',t.source_table,',
            '''source_record_id'',t.source_record_id,''extra_json'',',
            'CAST(IF(JSON_VALID(t.extra_json),t.extra_json,''null'') AS JSON)))=1) ',
            'ON DUPLICATE KEY UPDATE ',
            'title=IF(NULLIF(TRIM(kg_report.title),'''') IS NULL,VALUES(title),kg_report.title),',
            'title_cn=IF(NULLIF(TRIM(kg_report.title_cn),'''') IS NULL,VALUES(title_cn),kg_report.title_cn),',
            'title_en=IF(NULLIF(TRIM(kg_report.title_en),'''') IS NULL,VALUES(title_en),kg_report.title_en),',
            'abstract_cn=IF(NULLIF(TRIM(kg_report.abstract_cn),'''') IS NULL,VALUES(abstract_cn),kg_report.abstract_cn),',
            'abstract_en=IF(NULLIF(TRIM(kg_report.abstract_en),'''') IS NULL,VALUES(abstract_en),kg_report.abstract_en),',
            'publication_date=IF(NULLIF(TRIM(kg_report.publication_date),'''') IS NULL,VALUES(publication_date),kg_report.publication_date),',
            'keywords=IF(NULLIF(TRIM(kg_report.keywords),'''') IS NULL,VALUES(keywords),kg_report.keywords),',
            'source_url=IF(NULLIF(TRIM(kg_report.source_url),'''') IS NULL,VALUES(source_url),kg_report.source_url),',
            'source_system=IF(NULLIF(TRIM(kg_report.source_system),'''') IS NULL,VALUES(source_system),kg_report.source_system),',
            'source_table=IF(NULLIF(TRIM(kg_report.source_table),'''') IS NULL,VALUES(source_table),kg_report.source_table),',
            'source_record_id=IF(NULLIF(TRIM(kg_report.source_record_id),'''') IS NULL,VALUES(source_record_id),kg_report.source_record_id),',
            'source_update_time=IF(NULLIF(TRIM(kg_report.source_update_time),'''') IS NULL,VALUES(source_update_time),kg_report.source_update_time),',
            'ingest_batch=IF(NULLIF(TRIM(kg_report.ingest_batch),'''') IS NULL,VALUES(ingest_batch),kg_report.ingest_batch),',
            'ingest_time=IF(NULLIF(TRIM(kg_report.ingest_time),'''') IS NULL,VALUES(ingest_time),kg_report.ingest_time),',
            'extra_json=IF(NULLIF(TRIM(kg_report.extra_json),'''') IS NULL,VALUES(extra_json),kg_report.extra_json)'
        );
        PREPARE kg27_report_stmt FROM @kg27_report_sql;
        EXECUTE kg27_report_stmt;
        SET v_affected=ROW_COUNT();
        DEALLOCATE PREPARE kg27_report_stmt;
        INSERT INTO tmp_kg_patch_log VALUES ('Report:merge','DONE',v_affected,
            'MySQL affected-row count (insert=1, changed existing row=2); source IDs preserved as business keys; only empty columns filled.');
        -- Emit conflicting identities for inspection in the same session.
        SELECT 'Report source ID collision: skipped' AS issue, report_id FROM tmp_kg27_report_conflict;
        DROP TEMPORARY TABLE IF EXISTS tmp_kg27_report_best;
        DROP TEMPORARY TABLE IF EXISTS tmp_kg27_report_conflict;
        DROP TEMPORARY TABLE IF EXISTS tmp_kg27_report_stage;
    END IF;

    SET @kg27_report_sql = CONCAT(
        'CREATE TABLE IF NOT EXISTS ',v_target,'.kg_data_source (',
        'source_table VARCHAR(128) NOT NULL,table_cn_name VARCHAR(255),tier VARCHAR(32),library VARCHAR(128),',
        'PRIMARY KEY(source_table)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci ',
        'COMMENT=''实际存在来源表的目录元数据；不代表业务事实数量'''
    );
    PREPARE kg27_report_stmt FROM @kg27_report_sql;
    EXECUTE kg27_report_stmt;
    DEALLOCATE PREPARE kg27_report_stmt;
    SELECT COUNT(*) INTO v_count FROM information_schema.columns
    WHERE table_schema=@target_db AND table_name='kg_data_source'
      AND column_name IN ('source_table','table_cn_name','tier','library');
    SELECT COUNT(*) INTO v_key_count FROM information_schema.key_column_usage
    WHERE table_schema=@target_db AND table_name='kg_data_source' AND constraint_name='PRIMARY';
    IF v_count <> 4 OR v_key_count <> 1 OR NOT EXISTS (
        SELECT 1 FROM information_schema.key_column_usage
        WHERE table_schema=@target_db AND table_name='kg_data_source' AND constraint_name='PRIMARY' AND column_name='source_table'
    ) THEN
        INSERT INTO tmp_kg_patch_log VALUES ('DataSource:target_schema','SKIPPED',0,'Existing kg_data_source differs from the expected four-column directory schema.');
        LEAVE module_main;
    END IF;
    DROP TEMPORARY TABLE IF EXISTS tmp_kg27_source_catalog;
    CREATE TEMPORARY TABLE tmp_kg27_source_catalog (
        source_table VARCHAR(128) NOT NULL PRIMARY KEY, table_cn_name VARCHAR(255) NOT NULL
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    -- Generated from pinned org_catalog.py (39 registered institution-domain source tables).
    INSERT INTO tmp_kg27_source_catalog(source_table,table_cn_name) VALUES
    ('dwd_org_base_info','机构基本信息'),
    ('dwd_org_shareholder_info','国内机构股东信息'),
    ('dwd_org_executive_info','国内机构高管信息'),
    ('dwd_org_org_product_info','国内机构经营信息'),
    ('dwd_org_annual_financial_info','年报财务信息'),
    ('dwd_org_important_news_info','重点资讯'),
    ('dwd_org_changerecord_info','工商变更'),
    ('dwd_org_merger_acquisition_info','并购事件'),
    ('dwd_org_financing_info','融资事件'),
    ('dwd_org_invest_info','投资事件'),
    ('dwd_org_recruit_info','招聘信息'),
    ('dwd_org_heis_info','高校基本信息'),
    ('dwd_org_stock_base','上市企业基本信息'),
    ('dwd_org_stock_finance_info','上市企业财务信息'),
    ('dwd_org_company_abnormal','经营异常'),
    ('dwd_org_company_punish','行政处罚'),
    ('dwd_org_company_illegal','严重违法'),
    ('dwd_org_risk_tax_punish','税收违法'),
    ('dwd_org_opt_judicial_case','司法案件'),
    ('dwd_org_risk_shixin','失信被执行人'),
    ('dwd_org_risk_zhixing','被执行人'),
    ('dwd_org_bankruptcy_public_cases','破产案件'),
    ('dwd_org_bankruptcy_public_cases_list','破产案件当事人'),
    ('dwd_special_hongkong_company','香港企业'),
    ('dwd_special_taiwan_company','台湾企业'),
    ('dwd_special_aomen_company','澳门企业'),
    ('dwd_bid_base_out','招投标公告'),
    ('dwd_bid_win_candidate_out','中标候选人'),
    ('dwd_bid_purchase_agency_out','采购代理'),
    ('dwd_bid_target_item_out','招投标标的物'),
    ('dwd_research_institute_base_info','科研机构基本信息'),
    ('dwd_forg_base_info','海外机构基本信息'),
    ('dwd_forg_shareholder_info','海外机构股东信息'),
    ('dwd_forg_subsidiary_info','海外机构子公司'),
    ('dwd_forg_executive_info','海外机构高管信息'),
    ('dwd_forg_product_info','海外机构经营信息'),
    ('dwd_forg_beneficiary_info','海外机构受益人'),
    ('dwd_forg_act_contro_info','海外机构实际控制人'),
    ('dwd_forg_stock_fin_info','海外上市企业财务信息');
    SET @kg27_report_sql = CONCAT(
        'INSERT INTO ',v_target,'.kg_data_source(source_table,table_cn_name,tier,library) ',
        'SELECT c.source_table,c.table_cn_name,''DWD'',',
        'CASE WHEN LEFT(c.source_table,9)=''dwd_forg_'' OR LEFT(c.source_table,7)=''dwd_en_'' ',
        'THEN ''国外机构要素库'' ELSE ''国内机构要素库'' END ',
        'FROM tmp_kg27_source_catalog c JOIN information_schema.tables t ',
        'ON t.table_schema=',QUOTE(@source_db),' AND t.table_name=c.source_table ',
        'ON DUPLICATE KEY UPDATE ',
        'table_cn_name=IF(NULLIF(TRIM(kg_data_source.table_cn_name),'''') IS NULL,VALUES(table_cn_name),kg_data_source.table_cn_name),',
        'tier=IF(NULLIF(TRIM(kg_data_source.tier),'''') IS NULL,VALUES(tier),kg_data_source.tier),',
        'library=IF(NULLIF(TRIM(kg_data_source.library),'''') IS NULL,VALUES(library),kg_data_source.library)'
    );
    PREPARE kg27_report_stmt FROM @kg27_report_sql;
    EXECUTE kg27_report_stmt;
    SET v_affected=ROW_COUNT();
    DEALLOCATE PREPARE kg27_report_stmt;
    INSERT INTO tmp_kg_patch_log VALUES ('DataSource:directory','DONE',v_affected,
        'Only catalog tables actually present in @source_db are registered; these are directory metadata, not fabricated entity facts.');
    DROP TEMPORARY TABLE IF EXISTS tmp_kg27_source_catalog;
END$$

CALL sp_kg27_reports_and_sources()$$
DROP PROCEDURE sp_kg27_reports_and_sources$$
DROP PROCEDURE sp_kg27_one_report$$
DROP PROCEDURE sp_kg27_report_expr$$
DELIMITER ;


-- Eligible entity IDs; uncertain/test-marked aggregates are never endpoints.
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_entity_allow;
CREATE TEMPORARY TABLE tmp_kg27_entity_allow(entity_type VARCHAR(64) NOT NULL,entity_id VARCHAR(255) NOT NULL,PRIMARY KEY(entity_type,entity_id)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'Organization',`org_id` FROM `kg_organization` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`org_id`,'source_system',source_system,'source_record_id',source_record_id,'organization_id',organization_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'Person',`person_id` FROM `kg_person` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`person_id`,'source_system',source_system,'source_record_id',source_record_id,'organization_id',organization_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'Paper',`id` FROM `kg_paper` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`id`,'source_system',source_system,'source_record_id',source_record_id,'organization_id',organization_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'Patent',`patent_id` FROM `kg_patent` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`patent_id`,'source_system',source_system,'source_record_id',source_record_id,'organization_id',organization_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'Project',`id` FROM `kg_project` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`id`,'source_system',source_system,'source_record_id',source_record_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'Report',`report_id` FROM `kg_report` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`report_id`,'source_system',source_system,'source_record_id',source_record_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'News',`news_id` FROM `kg_news` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`news_id`,'source_system',source_system,'source_record_id',source_record_id,'organization_id',organization_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'Event',`event_id` FROM `kg_event` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`event_id`,'source_system',source_system,'source_record_id',source_record_id,'organization_id',organization_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'IndustryChain',`chain_code` FROM `kg_industry_chain` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`chain_code`,'source_system',source_system,'source_record_id',source_record_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
INSERT IGNORE INTO tmp_kg27_entity_allow SELECT 'IndustryNode',`node_id` FROM `kg_industry_node` WHERE fn_kg27_is_real_json(JSON_OBJECT('join_key',`node_id`,'source_system',source_system,'source_record_id',source_record_id,'extra_json',CAST(IF(JSON_VALID(extra_json),extra_json,'null') AS JSON)))=1;
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_person_names;
CREATE TEMPORARY TABLE tmp_kg27_person_names(person_id VARCHAR(128),norm_text VARCHAR(512),norm_name VARCHAR(512),raw_name TEXT,kind VARCHAR(32),KEY ix_text(norm_text),KEY ix_name(norm_name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_org_names;
CREATE TEMPORARY TABLE tmp_kg27_org_names(org_id VARCHAR(255),norm_text VARCHAR(512),norm_name VARCHAR(512),raw_name TEXT,KEY ix_text(norm_text),KEY ix_name(norm_name)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
INSERT INTO tmp_kg27_person_names SELECT DISTINCT p.person_id,fn_kg27_norm_text(p.`name_zh`),fn_kg27_norm_name(p.`name_zh`),p.`name_zh`,'name_zh' FROM kg_person p JOIN tmp_kg27_entity_allow a ON a.entity_type='Person' AND BINARY a.entity_id=BINARY p.person_id WHERE NULLIF(TRIM(p.`name_zh`),'') IS NOT NULL AND CHAR_LENGTH(p.`name_zh`)<=512 AND CHAR_LENGTH(fn_kg27_norm_text(p.`name_zh`))<=512;
INSERT INTO tmp_kg27_person_names SELECT DISTINCT p.person_id,fn_kg27_norm_text(p.`name_cn`),fn_kg27_norm_name(p.`name_cn`),p.`name_cn`,'name_cn' FROM kg_person p JOIN tmp_kg27_entity_allow a ON a.entity_type='Person' AND BINARY a.entity_id=BINARY p.person_id WHERE NULLIF(TRIM(p.`name_cn`),'') IS NOT NULL AND CHAR_LENGTH(p.`name_cn`)<=512 AND CHAR_LENGTH(fn_kg27_norm_text(p.`name_cn`))<=512;
INSERT INTO tmp_kg27_person_names SELECT DISTINCT p.person_id,fn_kg27_norm_text(p.`name_en`),fn_kg27_norm_name(p.`name_en`),p.`name_en`,'name_en' FROM kg_person p JOIN tmp_kg27_entity_allow a ON a.entity_type='Person' AND BINARY a.entity_id=BINARY p.person_id WHERE NULLIF(TRIM(p.`name_en`),'') IS NOT NULL AND CHAR_LENGTH(p.`name_en`)<=512 AND CHAR_LENGTH(fn_kg27_norm_text(p.`name_en`))<=512;
INSERT INTO tmp_kg27_person_names SELECT DISTINCT p.person_id,fn_kg27_norm_text(p.`source_record_id`),fn_kg27_norm_name(p.`source_record_id`),p.`source_record_id`,'source_record_id' FROM kg_person p JOIN tmp_kg27_entity_allow a ON a.entity_type='Person' AND BINARY a.entity_id=BINARY p.person_id WHERE NULLIF(TRIM(p.`source_record_id`),'') IS NOT NULL AND CHAR_LENGTH(p.`source_record_id`)<=512 AND CHAR_LENGTH(fn_kg27_norm_text(p.`source_record_id`))<=512;
INSERT INTO tmp_kg27_org_names SELECT DISTINCT o.org_id,fn_kg27_norm_text(o.`name_cn`),fn_kg27_norm_name(o.`name_cn`),o.`name_cn` FROM kg_organization o JOIN tmp_kg27_entity_allow a ON a.entity_type='Organization' AND BINARY a.entity_id=BINARY o.org_id WHERE NULLIF(TRIM(o.`name_cn`),'') IS NOT NULL AND CHAR_LENGTH(o.`name_cn`)<=512 AND CHAR_LENGTH(fn_kg27_norm_text(o.`name_cn`))<=512;
INSERT INTO tmp_kg27_org_names SELECT DISTINCT o.org_id,fn_kg27_norm_text(o.`name_en`),fn_kg27_norm_name(o.`name_en`),o.`name_en` FROM kg_organization o JOIN tmp_kg27_entity_allow a ON a.entity_type='Organization' AND BINARY a.entity_id=BINARY o.org_id WHERE NULLIF(TRIM(o.`name_en`),'') IS NOT NULL AND CHAR_LENGTH(o.`name_en`)<=512 AND CHAR_LENGTH(fn_kg27_norm_text(o.`name_en`))<=512;


-- Source-backed Event entity completion only. No relationship tables are used.
-- MySQL 8.0.21+. This module is assembled after the shared preflight/staging code.
-- No graph VID/EID is reused. New events require complete unique real business keys.
-- Existing nonempty fields are preserved. Ambiguity and conflicting source evidence enter issues.

DELIMITER $$
DROP FUNCTION IF EXISTS fn_kg27_or_text$$
CREATE FUNCTION fn_kg27_or_text(p_doc LONGTEXT, p_path VARCHAR(1024))
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN
  DECLARE v JSON;
  DECLARE s LONGTEXT;
  IF p_doc IS NULL OR JSON_VALID(p_doc)=0 THEN RETURN NULL; END IF;
  SET v=JSON_EXTRACT(p_doc,p_path);
  IF v IS NULL OR JSON_TYPE(v) IN ('NULL','OBJECT','ARRAY') THEN RETURN NULL; END IF;
  SET s=TRIM(JSON_UNQUOTE(v));
  RETURN NULLIF(NULLIF(s,''),'null');
END$$

DROP FUNCTION IF EXISTS fn_kg27_or_first$$
CREATE FUNCTION fn_kg27_or_first(p_doc LONGTEXT,p_fields TEXT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN
  DECLARE v_fields TEXT;
  DECLARE v_key VARCHAR(128);
  DECLARE v_value LONGTEXT;
  SET v_fields=p_fields;
  WHILE COALESCE(v_fields,'')<>'' DO
    SET v_key=SUBSTRING_INDEX(v_fields,',',1);
    SET v_value=fn_kg27_or_text(p_doc,CONCAT('$.',JSON_QUOTE(v_key)));
    IF v_value IS NOT NULL THEN RETURN v_value; END IF;
    IF LOCATE(',',v_fields)=0 THEN SET v_fields='';
    ELSE SET v_fields=SUBSTRING(v_fields,LOCATE(',',v_fields)+1); END IF;
  END WHILE;
  RETURN NULL;
END$$

DROP FUNCTION IF EXISTS fn_kg27_or_short$$
CREATE FUNCTION fn_kg27_or_short(p_value LONGTEXT,p_limit INT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN
  IF p_value IS NULL THEN RETURN NULL; END IF;
  IF CHAR_LENGTH(p_value)<=p_limit THEN RETURN p_value; END IF;
  RETURN CONCAT('sha256:',SHA2(p_value,256));
END$$

DROP FUNCTION IF EXISTS fn_kg27_or_num$$
CREATE FUNCTION fn_kg27_or_num(p_value LONGTEXT)
RETURNS DOUBLE DETERMINISTIC NO SQL
BEGIN
  DECLARE s LONGTEXT;
  DECLARE v_exp INT DEFAULT 0;
  IF p_value IS NULL THEN RETURN NULL; END IF;
  SET s=TRIM(p_value);
  -- Preserve the source's numeric scale: a terminal percent sign is removed but
  -- never divided by 100. Currency/Chinese units are not silently discarded.
  IF RIGHT(s,1)='%' THEN SET s=TRIM(LEFT(s,CHAR_LENGTH(s)-1)); END IF;
  IF LOCATE(',',s)>0 THEN
    IF NOT REGEXP_LIKE(s,'^[+-]?[0-9]{1,3}(,[0-9]{3})+([.][0-9]+)?([eE][+-]?[0-9]+)?$') THEN RETURN NULL; END IF;
    SET s=REPLACE(s,',','');
  END IF;
  IF CHAR_LENGTH(s)>64 OR NOT REGEXP_LIKE(s,'^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$') THEN
    RETURN NULL;
  END IF;
  IF REGEXP_LIKE(s,'[eE]') THEN
    IF CHAR_LENGTH(SUBSTRING_INDEX(LOWER(s),'e',-1))>4 THEN RETURN NULL; END IF;
    SET v_exp=CAST(SUBSTRING_INDEX(LOWER(s),'e',-1) AS SIGNED);
    IF ABS(v_exp)>200 THEN RETURN NULL; END IF;
  END IF;
  RETURN CAST(s AS DOUBLE);
END$$

DROP FUNCTION IF EXISTS fn_kg27_or_stable_values$$
CREATE FUNCTION fn_kg27_or_stable_values(p_table VARCHAR(128),p_doc LONGTEXT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN
  DECLARE field_list TEXT;
  DECLARE field_name VARCHAR(128);
  DECLARE v LONGTEXT;
  DECLARE result_json JSON;
  SET field_list=CASE p_table
    WHEN 'dwd_org_annual_financial_info' THEN 'org_id,year'
    WHEN 'dwd_org_stock_finance_info' THEN 'org_id,occur_period'
    WHEN 'dwd_forg_stock_fin_info' THEN 'org_id,occur_period'
    WHEN 'dwd_org_changerecord_info' THEN 'org_id,update_date,update_content'
    WHEN 'dwd_org_financing_info' THEN 'org_id,completion_date,funding_round'
    WHEN 'dwd_org_recruit_info' THEN 'org_id,release_date,job_title'
    WHEN 'dwd_org_company_abnormal' THEN 'abnormal_id'
    WHEN 'dwd_org_company_punish' THEN 'penalty_id'
    WHEN 'dwd_org_company_illegal' THEN 'sv_id'
    WHEN 'dwd_org_risk_tax_punish' THEN 'tax_vio_id'
    WHEN 'dwd_org_opt_judicial_case' THEN 'case_id'
    WHEN 'dwd_org_risk_shixin' THEN 'dishonest_id'
    WHEN 'dwd_org_risk_zhixing' THEN 'exec_person_id'
    WHEN 'dwd_org_bankruptcy_public_cases' THEN 'case_no'
    WHEN 'dwd_bid_base_out' THEN 'u_id'
    ELSE NULL END;
  IF field_list IS NULL THEN RETURN NULL; END IF;
  SET result_json=JSON_ARRAY();
  WHILE field_list<>'' DO
    SET field_name=SUBSTRING_INDEX(field_list,',',1);
    SET v=fn_kg27_or_text(p_doc,CONCAT('$.',JSON_QUOTE(field_name)));
    IF v IS NULL THEN RETURN NULL; END IF;
    SET result_json=JSON_ARRAY_APPEND(result_json,'$',v);
    IF LOCATE(',',field_list)=0 THEN SET field_list='';
    ELSE SET field_list=SUBSTRING(field_list,LOCATE(',',field_list)+1); END IF;
  END WHILE;
  RETURN CAST(result_json AS CHAR CHARACTER SET utf8mb4);
END$$

DROP FUNCTION IF EXISTS fn_kg27_or_legacy_key$$
CREATE FUNCTION fn_kg27_or_legacy_key(p_values LONGTEXT)
RETURNS LONGTEXT CHARACTER SET utf8mb4 COLLATE utf8mb4_bin DETERMINISTIC NO SQL
BEGIN
  DECLARE i INT DEFAULT 0;
  DECLARE s LONGTEXT DEFAULT '';
  IF p_values IS NULL OR JSON_VALID(p_values)=0 THEN RETURN NULL; END IF;
  WHILE i<JSON_LENGTH(p_values) DO
    IF i>0 THEN SET s=CONCAT(s,'|'); END IF;
    SET s=CONCAT(s,JSON_UNQUOTE(JSON_EXTRACT(p_values,CONCAT('$[',i,']'))));
    SET i=i+1;
  END WHILE;
  RETURN NULLIF(s,'');
END$$
DELIMITER ;

-- These calls are idempotent; a missing DWD table is logged by the shared stager.
CALL sp_kg27_stage_source('dwd_org_annual_financial_info');
CALL sp_kg27_stage_source('dwd_org_stock_finance_info');
CALL sp_kg27_stage_source('dwd_forg_stock_fin_info');
CALL sp_kg27_stage_source('dwd_org_changerecord_info');
CALL sp_kg27_stage_source('dwd_org_financing_info');
CALL sp_kg27_stage_source('dwd_org_recruit_info');
CALL sp_kg27_stage_source('dwd_org_company_abnormal');
CALL sp_kg27_stage_source('dwd_org_company_punish');
CALL sp_kg27_stage_source('dwd_org_company_illegal');
CALL sp_kg27_stage_source('dwd_org_risk_tax_punish');
CALL sp_kg27_stage_source('dwd_org_opt_judicial_case');
CALL sp_kg27_stage_source('dwd_org_risk_shixin');
CALL sp_kg27_stage_source('dwd_org_risk_zhixing');
CALL sp_kg27_stage_source('dwd_org_bankruptcy_public_cases');
CALL sp_kg27_stage_source('dwd_bid_base_out');

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_specs;
CREATE TEMPORARY TABLE tmp_kg27_or_event_specs (
  source_table VARCHAR(128) COLLATE utf8mb4_bin PRIMARY KEY,
  event_type VARCHAR(64) COLLATE utf8mb4_bin NOT NULL
) ENGINE=InnoDB;
INSERT INTO tmp_kg27_or_event_specs VALUES
 ('dwd_org_annual_financial_info','annual_finance'),
 ('dwd_org_stock_finance_info','stock_finance'),
 ('dwd_forg_stock_fin_info','stock_finance'),
 ('dwd_org_changerecord_info','change_record'),
 ('dwd_org_financing_info','financing'),
 ('dwd_org_recruit_info','recruit'),
 ('dwd_org_company_abnormal','abnormal'),
 ('dwd_org_company_punish','punish'),
 ('dwd_org_company_illegal','illegal'),
 ('dwd_org_risk_tax_punish','tax_punish'),
 ('dwd_org_opt_judicial_case','judicial_case'),
 ('dwd_org_risk_shixin','shixin'),
 ('dwd_org_risk_zhixing','zhixing'),
 ('dwd_org_bankruptcy_public_cases','bankruptcy'),
 ('dwd_bid_base_out','bid');

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_source_counts;
CREATE TEMPORARY TABLE tmp_kg27_or_source_counts AS
SELECT source_table,source_key,COUNT(*) AS source_count
FROM tmp_kg27_source_rows
WHERE source_table IN (
 'dwd_bid_base_out',
 'dwd_forg_stock_fin_info',
 'dwd_org_annual_financial_info',
 'dwd_org_bankruptcy_public_cases',
 'dwd_org_changerecord_info',
 'dwd_org_company_abnormal',
 'dwd_org_company_illegal',
 'dwd_org_company_punish',
 'dwd_org_financing_info',
 'dwd_org_opt_judicial_case',
 'dwd_org_recruit_info',
 'dwd_org_risk_shixin',
 'dwd_org_risk_tax_punish',
 'dwd_org_risk_zhixing',
 'dwd_org_stock_finance_info')
GROUP BY source_table,source_key;
INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',source_table,fn_kg27_or_short(source_key,512),'CONFLICTING_SOURCE_RECORD',
 JSON_OBJECT('source_key',source_key,'distinct_snapshots',source_count,
 'action','Skip conflicting source key; do not choose a snapshot arbitrarily.')
FROM tmp_kg27_or_source_counts WHERE source_count>1;

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_sources;
CREATE TEMPORARY TABLE tmp_kg27_or_sources (
 source_table VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 source_key VARCHAR(512) COLLATE utf8mb4_bin NOT NULL,
 row_hash CHAR(64) COLLATE utf8mb4_bin NOT NULL,
 doc JSON NOT NULL,
 PRIMARY KEY(source_table,row_hash)
) ENGINE=InnoDB;
INSERT INTO tmp_kg27_or_sources
SELECT s.source_table,s.source_key,s.row_hash,s.doc
FROM tmp_kg27_source_rows s JOIN tmp_kg27_or_source_counts c
 ON BINARY c.source_table=BINARY s.source_table AND BINARY c.source_key=BINARY s.source_key
WHERE c.source_count=1 AND fn_kg27_is_real_json(s.doc)=1;

-- Rebuild exact aliases whenever event completion has added real source-backed rows.
DELIMITER $$
DROP PROCEDURE IF EXISTS sp_kg27_or_event_aliases$$
CREATE PROCEDURE sp_kg27_or_event_aliases()
BEGIN
 DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_events;
 CREATE TEMPORARY TABLE tmp_kg27_or_events (
  event_id VARCHAR(255) COLLATE utf8mb4_bin PRIMARY KEY,
  source_table VARCHAR(128) COLLATE utf8mb4_bin,
  raw_id LONGTEXT COLLATE utf8mb4_bin,
  source_record_id LONGTEXT COLLATE utf8mb4_bin,
  organization_id LONGTEXT COLLATE utf8mb4_bin,
  case_no LONGTEXT COLLATE utf8mb4_bin,
  u_id LONGTEXT COLLATE utf8mb4_bin,
  case_role LONGTEXT COLLATE utf8mb4_bin,
  exec_person_type LONGTEXT COLLATE utf8mb4_bin,
  doc JSON NOT NULL
 ) ENGINE=InnoDB;
 INSERT INTO tmp_kg27_or_events
 SELECT e.event_id,e.source_table,e.raw_id,e.source_record_id,e.organization_id,e.case_no,e.u_id,
  e.case_role,e.exec_person_type,
  CAST(IF(JSON_VALID(e.extra_json),e.extra_json,'{}') AS JSON)
 FROM kg_event e JOIN tmp_kg27_entity_allow a
  ON a.entity_type='Event' AND BINARY a.entity_id=BINARY e.event_id;

 DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_docs;
 CREATE TEMPORARY TABLE tmp_kg27_or_event_docs (
  event_id VARCHAR(255) COLLATE utf8mb4_bin,
  source_table VARCHAR(128) COLLATE utf8mb4_bin,
  doc JSON NOT NULL
 ) ENGINE=InnoDB;
 INSERT INTO tmp_kg27_or_event_docs SELECT event_id,source_table,doc FROM tmp_kg27_or_events;
 INSERT INTO tmp_kg27_or_event_docs
 SELECT event_id,source_table,JSON_EXTRACT(doc,'$.existing_payload')
 FROM tmp_kg27_or_events WHERE JSON_TYPE(JSON_EXTRACT(doc,'$.existing_payload'))='OBJECT';
 INSERT INTO tmp_kg27_or_event_docs
 SELECT e.event_id,e.source_table,JSON_EXTRACT(e.doc,CONCAT('$.source_records.',JSON_QUOTE(j.record_key)))
 FROM tmp_kg27_or_events e
 JOIN JSON_TABLE(COALESCE(JSON_KEYS(JSON_EXTRACT(e.doc,'$.source_records')),JSON_ARRAY()),
 '$[*]' COLUMNS(record_key TEXT PATH '$')) j ON TRUE
 WHERE BINARY SUBSTRING_INDEX(j.record_key,':',1)=BINARY e.source_table
 AND JSON_TYPE(JSON_EXTRACT(e.doc,CONCAT('$.source_records.',JSON_QUOTE(j.record_key))))='OBJECT';

 DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_aliases;
 CREATE TEMPORARY TABLE tmp_kg27_or_event_aliases (
  source_table VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
  key_kind VARCHAR(32) COLLATE utf8mb4_bin NOT NULL,
  key_hash CHAR(64) COLLATE utf8mb4_bin NOT NULL,
  key_value LONGTEXT COLLATE utf8mb4_bin NOT NULL,
  event_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
  PRIMARY KEY(source_table,key_kind,key_hash,event_id)
 ) ENGINE=InnoDB;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'record',SHA2(TRIM(raw_id),256),TRIM(raw_id),event_id
 FROM tmp_kg27_or_events WHERE NULLIF(TRIM(raw_id),'') IS NOT NULL AND source_table IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'record',SHA2(TRIM(source_record_id),256),TRIM(source_record_id),event_id
 FROM tmp_kg27_or_events WHERE NULLIF(TRIM(source_record_id),'') IS NOT NULL AND source_table IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'record',SHA2(fn_kg27_or_first(doc,'id,source_row_id,dwd_id'),256),
  fn_kg27_or_first(doc,'id,source_row_id,dwd_id'),event_id
 FROM tmp_kg27_or_event_docs
 WHERE source_table IS NOT NULL AND fn_kg27_or_first(doc,'id,source_row_id,dwd_id') IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'stable',SHA2(fn_kg27_or_stable_values(source_table,doc),256),
  fn_kg27_or_stable_values(source_table,doc),event_id
 FROM tmp_kg27_or_event_docs
 WHERE source_table IS NOT NULL AND fn_kg27_or_stable_values(source_table,doc) IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'case_no',SHA2(TRIM(case_no),256),TRIM(case_no),event_id
 FROM tmp_kg27_or_events WHERE source_table='dwd_org_bankruptcy_public_cases' AND NULLIF(TRIM(case_no),'') IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'case_no',SHA2(fn_kg27_or_text(doc,'$.case_no'),256),fn_kg27_or_text(doc,'$.case_no'),event_id
 FROM tmp_kg27_or_event_docs WHERE source_table='dwd_org_bankruptcy_public_cases' AND fn_kg27_or_text(doc,'$.case_no') IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'u_id',SHA2(TRIM(u_id),256),TRIM(u_id),event_id
 FROM tmp_kg27_or_events WHERE source_table='dwd_bid_base_out' AND NULLIF(TRIM(u_id),'') IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,'u_id',SHA2(fn_kg27_or_text(doc,'$.u_id'),256),fn_kg27_or_text(doc,'$.u_id'),event_id
 FROM tmp_kg27_or_event_docs WHERE source_table='dwd_bid_base_out' AND fn_kg27_or_text(doc,'$.u_id') IS NOT NULL;
 -- A raw/source record key is an accepted alias only for that source's known business key.
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,IF(source_table='dwd_bid_base_out','u_id','case_no'),SHA2(TRIM(raw_id),256),TRIM(raw_id),event_id
 FROM tmp_kg27_or_events WHERE source_table IN ('dwd_bid_base_out','dwd_org_bankruptcy_public_cases') AND NULLIF(TRIM(raw_id),'') IS NOT NULL;
 INSERT IGNORE INTO tmp_kg27_or_event_aliases
 SELECT source_table,IF(source_table='dwd_bid_base_out','u_id','case_no'),SHA2(TRIM(source_record_id),256),TRIM(source_record_id),event_id
 FROM tmp_kg27_or_events WHERE source_table IN ('dwd_bid_base_out','dwd_org_bankruptcy_public_cases') AND NULLIF(TRIM(source_record_id),'') IS NOT NULL;
END$$
DELIMITER ;
CALL sp_kg27_or_event_aliases();

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_input;
CREATE TEMPORARY TABLE tmp_kg27_or_event_input (
 source_table VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 source_key VARCHAR(512) COLLATE utf8mb4_bin NOT NULL,
 row_hash CHAR(64) COLLATE utf8mb4_bin NOT NULL,
 event_type VARCHAR(64) COLLATE utf8mb4_bin NOT NULL,
 doc JSON NOT NULL,
 business_json LONGTEXT COLLATE utf8mb4_bin,
 business_hash CHAR(64) COLLATE utf8mb4_bin,
 legacy_key LONGTEXT COLLATE utf8mb4_bin,
 raw_source_id LONGTEXT COLLATE utf8mb4_bin,
 PRIMARY KEY(source_table,row_hash)
) ENGINE=InnoDB;
INSERT INTO tmp_kg27_or_event_input
SELECT s.source_table,s.source_key,s.row_hash,c.event_type,s.doc,
 fn_kg27_or_stable_values(s.source_table,s.doc),SHA2(fn_kg27_or_stable_values(s.source_table,s.doc),256),
 fn_kg27_or_legacy_key(fn_kg27_or_stable_values(s.source_table,s.doc)),fn_kg27_or_first(s.doc,'id,source_row_id,dwd_id')
FROM tmp_kg27_or_sources s JOIN tmp_kg27_or_event_specs c ON BINARY c.source_table=BINARY s.source_table;

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_input_counts;
CREATE TEMPORARY TABLE tmp_kg27_or_event_input_counts AS
SELECT source_table,business_hash,COUNT(*) AS n
FROM tmp_kg27_or_event_input WHERE business_hash IS NOT NULL GROUP BY source_table,business_hash;
INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',s.source_table,s.source_key,'CONFLICTING_EVENT_BUSINESS_KEY',
 JSON_OBJECT('business_key',CAST(s.business_json AS JSON),'source_snapshots',c.n,
 'action','Skip source versions sharing a business key; resolve source/court/organization ambiguity first.')
FROM tmp_kg27_or_event_input s JOIN tmp_kg27_or_event_input_counts c
 ON BINARY c.source_table=BINARY s.source_table AND c.business_hash=s.business_hash WHERE c.n>1;

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_matches;
CREATE TEMPORARY TABLE tmp_kg27_or_event_matches (
 source_table VARCHAR(128) COLLATE utf8mb4_bin NOT NULL,
 row_hash CHAR(64) COLLATE utf8mb4_bin NOT NULL,
 event_id VARCHAR(255) COLLATE utf8mb4_bin NOT NULL,
 PRIMARY KEY(source_table,row_hash,event_id)
) ENGINE=InnoDB;
INSERT IGNORE INTO tmp_kg27_or_event_matches
SELECT s.source_table,s.row_hash,a.event_id FROM tmp_kg27_or_event_input s JOIN tmp_kg27_or_event_aliases a
 ON BINARY a.source_table=BINARY s.source_table AND a.key_kind='stable'
 AND a.key_hash=s.business_hash AND BINARY a.key_value=BINARY s.business_json;
INSERT IGNORE INTO tmp_kg27_or_event_matches
SELECT s.source_table,s.row_hash,a.event_id FROM tmp_kg27_or_event_input s JOIN tmp_kg27_or_event_aliases a
 ON BINARY a.source_table=BINARY s.source_table AND a.key_kind='record'
 AND a.key_hash=SHA2(s.legacy_key,256) AND BINARY a.key_value=BINARY s.legacy_key;
INSERT IGNORE INTO tmp_kg27_or_event_matches
SELECT s.source_table,s.row_hash,a.event_id FROM tmp_kg27_or_event_input s JOIN tmp_kg27_or_event_aliases a
 ON BINARY a.source_table=BINARY s.source_table AND a.key_kind='record'
 AND a.key_hash=SHA2(s.raw_source_id,256) AND BINARY a.key_value=BINARY s.raw_source_id;
INSERT IGNORE INTO tmp_kg27_or_event_matches
SELECT s.source_table,s.row_hash,a.event_id FROM tmp_kg27_or_event_input s JOIN tmp_kg27_or_event_aliases a
 ON BINARY a.source_table=BINARY s.source_table
 AND a.key_kind=IF(s.source_table='dwd_bid_base_out','u_id','case_no')
 AND a.key_hash=SHA2(fn_kg27_or_first(s.doc,IF(s.source_table='dwd_bid_base_out','u_id','case_no')),256)
 AND BINARY a.key_value=BINARY fn_kg27_or_first(s.doc,IF(s.source_table='dwd_bid_base_out','u_id','case_no'))
WHERE s.source_table IN ('dwd_bid_base_out','dwd_org_bankruptcy_public_cases');

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_match_counts;
CREATE TEMPORARY TABLE tmp_kg27_or_event_match_counts AS
SELECT source_table,row_hash,COUNT(*) AS n,MIN(event_id) AS event_id
FROM tmp_kg27_or_event_matches GROUP BY source_table,row_hash;
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_target_counts;
CREATE TEMPORARY TABLE tmp_kg27_or_event_target_counts AS
SELECT event_id,COUNT(*) AS n FROM tmp_kg27_or_event_matches GROUP BY event_id;

INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',s.source_table,s.source_key,'AMBIGUOUS_EXISTING_EVENT',
 JSON_OBJECT('candidate_events',m.n,'business_key',CAST(s.business_json AS JSON))
FROM tmp_kg27_or_event_input s JOIN tmp_kg27_or_event_match_counts m
 ON BINARY m.source_table=BINARY s.source_table AND m.row_hash=s.row_hash WHERE m.n>1;
INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',s.source_table,s.source_key,'MULTIPLE_SOURCE_RECORDS_FOR_EVENT',
 JSON_OBJECT('event_id',m.event_id,'source_records',t.n,'action','Do not select an update record arbitrarily.')
FROM tmp_kg27_or_event_input s JOIN tmp_kg27_or_event_match_counts m
 ON BINARY m.source_table=BINARY s.source_table AND m.row_hash=s.row_hash
JOIN tmp_kg27_or_event_target_counts t ON BINARY t.event_id=BINARY m.event_id
WHERE m.n=1 AND t.n>1;
INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',s.source_table,s.source_key,'MISSING_EVENT_BUSINESS_KEY',
 JSON_OBJECT('action','No exact existing event and incomplete stable business key; do not invent a row-hash event.')
FROM tmp_kg27_or_event_input s LEFT JOIN tmp_kg27_or_event_match_counts m
 ON BINARY m.source_table=BINARY s.source_table AND m.row_hash=s.row_hash
WHERE s.business_json IS NULL AND COALESCE(m.n,0)=0;

DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_ready;
CREATE TEMPORARY TABLE tmp_kg27_or_event_ready AS
SELECT s.*,m.event_id AS existing_event_id,
 CASE WHEN m.event_id IS NOT NULL THEN m.event_id
 ELSE CONCAT('src:',s.source_table,':',s.business_hash) END AS target_event_id
FROM tmp_kg27_or_event_input s
LEFT JOIN tmp_kg27_or_event_match_counts m ON BINARY m.source_table=BINARY s.source_table AND m.row_hash=s.row_hash
LEFT JOIN tmp_kg27_or_event_input_counts b ON BINARY b.source_table=BINARY s.source_table AND b.business_hash=s.business_hash
LEFT JOIN tmp_kg27_or_event_target_counts t ON BINARY t.event_id=BINARY m.event_id
WHERE (m.n=1 AND t.n=1 AND COALESCE(b.n,1)=1)
 OR (COALESCE(m.n,0)=0 AND s.business_json IS NOT NULL AND b.n=1);

-- Snapshot is retained verbatim. Oversized optional scalar fields remain NULL rather
-- than being silently truncated; the original value remains available in extra_json.
DROP TEMPORARY TABLE IF EXISTS tmp_kg27_or_event_values;
CREATE TEMPORARY TABLE tmp_kg27_or_event_values AS
SELECT s.*,
 fn_kg27_or_first(doc,'title,project_name,case_title,job_title,funding_round,update_name,abn_reason,violation_type,category,case_type,target_item_name,bid_item_name') AS new_title,
 COALESCE(fn_kg27_or_first(doc,'content,project_content,service_content,job_description,penalty_content,violation_fact,illegal_fact,legal_obligation,update_content,dishonest_behavior,exec_target'),CAST(doc AS CHAR CHARACTER SET utf8mb4)) AS new_content,
 fn_kg27_or_first(doc,'case_no,reg_no,decision_no,project_number') AS new_case_no,
 fn_kg27_or_first(doc,'case_cause,case_type,case_type_tag') AS new_case_cause,
 fn_kg27_or_first(doc,'publish_time,public_date,publish_date,penalty_date,procedure_date,completion_date,release_date,update_date,abn_date,filing_date,occur_period,year') AS new_occur_date,
 fn_kg27_or_num(fn_kg27_or_first(doc,'amount,funding_amount,fine_amount,exec_target,total_amount,project_budget_amount,total_assets,unit_price_amount')) AS new_amount,
 fn_kg27_or_first(doc,'currency,currency_code,funding_currency_code,amount_unit,total_amount_unit,project_budget_amount_unit') AS new_currency,
 fn_kg27_or_first(doc,'organization_id,org_id,company_id') AS new_org_id,
 fn_kg27_or_first(doc,'updated_time,update_time') AS new_source_update_time,
 fn_kg27_or_first(doc,'source_url,url') AS new_source_url,
 fn_kg27_or_text(doc,'$.case_role') AS new_case_role,
 fn_kg27_or_text(doc,'$.exec_person_type') AS new_exec_person_type,
 fn_kg27_or_text(doc,'$.party_role_type') AS new_party_role_type,
 fn_kg27_or_text(doc,'$.u_id') AS new_u_id
FROM tmp_kg27_or_event_ready s;

INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',source_table,source_key,'OVERSIZED_EVENT_FIELD',
 JSON_OBJECT('title_chars',CHAR_LENGTH(new_title),'case_no_chars',CHAR_LENGTH(new_case_no),
 'case_cause_chars',CHAR_LENGTH(new_case_cause),'occur_date_chars',CHAR_LENGTH(new_occur_date),
 'currency_chars',CHAR_LENGTH(new_currency),'snapshot_bytes',OCTET_LENGTH(CAST(doc AS CHAR CHARACTER SET utf8mb4)),
 'action','Keep the full source snapshot; do not truncate scalar business values.')
FROM tmp_kg27_or_event_values
WHERE CHAR_LENGTH(new_title)>1024 OR CHAR_LENGTH(new_case_no)>1024 OR CHAR_LENGTH(new_case_cause)>512
 OR CHAR_LENGTH(new_occur_date)>64 OR CHAR_LENGTH(new_currency)>64 OR CHAR_LENGTH(new_org_id)>255
 OR CHAR_LENGTH(new_u_id)>255 OR OCTET_LENGTH(new_content)>16777215
 OR OCTET_LENGTH(CAST(doc AS CHAR CHARACTER SET utf8mb4))>16777215;

INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',source_table,source_key,'INVALID_OR_UNIT_BEARING_EVENT_AMOUNT',
 JSON_OBJECT('source_amount',fn_kg27_or_first(doc,'amount,funding_amount,fine_amount,exec_target,total_amount,project_budget_amount,total_assets,unit_price_amount'),
 'action','Keep the amount NULL; do not discard units or infer a conversion. Full source remains in extra_json.')
FROM tmp_kg27_or_event_values
WHERE fn_kg27_or_first(doc,'amount,funding_amount,fine_amount,exec_target,total_amount,project_budget_amount,total_assets,unit_price_amount') IS NOT NULL
 AND new_amount IS NULL;

INSERT INTO tmp_kg27_issues(relation_type,source_table,source_record_id,issue_code,detail)
SELECT 'Event',s.source_table,s.source_key,'EXISTING_EVENT_NONEMPTY_CONFLICT',
 JSON_OBJECT('event_id',e.event_id,'existing_organization_id',e.organization_id,'source_organization_id',s.new_org_id,
 'existing_case_no',e.case_no,'source_case_no',s.new_case_no,'existing_u_id',e.u_id,'source_u_id',s.new_u_id,
 'action','Existing nonempty fields are preserved; review changed endpoint/business evidence.')
FROM tmp_kg27_or_event_values s JOIN kg_event e ON BINARY e.event_id=BINARY s.existing_event_id
WHERE (NULLIF(TRIM(e.organization_id),'') IS NOT NULL AND s.new_org_id IS NOT NULL AND BINARY TRIM(e.organization_id)<>BINARY s.new_org_id)
 OR (NULLIF(TRIM(e.case_no),'') IS NOT NULL AND s.new_case_no IS NOT NULL AND BINARY TRIM(e.case_no)<>BINARY s.new_case_no)
 OR (NULLIF(TRIM(e.u_id),'') IS NOT NULL AND s.new_u_id IS NOT NULL AND BINARY TRIM(e.u_id)<>BINARY s.new_u_id);

UPDATE kg_event e JOIN tmp_kg27_or_event_values s ON BINARY s.existing_event_id=BINARY e.event_id
SET e.event_type=COALESCE(NULLIF(e.event_type,''),s.event_type),
 e.raw_id=COALESCE(NULLIF(e.raw_id,''),fn_kg27_or_short(s.legacy_key,255)),
 e.title=COALESCE(NULLIF(e.title,''),IF(CHAR_LENGTH(s.new_title)<=1024,s.new_title,NULL)),
 e.content=COALESCE(NULLIF(e.content,''),IF(OCTET_LENGTH(s.new_content)<=16777215,s.new_content,NULL)),
 e.case_no=COALESCE(NULLIF(e.case_no,''),IF(CHAR_LENGTH(s.new_case_no)<=1024,s.new_case_no,NULL)),
 e.case_cause=COALESCE(NULLIF(e.case_cause,''),IF(CHAR_LENGTH(s.new_case_cause)<=512,s.new_case_cause,NULL)),
 e.occur_date=COALESCE(NULLIF(e.occur_date,''),IF(CHAR_LENGTH(s.new_occur_date)<=64,s.new_occur_date,NULL)),
 e.amount=COALESCE(e.amount,s.new_amount),
 e.currency=COALESCE(NULLIF(e.currency,''),IF(CHAR_LENGTH(s.new_currency)<=64,s.new_currency,NULL)),
 e.organization_id=COALESCE(NULLIF(e.organization_id,''),IF(CHAR_LENGTH(s.new_org_id)<=255,s.new_org_id,NULL)),
 e.source_table=COALESCE(NULLIF(e.source_table,''),s.source_table),
 e.source_record_id=COALESCE(NULLIF(e.source_record_id,''),fn_kg27_or_short(s.legacy_key,255)),
 e.source_url=COALESCE(NULLIF(e.source_url,''),IF(CHAR_LENGTH(s.new_source_url)<=1024,s.new_source_url,NULL)),
 e.source_update_time=COALESCE(NULLIF(e.source_update_time,''),IF(CHAR_LENGTH(s.new_source_update_time)<=64,s.new_source_update_time,NULL)),
 e.extra_json=COALESCE(NULLIF(e.extra_json,''),IF(OCTET_LENGTH(CAST(s.doc AS CHAR CHARACTER SET utf8mb4))<=16777215,CAST(s.doc AS CHAR CHARACTER SET utf8mb4),NULL)),
 e.case_role=COALESCE(NULLIF(e.case_role,''),s.new_case_role),
 e.exec_person_type=COALESCE(NULLIF(e.exec_person_type,''),s.new_exec_person_type),
 e.party_role_type=COALESCE(NULLIF(e.party_role_type,''),s.new_party_role_type),
 e.u_id=COALESCE(NULLIF(e.u_id,''),IF(CHAR_LENGTH(s.new_u_id)<=255,s.new_u_id,NULL));
INSERT INTO tmp_kg_patch_log VALUES('event:fill_existing','OK',ROW_COUNT(),'Exact source/business aliases only; nonempty fields preserved.');

INSERT INTO kg_event(event_id,event_type,raw_id,title,content,case_no,case_cause,occur_date,amount,currency,
 organization_id,source_system,source_table,source_record_id,source_url,ingest_batch,ingest_time,
 source_update_time,extra_json,case_role,exec_person_type,party_role_type,u_id)
SELECT target_event_id,event_type,fn_kg27_or_short(legacy_key,255),
 IF(CHAR_LENGTH(new_title)<=1024,new_title,NULL),IF(OCTET_LENGTH(new_content)<=16777215,new_content,NULL),
 IF(CHAR_LENGTH(new_case_no)<=1024,new_case_no,NULL),IF(CHAR_LENGTH(new_case_cause)<=512,new_case_cause,NULL),
 IF(CHAR_LENGTH(new_occur_date)<=64,new_occur_date,NULL),new_amount,
 IF(CHAR_LENGTH(new_currency)<=64,new_currency,NULL),IF(CHAR_LENGTH(new_org_id)<=255,new_org_id,NULL),
 @source_db,source_table,fn_kg27_or_short(legacy_key,255),IF(CHAR_LENGTH(new_source_url)<=1024,new_source_url,NULL),
 @kg27_batch,DATE_FORMAT(UTC_TIMESTAMP(6),'%Y-%m-%dT%H:%i:%s.%fZ'),
 IF(CHAR_LENGTH(new_source_update_time)<=64,new_source_update_time,NULL),CAST(doc AS CHAR CHARACTER SET utf8mb4),
 new_case_role,new_exec_person_type,new_party_role_type,IF(CHAR_LENGTH(new_u_id)<=255,new_u_id,NULL)
FROM tmp_kg27_or_event_values
WHERE existing_event_id IS NULL AND OCTET_LENGTH(CAST(doc AS CHAR CHARACTER SET utf8mb4))<=16777215
ON DUPLICATE KEY UPDATE event_id=kg_event.event_id;
INSERT INTO tmp_kg_patch_log VALUES('event:insert_source_backed','OK',ROW_COUNT(),'New src: business IDs require complete unique stable keys; no row-hash fallback.');

-- Only newly source-backed events passing the complete-row filter become allowed.
INSERT IGNORE INTO tmp_kg27_entity_allow(entity_type,entity_id)
SELECT 'Event',e.event_id FROM kg_event e JOIN tmp_kg27_or_event_values s
 ON BINARY s.target_event_id=BINARY e.event_id
WHERE s.existing_event_id IS NULL AND fn_kg27_is_real_json(JSON_OBJECT(
 'event_id',e.event_id,'raw_id',e.raw_id,'organization_id',e.organization_id,
 'source_system',e.source_system,'source_record_id',e.source_record_id,
 'extra_json',CAST(IF(JSON_VALID(e.extra_json),e.extra_json,'null') AS JSON)))=1;



-- All changes above target kg_event or temporary audit/staging objects only.
-- Provenance correction: dwd_forg_stock_fin_info was staged from gkx_element (absent in gkx_dwd_local),
-- but the event INSERT stamps source_system=@source_db uniformly.
UPDATE kg_event SET source_system='gkx_element'
WHERE source_table='dwd_forg_stock_fin_info' AND BINARY source_system=BINARY 'gkx_dwd_local'
  AND BINARY ingest_batch=BINARY @kg27_batch;
INSERT INTO tmp_kg_patch_log VALUES('event:forg_stock_fin_provenance','UPDATED',ROW_COUNT(),'Rows staged from gkx_element; source_system corrected from the uniform @source_db stamp.');

DROP PROCEDURE IF EXISTS sp_kg27_or_event_aliases;
DROP FUNCTION IF EXISTS fn_kg27_or_legacy_key;
DROP FUNCTION IF EXISTS fn_kg27_or_stable_values;
DROP FUNCTION IF EXISTS fn_kg27_or_num;
DROP FUNCTION IF EXISTS fn_kg27_or_short;
DROP FUNCTION IF EXISTS fn_kg27_or_first;
DROP FUNCTION IF EXISTS fn_kg27_or_text;


SELECT relation_type,source_table,source_record_id,issue_code,detail FROM tmp_kg27_issues ORDER BY relation_type,issue_code,source_table;

-- Completion log counts changed rows, not confirmed graph relationships.
SELECT step,status,affected_rows,detail FROM tmp_kg_patch_log ORDER BY step,status;
SELECT entity_type,table_name,primary_key_column FROM (
  SELECT 'Person' entity_type,'kg_person' table_name,'person_id' primary_key_column UNION ALL
  SELECT 'Organization','kg_organization','org_id' UNION ALL SELECT 'Paper','kg_paper','id' UNION ALL
  SELECT 'Patent','kg_patent','patent_id' UNION ALL SELECT 'Project','kg_project','id' UNION ALL
  SELECT 'Journal','kg_journal','publication_id' UNION ALL SELECT 'Keyword','kg_keyword','keyword_id' UNION ALL
  SELECT 'IndustryChain','kg_industry_chain','chain_code' UNION ALL SELECT 'IndustryNode','kg_industry_node','node_id' UNION ALL
  SELECT 'Event','kg_event','event_id' UNION ALL SELECT 'News','kg_news','news_id' UNION ALL
  SELECT 'Product','kg_product','product_id' UNION ALL SELECT 'PatentFamily','kg_patent_family','family_number' UNION ALL
  SELECT 'Report','kg_report','report_id' UNION ALL SELECT 'DataSource','kg_data_source','source_table'
) entity_map ORDER BY entity_type;
DROP PROCEDURE IF EXISTS sp_kg27_fill_from_source;
DROP PROCEDURE IF EXISTS sp_kg27_add_column;
DROP PROCEDURE IF EXISTS sp_kg27_assert_base;
DROP FUNCTION IF EXISTS fn_kg27_is_real_json;

DROP PROCEDURE IF EXISTS sp_kg27_import_entity;
DROP PROCEDURE IF EXISTS sp_kg27_stage_source;
DROP FUNCTION IF EXISTS fn_kg27_json_text;
DROP FUNCTION IF EXISTS fn_kg27_norm_text;
DROP FUNCTION IF EXISTS fn_kg27_norm_name;
DROP FUNCTION IF EXISTS fn_kg27_norm_doi;
DROP FUNCTION IF EXISTS fn_kg27_norm_patent;
DROP FUNCTION IF EXISTS fn_kg27_confidence_doc;
