# 统一用户中心 OAuth2 v2.3.1 接入

本系统采用后端托管会话（BFF）模式接入统一用户中心。Vue 前端只拿到
HttpOnly Session Cookie；`client_secret`、统一用户中心 `access_token` 和
`refresh_token` 始终保存在 FastAPI/Redis 侧，不写入浏览器存储。

## 登录流程

1. 前端调用 `GET /api/v1/auth/login-url?next=/overview`。
2. 后端生成一次性 `state`，写入 Redis 和当前浏览器的短期 HttpOnly Cookie，
   并返回统一用户中心 SSO 登录地址。
3. 用户中心授权后回调 `GET /api/v1/auth/callback?code=...&state=...`。
4. FastAPI 使用 Basic Auth 调用 `/token` 换取 token，再调用
   `/v1/get-permission-info` 获取用户、角色、菜单和权限。
5. FastAPI 将会话写入 Redis、设置 HttpOnly Cookie，然后跳回前端 hash 路由。
6. 浏览器业务请求使用 Session Cookie；其他厂商调用 API 时可以使用
   `Authorization: Bearer <access_token>`。

## 门户共享登录态（v2.1）

v2.1 新增了同一主域名下由门户 Cookie 共享 `portal_access_token` 的流程。本系统采用
“后端兑换本地会话”的兼容方式：FastAPI 从请求 Cookie 读取门户 token，调用统一
用户中心 `/check-token` 与 `/v1/get-permission-info` 完成校验，然后创建 Redis
会话并下发本系统 HttpOnly Session Cookie。token 不写入 localStorage，也不由 Vue
主动读取。门户不会提供 `refresh_token`，因此“同步最新权限”会重新执行 token 校验
和权限查询，并更新同一个 Redis 会话。

该能力默认关闭，只有确认门户实际 Cookie 名称、Domain、Path、SameSite 和 Secure
属性允许 `/bkg_zp` 请求携带后才开启：

```dotenv
USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED=true
USER_CENTER_PORTAL_TOKEN_COOKIE=portal_access_token
```

未携带门户 Cookie 或校验失败时仍返回 401，前端会继续使用标准 OAuth2 授权码登录。

## API

- `GET /api/v1/auth/login-url`：生成登录地址和一次性 state。
- `GET /api/v1/auth/callback`：OAuth2 授权码回调（不在 Swagger 展示）。
- `GET /api/v1/auth/me`：当前用户、角色、机构和操作权限。
- `GET /api/v1/auth/permissions`：统一用户中心完整权限结构。
- `GET /api/v1/auth/security`：账号绑定、认证方式、会话安全和统一用户中心管理入口。
- `GET /api/v1/auth/operation-logs`：当前用户的登录、会话刷新和退出操作记录。
- `POST /api/v1/auth/refresh`：刷新当前浏览器会话的 token。
- `POST /api/v1/auth/logout`：撤销统一用户中心 token 并清除本地会话。

除健康检查、Swagger/OpenAPI 和上述登录入口外，`/api/v1` 业务路由统一要求
Session Cookie 或 Bearer Token。`/internal/operators/reload` 继续使用独立的
`X-Operator-Reload-Token`，供内部工作流回调。

## 环境变量

生产环境至少需要配置：

```dotenv
AUTH_ENABLED=true
AUTH_SESSION_BACKEND=redis
REDIS_URL=redis://auth-redis:6379/0
AUTH_FRONTEND_URL=https://edu.itic-sci.com/bkg_zp
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_PATH=/bkg_zp
AUTH_AUDIT_TTL_SECONDS=7776000
AUTH_AUDIT_MAX_ITEMS=200
USER_CENTER_CLIENT_ID=<统一用户中心分配的客户端编号>
USER_CENTER_CLIENT_SECRET=<仅保存在服务端的客户端密钥>
USER_CENTER_REDIRECT_URI=https://edu.itic-sci.com/bkg_zp/api/v1/auth/callback
USER_CENTER_SSO_LOGIN_URL=https://edu.itic-sci.com/uc/sso/login
USER_CENTER_OAUTH_BASE_URL=https://edu.itic-sci.com/uc/admin-api/system/oauth2
USER_CENTER_ACCOUNT_URL=https://edu.itic-sci.com/uc/admin/login?redirect=/index
USER_CENTER_SCOPE=
USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED=true
USER_CENTER_PORTAL_TOKEN_COOKIE=portal_access_token
```

`USER_CENTER_SCOPE` 默认留空。只有统一用户中心已明确给当前应用分配了授权范围时才填写；
否则新建应用会在授权页提示“授权范围过大”。

如果网关保留 `/bkg_zp` 前缀，前端构建时设置：

```dotenv
VITE_BASE=/bkg_zp/
VITE_API_BASE=/bkg_zp/api
```

如果网关已经去掉前缀，则保留默认的 `VITE_BASE=./` 和
`VITE_API_BASE=/api`。最终以网关实际转发规则为准。

本地尚未获得 OAuth 客户端凭证时，可以在 `backend/.env` 设置：

```dotenv
AUTH_ENABLED=false
AUTH_SESSION_BACKEND=memory
```

此模式会返回明确标记为本地开发用户的资料，不连接 Redis 和用户中心；生产环境
不得关闭鉴权。

## 安全约束

- `state` 同时校验 Redis 一次性记录与浏览器短期 Cookie，默认 5 分钟过期，
  防止登录 CSRF 和跨浏览器复用。
- Session ID 使用加密安全随机数生成，Cookie 开启 HttpOnly。
- Bearer Token 缓存键只保存 SHA-256 摘要，不把明文 token 放入 Redis key。
- 权限缓存 TTL 不超过 token 剩余有效期。
- 回跳路径只接受站内绝对路径，拒绝 `//example.com` 一类开放重定向。
- 操作记录按用户隔离保存在 Redis，默认保留 90 天、最多 200 条；仅记录操作类型、结果、IP、User-Agent 和时间，不记录密码、Token 或 Client Secret。
- v2.1 权限菜单新增 `linkType`（0=内部链接、1=外部链接），后端会结构化返回菜单及角色—菜单映射；前端展示链接类型但不会把外部地址直接作为未校验的站内路由执行。
- v2.1 仍未提供修改密码接口，因此账号资料和密码修改只跳转统一用户中心，本平台不代理或保存密码。
- v2.3.1 的 `/open-api/system` 机构/用户查询、菜单权限资源、按 Token 获取用户信息、令牌交换和机构角色分配并非本平台标准 OAuth2 登录与 API 鉴权的必需链路，当前任务不调用这些高权限接口。
- v2.3.1 仅调整了 `2.2 分页获取用户列表` 的筛选参数；本平台没有调用该接口，因此此次文档更新不影响现有 OAuth2 登录、Redis 会话或 FastAPI 鉴权实现。
