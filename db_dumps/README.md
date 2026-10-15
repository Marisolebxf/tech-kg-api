# 控制面库 techkg_control 数据快照

## kg_schema_definition 全字段注释版(推荐单独导入)

- 文件:`kg_schema_definition_annotated_20261015.sql.gz`(168KB)
- 内容:重写 CREATE TABLE,30 个字段全部补中文 COLUMN COMMENT + 表注释,数据为 dev2 快照全集(1484 行);已在临时库实测导入,Navicat/DataGrip/DBeaver 表设计视图可直接看到字段说明
- 注意:含 `DROP TABLE IF EXISTS`,会覆盖同名表;默认 DEFAULT (now()) 等表达式需 MySQL 8.0.13+
## dev2 栈 Schema 目录(主要快照)

- 文件:`techkg_control_dev2_schema_tables_20261015.sql.gz`(1.4MB)
- 来源:dev2 栈容器 `tech-kg-temporal-mysql-dev2`,库 `techkg_control` 的 5 张 schema 相关表
- 内容:`kg_schema_definition`(1501 行)/`kg_schema_property`(18767 行,含 required/provenance 公共属性行)/`kg_schema_source`(3336 行,来源表绑定+水位)/`kg_schema_script`(1126 行,脚本 S3 元数据)/`kg_schema_mapping`(78 行)
- 恢复:先建库 `CREATE DATABASE techkg_control`,再 `gunzip -c techkg_control_dev2_schema_tables_20261015.sql.gz | mysql -uroot -p techkg_control`(不含 CREATE DATABASE)
- 未包含:该库其余 workflow/review 控制面表(workflow_executions 等,整库约 155MB)

## 主栈全库(参考)

- 文件:`techkg_control_root_20261015.sql.gz`(17KB)
- 来源:主栈容器 `tech-kg-temporal-mysql`,全库 14 张表(含 CREATE DATABASE,会覆盖同名库)
- 注意:主栈 67 个 Schema 为初始化脚本直建,`kg_schema_property` 里没有 required/provenance 公共属性行
