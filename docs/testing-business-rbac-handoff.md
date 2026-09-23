# 业务图空间权限与隔离脚本执行——测试交接说明

文档日期：2026-09-23。阶段：可编写用例，尚不能确认具备现场执行与截图条件。本文不包含账号密码、登录令牌、数据库凭据或运行器密钥。

## 1. 功能说明及本次范围

功能名称：按业务隔离图空间的三角色权限、空间创建审批、开发脚本隔离执行。

解决的问题：同一业务多个统一认证账号需要共享空间，不同业务空间不能互相访问；原后台管理入口只有粗粒度权限；开发者上传的 Python 不应取得后台全局凭据绕过空间隔离。

本系统业务 clientId 是自定义业务标识，与统一认证 OAuth 应用 clientId、账号真实 userId 不同。一个账号当前绑定一个业务，一个业务可含多个账号和多个空间。

已约定内部业务：亿级知识图谱引擎 / `billion-scale-kg-engine`。这只是预定配置，尚未在真实数据库创建。

用户操作：统一认证登录 → 管理员在原“配置管理”页的“业务与图空间”区域创建业务、编辑成员角色及归属、登记空间 → 开发维护申请新空间 → 管理员批准或驳回 → 各角色在获准空间工作。保留原页面布局与业务入口，不另建独立业务管理页面。

本次包括：

- user / developer / admin 三角色、业务成员与空间绑定、共享生产空间。
- 页面可见性与后端接口授权；图查询、Schema、任务、算法结果、人工审核及相关缓存的空间边界。
- 创建申请、批准后的图/向量空间创建、失败重试。
- 开发者继续上传/修改脚本，隔离容器运行、受控 SDK 资源访问。
- 保留原 businessOnly 公司测试账号的“仅九大业务”上限。
- 增量迁移、首次管理员初始化工具、dev2 部署覆盖配置和操作说明。

不包括：统一认证中心注册/改密、重做九大业务、为实际业务批量分配空间、自动迁移全部历史 owner、水位及审核归属、单独审核员角色、生产部署完成证明。操作有审计记录不等于新增了完整人员操作记录管理产品。

## 2. 预期行为

### 2.1 角色矩阵（新权限开启、真实认证开启）

| 能力 | 普通 user | 开发维护 developer | 管理员 admin |
| --- | --- | --- | --- |
| 本业务私有空间 | 查询 | 查询、写入、构建、审核 | 全部 |
| 其他业务私有空间 | 拒绝 | 拒绝 | 全部 |
| 共享生产空间 | 查询 | 查询、写入、构建，不能人工审核 | 全部及人工审核 |
| Schema/构建/人工处理/配置等管理入口 | 隐藏，直接请求接口也拒绝 | 可见，仍按资源授权 | 可见 |
| 管理业务、成员、空间归属 | 拒绝 | 拒绝 | 允许 |
| 申请空间 | 拒绝 | 仅本业务 | 可选择业务 |
| 批准、驳回、重试创建 | 拒绝 | 拒绝 | 允许 |
| 上传/修改抽取脚本 | 拒绝 | 在授权资源范围允许 | 允许，开启新权限时也走隔离运行 |

补充边界：

- businessOnly 与上述权限取交集；即使赋予 developer/admin，也不能突破原九大业务访问上限。
- 未登记归属的私有空间，对非管理员拒绝；不得回退旧个人空间绑定绕过隔离。
- 未绑定业务的普通用户仍可读取已登记的共享生产空间，不能读取私有空间。开发维护绑定业务是必填。
- 生产“不能人工审核”不代表全部生产写入都要先审批。开发维护的原直写/构建仍可执行，进入人工审核的生产记录只能管理员处理。
- 前台管理员可能来自门户身份或本地授权；后台任务要求可信本地管理员授权/初始管理员配置，门户管理员快照不能替代后台授权。
- 停用业务后其成员不再解析为该业务角色；已有独立管理员授权不会因此消失。普通共享空间只读不等于业务私有权限。

### 2.2 主流程、输入和输出

| 流程 | 输入/动作 | 预期输出及验证点 |
| --- | --- | --- |
| 首次管理员 | 已登录并登记的 username，预览真实 userId，再传 --expect-user-id 与 --apply | 预览不写；唯一精确账号匹配后授予本地管理员；输出 isLocalAdmin=true；重复不重复写 |
| 保存业务 | clientId、名称、enabled | 新建或更新业务；原 ID 对应业务被更新，不应当成重复 ID 创建错误 |
| 成员绑定 | 已登记 userId、clientId、角色 | 保存账号业务/角色；列表刷新；随后后端按当前绑定授权；不能用前端伪造角色 |
| 现有空间绑定 | 已存在空间名、业务或共享标记 | 更新归属，不创建/删除图数据；共享空间不归属单业务；唯一共享槽位 |
| 申请创建 | spaceName、reason，本业务/管理员所选业务 | pending（待审批），此时不应创建实际空间 |
| 批准 | approve=true、note | pending→creating→ready；实际图空间和向量库准备完成后返回已创建 |
| 驳回 | approve=false、note | rejected，不建空间，释放活跃申请槽位 |
| 创建异常与重试 | 管理员重试失败或 creating 超过10分钟的申请 | failed 保留空间归属预约；重试继续原批准申请，不让其他业务抢占 |
| 抽取脚本 | @step 脚本、Schema来源、SDK配置、批次数据 | 独立容器运行，输出实体/边及统计，平台写授权空间；支持异步和多步骤 |
| 人工审核 | 授权空间内审核 case | 本业务私有 case 开发维护可处理；生产 case 仅管理员；未知空间 case 先核实补归属 |

API 均在 `/api/v1/business-access` 下：GET `/state`；PUT `/businesses/{client_id}`、`/members/{user_id}`、`/spaces/{space_name}`；POST `/requests`、`/requests/{id}/decision`、`/requests/{id}/retry`。成功通常为 ApiResponse 的 data 内容；失败检查 HTTP 状态和提示，不只看按钮是否隐藏。

### 2.3 校验与异常用例

- clientId：1～64字符，`^[a-z0-9][a-z0-9_-]{0,63}$`。业务名称 API 允许1～200字符，当前页面 maxlength=64；前后端上限不一致是已知事实，边界测试分别记录。
- 新空间：1～64字符，`^[A-Za-z_][A-Za-z0-9_]{0,63}$`；reason/note 最多2000字符。业务必须存在且启用。
- 不存在的成员拒绝并提示先登录登记；成员表中的真实 userId 才是绑定主键。初始管理员撤权/最后管理员保护沿用既有约束。
- 共享空间与业务同时指定拒绝；不存在的实际空间拒绝绑定；第二个共享生产槽位冲突拒绝，需要先处理原绑定。
- 重复活跃申请、空间已登记或已存在、重复审批、未批准请求的重试均拒绝；不可用驳回操作清理已经创建的空间。
- 未登录通常401，越权403；成员/空间不存在404；状态冲突409；输入格式422；业务未启用400。具体端点以实现为准，不能将所有失败统一断言为403。
- BUSINESS_RBAC_ENABLED=false 时业务管理接口返回409；AUTH_ENABLED=false 是免登录开发语义，不能拿来验收三角色隔离。
- 权限表不可用时相关鉴权503，不退回宽松权限。私有资源跨业务直接改 URL/请求空间字段必须拒绝；任务结果、审核详情、缓存和列表均需覆盖。
- 后台批次及脚本 RPC 重新检查当前账号/业务/来源绑定；撤权或来源改变不能继续按旧授权访问。
- runner 缺失/不可用、脚本 hash 不一致、超时、协议非法、输出超限、资源耗尽应失败，不回退后台本机执行。
- 脚本没有网络、后台源码、全局环境凭据、Docker socket；SDK 不允许自选连接地址或空间。MySQL 只允许所选来源数据库受限只读 SQL；图支持授权读写，但不开放全局管理/审核；Milvus 固定任务空间同名数据库。
- 语义记录只允许同一次 Temporal 运行、同账号/业务/空间复用；授权记录30天过期。不能传其他任务 record ID 绕过隔离。
- 脚本直接 import infra/dao、读取后台 .env、任意联网需改为 SDK；额外计算依赖需预装固定镜像。这是兼容限制，不应判定任意旧脚本均须无修改通过。

## 3. 代码、版本和部署状态

仓库：https://github.com/Marisolebxf/tech-kg-api 。目标分支 `kgetl`。

| 变更 | PR/提交 | 交接核实状态 |
| --- | --- | --- |
| 三角色、业务隔离、审批、隔离脚本 | PR #357；实现 f9582a8a、75dfc656；合并 72616027aacb6371bf5183b653121ab03188bbdf | 已合并，GitHub mergedAt=2026-09-23T15:00:06Z |
| 首次管理员工具、dev2部署操作单 | PR #360；实现568003cc；交接前分支HEAD 83c04239c77dfc2a4145d42e9718c2fe27e2d98d | OPEN，尚未合并；本测试交接说明后续也放入该分支 |

开发分支分别为 `feat/kgetl-business-space-rbac`、`feat/dev2-rbac-bootstrap-handoff`。本文描述已检查的本地代码，不代表后续任意 kgetl 版本。

拟测试地址：https://edu.itic-sci.com/bkg_zpt/ 。配置管理前端路由 `/configurations`，预计完整入口 `/bkg_zpt/configurations`；应优先从登录后的菜单进入，以实际网关路由为准。业务区域叫“业务与图空间”。没有为本次新增独立管理页面。

线上状态：未连接部署服务器，未取得部署 commit、迁移回执、环境开关及runner健康证明。之前无登录访问认证接口得到401，只能证明当时接口可达，不能证明新版本已部署；本次未重新探测线上。三个指定账号尚未由本任务执行授权/业务绑定。部署执行与截图均待现场条件具备。

关键文件（均为仓库相对路径）：

| 职责 | 文件 |
| --- | --- |
| 页面与API客户端 | frontend/src/components/BusinessAccessManagement.vue；frontend/src/views/platform/ConfigurationManagementView.vue；frontend/src/api/businessAccess.ts；frontend/src/router/index.ts |
| 管理接口与校验 | backend/biz/handler/business_access.py（请求模型也在此文件，不另有schemas/business_access.py） |
| 中央空间授权 | backend/service/business_access_control.py；backend/service/platform_access.py |
| 模型 | backend/db_model/business_access.py；backend/db_model/platform_governance.py；backend/db_model/script_resource_grant.py |
| 后台任务与隔离代理 | backend/service/temporal_workflows.py；backend/service/script_resource_broker.py；backend/service/script_resource_grants.py；backend/service/script_sandbox_client.py |
| SDK与运行器 | backend/sdk/kg_sdk.py；backend/sdk/sandbox_proxy.py；sandbox/runner.py；sandbox/runtime.py |
| 首次上线 | backend/script/migrate_business_access.py；backend/script/bootstrap_business_admin.py；docker-compose.sandbox.yml；sandbox/compose.dev2.yml；sandbox/compose.dev2-rbac.yml |

## 4. 测试条件及数据准备

执行前部署人员需交付：实际commit、迁移通过、AUTH与RBAC开启、API/worker/前端默认空间一致、runner healthy、初始管理员已授权、实际共享空间名称和数据库共享范围。操作参照 docs/dev2-rbac-deployment-handoff.md。

指定三个内部账号由项目人员另行提供登录凭据：管理员账号尾号8056；普通账号尾号3038；开发维护账号尾号6340。正式文档不记密码；三个账号均需至少真实登录一次并登记。真实userId待现场核实。

仅这三个同业务账号不足以验收全部隔离，执行阶段还需：

| 对象 | 用途 | 当前状态 |
| --- | --- | --- |
| 业务A：billion-scale-kg-engine | 内部三角色流程 | 名称已定，未实配 |
| 独立测试业务B + 至少1名开发账号 | 正反向跨业务请求、来源/任务隔离 | 待准备，不可冒用真实外部业务 |
| 业务A第二个开发账号（可选扩充） | 多人同业务协作 | 待准备 |
| 原businessOnly测试账号 | 验证九大业务上限，不要用普通账号冒充 | 待确认 |
| 私有空间A/B | 本业务操作与跨业务拒绝 | 建议审批新建 qa_rbac_a_日期 / qa_rbac_b_日期；仅示例命名，不是已有空间 |
| 一个共享生产空间 | 共享查询、开发写入、管理员审核 | 名称待部署方确认；共享数据不保证可随意写入 |
| 每空间适配的Schema/来源/配置与少量合成记录 | 上传、构建、审核、SDK测试 | 待准备；用唯一 qa_rbac_ 批次标识 |
| 私有/共享各一条审核case、失败申请 | 审核权限与重试 | 待在授权测试数据上生成 |

依赖：统一认证与门户网关、Redis会话、业务MySQL、Temporal及控制库、trs-graph、Milvus、脚本S3/RustFS、Docker/runner。测试LLM/Embedding/语义SDK时还需对应已授权服务配置和可用端点。普通菜单测试不代表这些依赖都已验证。

测试查询请求、Schema、来源ID、任务ID和case ID均应来自本轮已记录对象，不编造实际ID。本业务历史配置owner迁移、未知审核归属须由管理员核实；不能把“资源不可见”一律判断成前端bug。

## 5. 操作影响与清理

| 操作 | 真实影响 | 测试及清理要求 |
| --- | --- | --- |
| 登录/读取 | 登录会刷新本地账号/会话记录；业务查询主要读数据 | 不把登录当作绝对无写入；不要清空共享会话库 |
| 保存业务/成员 | 新增或更新业务、业务归属、管理员角色，并有管理审计 | 先记原值，结束后由管理员恢复；不撤销最后管理员，不删真实账号 |
| 停用业务/改空间归属 | 改变其他账号即时授权范围，不搬迁图数据 | 只用测试业务/空间；保存原绑定后恢复 |
| 申请/审批 | 写申请；批准会实际创建图空间及向量库，失败也可能留下部分对象 | 记录申请/空间/向量库ID；重试可能继续创建，不能盲目重复 |
| 运行脚本/构建/算法 | 启动任务，读来源，可能写图/向量、S3输出、水位、语义授权及失败审核记录 | 少量合成输入，唯一批次；清理前先停止提交并确认任务终止 |
| 审核通过/修改/重跑 | 改case状态，可能写图或发起新抽取任务 | 只对本轮测试case操作；记录下游实际对象 |
| 超时/OOM/依赖中断 | 消耗资源、可能影响并发请求 | 故障注入仅独立测试运行器/环境；不要停共享生产服务 |
| 数据库迁移 | 持久增表/列/索引及可靠归属回填 | 不是每条用例前后反复执行的清理动作；不DROP迁移表 |

清理顺序：记录本轮资源清单→停止/确认测试任务结束→只清理有唯一标记的图/向量测试数据和对应输出→恢复角色/owner/空间绑定原值→核对残留任务与case。任务/审核审计按项目保留策略处理，不批量清库。

当前新业务管理接口没有业务/申请的DELETE端点；驳回不等于删除，解除归属也不等于DROP空间。需要回收已批准的新空间时，由部署/数据库负责人核实无引用后使用项目已有管理能力分别处理图空间、向量库和登记记录；具体现场清理命令待环境对象确认，本文不提供可误删生产对象的通用DROP命令。失败创建可能留有对象，也按实际清单清理。

runner正常/异常结束会清理自己的执行容器，重启有owner回收；不能用 docker system prune 代替本次清理。共享生产空间写入必须事先约定可写测试Schema/记录及清理负责人，否则只编写用例，不执行写入。

## 6. 当前状态、证据与可复用材料

### 6.1 已完成/未完成

已完成：代码中的三角色及业务隔离、空间审批、隔离脚本执行；迁移和初始化工具；部署操作单；专项自动化验证。#357已合并，#360待合并。

未完成/待核实：实际部署、管理员授权、业务及空间绑定、第二业务账号准备、真实统一认证与生产图服务联调、用户页面验收、测试截图。不能把自动测试通过解释为这些事项已完成。

已知限制：业务名页面64/API200上限差异；旧直接访问后台模块/网络的脚本需迁移SDK；dev2原默认空间不一致由专用overlay解决但未证明线上已应用；主/dev2/gray可能共用业务库；历史未归属资源与旧任务需人工核实；未宣称全量后端测试全绿。

### 6.2 已有自动测试结果（不同阶段，不能简单累加）

| 验证 | 已记录结果 | 证据范围 |
| --- | --- | --- |
| 后端权限/隔离/迁移联合专项 | 364 passed，包含真实测试MySQL查询与新库迁移 | 前一实现轮终端结果；未另存完整日志，不宣称本次复跑 |
| 合入当时最新kgetl后的图查询专项 | 213 passed、1 skipped；MySQL opt-in后在联合专项执行 | 前一轮终端结果 |
| 真实Docker隔离/协议 | 15 passed | tmp/sandbox-isolation.log，包含SDK、资源限制、清理、重启回收 |
| runner镜像/入口与Compose | 构建、Linux真实子容器执行、三套overlay通过 | 前一轮工具结果；非生产部署 |
| 前端权限专项 | 8文件112 passed；后续Schema提示11 passed；生产构建通过 | 前一轮终端结果，非人工界面验收 |
| 首次管理员工具 | 5 passed（Docker）；Ruff通过 | 本次初始化实现轮终端结果；测试脚本可复跑 |
| dev2启用overlay | 空间/认证四服务一致、API/worker RBAC一致断言通过 | 配置解析结果，未启动真实dev2 |
| 扩展后端全量及基线复查 | 初次1813 passed/49 failed；修复本次SSE调用测试后余48失败与ff0383c1节点/信息一致 | tmp/baseline-comparison.md/json及对应log/xml；不是最新版本全量通过证明 |

48项基线失败分类：27项测试镜像缺pymilvus，17项旧Schema夹具，4项旧graph console替身缺_all_spaces。后续代码已变化，需在最终部署版本按需重跑，不能将旧基线结论无限外推。

### 6.3 准确材料路径

本机工作区根：`D:\CodexProjects\tech-kg-kgetl-business-space-rbac`。以下均相对此根；测试人员拿到仓库后改为其本地根，不要求使用本机D盘。

已提交/拟随本交接提交：

- `docs/testing-business-rbac-handoff.md`：本文。
- `docs/dev2-rbac-deployment-handoff.md`：部署人员命令及首次管理员初始化顺序。
- `docs/kgetl-business-rbac.md`：权限边界、兼容、迁移说明。
- `backend/script/sql/business_access_bindings.example.sql`：占位绑定/只读盘点，写语句默认注释，不直接当生产初始化数据执行。
- `sandbox/README.md`、`sandbox/example_extract.py`：隔离协议、限制、复现命令及最小SDK脚本。
- `backend/tests/unit/test_business_access_control.py`、`test_business_space_approval.py`、`test_business_access_migration.py`、`test_manual_review_business_rbac.py`、`test_workflow_business_rbac.py`、`test_role_router_access.py`：同目录权限用例。
- `backend/tests/unit/test_script_resource_broker.py`、`test_script_resource_grants.py`、`test_script_sandbox_client.py`、`test_sandbox_sdk.py`、`test_bootstrap_business_admin.py`：同目录隔离及初始化用例。
- `frontend/src/components/BusinessAccessManagement.spec.ts`、`frontend/src/router/role-access.spec.ts`：页面/路由自动化用例。
- `sandbox/tests/test_runner.py`：独立运行器测试，开启Docker集成会实际创建并清理测试容器。

仅本机留存、未进Git（转交测试人员时需另行复制，链接仓库无法取得）：

- `tmp/sandbox-isolation.log`
- `tmp/baseline-comparison.md`、`tmp/baseline-comparison.json`
- `tmp/baseline-failures.log`、`tmp/baseline-failures.xml`
- `tmp/current-failures.log`、`tmp/current-failures.xml`
- `tmp/baseline-selected-nodeids.json`

这些证据中的“当前”指当时基线复查轮，不代表本次或未来部署HEAD。临时MySQL测试容器/网络已清理，不能直接依赖旧容器复跑。后端依赖测试按项目规则在Docker中运行。

## 7. 用例编写与执行交界

现在可依据本文先编写：角色矩阵、页面入口、直接接口越权、跨业务资源/任务、申请状态机、生产审核、SDK限制、旧businessOnly兼容、迁移/初始化异常用例。

执行前必须填齐：实际地址/commit、开关、账号真实ID与业务、空间清单、依赖健康、合成数据与清理人。未满足的用例标“阻塞/未执行”，不要截取旧版本页面作为新功能证据。截图阶段至少覆盖三个角色菜单、成员绑定结果、空间范围、审批状态、开发者生产审核拒绝、管理员审核成功及一次隔离抽取结果；图片中遮盖凭据和不必要个人信息。
