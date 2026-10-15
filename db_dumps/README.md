# 控制面库 techkg_control 数据快照

- 来源:主栈容器 `tech-kg-temporal-mysql`(根 docker-compose),库 `techkg_control`
- 导出时间:2026-10-15,mysqldump `--single-transaction --routines --triggers --databases`
- 内容:14 张表,含 Schema 目录 5 张(`kg_schema_definition` 67 行 / `kg_schema_property` 195 行 / `kg_schema_mapping` 39 行)及 workflow/review 控制面表
- 恢复:`gunzip -c techkg_control_root_20261015.sql.gz | mysql -uroot -p`(含 CREATE DATABASE,会覆盖同名库)
- 注意:dev2 栈(`tech-kg-temporal-mysql-dev2`)同名库另有 1501 个 Schema 定义 + 来源/脚本绑定 + 全流程执行记录(约 155MB),未包含在本快照内
