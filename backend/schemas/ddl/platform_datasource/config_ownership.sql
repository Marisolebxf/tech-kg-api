CREATE TABLE IF NOT EXISTS platform_config_ownership (
    config_kind VARCHAR(16) NOT NULL,
    config_id VARCHAR(64) NOT NULL,
    business_id VARCHAR(64) NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (config_kind, config_id),
    INDEX ix_config_ownership_business (business_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
