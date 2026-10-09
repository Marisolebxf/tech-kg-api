# 图空间权限发布说明

本次交付增加多业务成员、公共/业务/未归属空间权限和空间隔离标注。以下为发布步骤，尚未在生产执行。

## 数据兼容与归属

- 新增 `kg_business_membership_state`、`kg_business_membership`、`kg_business_space_policy`，不修改旧 `kg_business_member` 的 `user_id` 单列主键、旧绑定或 `shared_key=production` 唯一默认源。
- 没有新成员状态记录时读取原成员绑定；管理员明确保存多业务成员后，新关联表成为该成员的授权依据。明确清空时保留状态记录，防止旧授权重新生效。
- 附带的 `business-space-permissions-plan.json` 仅登记已确认空间：`dev`、`dev2` 公共，`gaoxing_test` 属于 `billion-scale-kg-engine`。`memberships: []` 不修改任何人员绑定；不推断其余空间或历史配置归属。
- 其他未登记空间仅管理员可见、可操作。旧配置个人 `owner` 保留，管理员可在配置管理明确改为 `business:<clientId>`；开发人员不自动获得旧个人配置。
- 新标注表 `kg_space_indirect_relation_annotation` 主键为 `(graph_space, source_vid, target_vid)`。旧 `kg_indirect_relation_annotation` 原样保留，未确认空间的历史标注不复制、不猜归属。
- 旧实例继续读取旧表；新规则只由新版且启用 `BUSINESS_RBAC_ENABLED` 的实例执行。业务主表 `kg_business_client` 仍共享，管理端停用或改名会影响读取该表的其他实例，应按实际业务执行。

## 发布顺序

1. 核对部署目标为本次 API/worker，而非其他共享业务库的实例；使用现有备份流程保存迁移前数据。部署前检查业务库已有旧版权限表，确认计划中的业务与空间仍存在。
2. 在新版 API 镜像内、`backend` 工作目录执行只读检查（未建新表时退出码 `2` 表示待迁移；不兼容结构会报错并停止）：

   ```bash
   python -m script.migrate_space_permissions --check --plan ../docs/deployment/business-space-permissions-plan.json
   python -m script.migrate_space_annotations --check
   ```

   运行镜像若只包含 `backend`，将计划文件挂载到镜像可读路径并替换 `--plan` 参数。

3. 审核同一 JSON 计划后执行增量迁移；不要执行旧工具来批量重写成员、配置、历史任务或标注归属：

   ```bash
   python -m script.migrate_space_permissions --apply --plan ../docs/deployment/business-space-permissions-plan.json
   python -m script.migrate_space_annotations --apply
   python -m script.migrate_space_permissions --check
   python -m script.migrate_space_annotations --check
   ```

   两个脚本均默认只读检查，只有 `--apply` 写入。可重复执行，已有合规表不会重建；计划只替换列明人员或空间的新版权限记录。

4. API 与 Temporal worker 同时使用本次版本和 `BUSINESS_RBAC_ENABLED=true`。保留唯一默认生产源 `dev`，将两端兼容默认 `TRS_GRAPH_SPACE` 对齐为 `dev`；浏览器与新任务显式使用各自选择或持久化的空间。先前 API=`dev`、worker=`dev2` 的默认值不一致不能继续保留。
5. 发布前端，验证管理员全目录、开发者多业务目录/公共只读、普通用户公共目录；开发者在公共空间仍可进入三个治理页面查看。新任务固定持久化空间及单一业务，切换总览不改变已有后台任务的目标。
6. 在配置管理按实际人员授权保存多业务成员；公共空间下多业务开发者须明确选择配置业务。核实旧配置后逐项归属，不按当前唯一业务批量指派。

## 验收与回退

- 检查总览及九大业务切换空间不混入旧结果；公共空间治理写入、脚本写入、任务重试/暂停/执行和审核提交均由服务端拒绝。
- 检查任务实际持久化空间与业务、配置 `owner` 一致；多业务成员不能让业务 B 的任务使用业务 A 的配置。撤销业务绑定后，已缓存脚本资源和后续 worker 执行重新鉴权。
- 检查旧成员主键、旧空间默认源、旧标注和历史配置未被改写。无空间的旧任务/审核不按当前选择猜归属，需管理员核实。
- 如需回退，API 与 worker 一并回到此前匹配版本/配置，保留新增表和数据，不删除旧表。回退会恢复此前版本的权限行为，不能视为继续满足公共只读及多业务规则。

## 本地验证记录

2026-10-09 在 Docker 内部网络的独立 MySQL 库 `space_migration_verify_a6f7928b4e` 验证：只读检查未写表；执行仅增加 4 张并行表；第二次执行幂等；旧表记录、列、主键、索引保持一致；默认计划不改成员；两公共空间与业务空间归属正确；多业务授权/清空保留覆盖状态；旧标注未复制。脚本代理与多业务相关测试 `70 passed, 1 skipped`（跳过外部专用 MySQL 测试）。未连接或修改线上数据。
