# MySQL 与语言模型业务归属部署

本次仅新增 `platform_config_ownership`，以 `(config_kind, config_id)` 为主键。
`business_id IS NULL` 表示公共，未登记的历史配置也按公共读取。
原配置表的 owner、默认标记、连接参数、密钥、创建时间与引用 ID 均不改写。

默认功能按本次最终确认保留原规则：默认入口仍由管理员操作，未新增业务默认，
也未增加“只能将公共配置设为默认”的限制。原全局默认模型选择不读取新增归属表，
因此管理员若将业务专属模型设为全局默认，仍可能被其他业务的自动模型调用使用。
这是此次明确保留的既有默认行为，不应宣称默认调用也已按业务隔离。
本次隔离覆盖配置列表、详情、管理、显式选用及持久化任务中指定配置的访问。

## 先核查并保存精确计划

在部署目标的 backend 环境执行，复用已有 `MYSQL_*` 环境变量，不在命令行传密码：

```sh
python -m script.migrate_config_ownership --check --write-plan /approved-path/config-ownership-plan.json
python -m script.migrate_config_ownership --check --plan /approved-path/config-ownership-plan.json
```

默认只读，不创建数据库或归属表。计划只包含 ID、名称与归属，不包含连接信息或凭据。
输出文件必须尚不存在，防止覆盖已审查计划。计划绑定业务 ID `billion-scale-kg-engine`，
并记录数据库中的真实业务名称。两类配置各要求恰好一条精确名称“开发者测试”，否则停止。
其余当时盘点到的配置归公共。计划生成后新增的配置不会被此清单迁移或重置。

若“开发者测试”当前是默认配置，预检报告 `默认配置归属冲突` 并阻止写入。
这不是修改默认机制：本次不自动取消默认、不替换默认，也不建立业务默认。
必须先就实际冲突取得用户决定；不能为了通过迁移自行改默认标记。

## 引用核查范围

脚本只读列出受影响 MySQL 的 `kg_schema_source` 引用、Schema ID 和图空间，
以及语言模型的 `kg_schema_definition.llm_config_id` 引用。缺少引用表或该列时明确报告未完整核查。
`review_required` 意味着需要结合实际空间业务归属逐条判断，不能当作检查通过。
业务归属需以现行空间策略为准；公共空间和其他业务的引用尤其需要审查。
脚本不自动改写、删除或替换任何引用。

工作流控制库使用独立 `WORKFLOW_MYSQL_*` 连接配置，不能假定与业务库同库。
脚本始终标注工作流引用 `not_checked_separate_database`。部署前另用现有只读工具核对
流程配置、任务快照及执行配置中受影响 MySQL/LLM ID；未完成时应明确记录未核验，
发现跨业务引用时先解决实际冲突，再执行迁移。

## 应用与验证

先保留只读清单和现有数据备份，暂停配置写入，完成上述引用核查后执行：

```sh
python -m script.migrate_config_ownership --apply --plan /approved-path/config-ownership-plan.json
python -m script.migrate_config_ownership --check --plan /approved-path/config-ownership-plan.json
```

应用前校验整个清单：重复、不存在、名称变化、无效业务、已有不同归属、默认冲突均拒绝。
同计划重复执行幂等；只新增缺少的归属记录，不覆盖已有不同归属。
MySQL 建表 DDL 自动提交；记录插入使用事务。部署窗口保持配置写入暂停，避免核查与应用之间变化。
本脚本不作为每次启动时的自动回填任务。

核对两条业务配置标识、其余公共标识，以及管理员、本业务两位开发人员、其他业务开发人员的
列表、详情、管理、Schema 来源与任务使用权限。保留既有默认行为的验证结果。
回滚应回滚应用版本并保留新增归属表和审查清单；不要删除用户配置或重写原配置字段。

隔离测试：`python -m pytest tests/unit/test_config_ownership_migration.py -q`。
该单元测试使用内存 SQLite，不连接线上；另需在隔离 MySQL 验证 DDL 与事务行为。
此文档和脚本的存在不代表线上已核查、已应用或已部署。

## 已完成的隔离 MySQL 验证

2026-10-12 使用现有 `kg-space-backend-test` 连接 `kg-space-mysql` 测试实例，
仅新建本次随机命名 `config_ownership_verify_<16位随机十六进制>` 库。验证通过：
只读检查不建表；重复、缺失、改名、业务不符及默认冲突计划均在写入前拒绝；
特殊名称缺失或多条拒绝；合法应用仅新增归属表；重复应用幂等；原三表的全部字段和记录保持一致；
已有归属表时错误计划不部分写入。完成后仅删除本次新建库。

本机验证脚本（不作为发布文件）：`artifacts/verify_config_ownership_mysql.py`，在本机仓库根目录执行：

```powershell
Get-Content -Raw -Encoding utf8 artifacts/verify_config_ownership_mysql.py | docker exec -i -w /workspace kg-space-backend-test python -
```

脚本从容器既有环境取得连接参数，不输出凭据。不应指向生产实例。
