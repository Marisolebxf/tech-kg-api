CREATE TABLE IF NOT EXISTS `kg_schema_mapping` (
  `id` VARCHAR(36) NOT NULL,
  `schema_id` VARCHAR(36) NOT NULL,
  `source_name` VARCHAR(255) NOT NULL,
  `position` INT NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_mapping_source` (`schema_id`, `source_name`),
  CONSTRAINT `fk_kg_schema_mapping_schema`
    FOREIGN KEY (`schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Schema 来源对象映射'
