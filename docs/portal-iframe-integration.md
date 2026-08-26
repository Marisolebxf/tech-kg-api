# 统一门户 iframe 子系统接入

本项目按《国科信项目统一门户 iframe 集成技术方案》作为业务子系统接入统一门户，
同时保留独立访问能力。门户嵌入时不再渲染本系统顶部导航、左侧菜单、登录入口、
用户信息区、重复面包屑和页脚。

## 门户菜单配置

建议在统一用户中心登记叶子菜单：

```json
{
  "id": "tech-kg-overview",
  "parentId": "tech-kg-api",
  "name": "亿级知识图谱平台",
  "code": "tech-kg-overview",
  "type": "menu",
  "openType": "iframe",
  "systemCode": "tech-kg-api",
  "permission": "tech-kg:overview:view",
  "url": "https://edu.itic-sci.com/bkg_zp/#/overview?embedded=1",
  "visible": true,
  "enabled": true,
  "keepAlive": false
}
```

其它页面可以将 `/overview` 替换为对应 hash 路由。长期 Token 不得拼接到 URL。

## 通信协议

子系统发送统一消息结构：

```js
{
  protocol: 'iframe-bridge',
  version: '1.0',
  id: 'msg_1719700000000_1',
  action: 'page.ready',
  data: { source: 'tech-kg-api', title: '平台总览' }
}
```

当前实现支持：

- `page.ready`：路由页面完成渲染后强制通知门户。
- `loading.show` / `loading.hide`：门户全局加载状态。
- `route.change`：将子系统 hash 路由同步给门户。
- `menu.navigate`：子系统请求门户切换菜单。
- `session_expired`：API 返回 401 时通知门户处理登录过期。
- `NO_PERMISSION`：API 返回 403 时通知门户展示无权限页。
- `LOGOUT` / `user.logout`：接收门户退出命令并清理本地会话。

消息只接受来自 `window.parent` 且命中来源白名单的事件；发送时始终指定明确
`targetOrigin`，不会使用 `*`。

## 构建配置

```dotenv
VITE_BASE=/bkg_zp/
VITE_API_BASE=/bkg_zp/api
VITE_AUTH_ENABLED=true
VITE_PORTAL_EMBEDDED_DEFAULT=false
VITE_PORTAL_ALLOWED_ORIGINS=https://edu.itic-sci.com
VITE_PORTAL_TARGET_ORIGIN=https://edu.itic-sci.com
VITE_PORTAL_SOURCE=tech-kg-api
```

多个门户环境使用英文逗号分隔 `VITE_PORTAL_ALLOWED_ORIGINS`。测试和生产环境必须
分别构建，禁止将无法确认的来源加入白名单。

后端生产配置：

```dotenv
AUTH_ENABLED=true
AUTH_SESSION_BACKEND=redis
AUTH_FRONTEND_URL=https://edu.itic-sci.com/bkg_zp
AUTH_COOKIE_SECURE=true
AUTH_COOKIE_SAMESITE=lax
AUTH_COOKIE_PATH=/bkg_zp
USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED=true
USER_CENTER_PORTAL_TOKEN_COOKIE=access_token
USER_CENTER_REDIRECT_URI=https://edu.itic-sci.com/bkg_zp/api/v1/auth/callback
```

统一门户写入的 `access_token` Cookie 必须能随 `/bkg_zp` 后端请求发送。推荐门户、
统一用户中心和子系统部署在同一主域名下，并由部署方确认 Cookie 的 `Domain`、
`Path`、`Secure` 和 `SameSite`。本系统后端校验该 Token 后创建 HttpOnly Redis 会话；
Vue 不读取、不持久化统一用户中心 Token。

## iframe 安全

容器内 Nginx 默认返回：

```http
Content-Security-Policy: frame-ancestors 'self' https://edu.itic-sci.com
```

如果外层网关覆盖响应头，必须在外层网关配置等价规则。不得设置
`X-Frame-Options: DENY` 或 `ALLOWALL`。若门户与子系统不同源，不能使用
`X-Frame-Options: SAMEORIGIN`。

## 联调验收

1. 独立打开系统，顶部导航和左侧菜单正常显示。
2. 从统一门户打开 `embedded=1` URL，子系统自身导航和登录入口不显示。
3. 已登录门户用户进入子系统时不重复登录。
4. 每次进入或切换子系统路由，门户收到 `page.ready` 和 `route.change`。
5. API 返回 401 时门户收到 `session_expired`；返回 403 时收到 `NO_PERMISSION`。
6. 门户发送 `LOGOUT` 后，本系统清除本地会话并显示退出状态。
7. 非白名单来源的消息被忽略，消息发送目标不使用 `*`。
8. 响应头只允许指定门户通过 iframe 嵌入。
9. 页面宽高适应门户内容区，子系统内部滚动，不重复实现门户主导航。
10. 门户使用 `iframe onload + page.ready + 超时` 判断加载失败并提供重新加载入口。
