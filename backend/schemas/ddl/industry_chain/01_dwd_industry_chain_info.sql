CREATE TABLE IF NOT EXISTS dwd_industry_chain_info (
    `chain_code` VARCHAR(255) NOT NULL COMMENT '产业链唯一id，用于关联其它表。',
    `chain_name` VARCHAR(255) NOT NULL COMMENT '产业链名称',
    `node_id` VARCHAR(255) NOT NULL COMMENT '产业链节点唯一id，用于关联其它表。',
    `node_name` VARCHAR(255) NOT NULL COMMENT '节点名称',
    `node_type` BIGINT NOT NULL COMMENT '1-大类节点：为构建图谱结构设置的虚拟节点，不直接关联企业，可通过其下属业务节点间接关联企业。
2-业务节点：具备实际业务含义的节点，在数据处理环节直接关联企业。
3 展示节点：与产业链相关性极弱，仅做图谱关系展示，不关联企业。',
    `level` BIGINT NOT NULL COMMENT '产业链节点分类层级中，节点所处层级。',
    `node_seq` BIGINT COMMENT '同一父级节点下的子节点排序参考值。',
    `parent_id` VARCHAR(255) COMMENT '产业链节点唯一id，用于关联其它表。',
    `parent_name` TEXT COMMENT '父级节点名称',
    `node_imp_level` BIGINT COMMENT '产业链节点在整个产业链体系中重要性。1为重要性最高，5为重要性最低。仅适用于节点类型为2的业务节点。',
    `downstream_link_code` VARCHAR(255) COMMENT '产业链节点唯一id，用于关联其它表。',
    `node_stage` BIGINT COMMENT '适用于上中下游型产业链，1-上游，2-中游，3-下游。',
    `node_path` TEXT COMMENT '节点路径',
    `data_source` VARCHAR(255) NOT NULL COMMENT '数据来源',
    `created_time` DATETIME NOT NULL COMMENT '创建时间',
    `updated_time` DATETIME NOT NULL COMMENT '更新时间',
    KEY `idx_chain_code` (`chain_code`),
    KEY `idx_node_id` (`node_id`),
    KEY `idx_node_imp_level` (`node_imp_level`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='产业链图谱';
