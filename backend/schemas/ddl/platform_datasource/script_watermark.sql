CREATE TABLE IF NOT EXISTS `kg_script_watermark` (
  `definition_id` VARCHAR(64) NOT NULL,
  `step_id` VARCHAR(64) NOT NULL DEFAULT '_default',
  `watermark` DATETIME NOT NULL,
  `checkpoint` JSON NULL,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`definition_id`, `step_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='脚本增量抽取水位（领域 ETL 游标）'
