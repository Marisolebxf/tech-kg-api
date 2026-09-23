# dev2 首次权限上线：部署人员操作单

目标：仅部署 `/bkg_zpt` 对应的 dev2。业务名称“亿级知识图谱引擎”，clientId 为 `billion-scale-kg-engine`。账号密码不属于部署材料，不写入仓库、命令或 SQL。

## 1. 核实对象、安排维护窗口

由有服务器权限的部署人员执行。确认当前目录是服务器上的项目仓库，确认门户 `/bkg_zpt` 确实转发到本机 dev2。记录当前镜像版本和配置，备份业务数据库。检查主环境、dev2、gray 的 `MYSQL_HOST/PORT/DATABASE`（不要输出密码）：角色表在业务库，不在 WORKFLOW 控制库；若连接同一业务库，本次账号授权也会影响使用该库的其他环境，不能声称仅修改 dev2 数据。发现不符合预期时先协调共享范围，不自动复制整个数据库。

确认 PR #357 已合并到 kgetl，再在干净的部署工作区执行 `git switch kgetl`、`git pull --ff-only origin kgetl`。保留服务器原有 `.env`、`backend/.env` 和登录配置，不用仓库模板覆盖它们。

## 2. 准备 dev2 专用配置

从服务器现有根 `.env` 复制出本地 `.env.dev2-rbac`，限制文件读取权限，禁止提交 Git。保留原有连接参数，在该文件中设置：

```dotenv
AUTH_ENABLED=true
VITE_AUTH_ENABLED=true
BUSINESS_RBAC_ENABLED=false
DEV2_SHARED_GRAPH_SPACE=填写已核实的现有生产数据图空间名称
SCRIPT_RUNNER_TOKEN=填写新生成的至少32字符随机密钥
```

不要照抄中文占位符。使用密码管理器生成 runner 密钥。仓库原 dev2 API 写死 `dev`，worker 写死 `dev2`，所以必须核实哪个空间才是九大业务当前数据来源，不能随意选一个。下面的专用 overlay 会统一 API、worker 和两个前端的默认空间，不改动主环境/gray 配置。

在 Bash 中定义后续命令，保持原来部署时的 Compose project name（若原命令使用 `-p`，这里也添加相同值）：

```bash
dc() {
  docker compose --env-file .env.dev2-rbac \
    -f docker-compose.dev2.yml -f docker-compose.sandbox.yml \
    -f sandbox/compose.dev2.yml -f sandbox/compose.dev2-rbac.yml "$@"
}
dc config --quiet
dc --profile sandbox-build build api-dev2 web-dev2 script-runner script-sandbox-image
```

## 3. 先迁移，再启动新版本

维护窗口内暂停 dev2 的新任务提交，确认旧任务已结束或记录重新提交方案，停止 API/worker，避免新 ORM 在旧表结构上运行：

```bash
dc stop api-dev2 temporal-worker-dev2
dc run --rm --no-deps api-dev2 .venv/bin/python -m script.migrate_business_access --check
# 首次 check 返回 2 表示结构尚未就绪，检查报告后执行：
dc run --rm --no-deps api-dev2 .venv/bin/python -m script.migrate_business_access --apply
dc run --rm --no-deps api-dev2 .venv/bin/python -m script.migrate_business_access --check
```

最后一次检查必须通过。若缺失原审核表，先完成项目原有数据库初始化，不绕过错误。然后保持 BUSINESS_RBAC_ENABLED=false，在受控维护窗口启动新 API 和前端供账号登录，暂不启动 worker：

```bash
dc up -d --no-deps api-dev2 web-dev2 web-dev2-root
```

此阶段仍是旧权限语义，不向其他用户开放操作。确认依赖服务原本已运行；没有运行则按服务器原部署流程启动。确认统一认证登录可用，回调地址配置与 `/bkg_zpt` 一致。

## 4. 首次管理员初始化（命令只执行这一次）

让指定管理员先通过门户登录一次并进入 `/bkg_zpt`，使账号登记到 `kg_platform_user`。指定登录账号是 **19941138056**。

```bash
dc exec -T api-dev2 .venv/bin/python -m script.bootstrap_business_admin --username 19941138056
```

默认仅查询，不写入。将输出的 `userId` 与该账号登录后的 `/api/v1/auth/me` 身份或统一认证中心记录核对，再执行（替换占位值）：

```bash
dc exec -T api-dev2 .venv/bin/python -m script.bootstrap_business_admin \
  --username 19941138056 --expect-user-id '已核实的真实认证ID' --apply
```

成功输出 `isLocalAdmin: true`。重复执行不会重复授权，也不会撤销其他管理员。若账号未登记、用户名不唯一或 ID 不符，脚本拒绝写入。认证中心的 username 不一定等于手机号：若未匹配，由部署人员核实该账号实际 username 后替换参数，禁止猜 ID 或用手机号伪造账号记录。用户密码完全不需要提供给脚本。

## 5. 启用新权限和隔离运行器

把 `.env.dev2-rbac` 中 `BUSINESS_RBAC_ENABLED` 改为 `true`，先启动 runner，再同步重新创建 API 和 worker：

```bash
dc up -d script-runner
dc ps script-runner
# runner 必须 healthy，再执行：
dc up -d --force-recreate api-dev2 temporal-worker-dev2 web-dev2 web-dev2-root
dc ps
```

不可只 docker restart：它不会加载新环境变量。账号和空间未绑定前，普通账号看不到私有空间属于预期行为。保持维护窗口，由管理员完成下一步后再放开任务。

## 6. 管理员在页面完成其余配置

管理员重新登录 → 配置管理 → 业务权限相关区域：

1. 创建业务：名称“亿级知识图谱引擎”，clientId `billion-scale-kg-engine`。
2. 普通账号 **15838653038**、开发账号 **13543306340** 各登录一次进入系统。管理员在成员列表核实真实账号 ID，将两者分别设为普通角色和开发维护，业务都选上述业务。管理员保持管理员角色。
3. 将第2步核实的默认图空间登记为唯一“共享生产空间”，不绑定到某一个业务。现有私有空间逐个核实后绑定本业务，不批量把所有空间标记共享。
4. 需要新私有空间时由开发维护申请、管理员审批。核实旧数据源/模型/向量配置的 owner 与未知历史审核归属，按 `kgetl-business-rbac.md` 及绑定 SQL 模板处理；不能把其他业务配置批量转移。

之后新增用户的常规流程就是“登录一次 → 管理员页面分配业务/角色”，无需再次部署或运行初始化脚本。

## 7. 验收后交付

- 管理员可见全部空间和配置管理；普通用户只能查询授权空间，管理入口隐藏。
- 开发维护可维护本业务空间、写入/构建共享生产空间，但不能处理生产人工审核；管理员能审核。
- 用 `sandbox/example_extract.py` 对适配的测试 Schema 验证一次抽取，确认 worker 使用 runner；检查任务结果及 runner 清理情况。旧脚本直接 import infra/dao 或任意联网的用法需改 SDK。
- 验证原 businessOnly 测试账号仍只有原九大业务入口。若指定三个账号本来带此限制，不默默删除该限制；核实其用途再处理。
- 回传部署 commit、迁移结果、三个账号角色、共享空间名称和上述测试结果。不要发送密码、token 或整个环境文件。

若失败，保留错误与旧镜像，暂停开放；不要简单关闭业务权限开关继续对外服务，那会恢复旧权限语义。迁移为增量变更，保留结构，在维护窗口按已记录版本和配置处理回退。
