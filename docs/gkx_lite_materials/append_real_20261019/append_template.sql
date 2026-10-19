-- append_template.sql — gkx_lite 真实数据追加模板（零真实字面量版）
--
-- 用途：本文件是公开分支的结构模板，展示追加 SQL 的精确形态（列清单、
-- 幂等防重骨架、批次约定）。真实字面量全量版本 append.sql 仅存服务器侧
-- 受限区（见 README.md），不进入公开仓库。
--
-- 硬性约定（真实版必须逐条满足）：
--   1. 只 INSERT。禁止 UPDATE / DELETE / TRUNCATE / REPLACE / upsert 覆盖。
--   2. 幂等：每行一条 INSERT ... SELECT ... WHERE NOT EXISTS，以业务键判重；
--      重复执行只跳过已导入行，不覆盖任何既有记录。
--   3. 业务键选择（各表无唯一键时按组合条件判重）：
--      dwd_zh_paper.id / dwd_zh_journal.publication_id /
--      dwd_scholar.scholar_id / dwd_zh_author.(paper_id+author_id) /
--      dwd_org_base_info.org_id /
--      dwd_org_industry_chain_dtl.(chain_code+node_id+antitypic)
--   4. 新增业务 ID 规则：R<表代码>_<源主键>
--      （ZP/ZA/ZJ/SCH/ORG = 源表代码；与存量 P2026L*/J0*/A2026L*/O2026L* 零冲突，
--       列宽已核对：最长 R-id 37 字符，全部目标列可容纳）
--   5. 列映射约定：
--      - 物理 AUTO_INCREMENT 主键列（pk_id/dwd_id）不写入，自然续增；
--      - dwd_zh_author.institution ← 源 affiliation（JSON 数组取首个机构字符串）；
--      - dwd_zh_author.email 一律 NULL（敏感列不选用）；
--      - dwd_scholar.avatar 一律 NULL；
--      - data_source 保持源库真实值 'gkx'（批次信息只记 manifest，不写业务列）；
--      - created_time/updated_time = 批次统一时间（真实版为固定时间戳字面量）；
--      - is_deleted = 0。
--   6. 目标库字符集 utf8mb4 / 排序规则 utf8mb4_general_ci；源查询涉及
--      dwd_scholar（utf8mb4_0900_ai_ci）时需显式 COLLATE，INSERT 字面量本身
--      为 utf8mb4，无需转换函数。
--   7. 执行前置：先对 gkx_lite 七表 SELECT COUNT(*) 留快照（rowcounts_before），
--      执行后复核对账；差值必须精确等于本批各表导入行数。
--
-- ============================================================
-- 每表模板形态（真实版按此展开，每行一条语句）：
-- ============================================================

-- dwd_zh_paper（列清单与 gkx_lite 实际结构一致；25 列去掉自增 pk_id）
INSERT INTO gkx_lite.dwd_zh_paper
  (id, doi, en_name, zh_name, publication_id, paper_type, publication_type,
   publication_zh_name, issn, volume, issue, first_page, last_page,
   cover_year_start, cover_date_start, language_classify, abstract_available,
   open_access, paper_url, data_source, download_num,
   created_time, updated_time, is_deleted)
SELECT
  '<RZP_业务id>', '<doi>', '<en_name>', '<zh_name>', '<RZJ_期刊id 或源刊号>',
  '<paper_type>', '<publication_type>', '<publication_zh_name>', '<issn>',
  '<volume>', '<issue>', '<first_page>', '<last_page>',
  '<cover_year_start>', '<cover_date_start>', '<language_classify>',
  '<abstract_available>', '<open_access>', '<paper_url>',
  'gkx', '<download_num>',
  '<批次时间>', '<批次时间>', 0
WHERE NOT EXISTS (
  SELECT 1 FROM gkx_lite.dwd_zh_paper WHERE id = '<RZP_业务id>'
);

-- dwd_zh_journal（26 列去掉自增 pk_id）
INSERT INTO gkx_lite.dwd_zh_journal
  (publication_id, publication_type, country, zh_name, name_abbr, en_name,
   iscn, issn, eissn, founding_time, jn_official, zh_description,
   chief_editor, organizer, publisher_place, cite_nums, annual_publication,
   impact_score, jn_zone, publication_cycle, paper_nums, publisher,
   created_time, updated_time, is_deleted)
SELECT
  '<RZJ_业务id>', '<publication_type>', '<country>', '<zh_name>',
  '<name_abbr>', '<en_name>', '<iscn>', '<issn>', '<eissn>',
  '<founding_time>', '<jn_official>', '<zh_description>', '<chief_editor>',
  '<organizer>', '<publisher_place>', '<cite_nums>', '<annual_publication>',
  '<impact_score>', '<jn_zone>', '<publication_cycle>', '<paper_nums>',
  '<publisher>',
  '<批次时间>', '<批次时间>', 0
WHERE NOT EXISTS (
  SELECT 1 FROM gkx_lite.dwd_zh_journal WHERE publication_id = '<RZJ_业务id>'
);

-- dwd_scholar（17 列去掉自增 dwd_id；avatar 恒 NULL；列清单已经 SHOW COLUMNS 复核）
INSERT INTO gkx_lite.dwd_scholar
  (scholar_id, name_en, name_zh, avatar, scholar_org_name_en,
   scholar_org_name_zh, scholar_org_id, orc_id, bio_zh, paper_nums,
   citation_nums, h_index, status,
   created_time, updated_time, is_deleted)
SELECT
  '<RSCH_业务id>', '<name_en>', '<name_zh>', NULL, '<scholar_org_name_en>',
  '<scholar_org_name_zh>', '<scholar_org_id>', '<orc_id>', '<bio_zh>',
  '<paper_nums>', '<citation_nums>', '<h_index>', '<status>',
  '<批次时间>', '<批次时间>', 0
WHERE NOT EXISTS (
  SELECT 1 FROM gkx_lite.dwd_scholar WHERE scholar_id = '<RSCH_业务id>'
);

-- dwd_zh_author（12 列去掉自增 pk_id；institution←affiliation；email 恒 NULL）
INSERT INTO gkx_lite.dwd_zh_author
  (paper_id, author_sequence, author_id, en_name, zh_name, email,
   correspond, institution,
   created_time, updated_time, is_deleted)
SELECT
  '<RZP_论文id>', '<author_sequence>', '<RZA_作者行id>', '<en_name>',
  '<zh_name>', NULL, '<correspond>', '<institution←源affiliation>',
  '<批次时间>', '<批次时间>', 0
WHERE NOT EXISTS (
  SELECT 1 FROM gkx_lite.dwd_zh_author
  WHERE paper_id = '<RZP_论文id>' AND author_id = '<RZA_作者行id>'
);

-- dwd_org_base_info（21 列去掉自增 dwd_id；email 类敏感列恒 NULL）
INSERT INTO gkx_lite.dwd_org_base_info
  (org_id, name_cn, incorporation_date, lerep, org_type,
   registered_capital_value, address, province, city, external_id, area,
   postal_code, reg_status, incorporation_year, industry, data_source,
   org_size,
   created_time, updated_time, is_deleted)
SELECT
  '<RORG_业务id>', '<name_cn>', '<incorporation_date>', '<lerep>',
  '<org_type>', '<registered_capital_value>', '<address>', '<province>',
  '<city>', '<external_id=统一社会信用代码>', '<area>', '<postal_code>',
  '<reg_status>', '<incorporation_year>', '<industry>', 'gkx', '<org_size>',
  '<批次时间>', '<批次时间>', 0
WHERE NOT EXISTS (
  SELECT 1 FROM gkx_lite.dwd_org_base_info WHERE org_id = '<RORG_业务id>'
);

-- dwd_org_industry_chain_dtl（10 列全业务键；本批为测试性关联，见 MANIFEST 说明）
INSERT INTO gkx_lite.dwd_org_industry_chain_dtl
  (chain_code, chain_name, node_id, node_name, antitypic, credit_code,
   chain_score, data_source,
   created_time, updated_time)
SELECT
  '<chain_code 现有节点>', '<chain_name>', '<node_id 现有节点>',
  '<node_name>', '<RORG_机构id>', '<credit_code>', '<chain_score>', 'gkx',
  '<批次时间>', '<批次时间>'
WHERE NOT EXISTS (
  SELECT 1 FROM gkx_lite.dwd_org_industry_chain_dtl
  WHERE chain_code = '<chain_code>' AND node_id = '<node_id>'
    AND antitypic = '<RORG_机构id>'
);
