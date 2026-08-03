CREATE TABLE IF NOT EXISTS `kg_schema_property` (
  `id` VARCHAR(36) NOT NULL,
  `schema_id` VARCHAR(36) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `data_type` VARCHAR(128) NOT NULL,
  `required` TINYINT(1) NOT NULL DEFAULT 0,
  `rule` VARCHAR(512) NOT NULL DEFAULT '',
  `category` VARCHAR(16) NOT NULL DEFAULT 'core',
  `position` INT NOT NULL DEFAULT 0,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_property_name` (`schema_id`, `name`),
  CONSTRAINT `fk_kg_schema_property_schema`
    FOREIGN KEY (`schema_id`) REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Schema 属性与约束'
