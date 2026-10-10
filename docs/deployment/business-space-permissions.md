# 图空间权限发布说明

当前规则（2026-10-11）：开发人员只绑定一个业务，公共空间只读；管理员创建默认公共，开发人员创建归属自己的业务。语言模型与 MySQL 数据源为平台共享配置，开发人员可查看/选用，只有管理员可修改。以下为本次预览后的发布步骤，不代表已经部署。

## 数据兼容与归属

- 新增 `kg_business_membership_state`、`kg_business_membership`、`kg_business_space_policy`，不修改旧 `kg_business_member` 的 `user_id` 单列主键、旧绑定或 `shared_key=production` 唯一默认源。
- 没有新成员状态记录时读取原成员绑定；管理员保存唯一业务后，新关联表成为该成员的授权依据。明确清空时保留状态记录，防止旧授权重新生效。上线前盘点已有多个业务的开发人员，由管理员确认保留业务，不能自动选第一项。
- 2026-10-10 确认的实验归属覆盖 2026-10-09 调查列出的全部 20 个空间：`gaoxing_test`、`test_space_01` 属于“亿级知识图谱引擎”（`billion-scale-kg-engine`）；其余 18 个（包括 `dev`、`dev2`）全部公共，逐项列于 `business-space-permissions-plan.json`。本清单替代此前“其余 17 个未归属”的实验安排。
- 新建空间在执行 DDL 前登记归属；失败保留预留记录以便按原归属重试，尚不存在的空间不出现在列表。清单外、缺少归属的外部空间不自动公开，也不显示“未归属”分类；应核实归属后登记。`public-space-corrections-20261011.json` 仅将用户指定的 `gkx_verify_1`、`hh` 设为公共。
- 只有开发者需要业务绑定；管理员可操作全部空间，普通用户只看公共空间，开发者可操作所绑定业务空间、只读公共空间。实验拟让两个已确认的开发者都绑定上述业务；`memberships: []` 暂保留现有成员记录，第二个账号及内部 `userId` 核实前不新增人员授权，也不将已有普通成员自动提升为开发者。
- 语言模型/MySQL 的旧 `owner` 元数据和现有引用保留，但不再用于过滤或限制读取/使用；不批量重写配置。其他配置类型不在本次共享配置变更范围。
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
5. 发布前端，验证管理员全目录、开发人员唯一业务目录/公共只读、普通用户公共目录；开发人员在公共空间仍可进入三个治理页面查看。新任务固定持久化空间及单一业务，切换总览不改变已有后台任务的目标。
6. 用迁移脚本 `--check --plan` 检查两个空间纠正清单后，在备份基础上 `--apply --plan` 应用同一文件；不得覆盖其余空间。配置管理显示授权全集；管理员/开发人员个人解绑仅从本人下拉隐藏，普通用户无解绑能力。保留现有 `kg_user_graph_space_hidden` 记录及表。

## 验收与回退

- 检查总览及九大业务切换空间不混入旧结果；公共空间治理写入、脚本写入、任务重试/暂停/执行和审核提交均由服务端拒绝。
- 检查任务实际持久化空间与业务一致；允许选用任意共享语言模型/MySQL 配置，但不能借配置访问权限写其他业务或公共空间。撤销业务绑定后，已缓存脚本资源和后续 worker 执行重新鉴权。
- 检查旧成员主键、旧空间默认源、旧标注和历史配置未被改写。无空间的旧任务/审核不按当前选择猜归属，需管理员核实。
- 如需回退，API 与 worker 一并回到此前匹配版本/配置，保留新增表和数据，不删除旧表。回退会恢复此前版本的权限行为，不能视为继续满足当前规则。

## 本地验证记录

2026-10-09 在 Docker 内部网络的独立 MySQL 库 `space_migration_verify_a6f7928b4e` 验证：只读检查未写表；执行仅增加 4 张并行表；第二次执行幂等；旧表记录、列、主键、索引保持一致；默认计划不改成员；两公共空间与业务空间归属正确；多业务授权/清空保留覆盖状态；旧标注未复制。脚本代理与多业务相关测试 `70 passed, 1 skipped`（跳过外部专用 MySQL 测试）。未连接或修改线上数据。

2026-10-10 将实验计划扩展到全部 20 个已调查空间后，在独立 MySQL 库 `space_migration_verify_2ff1bcec51` 复验：18 个公共空间、两个指定业务空间及其 ClientId 均正确；默认检查不写入，重复执行幂等，旧表结构、数据和现有成员绑定不变。该实验计划尚未应用到线上，两个开发者的完整账号映射仍待核实。
