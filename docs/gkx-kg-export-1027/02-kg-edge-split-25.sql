DROP TABLE IF EXISTS `kg_edge_acquires`;
CREATE TABLE `kg_edge_acquires` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_actual_controller_of`;
CREATE TABLE `kg_edge_actual_controller_of` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_affiliated_with`;
CREATE TABLE `kg_edge_affiliated_with` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_applied_by`;
CREATE TABLE `kg_edge_applied_by` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_authored_by`;
CREATE TABLE `kg_edge_authored_by` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_belongs_to_node`;
CREATE TABLE `kg_edge_belongs_to_node` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_beneficial_owner_of`;
CREATE TABLE `kg_edge_beneficial_owner_of` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_cites`;
CREATE TABLE `kg_edge_cites` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_coauthor_with`;
CREATE TABLE `kg_edge_coauthor_with` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_executive_of`;
CREATE TABLE `kg_edge_executive_of` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_funded_by`;
CREATE TABLE `kg_edge_funded_by` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_has_keyword`;
CREATE TABLE `kg_edge_has_keyword` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_has_news`;
CREATE TABLE `kg_edge_has_news` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_has_node`;
CREATE TABLE `kg_edge_has_node` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_has_participant`;
CREATE TABLE `kg_edge_has_participant` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_invented_by`;
CREATE TABLE `kg_edge_invented_by` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_invests_in`;
CREATE TABLE `kg_edge_invests_in` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_involved_in`;
CREATE TABLE `kg_edge_involved_in` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_leads`;
CREATE TABLE `kg_edge_leads` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_legal_rep_of`;
CREATE TABLE `kg_edge_legal_rep_of` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_member_of_family`;
CREATE TABLE `kg_edge_member_of_family` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_produces`;
CREATE TABLE `kg_edge_produces` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_published_in`;
CREATE TABLE `kg_edge_published_in` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_shareholder_of`;
CREATE TABLE `kg_edge_shareholder_of` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
DROP TABLE IF EXISTS `kg_edge_subsidiary_of`;
CREATE TABLE `kg_edge_subsidiary_of` (
  `src_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `dst_id` varchar(256) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL,
  `edge_rank` int NOT NULL DEFAULT '0',
  `props` json DEFAULT NULL,
  PRIMARY KEY (`src_id`,`dst_id`,`edge_rank`),
  KEY `idx_dst` (`dst_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='kg_edge 按型拆分 20261027';
