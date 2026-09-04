# Schema 存储表结构（实体与关系）

> 导出自 dev2 控制库 `techkg_control`（MySQL），2026-09-03。
> ORM 模型：`backend/db_model/schema_management.py`（`GraphSchemaDefinition` / `GraphSchemaProperty` / `GraphSchemaMapping` / `GraphSchemaScript` / `GraphSchemaSource`）。
> 库定位：控制库（`WORKFLOW_MYSQL_DATABASE`，dev2 为 `techkg_control`）——schema 目录、脚本元数据、来源绑定、水位都在这里。

## 表关系

```
kg_schema_definition（实体/关系定义，1 行 = 1 个 schema）
 ├── kg_schema_property   1:N  属性与约束（硬删除：删行 + 图库 ALTER DROP）
 ├── kg_schema_mapping    1:N  来源对象映射（展示用）
 ├── kg_schema_script     1:1  抽取脚本元数据（脚本本体在 S3/RustFS）
 └── kg_schema_source     1:N  来源表绑定（平台喂数抽取的读取源）
      自引用 source_schema_id / target_schema_id → kg_schema_definition.id（关系的起点/终点实体，RESTRICT）
```

## kg_schema_definition（实体与关系 Schema 定义）

```sql
CREATE TABLE `kg_schema_definition` (
  `id` varchar(36) NOT NULL,
  `schema_key` varchar(64) NOT NULL,
  `kind` varchar(16) NOT NULL COMMENT 'entity/relation',
  `name` varchar(128) NOT NULL,
  `label` varchar(128) NOT NULL,
  `description` text NOT NULL,
  `identity_key` varchar(512) NOT NULL,
  `attribute_identity_key` varchar(512) NOT NULL,
  `attribute_source` varchar(1024) NOT NULL,
  `instance_count` bigint NOT NULL,
  `version` varchar(32) NOT NULL,
  `display_order` int NOT NULL,
  `is_core` tinyint(1) NOT NULL,
  `relation_category` varchar(16) DEFAULT NULL COMMENT 'fact/inferred，仅关系 Schema 使用',
  `is_system` tinyint(1) NOT NULL,
  `created_by` varchar(128) DEFAULT NULL,
  `source_schema_id` varchar(36) DEFAULT NULL,
  `target_schema_id` varchar(36) DEFAULT NULL,
  `source_expression` varchar(512) DEFAULT NULL,
  `target_expression` varchar(512) DEFAULT NULL,
  `llm_config_id` varchar(64) DEFAULT NULL COMMENT '作业默认 LLM 配置 ID（软关联 platform_llm_config.id）',
  `ddl_statement` varchar(2048) DEFAULT NULL,
  `ddl_status` varchar(16) NOT NULL COMMENT 'pending/succeeded/failed/skipped',
  `ddl_error` varchar(1024) DEFAULT NULL,
  `ddl_executed_at` datetime DEFAULT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  `property_revision` int NOT NULL DEFAULT '1',
  `graph_space` varchar(64) NOT NULL DEFAULT 'dev2',
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_definition_key` (`schema_key`,`graph_space`),
  UNIQUE KEY `uk_kg_schema_definition_name` (`name`,`graph_space`),
  KEY `source_schema_id` (`source_schema_id`),
  KEY `target_schema_id` (`target_schema_id`),
  KEY `idx_kg_schema_definition_kind_created` (`kind`,`created_at`),
  KEY `idx_kg_schema_definition_space` (`graph_space`),
  CONSTRAINT `kg_schema_definition_ibfk_1` FOREIGN KEY (`source_schema_id`)
    REFERENCES `kg_schema_definition` (`id`) ON DELETE RESTRICT,
  CONSTRAINT `kg_schema_definition_ibfk_2` FOREIGN KEY (`target_schema_id`)
    REFERENCES `kg_schema_definition` (`id`) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='知识图谱实体与关系 Schema 定义';
```

关键设计：

- **图空间隔离**：唯一键是 `(schema_key, graph_space)` / `(name, graph_space)` 复合——同名 schema 可存在于不同空间；DDL 在 `graph_space` 指定的空间执行。
- **软删（假删）**：`is_deleted` 置标记而非物理删行（读取路径统一过滤）；删除时改写 `schema_key`/`name`（追加 `#del-<时间戳>` 后缀）释放唯一键，允许同名重建。图库 TAG/EDGE **不 DROP**。
- **属性修订号**：`property_revision` 随增/删属性 +1；脚本上传时快照到 `kg_schema_script.captured_revision`，用于「脚本落后于 Schema N 版」角标。
- **关系端点**：`source_schema_id`/`target_schema_id` 自引用（RESTRICT——被关系引用的实体不可物理删除）。

## kg_schema_property（Schema 属性与约束）

```sql
CREATE TABLE `kg_schema_property` (
  `id` varchar(36) NOT NULL,
  `schema_id` varchar(36) NOT NULL,
  `name` varchar(128) NOT NULL,
  `data_type` varchar(128) NOT NULL,
  `required` tinyint(1) NOT NULL,
  `rule` varchar(512) NOT NULL,
  `category` varchar(16) NOT NULL COMMENT 'core=业务属性 / required=公共必选',
  `position` int NOT NULL,
  `is_deleted` tinyint(1) NOT NULL DEFAULT '0',
  `deleted_at` datetime DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_property_name` (`schema_id`,`name`),
  CONSTRAINT `kg_schema_property_ibfk_1` FOREIGN KEY (`schema_id`)
    REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Schema 属性与约束';
```

属性删除是**硬删除**（目录删行 + 图库 `ALTER ... DROP` 物理删列，产品决策 ae31551）；`is_deleted`/`deleted_at` 为历史遗留列，代码不再读写。

## kg_schema_mapping（Schema 来源对象映射）

```sql
CREATE TABLE `kg_schema_mapping` (
  `id` varchar(36) NOT NULL,
  `schema_id` varchar(36) NOT NULL,
  `source_name` varchar(255) NOT NULL,
  `position` int NOT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_mapping_source` (`schema_id`,`source_name`),
  CONSTRAINT `kg_schema_mapping_ibfk_1` FOREIGN KEY (`schema_id`)
    REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Schema 来源对象映射';
```

## kg_schema_script（Schema Python 处理脚本 S3 对象元数据）

```sql
CREATE TABLE `kg_schema_script` (
  `id` varchar(36) NOT NULL,
  `schema_id` varchar(36) NOT NULL,
  `bucket` varchar(128) NOT NULL,
  `object_key` varchar(512) NOT NULL,
  `original_filename` varchar(255) NOT NULL,
  `content_type` varchar(128) NOT NULL,
  `size_bytes` bigint NOT NULL,
  `etag` varchar(128) DEFAULT NULL,
  `sha256` varchar(64) NOT NULL,
  `uploaded_by` varchar(128) NOT NULL,
  `workflow_definition_id` varchar(64) DEFAULT NULL,
  `workflow_function_name` varchar(128) DEFAULT NULL,
  `safety_summary` text NOT NULL,
  `safety_issues` text NOT NULL,
  `uploaded_at` datetime NOT NULL DEFAULT (now()),
  `captured_revision` int NOT NULL DEFAULT '1',
  `last_run_status` varchar(16) NOT NULL DEFAULT 'none',
  `last_run_error` varchar(1024) DEFAULT NULL,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_script_schema` (`schema_id`),
  CONSTRAINT `kg_schema_script_ibfk_1` FOREIGN KEY (`schema_id`)
    REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Schema Python 处理脚本 S3 对象元数据';
```

脚本本体存 S3（`SCHEMA_S3_*`，dev2 走 operator-rustfs）；表里只存对象定位与安全校验结论。每 schema 至多一个脚本（唯一键 `schema_id`），更换脚本覆盖。

## kg_schema_source（Schema 来源表绑定）

```sql
CREATE TABLE `kg_schema_source` (
  `id` varchar(36) NOT NULL,
  `schema_id` varchar(36) NOT NULL,
  `datasource_id` varchar(64) NOT NULL COMMENT '软关联 platform_mysql_datasource.id',
  `database_name` varchar(128) NOT NULL,
  `table_name` varchar(128) NOT NULL,
  `pk_column` varchar(128) NOT NULL,
  `time_column` varchar(128) NOT NULL COMMENT '水位列（时间游标）',
  `position` int NOT NULL,
  `created_at` datetime NOT NULL DEFAULT (now()),
  `updated_at` datetime NOT NULL DEFAULT (now()),
  `query_sql` text COMMENT '复杂 SQL 源（包子查询，须暴露与 time/pk 同名的列）',
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_kg_schema_source_table` (`schema_id`,`datasource_id`,`database_name`,`table_name`),
  KEY `idx_kg_schema_source_schema` (`schema_id`),
  CONSTRAINT `kg_schema_source_ibfk_1` FOREIGN KEY (`schema_id`)
    REFERENCES `kg_schema_definition` (`id`) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
  COMMENT='Schema 来源表绑定';
```

平台喂数抽取（`kg.schema.extract`）按绑定行独立推水位：普通表走时间列水位/pk keyset，复杂 SQL 走 `query_sql` 包子查询。注意**水位与图空间无关**（按 schema+来源绑定共享）——向另一空间抽取同 schema 时，先推水位才有新行可读。

## 关联表（控制库之外）

| 表 | 库 | 用途 |
|---|---|---|
| `kg_script_watermark` | 控制库 | 抽取水位/keyset 游标（按 definitionId+stepId） |
| `kg_entity_search_state` | 控制库 | 实体检索索引的 BM25 词表状态（每图空间一行） |
| `manual_review_case` | 业务库（gkx_element） | 审核队列（T_EXTRACT_FAIL / T_LINK 等 case 落这里，不在控制库） |
