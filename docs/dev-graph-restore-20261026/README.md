# dev 图空间 SQL 数据交接（2026-10-26）

本目录把原 `dev` 图导出结果转换成的 MySQL 数据交给 GLM，供其在**自己正在工作的当前分支**新增恢复脚本，并完成九大业务的数据准备和前端验收。VID 可以变化，实体属性、关系连接和业务可用性需要保留。

本交接分支只提供 SQL、数据结构、来源校验和执行要求。源 SQL 已在本地 MySQL 实际导入并校验；**目标环境的图恢复与九大业务验收仍需 GLM 执行，不能把来源校验当作目标环境已经通过。**

## 文件位置

交接分支：`codex/dev-graph-sql-handoff-20261026`，基于 `origin/kgetl` 的 `7bc8a5f9`。

| 文件 | 用途 |
| --- | --- |
| [data/dev_graph_restore_20261026.sql.gz](data/dev_graph_restore_20261026.sql.gz) | 全量 SQL，81,074,237 字节；解压后 866,312,689 字节 |
| [data/schema.sql](data/schema.sql) | 表、列、外键及输入视图定义，可先阅读而不解压全量数据 |
| [data/manifest.json](data/manifest.json) | 全部实体/关系类型、属性列映射、行数、逐表属性指纹和来源范围 |
| [data/sample_queries.sql](data/sample_queries.sql) | 查看人物、合著边、缺失端点及输入视图的示例 |
| [data/source_validation.json](data/source_validation.json) | 先前 SQL → 本地 MySQL 校验记录，含全部表的行数和属性指纹 |
| [checksums.sha256](checksums.sha256) | 交接文件 SHA-256；数据文件关闭 Git 换行转换，便于跨机器校验 |
| [GLM_TASK.md](GLM_TASK.md) | 可直接交给 GLM 的完整执行提示词 |
| [NINE_BUSINESS_TEST_DATA.md](NINE_BUSINESS_TEST_DATA.md) | 单独的九大业务测试数据登记文档；GLM 应在当前分支补齐真实数据和验证结果 |

只上传压缩 SQL。约 922 MB 的另一份 `mysqldump` 未压缩导出不放入 Git；它与这里使用同一批业务数据，但 SQL 语句组织不同。本目录没有提交本机连接密码、`.env`、私有身份对照或临时数据库文件。

## 在 GLM 当前分支获取材料

如果材料已经在当前分支，直接读取本目录即可。否则先检查同路径的未提交修改并保留，再获取交接目录，保持当前开发分支不变：

```bash
git fetch origin codex/dev-graph-sql-handoff-20261026
git restore --source=origin/codex/dev-graph-sql-handoff-20261026 -- docs/dev-graph-restore-20261026
```

在本目录内校验文件：

```bash
sha256sum -c checksums.sha256
gzip -t data/dev_graph_restore_20261026.sql.gz
```

Windows 可使用 Python 标准库 `hashlib`/`gzip` 做等价校验。读取和解压数据即可，不需要执行任何原始图导出包中的脚本。

## 数据基线与边界

| 项目 | 数量/含义 |
| --- | --- |
| 实际业务实体表 | 15 张，367,011 个有属性的独立节点 |
| 关系表 | 37 张，528,537 条关系 |
| 辅助表 | 2 张；不是额外的业务实体类型 |
| 输入视图 | 15 个 `v_input_*` 视图 |
| 缺少节点属性的独立关系端点 | 127,397 个：推定 Person 126,801 个、Organization 596 个 |
| 全部新节点关联键 | 494,408 个，包含实际节点和缺属性端点 |
| 合著关系 | `kg_edge_coauthor_with` 156,140 条 |
| 共挂基础标签 | `organization_base` 的 240,763 行均与业务实体重复，标签保留在节点索引中 |

包内记录可以完整转换，但不能据此断言原图每条边均被完整导出。`AUTHORED_BY`、`CITES`、`RELATED_TO`、`HAS_KEYWORD`、`INVOLVED_IN`、`REFERENCED_BY` 六类只有按端点折叠的导出文件，原图可能存在未被保留的并行 rank 边。目标是恢复本 SQL 能表达的图，以及与原来大体相似、能支撑业务的效果。

列类型根据实际图属性值推断，不能视作上游 DWD 源库的原始建表结构。没有数据文件或属性定义的空图类型，本 SQL 不包含对应空表。

## 实体表、输入视图与占位节点

| Schema | 实际实体表 | 建议输入视图 | 实际属性节点 | 占位端点 |
| --- | --- | --- | ---: | ---: |
| DataSource | `kg_data_source` | `v_input_data_source` | 39 | 0 |
| Event | `kg_event` | `v_input_event` | 24,669 | 0 |
| IndustryChain | `kg_industry_chain` | `v_input_industry_chain` | 3 | 0 |
| IndustryNode | `kg_industry_node` | `v_input_industry_node` | 180 | 0 |
| Journal | `kg_journal` | `v_input_journal` | 2,134 | 0 |
| Keyword | `kg_keyword` | `v_input_keyword` | 30,042 | 0 |
| News | `kg_news` | `v_input_news` | 1,492 | 0 |
| Organization | `kg_organization` | `v_input_organization` | 10,610 | 596 |
| Paper | `kg_paper` | `v_input_paper` | 244,646 | 0 |
| Patent | `kg_patent` | `v_input_patent` | 2,010 | 0 |
| PatentFamily | `kg_patent_family` | `v_input_patent_family` | 1,999 | 0 |
| Person | `kg_person` | `v_input_person` | 40,139 | 126,801 |
| Product | `kg_product` | `v_input_product` | 2,040 | 0 |
| Project | `kg_project` | `v_input_project` | 4,008 | 0 |
| Report | `kg_report` | `v_input_report` | 3,000 | 0 |

两张辅助表的作用：

- `kg_node_index`：全部新节点键、原有标签列表、`is_missing` 标记；关系端点均引用这里的 `id`。
- `kg_missing_node`：缺属性端点的新键、根据原前缀推定的类型、缺失原因；推定类型不是已导出的标签，也没有补造人物/机构资料。

`v_input_person` 共 166,940 行，`v_input_organization` 共 11,206 行；多出的部分只有关联键，其他业务属性为空，`_is_placeholder=1`。其余视图与实际表行数相同，`_is_placeholder=0`。先装载这些端点或采用明确的隔离策略，不能静默丢弃其关联边。占位节点不应充当“前端展示丰富”的测试成果；需要展示的数据不足时，另建明确标记的测试数据。

## ID、属性和关系的恢复约定

1. SQL `id` 是本次新编排的来源关联键，不是旧 VID/EID；GLM 可以据此生成自己的稳定 VID。先持久化 `(来源类型, id) → 新 VID`，再转换所有关系端点。
2. 业务属性已分别展开成同名列；`_properties` 保留原始属性对象，可用于核验属性类型、空值与缺失属性的区别。不要把辅助字段一股脑作为业务属性写入。
3. 关系 `id` 是新的独立关系键，`from_id/to_id` 引用新节点键。`from_schema/to_schema` 帮助识别端点类型。它们都不是旧图端点 ID。
4. SQL 不携带旧 EID/rank 结构列；原导出不同 rank 的边已分别保留成独立行。恢复到 NebulaGraph 时，应为需要保留的并行边生成稳定的新 rank/身份，不能全部用 `@0` 覆盖成一条。
5. `organization_base` 如为当前业务查询所需，应给同一新 VID 共挂标签，不再生成 240,763 个重复实体。先核对当前分支 DDL、索引与业务查询。
6. 不能认为“新 VID 已写图”就完成兼容。现有搜索、MySQL DAO、详情、关系构建、缓存、向量索引等可能使用原业务 ID；GLM 必须检查并打通这些入口。
7. `HAS_KEYWORD` 有 Paper/Patent/Project → Keyword 三种组合；`HAS_OUTPUT` 有 Project → Paper/Patent；`REFERENCED_BY` 有 Paper → Report/Paper。保留真实组合，不能按单一端点类型过滤丢数据。

## 导入 MySQL

MySQL 8.4 已实际验证。可在独立实例的空目标库导入；SQL 自带建库名 `dev_graph_restore_20261026`，没有 DROP。已有同名非空库时应先选择独立实例或明确调整目标库，避免将失败的重复导入误当成功。

```bash
# 先配置你实际环境中的 MYSQL_HOST、MYSQL_PORT、MYSQL_USER；密码交互输入。
gzip -dc data/dev_graph_restore_20261026.sql.gz | \
  mysql --default-character-set=utf8mb4 \
    --host="$MYSQL_HOST" --port="${MYSQL_PORT:-3306}" --user="$MYSQL_USER" --password
```

再使用 `data/sample_queries.sql` 检查表、视图和关系端点。远端服务不能把作者电脑的 `127.0.0.1` 当作自己的 MySQL 地址；连接配置由 GLM 按目标环境读取，不在 Git 中提交凭据。

## GLM 的完成标准

完整任务见 [GLM_TASK.md](GLM_TASK.md)。至少需要新增恢复、测试数据准备和核验脚本；完成当前环境 `dev` 的实体/关系恢复、幂等复跑与失败核对；按实际前端九大业务逐项准备非空场景并验证展示；把真实数据 ID、输入参数、期望与实测、截图/日志路径写入独立的 [测试数据文档](NINE_BUSINESS_TEST_DATA.md)。

“SQL 导入成功”“图里有节点”“接口 HTTP 200”“本目录历史校验 PASS”都不能单独代表九大业务验收通过。
