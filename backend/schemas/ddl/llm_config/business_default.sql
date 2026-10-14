CREATE TABLE IF NOT EXISTS platform_business_llm_default (
    business_id VARCHAR(64) NOT NULL PRIMARY KEY,
    config_id VARCHAR(64) NOT NULL,
    INDEX ix_platform_business_llm_default_config_id (config_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
