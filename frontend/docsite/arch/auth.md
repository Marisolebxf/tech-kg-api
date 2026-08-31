# 认证与权限

> 来源：`CLAUDE.md` Auth 子系统节 · `backend/docs/auth_integration.md` · `backend/config/auth.py`

`AUTH_ENABLED` 是总开关。关闭时 `require_authenticated_user` 返回开发上下文、admin 检查直接放行——本地开发与 CI 常用。开启后三条登录路径共存（`biz/dependencies/auth.py`）：

## 三条登录路径

| 路径 | 机制 | 场景 |
|---|---|---|
| **Bearer token** | `Authorization: Bearer <token>`，经 `application.resolve_bearer` 解析 | 第三方 API 调用方 |
| **Session cookie** | `techkg_session`（名来自 `AUTH_SESSION_COOKIE`），Redis 存储（`AUTH_SESSION_BACKEND=redis`） | 本地登录态 |
| **门户 cookie SSO** | 门户 `access_token` cookie 经统一用户中心 OAuth2 客户端（`infra/user_center.py`）换取本地 session；由 `USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED=true` 开启 | **生产默认**，应用嵌入统一门户 iframe |

## admin 检查

admin 路由在 `require_authenticated_user` 之上叠加 `require_platform_admin`（检查平台角色）。首次部署的管理员引导：`PLATFORM_BOOTSTRAP_FIRST_ADMIN` + `PLATFORM_INITIAL_ADMIN_USER_IDS`。

## 配置

认证配置集中在 `config/auth.py`（`AuthSettings`）；审计日志写 Redis（带 TTL）。

## 前端配合

- `stores/auth.ts` 管理认证状态；嵌入门户 iframe 时 `portal/iframeBridge.ts` 把门户登录态桥接进应用；
- 前端构建期开关 `VITE_AUTH_ENABLED`、`VITE_PORTAL_*` 系列（见[环境变量](/deploy/env)）；
- 路由守卫（`router/index.ts` beforeEach）：非 public 路由先 `loadCurrentUser`，未登录跳登录页。
