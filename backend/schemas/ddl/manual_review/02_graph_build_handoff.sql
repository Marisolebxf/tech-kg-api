-- Upgrade an existing manual-review installation for graph-build handoff.
ALTER TABLE manual_review_case
  ADD COLUMN event_id VARCHAR(128) NULL,
  ADD COLUMN pipeline_step_id VARCHAR(32) NOT NULL DEFAULT 'validate',
  ADD COLUMN workflow_type VARCHAR(128) NULL,
  ADD COLUMN workflow_id VARCHAR(256) NULL,
  ADD COLUMN workflow_run_id VARCHAR(256) NULL,
  ADD COLUMN task_queue VARCHAR(128) NULL,
  ADD COLUMN resume_token VARCHAR(1000) NULL,
  ADD COLUMN exception_code VARCHAR(128) NULL,
  ADD COLUMN isolation_scope VARCHAR(16) NOT NULL DEFAULT 'OBJECT',
  ADD COLUMN template_payload_version VARCHAR(32) NOT NULL DEFAULT '1.0',
  ADD UNIQUE KEY uk_manual_review_case_event_id (event_id);

UPDATE manual_review_case SET pipeline_step_id = CASE
  WHEN LOWER(node_id) IN ('source','normalize','schema','extract','align','validate','persist') THEN LOWER(node_id)
  WHEN node_id LIKE '%Schema%' OR node_id LIKE '%映射%' THEN 'schema'
  WHEN node_id LIKE '%抽取%' OR node_id LIKE '%大模型%' THEN 'extract'
  WHEN node_id LIKE '%对齐%' OR node_id LIKE '%消歧%' THEN 'align'
  WHEN node_id LIKE '%入库%' OR node_id LIKE '%写入%' THEN 'persist'
  WHEN node_id LIKE '%标准%' OR node_id LIKE '%清洗%' THEN 'normalize'
  ELSE 'validate' END;
UPDATE manual_review_case SET template_id='T_LINK' WHERE template_id='T_ENTITY';
UPDATE manual_review_case SET template_id='T_EVIDENCE' WHERE template_id='T_RELATION';

ALTER TABLE manual_review_correction
  ADD COLUMN correction_version INT NOT NULL DEFAULT 1,
  ADD COLUMN payload_sha256 VARCHAR(64) NOT NULL DEFAULT '',
  ADD COLUMN rerun_step_id VARCHAR(32) NOT NULL DEFAULT 'validate';
UPDATE manual_review_correction SET payload_sha256=SHA2(payload,256) WHERE payload_sha256='';

CREATE TABLE manual_review_execution_event (
 event_id VARCHAR(128) PRIMARY KEY, case_id VARCHAR(64) NOT NULL, execution_id VARCHAR(128) NOT NULL,
 event_type VARCHAR(64) NOT NULL, stage INT NOT NULL, payload TEXT NOT NULL, occurred_at DATETIME NOT NULL, created_at DATETIME NOT NULL,
 INDEX ix_manual_review_execution_event_case_id(case_id)
);
