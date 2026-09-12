# bkg_zp 登录续期与退出恢复

适用对象：原系统 `https://edu.itic-sci.com/bkg_zp/`，目标分支 `main`。
本补丁不改变页面布局、样式、按钮、文案、角色权限或既有超时时长，不包含 `kgetl / bkg_zpt` 的权限改动。

## 修复后的行为

- 成功的本地会话请求同步延长 Redis TTL 和浏览器 HttpOnly 会话 Cookie，包括直接返回 `Response` 的业务查询；空闲超过 `AUTH_SESSION_TTL_SECONDS` 后仍会失效。
- 普通访问只延长 TTL，不回写旧令牌。刷新只更新仍存在的会话，退出原子移除会话，避免在途续期或刷新重新创建已退出的会话。同一应用进程的并发刷新合并处理。
- `401` 清除前端旧身份并只触发一次登录恢复；独立入口保留原页面，iframe 通知门户。登录探测、登录地址和退出请求不引发恢复循环；`403` 保留原权限处理。
- 登录按钮在导航取消、错误和浏览器返回后恢复可点击；晚到的身份响应不会撤销退出或覆盖新的登录状态。
- 退出不要求会话仍有效，不刷新令牌，也不从门户 Cookie 创建新会话。存储故障仍返回 `503`，但响应会清理本地 Cookie；前端完成当前页面的退出状态。
- OAuth 登录得到的本系统令牌仍按原接口撤销；门户共享令牌不由本系统撤销。`remoteRevoked=false` 表示未完成远端令牌撤销，不代表本地退出失败。
- 本系统设置与会话相同作用域的 HttpOnly `techkg_session_portal_logout` 标记（会话 Cookie 名可配置）。只记录门户令牌摘要，阻止该旧令牌立即静默登录；新门户令牌可正常登录，明确 OAuth 登录成功后清除标记。不会删除或改写门户共享 Cookie。
- 认证接口及重定向、错误响应使用 `Cache-Control: no-store`。

现存 Redis 会话无需迁移：新字段 `token_source` 记录令牌来源；旧记录有刷新令牌时按 OAuth 处理，来源无法确认时仅执行本地退出，避免误撤销门户共享令牌。

## 部署核对

部署前读取运行中 API 容器的下列非敏感设置，以实际值为准：

```text
AUTH_ENABLED
AUTH_SESSION_BACKEND
AUTH_SESSION_TTL_SECONDS
AUTH_SESSION_COOKIE
AUTH_COOKIE_PATH
AUTH_COOKIE_SECURE
AUTH_COOKIE_SAMESITE
AUTH_FRONTEND_URL
USER_CENTER_REDIRECT_URI
USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED
USER_CENTER_PORTAL_TOKEN_COOKIE
```

仓库主 Compose 的会话默认值为 `1800` 秒，但 `.env` 可覆盖；本次未取得运行中容器的实际 TTL，不据此断言线上为 30 分钟。保持既有超时策略，不通过本补丁延长授权期限。

本系统前缀和回调应分别对应 `/bkg_zp`、`https://edu.itic-sci.com/bkg_zp/api/v1/auth/callback`。会话与退出标记沿用实际配置的 Cookie Path，不做全域 Cookie 清理。只读探测发现线上 OAuth state Cookie 使用 `Path=/`，与 Compose 默认 `/bkg_zp` 不同；上线前需核对会话 Cookie 的真实作用域，涉及旧 Cookie 迁移时另行制定精确清理范围，避免影响 `/bkg_zpt` 和门户。

本次对同一进程的刷新做合并，默认 Compose 的单 Uvicorn 进程可覆盖。若实际环境使用多个 API worker 或副本，需先确认用户中心的刷新令牌并发语义，并验证跨进程刷新；不能把进程内合并当作分布式锁。

重新构建并发布本系统 API 与前端后生效。此变更交付为独立 PR，不自动合并、部署、修改服务器环境变量或真实用户权限。

## 验证范围

自动验证在一次性 Docker 容器执行，使用模拟用户中心、内存会话和隔离临时目录，不访问真实用户中心、业务数据库或现有运行容器。

本次交付验证：前端 12 个文件共 195 项测试通过（排除需要专用环境的 `review-full-integration.spec.ts`），前端类型检查和 Vite 构建通过；后端原有与新增认证回归共 51 项通过，修改文件的 Ruff lint 与格式检查通过。

回归重点：浏览器 Cookie 与 Redis 滑动续期、真正空闲超时、显式 Response、过期会话退出、门户共享令牌保留及旧令牌静默登录抑制、OAuth 重登、存储失败清 Cookie、退出与刷新并发、401 去重、403 语义、晚到请求、登录按钮恢复。

部署后由指定测试账号验证：独立入口活跃访问跨过原到期点、空闲后重新登录、主动退出后立即重新登录，以及统一门户进入/退出/重新进入。实际用户中心登录与门户联调尚未执行，自动测试不代替线上验收。
