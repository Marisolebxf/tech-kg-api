# Script

启动、维护、数据初始化等脚本放在此目录。

## 脚本清单

| 脚本 | 作用 | 说明 |
|---|---|---|
| `init_db.py` | 执行 `schemas/ddl/` 下全部 DDL | 默认连接开发业务库 `127.0.0.1:3306/gkx_element` |
| `sync_schema_from_mysql.py` | 从源 MySQL 同步 DDL、字段规范和 ORM | 优先读取 `SOURCE_MYSQL_*`，只读 `information_schema` 和 `SHOW CREATE TABLE` |
| `paper_journal_relation/` | 论文/期刊实体关系抽取 ETL | 从 `gkx_element` 论文关系表抽取「从论文出发」的有向边（Paper→Paper: RELATED_TO/CITES/CITED_BY；Paper→Keyword: HAS_KEYWORD；Paper→Report: REFERENCED_BY）写入 TRSGraph `dev` 空间，使用 `infra.graph_db.TRSGraphClient`，详见子目录 README |
| `organization_entity_etl.py` | 装载机构领域实体 | 只新增 `Organization`、`DataSource` 顶点；已有 VID 跳过，不覆盖、不写边 |
| `organization_relation_etl.py` | 装载机构领域关系 | 唯一关系写入入口；只连接已有端点，相同类型/端点/rank 的边跳过 |
| `organization_etl_common.py` | 机构 ETL 公共规则 | 统一关系规格、清洗、VID、`source_record_id`、rank、nGQL 与互斥锁 |
| `organization_graph_etl.py` | 旧命令兼容入口 | 已废弃；现在仅转发到 `organization_entity_etl.py`，不会再写关系 |

## 机构 ETL 单一职责

机构实体和关系必须分两阶段运行，不能对同一批数据并行执行。两个入口共用
`/tmp/tech_kg_organization_etl.lock`，交叉运行会直接失败并报告当前占锁批次。
两个入口在写入前还会批量检查图中已有实体或边，已有数据计入 `existing/skipped`
并保持原属性不变。

统一 Schema 位于 `schemas/dev_organization_schema.ngql`。旧的
`dev_organization_graph.ngql` 和 `dev_organization_relations.ngql` 仅保留弃用提示，
不再维护重复定义。

先 dry-run 机构节点：

```bash
uv run python -m script.organization_entity_etl load \
  --table all \
  --full \
  --dry-run
```

确认后写入节点：

```bash
uv run python -m script.organization_entity_etl load \
  --table all \
  --full \
  --write
```

节点准备完成后 dry-run 关系：

```bash
uv run python -m script.organization_relation_etl \
  --relation all \
  --dry-run
```

确认端点缺失统计后写入关系：

```bash
uv run python -m script.organization_relation_etl \
  --relation all \
  --write
```

## 常用命令

初始化已有的科技要素业务库 `gkx_element` 中由本项目维护的表：

目标数据库必须预先存在；脚本只执行 `schemas/ddl/` 下由本项目维护的建表 DDL，不负责创建数据库，也不创建专利厂商源表。

```bash
MYSQL_HOST=127.0.0.1 \
MYSQL_PORT=3306 \
MYSQL_DATABASE=gkx_element \
MYSQL_USERNAME=root \
MYSQL_PASSWORD=123456789 \
uv run python script/init_db.py
```

同步远程 `gkx` schema：

```bash
SOURCE_MYSQL_HOST=183.240.141.251 \
SOURCE_MYSQL_PORT=3318 \
SOURCE_MYSQL_DATABASE=gkx \
SOURCE_MYSQL_USERNAME=gkx_reader_zp \
SOURCE_MYSQL_PASSWORD='***' \
uv run python script/sync_schema_from_mysql.py
```

在其他目标库执行建表：

```bash
MYSQL_HOST=target_host \
MYSQL_PORT=target_port \
MYSQL_DATABASE=target_database \
MYSQL_USERNAME=target_user \
MYSQL_PASSWORD='target_password' \
uv run python script/init_db.py
```
