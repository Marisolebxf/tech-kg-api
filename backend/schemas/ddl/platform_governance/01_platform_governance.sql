CREATE TABLE IF NOT EXISTS kg_platform_user (
  user_id VARCHAR(128) PRIMARY KEY,
  username VARCHAR(128) NOT NULL DEFAULT '',
  nickname VARCHAR(128) NOT NULL DEFAULT '',
  email VARCHAR(255) NOT NULL DEFAULT '',
  last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kg_platform_user_role (
  id VARCHAR(36) PRIMARY KEY,
  user_id VARCHAR(128) NOT NULL,
  role_code VARCHAR(32) NOT NULL,
  granted_by VARCHAR(128) NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uk_kg_platform_user_role (user_id, role_code),
  KEY idx_kg_platform_user_role_code (role_code),
  CONSTRAINT fk_kg_platform_user_role_user FOREIGN KEY (user_id)
    REFERENCES kg_platform_user(user_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kg_manual_correction (
  id VARCHAR(36) PRIMARY KEY,
  target_type VARCHAR(32) NOT NULL,
  operation VARCHAR(16) NOT NULL,
  target_id VARCHAR(256) NOT NULL,
  title VARCHAR(255) NOT NULL,
  reason TEXT NOT NULL,
  before_data JSON NOT NULL,
  after_data JSON NOT NULL,
  status VARCHAR(32) NOT NULL,
  submitter_id VARCHAR(128) NOT NULL,
  submitter_name VARCHAR(128) NOT NULL,
  reviewer_id VARCHAR(128) NULL,
  reviewer_name VARCHAR(128) NULL,
  decision_note TEXT NOT NULL,
  version INT NOT NULL DEFAULT 1,
  submitted_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  reviewed_at DATETIME NULL,
  completed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  KEY idx_kg_manual_correction_submitter (submitter_id, created_at),
  KEY idx_kg_manual_correction_status (status, updated_at),
  KEY idx_kg_manual_correction_target (target_type, target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kg_correction_review (
  id VARCHAR(36) PRIMARY KEY,
  correction_id VARCHAR(36) NOT NULL,
  action VARCHAR(32) NOT NULL,
  actor_id VARCHAR(128) NOT NULL,
  actor_name VARCHAR(128) NOT NULL,
  note TEXT NOT NULL,
  snapshot JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_kg_correction_review_correction (correction_id, created_at),
  CONSTRAINT fk_kg_correction_review_correction FOREIGN KEY (correction_id)
    REFERENCES kg_manual_correction(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kg_correction_sync_task (
  id VARCHAR(36) PRIMARY KEY,
  correction_id VARCHAR(36) NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  mysql_status VARCHAR(32) NOT NULL,
  graph_status VARCHAR(32) NOT NULL,
  attempts INT NOT NULL DEFAULT 0,
  max_attempts INT NOT NULL DEFAULT 8,
  next_retry_at DATETIME NULL,
  last_error TEXT NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_kg_correction_sync_correction (correction_id),
  UNIQUE KEY uk_kg_correction_sync_idempotency (idempotency_key),
  KEY idx_kg_correction_sync_due (status, next_retry_at),
  CONSTRAINT fk_kg_correction_sync_correction FOREIGN KEY (correction_id)
    REFERENCES kg_manual_correction(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kg_correction_projection (
  id VARCHAR(36) PRIMARY KEY,
  target_type VARCHAR(32) NOT NULL,
  target_id VARCHAR(256) NOT NULL,
  payload JSON NOT NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  version INT NOT NULL DEFAULT 1,
  last_correction_id VARCHAR(36) NOT NULL,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  UNIQUE KEY uk_kg_correction_projection_target (target_type, target_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

CREATE TABLE IF NOT EXISTS kg_admin_audit_log (
  id VARCHAR(36) PRIMARY KEY,
  actor_id VARCHAR(128) NOT NULL,
  actor_name VARCHAR(128) NOT NULL,
  action VARCHAR(64) NOT NULL,
  resource_type VARCHAR(64) NOT NULL,
  resource_id VARCHAR(256) NOT NULL,
  detail JSON NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  KEY idx_kg_admin_audit_actor (actor_id, created_at),
  KEY idx_kg_admin_audit_resource (resource_type, resource_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
