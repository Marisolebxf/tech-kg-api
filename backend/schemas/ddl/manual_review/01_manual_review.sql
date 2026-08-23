CREATE TABLE manual_review_audit_log (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	case_id VARCHAR(64) NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	actor_id VARCHAR(128) NOT NULL, 
	actor_name VARCHAR(128) NOT NULL, 
	request_id VARCHAR(128) NOT NULL, 
	old_status VARCHAR(32), 
	new_status VARCHAR(32), 
	detail TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_manual_review_audit_log_case_id ON manual_review_audit_log (case_id);

CREATE TABLE manual_review_case (
	id VARCHAR(64) NOT NULL, 
	dedupe_key VARCHAR(64) NOT NULL, 
	event_id VARCHAR(128), 
	source_task_id VARCHAR(128) NOT NULL, 
	batch_id VARCHAR(128), 
	node_id VARCHAR(64) NOT NULL, 
	pipeline_step_id VARCHAR(32) NOT NULL, 
	object_id VARCHAR(256) NOT NULL, 
	object_type VARCHAR(64) NOT NULL, 
	object_name VARCHAR(500) NOT NULL, 
	error_type VARCHAR(128) NOT NULL, 
	error_fingerprint VARCHAR(128) NOT NULL, 
	category VARCHAR(64) NOT NULL, 
	template_id VARCHAR(32) NOT NULL, 
	template_version VARCHAR(32) NOT NULL, 
	domain VARCHAR(64) NOT NULL, 
	phase VARCHAR(32) NOT NULL, 
	risk_level VARCHAR(8) NOT NULL, 
	scope VARCHAR(16) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	assignee_id VARCHAR(128), 
	assignee_name VARCHAR(128), 
	submitted_by VARCHAR(128), 
	version INTEGER NOT NULL, 
	sla_claim_at DATETIME NOT NULL, 
	sla_resolve_at DATETIME NOT NULL, 
	claimed_at DATETIME, 
	heartbeat_at DATETIME, 
	completed_at DATETIME, 
	source_table VARCHAR(256), 
	source_record_id VARCHAR(256), 
	rule_version VARCHAR(128), 
	model_version VARCHAR(128), 
	workflow_type VARCHAR(128), 
	workflow_id VARCHAR(256), 
	workflow_run_id VARCHAR(256), 
	task_queue VARCHAR(128), 
	resume_token VARCHAR(1000), 
	exception_code VARCHAR(128), 
	isolation_scope VARCHAR(16) NOT NULL, 
	template_payload_version VARCHAR(32) NOT NULL, 
	input_snapshot TEXT NOT NULL, 
	candidate_snapshot TEXT NOT NULL, 
	diagnosis TEXT NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uk_manual_review_case_dedupe UNIQUE (dedupe_key), 
	UNIQUE (event_id)
);

CREATE INDEX ix_review_assignee ON manual_review_case (assignee_id, status);

CREATE INDEX ix_review_queue ON manual_review_case (status, risk_level, domain, created_at);

CREATE TABLE manual_review_correction (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	adapter VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	correction_version INTEGER NOT NULL, 
	payload_sha256 VARCHAR(64) NOT NULL, 
	rerun_step_id VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	attempts INTEGER NOT NULL, 
	last_error TEXT, 
	created_at DATETIME NOT NULL, 
	applied_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_manual_review_correction_case_id ON manual_review_correction (case_id);

CREATE TABLE manual_review_decision (
	id INTEGER NOT NULL AUTO_INCREMENT, 
	case_id VARCHAR(64) NOT NULL, 
	action_id VARCHAR(64) NOT NULL, 
	result TEXT NOT NULL, 
	note TEXT NOT NULL, 
	submitted_by VARCHAR(128) NOT NULL, 
	approved_by VARCHAR(128), 
	status VARCHAR(32) NOT NULL, 
	created_at DATETIME NOT NULL, 
	decided_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_manual_review_decision_case_id ON manual_review_decision (case_id);

CREATE TABLE manual_review_draft (
	case_id VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	updated_by VARCHAR(128) NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (case_id)
);

CREATE TABLE manual_review_evidence (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	file_name VARCHAR(500) NOT NULL, 
	content_type VARCHAR(128) NOT NULL, 
	size_bytes BIGINT NOT NULL, 
	sha256 VARCHAR(64) NOT NULL, 
	bucket VARCHAR(128) NOT NULL, 
	object_key VARCHAR(1000) NOT NULL, 
	source VARCHAR(256) NOT NULL, 
	trust_level VARCHAR(32) NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	uploaded_by VARCHAR(128) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_manual_review_evidence_case_id ON manual_review_evidence (case_id);

CREATE TABLE manual_review_execution (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	resume_node VARCHAR(64) NOT NULL, 
	workflow_type VARCHAR(128) NOT NULL, 
	workflow_id VARCHAR(256) NOT NULL, 
	run_id VARCHAR(256), 
	status VARCHAR(32) NOT NULL, 
	error TEXT, 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_manual_review_execution_case_id ON manual_review_execution (case_id);

CREATE TABLE manual_review_execution_event (
	event_id VARCHAR(128) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	execution_id VARCHAR(128) NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	stage INTEGER NOT NULL, 
	payload TEXT NOT NULL, 
	occurred_at DATETIME NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (event_id)
);

CREATE INDEX ix_manual_review_execution_event_case_id ON manual_review_execution_event (case_id);

CREATE TABLE manual_review_outbox (
	id VARCHAR(64) NOT NULL, 
	case_id VARCHAR(64) NOT NULL, 
	event_type VARCHAR(64) NOT NULL, 
	payload TEXT NOT NULL, 
	status VARCHAR(32) NOT NULL, 
	attempts INTEGER NOT NULL, 
	available_at DATETIME NOT NULL, 
	locked_at DATETIME, 
	last_error TEXT, 
	created_at DATETIME NOT NULL, 
	processed_at DATETIME, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_manual_review_outbox_case_id ON manual_review_outbox (case_id);
