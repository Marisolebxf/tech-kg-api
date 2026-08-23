# 全局管理员与人工修正上线说明

## 权限边界

- 普通用户：图谱查询、九大业务分析、提交/修改/撤销自己的人工修正申请。
- 全局管理员：审核所有人工修正、查看同步状态与重试、成员角色管理。首期管理端不提供 Schema 管理和图谱构建页面。
- 审核人、Schema 操作人等身份全部取自后端登录会话，不读取前端传入的用户 ID。管理员可以审核自己提交的申请。

首期人工修正对象为专家、机构/企业和 `EMPLOYED_BY` 专家任职关系。“删除”是可追溯的软删除，不物理删除业务数据。“查询”由修正列表、条件查询和详情接口承担；九大功能仍是原有业务分析查询，两者不混用。

## 首次部署

1. 在 `.env` 中设置统一用户中心的首批全局管理员，例如：

   ```dotenv
   PLATFORM_INITIAL_ADMIN_USER_IDS=10001,10002
   PLATFORM_BOOTSTRAP_FIRST_ADMIN=true
   CORRECTION_SYNC_WORKER_ENABLED=true
   CORRECTION_SYNC_MODE=projection
   OPERATOR_RELOAD_TOKEN=<随机强令牌>
   ```

2. 初始化正式 MySQL 治理表：

   ```bash
   cd backend
   uv run python -m script.init_platform_governance
   ```

3. 仅当完成业务映射和九大功能回归、准备将 `CORRECTION_SYNC_MODE` 切换为 `dual` 时，才为 `TRS_GRAPH_SPACE` 指向的图空间补充软删除和幂等字段：

   ```bash
   uv run python -m script.init_correction_graph_schema
   ```

4. 启动 API。用户首次登录后会自动进入成员列表；首批管理员可在“管理端 → 成员管理”授予后续管理员。

如果交付时还不知道统一用户中心用户 ID，可设置 `PLATFORM_BOOTSTRAP_FIRST_ADMIN=true`。系统只会在管理员角色表为空且没有配置首批管理员时执行一次：将第一个成功登录的用户永久写为全局管理员；之后首次登录的新账号仍是普通用户，并自动出现在成员管理列表中，由已有管理员授权。登录页的“用户端/管理端”只决定进入位置，不参与角色授予；账号注册仍由统一用户中心负责。

本机 MySQL 尚未启动、只需先联调管理端页面时，可设置 `APP_ENV=dev` 和 `PLATFORM_DEV_FIRST_USER_ADMIN=true`。它只把本次后端启动后第一个成功登录的账号临时视为管理员，重启后重新确定；该配置在生产环境强制失效。

## 真实接口联调

管理端默认在列表接口不可用或无记录时展示前端示例。调试真实后端时，新建或修改 `frontend/.env.local`：

```dotenv
VITE_API_TARGET=http://127.0.0.1:8000
VITE_ADMIN_EXAMPLE_FALLBACK=false
```

重启 Vite 后，页面不会再用示例掩盖空数据、500 或超时。然后按以下顺序启动本地环境：

```powershell
cd backend
.\.venv\Scripts\python.exe -m script.init_platform_governance
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

MySQL 连接参数使用 `backend/.env` 中的 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_DATABASE`、`MYSQL_USERNAME`、`MYSQL_PASSWORD`。只调试治理接口时，可在本机临时设置 `AUTH_ENABLED=false`，此时内置本地账号拥有管理员权限；不要把该设置带到部署环境。需要验证真实统一用户中心登录时，再恢复 `AUTH_ENABLED=true`。

启动前端后，可在 `http://127.0.0.1:8000/docs` 或管理端依次验证：

1. `GET /api/v1/auth/me`，先确认当前身份是管理员。
2. `GET /api/v1/corrections?scope=all&pageSize=100` 和 `GET /api/v1/admin/members`，确认 MySQL 治理表可读。
3. `POST /api/v1/corrections` 创建申请，再调用 `POST /api/v1/corrections/{id}/review` 审核。
4. 查看记录是否进入待同步、已完成或同步失败；失败记录可调用 `POST /api/v1/corrections/{id}/retry` 重新入队。

只有在 TRS 图服务和目标图空间可用时才执行 `.\.venv\Scripts\python.exe -m script.init_correction_graph_schema` 并验证图端同步。单独调试申请、列表、审核和成员权限时，先完成 MySQL 初始化即可。

### Windows 本地 MySQL 与 CRUD 联调

当本机 3306 已被其他项目占用时，可在 Docker Desktop 中为本项目单独使用 3307：

```powershell
docker start tech-kg-mysql
docker exec tech-kg-mysql mysqladmin ping -h 127.0.0.1 -uroot -p123456789 --silent
```

首次不存在容器时才执行：

```powershell
docker run -d --name tech-kg-mysql -p 127.0.0.1:3307:3306 `
  -e MYSQL_ROOT_PASSWORD=123456789 `
  -e MYSQL_DATABASE=gkx_element `
  -v tech-kg-mysql-data:/var/lib/mysql mysql:8.4
```

在一个 PowerShell 窗口启动后端：

```powershell
cd D:\CodexProjects\tech-kg-api\backend
$env:AUTH_ENABLED='false'
$env:APP_ENV='dev'
$env:MYSQL_HOST='127.0.0.1'
$env:MYSQL_PORT='3307'
$env:MYSQL_DATABASE='gkx_element'
$env:MYSQL_USERNAME='root'
$env:MYSQL_PASSWORD='123456789'
$env:CORRECTION_SYNC_MODE='projection'
$env:CORRECTION_SYNC_WORKER_ENABLED='true'
$env:CORRECTION_SYNC_INTERVAL_SECONDS='5'
.\.venv\Scripts\python.exe -m script.init_platform_governance
.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8002
```

本地 `frontend/.env.local` 配置为 `VITE_API_TARGET=http://127.0.0.1:8002` 和 `VITE_ADMIN_EXAMPLE_FALLBACK=false`，保证页面操作的是真实接口而不是前端示例。然后在第二个 PowerShell 窗口启动前端：

```powershell
cd D:\CodexProjects\tech-kg-api\frontend
& 'D:\developtools\node.is\corepack.cmd' pnpm dev --host 127.0.0.1 --port 5174
```

页面 CRUD 的对应关系如下：

- 新增：“新增修正申请”中选择“新增”，审核通过后写入修正投影。
- 查询：修正记录表是列表查询，“详情”是单条查询；接口还支持 `status`、`targetType`、`keyword`和分页参数。
- 修改：待审核记录可直接点“修改”；要修正已完成的业务对象，则新建一条操作类型为“修改”的申请。
- 删除：新建申请时选择“删除（软删除）”，审核通过后将投影标记为失效，保留审核和操作历史。页面中的“撤销”只是撤回待审核申请，不等于删除业务对象。

## 同步状态

交付演示默认使用 `CORRECTION_SYNC_MODE=projection`：审核通过后真实写入 MySQL 人工修正投影与操作历史，但不修改九大功能依赖的原始 DWD 数据和业务图库。后续完成统一数据映射与回归测试后，可切换为 `dual`，再启用图库同步。

审核通过只在 MySQL 中原子写入修正记录和 outbox 任务。后台 worker 至少更新 MySQL 修正投影；`projection` 模式到此完成，`dual` 模式才继续更新图库。失败会记录错误并按指数退避自动重试，管理员也可手动重新入队。投影和图写入使用修正记录 ID 作为幂等依据。

## 本期交付边界与后续差距

- 已完成：统一用户中心身份校验、首位管理员落库、成员授权，以及修正申请的新增、列表/详情查询、修改、软删除、撤销、审核、历史和 MySQL 投影同步。
- 当前隔离：`projection` 模式下，修正投影不会反向改写原始 DWD 表或业务图，因此九大功能不会被未验证的管理端数据影响，也不会立即读到修正结果。
- 待补工作：统一 `Person/Scholar` 实体与 `AFFILIATED_WITH/EMPLOYED_BY` 关系映射，完成九大功能数据回归后再启用 `dual` 模式。
- 待补工作：现有通用 Temporal 步骤和旧人工审核模块仍包含演示实现，尚未改成调用各业务 ETL/重构脚本的生产工作流。
- 待补工作：交付环境接入真实数据后，应设置 `VITE_ADMIN_EXAMPLE_FALLBACK=false`，避免示例数据掩盖接口异常。
- 外部依赖：同事关系等四个目前返回 501 的业务模块，需在对应上游分支/PR 合并后进行契约冒烟和回归测试；这不由人工修正流程代替。

## 专家同事关系

前端正式调用 `POST /api/v1/kg-service/expert-colleague-relation`，参数为必填的 `expert_a_id`、`expert_b_id` 和选填的 `start_time`、`end_time`（`YYYY-MM`）。该接口由业务服务内部调用 `/api/v1/graph-search/*`，前端不调用底层通用 `/query`。
