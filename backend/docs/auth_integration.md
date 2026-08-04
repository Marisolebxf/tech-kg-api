# 统一用户中心 OAuth2 接入

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

## API

- `GET /api/v1/auth/login-url`：生成登录地址和一次性 state。
- `GET /api/v1/auth/callback`：OAuth2 授权码回调（不在 Swagger 展示）。
- `GET /api/v1/auth/me`：当前用户、角色、机构和操作权限。
- `GET /api/v1/auth/permissions`：统一用户中心完整权限结构。
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
USER_CENTER_CLIENT_ID=<统一用户中心分配的客户端编号>
USER_CENTER_CLIENT_SECRET=<仅保存在服务端的客户端密钥>
USER_CENTER_REDIRECT_URI=https://edu.itic-sci.com/bkg_zp/api/v1/auth/callback
USER_CENTER_SSO_LOGIN_URL=https://edu.itic-sci.com/uc/sso/login
USER_CENTER_OAUTH_BASE_URL=https://edu.itic-sci.com/uc/admin-api/system/oauth2
```

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
