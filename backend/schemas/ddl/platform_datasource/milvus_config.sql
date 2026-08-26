CREATE TABLE IF NOT EXISTS `platform_milvus_config` (
  `id` VARCHAR(64) NOT NULL,
  `name` VARCHAR(128) NOT NULL,
  `description` VARCHAR(500) NOT NULL DEFAULT '',
  `uri` VARCHAR(256) NOT NULL DEFAULT '',
  `token` VARCHAR(256) NOT NULL DEFAULT '',
  `default_db` VARCHAR(128) NOT NULL DEFAULT 'default',
  `owner` VARCHAR(128) NOT NULL DEFAULT '',
  `is_default` TINYINT(1) NOT NULL DEFAULT 0,
  `status` VARCHAR(32) NOT NULL DEFAULT '正常',
  `created_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `updated_at` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `ix_milvus_config_default_status` (`is_default`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='平台 Milvus 配置'
