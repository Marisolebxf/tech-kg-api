CREATE TABLE IF NOT EXISTS `kg_schema_script` (
  `id` VARCHAR(36) NOT NULL,
  `schema_id` VARCHAR(36) NOT NULL,
  `bucket` VARCHAR(128) NOT NULL,
  `object_key` VARCHAR(512) NOT NULL,
  `original_filename` VARCHAR(255) NOT NULL,
  `content_type` VARCHAR(128) NOT NULL DEFAULT 'text/x-python',
  `size_bytes` BIGINT NOT NULL,
  `etag` VARCHAR(128) NULL,
  `sha256` VARCHAR(64) NOT NULL,
  `uploaded_by` VARCHAR(128) NOT NULL,
  `workflow_definition_id` VARCHAR(64) NULL,
  `workflow_function_name` VARCHAR(128) NULL,
  `uploaded_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_script_schema` (`schema_id`),
  CONSTRAINT `fk_kg_schema_script_schema`
    FOREIGN KEY (`schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Schema Python 处理脚本 S3 对象元数据'
