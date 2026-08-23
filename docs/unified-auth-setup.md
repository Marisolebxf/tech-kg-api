# 统一用户中心 OAuth2 登录联调说明

本文档说明如何在本地（docker-compose 部署）接入统一用户中心（`edu.itic-sci.com/uc`）的 OAuth2 登录，测试登录、个人中心、账号安全、操作记录等功能。

> 凭据安全：`USER_CENTER_CLIENT_ID` / `USER_CENTER_CLIENT_SECRET` 是后端应用凭据，**禁止提交到 Git**。`backend/.env` 已被 `.gitignore` 忽略，请勿 `git add -f`。本文档只写占位符，真实值见群通知或向应用管理员索取。

## 〇、临时关闭 / 重新启用登录

后端用 `AUTH_ENABLED` 单变量控制，**不删任何代码**。当前为方便联调已关闭登录，所有受保护接口走 `dev_context()`（本地开发用户 / `local_admin` 角色 / `["*"]` 全权限）。

### 关闭登录（当前状态）

根目录 `.env`：

```dotenv
AUTH_ENABLED=false
```

应用方式（必须 `up -d` 重建容器，`restart` 不会重读 env）：

```bash
docker compose up -d api
```

验证：

```bash
curl -s http://127.0.0.1:8001/api/v1/auth/me | python3 -m json.tool
# 期望：success=true, user.nickname="本地开发用户", roles=[local_admin], permissions=["*"], authEnabled=false
```

前端路由守卫调 `/auth/me` 拿到 profile 后不会跳 `/login`，app 直接可访问；点"使用统一用户中心登录"会调 `/auth/login-url`，后端在 `enabled=false` 时返回前端跳转（不触发 SSO），等同无操作。

### 重新启用登录

前置条件（首次启用时确认，配好就不用再动）：

1. 统一用户中心后台已为测试应用注册回调地址（推荐 `http://<server-ip>:8088/api/v1/auth/callback`，见[第一节](#一oauth2-回调地址选型)）。
2. 根目录 `.env` 中 `USER_CENTER_CLIENT_ID` / `USER_CENTER_CLIENT_SECRET` / `USER_CENTER_REDIRECT_URI` / `AUTH_FRONTEND_URL` 已填。
3. `auth-redis` 容器健康（session 存 Redis）。

操作：

```dotenv
# 根目录 .env
AUTH_ENABLED=true
```

```bash
docker compose up -d api     # 重建容器加载新 env
```

验证：

```bash
# 未登录访问 /auth/me 应 401
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8001/api/v1/auth/me
# 期望: 401

# login-url 应返回 SSO 跳转地址（含 client_id 与 redirect_uri）
curl -s "http://127.0.0.1:8001/api/v1/auth/login-url?next=/overview" | python3 -m json.tool
```

浏览器访问前端，点"使用统一用户中心登录"走完整 OAuth2 流程。

## 一、OAuth2 回调地址选型

OAuth2 授权码流程中，`USER_CENTER_REDIRECT_URI` 是**浏览器**完成 SSO 登录后被重定向回的后端地址（不是 SSO 服务端回拨后端），因此必须满足两个条件：

1. 浏览器能访问到（本机调试即 `http://127.0.0.1:<port>/...`）；
2. 与统一用户中心后台为该应用**注册过的回调 URL 一致**（OAuth2 会严格校验，不匹配会被拒）。

### docker-compose 部署（推荐）

`docker-compose.yml` 映射：

| 服务 | 容器端口 | 宿主端口 | 用途 |
|---|---|---|---|
| `api` | 8000 | **8000 + 8001** | 后端 FastAPI；8000 用于 OAuth 回调（SSO 已注册），8001 保留为常规直连 |
| `web` | 80 | **8088** | 前端 nginx，代理 `/api/` 到 `api:8000` |

> SSO 后台为测试应用注册的回调是 `http://127.0.0.1:8000/api/v1/auth/callback`，所以 `api` 容器必须映射宿主 8000 端口。如果宿主机 8000 被其它服务占用（如本机曾跑过 `semantic_toolkit_final`），先腾出 8000 再启动 tech-kg-api，否则映射会失败。

回调地址用 SSO 注册过的 8000：

```dotenv
USER_CENTER_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/callback
AUTH_FRONTEND_URL=http://127.0.0.1:8088
```

`docker-compose.yml` 中 `api` 服务端口段：

```yaml
ports:
  - "8001:8000"   # 常规直连（Swagger 等）
  - "8000:8000"   # OAuth 回调（SSO 已注册此端口）
```

登录流程：

1. 浏览器打开 `http://127.0.0.1:8088`，点击"使用统一用户中心登录"。
2. 前端调用 `/api/v1/auth/login-url`（经 nginx 代理到 api），后端返回 SSO 登录页 URL，参数含 `redirect_uri=http://127.0.0.1:8000/api/v1/auth/callback`。
3. 浏览器跳转到 SSO 登录页，用户输入统一用户中心账号密码。
4. SSO 把浏览器重定向回 `http://127.0.0.1:8000/api/v1/auth/callback?code=...&state=...`。
5. 后端校验 state、用 code 换 token、写 Redis session、Set-Cookie（域 `127.0.0.1`，`Path=/`），302 跳转到 `AUTH_FRONTEND_URL=http://127.0.0.1:8088`。
6. 浏览器落到前端页，后续 `/api/v1/auth/me` 等请求携带 cookie（cookie 不区分端口，8088 ↔ 8000 同域共享）。

> ⚠️ **回调注册**：如果改用其它端口（如直连 8001 或走 web 代理 8088），必须先去统一用户中心后台为测试应用新增对应回调 URL，否则 SSO 会以 `redirect_uri mismatch` 拒绝。

### 原生开发模式（备选）

不走 docker，按文档原始方案：

```bash
# backend/
uv run uvicorn main:app --host 127.0.0.1 --port 8000

# frontend/
pnpm dev --host 127.0.0.1   # 默认 5173
```

```dotenv
USER_CENTER_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/callback
AUTH_FRONTEND_URL=http://127.0.0.1:5173
```

要求宿主机 8000 端口空闲。

## 二、`.env` 配置（docker 模式写根目录 `.env`）

> ⚠️ **重要**：docker-compose 的 `environment:` 块用 `${VAR:-default}` 插值，插值来源是**项目根目录的 `.env`**（compose 级），不是 `backend/.env`（`env_file` 指令）。`environment:` 块的值会**覆盖** `env_file` 的同名变量。因此 `AUTH_*`、`USER_CENTER_*` 等 docker-compose 在 `environment:` 中显式列出的变量，必须写在**根目录 `.env`** 才能生效。

`backend/.env`（`env_file` 指令）只对**未出现在 `environment:` 块**的变量有效（如 `ZHIPUAI_API_KEY`），原生开发模式下也由 python-dotenv 直接加载。

docker-compose.yml 中的默认值面向生产 `edu.itic-sci.com/bkg_zp`，本地联调必须在根目录 `.env` 覆盖：

```dotenv
# 开启鉴权、用 Redis 存 session
AUTH_ENABLED=true
AUTH_SESSION_BACKEND=redis
AUTH_SESSION_COOKIE=techkg_session

# 本地 HTTP，cookie 不走 secure；SameSite=lax 允许 SSO 顶层跳转回 Set-Cookie
AUTH_COOKIE_SECURE=false
AUTH_COOKIE_SAMESITE=lax
AUTH_COOKIE_PATH=/
AUTH_FRONTEND_URL=http://127.0.0.1:8088

# 统一用户中心 endpoints
USER_CENTER_SSO_LOGIN_URL=https://edu.itic-sci.com/uc/sso/login
USER_CENTER_OAUTH_BASE_URL=https://edu.itic-sci.com/uc/admin-api/system/oauth2
USER_CENTER_ACCOUNT_URL=https://edu.itic-sci.com/uc/admin/login?redirect=/index

# 测试应用凭据（真实值见群通知，禁止提交 Git）
USER_CENTER_CLIENT_ID=<测试应用 Client ID>
USER_CENTER_CLIENT_SECRET=<测试应用 Client Secret>

# 回调地址（见上文选型）
USER_CENTER_REDIRECT_URI=http://127.0.0.1:8000/api/v1/auth/callback

# 新应用未分配授权范围时留空，否则会"授权范围过大"
USER_CENTER_SCOPE=
```

Redis 连接由 `docker-compose.yml` 默认 `REDIS_URL=redis://auth-redis:6379/0` 提供（`auth-redis` 服务），无需在 `.env` 重复设置。

> 原生开发模式（不走 docker）则把上述内容写入 `backend/.env`，由 python-dotenv 直接加载。

## 三、启动顺序

```bash
# 1. 启动所有服务（首次或镜像变更时加 --build）
docker compose up -d --build

# 2. 确认 api / web / auth-redis 健康
docker compose ps

# 3. 改了根目录 .env 后必须重启 api 容器才生效
docker compose up -d api   # 改了端口映射/环境变量用 up -d
docker compose restart api # 只改了 .env 也可用 restart

前端访问：http://127.0.0.1:8088
后端 Swagger：http://127.0.0.1:8001/docs

## 四、常见问题

| 现象 | 排查 |
|---|---|
| 提示缺少 Client ID/Secret | 检查根目录 `.env` 是否填写、`api` 容器是否已 `restart` |
| 提示授权范围过大 | 确认 `USER_CENTER_SCOPE=` 为空 |
| 提示回调地址错误 / redirect_uri mismatch | SSO 后台未注册当前回调地址，按上文"回调注册"提示新增 |
| 登录后仍显示未登录 | 确认 `auth-redis` 容器健康；`AUTH_COOKIE_PATH=/`、`AUTH_COOKIE_SECURE=false`；前后端地址不要混用 `localhost` 和 `127.0.0.1`（cookie 域不同） |
| 修改 `.env` 后没生效 | `docker compose restart api`（`environment:` 在容器启动时插值） |
| 改了 `backend/.env` 但 AUTH/USER_CENTER 变量没生效 | 这些变量在 `docker-compose.yml` 的 `environment:` 块里，必须写在根目录 `.env` 才能覆盖默认值；`backend/.env` 的 `env_file` 会被 `environment:` 覆盖 |
| 浏览器控制台 cookie 被拒 | 确认 `AUTH_COOKIE_SECURE=false`（HTTP 下 Secure cookie 会被浏览器丢弃） |

## 五、共享测试应用说明

大家不需要分别创建 OAuth 应用，可以共用现有的开发联调应用。Client ID 和 Client Secret 是**后端应用凭证**，不是个人账号；每位同学仍然使用自己的统一用户中心账号登录。

凭据获取：见项目内部群通知，或向应用管理员索取。**不要把凭据发到公开群聊，也不要提交到 Git。**

## 六、相关代码位置

- 后端路由：`backend/biz/handler/auth.py`（prefix `/auth`，挂在 `/api/v1`）
- 配置读取：`backend/config/auth.py` 与 `backend/biz/dependencies/auth.py`
- 前端 API：`frontend/src/api/auth.ts`、`frontend/src/stores/auth.ts`
- 前端登录页：`frontend/src/views/auth/LoginView.vue`
