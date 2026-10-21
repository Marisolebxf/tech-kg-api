-- gray-gate-v2 第一阶段迁移之一：T_LINK 案来源行账本（docs/人工审核专项方案复核_20261021.md）。
-- 唯一键 (case_id, execution_id, source_record_id)：同执行同源记录重放命中冲突整体回滚不加计；
-- execution_id 仅审计（逻辑 ingress identity 不含它）；evidence 只存字段名+布尔（≤2KB 零业务值）。
-- 索引内联进建表语句（本目录 DDL 按单语句执行）。
-- 注意：本文件随分支提交，实际执行 DDL 属部署审批范围（第一阶段明确不执行）。

CREATE TABLE manual_review_case_source (
	id INTEGER NOT NULL AUTO_INCREMENT,
	case_id VARCHAR(64) NOT NULL,
	execution_id VARCHAR(64) NOT NULL DEFAULT '',
	source_binding_id VARCHAR(64) NOT NULL DEFAULT '',
	source_record_id VARCHAR(128) NOT NULL,
	source_event_version VARCHAR(128) NOT NULL DEFAULT '',
	evidence TEXT NOT NULL,
	reason VARCHAR(256) NOT NULL DEFAULT '',
	created_at DATETIME NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT uk_review_case_source UNIQUE (case_id, execution_id, source_record_id),
	INDEX ix_review_case_source_case (case_id)
);
