CREATE TABLE IF NOT EXISTS `kg_indirect_relation_annotation` (
  `source_vid` VARCHAR(256) NOT NULL,
  `target_vid` VARCHAR(256) NOT NULL,
  `annotation` VARCHAR(64) NOT NULL DEFAULT '',
  `create_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  `update_time` DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (`source_vid`, `target_vid`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='单节点间接关系人工标注（主键为边两端节点 VID，方向归一）'
