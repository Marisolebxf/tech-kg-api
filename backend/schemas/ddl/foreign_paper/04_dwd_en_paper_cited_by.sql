CREATE TABLE `dwd_en_paper_cited_by` (
  `id` bigint NOT NULL AUTO_INCREMENT COMMENT '主键ID',
  `paper_eid` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '被引文献EID（指向dwd_paper_info_qh.eid）',
  `citing_eid` varchar(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_general_ci NOT NULL COMMENT '引用文献EID',
  `citing_year` int DEFAULT NULL COMMENT '引用文献发表年份',
  `create_time` datetime DEFAULT CURRENT_TIMESTAMP COMMENT '记录创建时间',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_citation` (`paper_eid`,`citing_eid`)
) ENGINE=InnoDB AUTO_INCREMENT=228219 DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci COMMENT='爱思唯尔外文论文引用关系表';
