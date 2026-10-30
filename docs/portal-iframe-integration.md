# 统一门户 iframe 子系统接入

本项目按《国科信项目统一门户 iframe 集成技术方案》作为业务子系统接入统一门户，
同时保留独立访问能力。门户嵌入时不再渲染本系统顶部导航、左侧菜单、登录入口、
用户信息区、重复面包屑和页脚。

内嵌模式保留独立系统的三层视觉结构：页面底色、白色 48% 透明度的
第二层底板（含白色边框和背景模糊）、白色 80% 透明度的功能工作区。
第二层显示当前页面标题，不增加可点击导航；总览沿用独立页面的内部滚动规则。
门户现有导航及九大业务菜单无需因此调整。

电脑布局下，业务页的图谱与结果详情、开发者接口页的请求与响应说明
保持左右两列，不再因页面宽度不超过 1280px 或工作区不超过 1100px 而变成上下单列。
此规则同时适用于独立访问和内嵌访问；不超过 767px 的窄屏仍使用单列布局。

门户右上角头像由门户前端渲染，不属于本仓库的 iframe 内容。
目前线上门户使用 `.volcano-user-trigger` / `.volcano-user-avatar` 显示邮箱首字符；
如果要与独立系统的蓝色用户头像一致，需要在门户源码中修改对应组件，
并保留门户原有账号与退出行为，不能靠子系统增加第二个用户入口替代。

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

- `page.ready`：子应用首次挂载并注册消息监听器后发送一次，门户随后下发初始深链。
- `page.setTitle`：页面标题变化时同步门户标题。
- `loading.show` / `loading.hide`：门户全局加载状态。
- `route.change`：使用 `{ code, subPath }` 双向同步路由；`code` 是门户菜单编码，`subPath` 是子应用完整路由（含查询参数），不是部署前缀或完整 URL。
- `menu.navigate`：子系统请求门户切换菜单。
- `session_expired`：API 返回 401 时通知门户处理登录过期。
- `NO_PERMISSION`：API 返回 403 时通知门户展示无权限页。
- `LOGOUT` / `user.logout`：接收门户退出命令并清理本地会话。

消息只接受来自 `window.parent` 且命中来源白名单的事件；发送时始终指定明确
`targetOrigin`，不会使用 `*`。

当前门户菜单编码与路由映射维护在 `frontend/src/portal/portalRoutes.ts`，例如
`/graph-build` 对应 `graph_build`，`/manual-review` 对应 `manual_review`。
同一菜单下的详情路由继续使用所属菜单编码。门户跨菜单导航会按菜单配置重载 iframe，
子应用在首次 `page.ready` 后接收下行 `route.change` 恢复深链；恢复期间不回发导航，
避免消息循环。后续本地导航发送 `route.change`，不重复发送 `page.ready`。
门户调整菜单编码时，应同步更新映射并验证总览内部入口、详情页刷新和前进/后退。

## 九大业务的内容区加载

九大业务使用 iframe 内的浅色骨架加载界面，不要求门户在初始化期间遮挡顶栏和左侧菜单。
index.html 直接包含骨架，并在主应用 JS 之前加载独立的 startup-shell.v1.js；
该脚本不依赖 Vue、路由或身份接口。

加载时序：

1. 文档骨架就位后，立即发送 loading.hide，请求门户释放全局遮罩。
2. 运行时配置加载后，按既有来源白名单和明确的 targetOrigin 再通知一次，支持跨源部署。
3. 身份、空间和页面模块继续在 iframe 内加载。此时不会提前发送 page.ready，也不会跳过鉴权。
4. 初始路由就绪后才发送一次 page.ready，保留门户下发深链的原有时序。
5. 后续路由切换只显示子应用内容区骨架；查询结果仍由业务页面各自管理加载状态。
6. 主 JS/路由模块失败时显示内容区错误和重试；持续加载超过 20 秒也会提供重试。
   慢请求仍可自然完成，不因超时提示授予权限或恢复旧账号状态。
7. 页面渲染错误可在当前业务内重试；切到其他业务会清除上一页面的错误。

门户需要配合的行为：

- 对当前 iframe、受信来源发送的 loading.hide，允许在 page.ready 之前释放全局遮罩。
  loading.hide 只代表由内容区接管加载提示，不代表用户已登录或业务数据已就绪。
- 九大业务菜单切换时保留门户顶栏和侧边栏可用；优先复用同一 iframe，用 route.change 切页。
  本仓库没有门户容器源码，不能通过修改子应用的 CSS 或直接操作父 DOM 来实现门户菜单复用。
- iframe 文档或独立启动脚本本身加载失败时，子应用无法发消息。门户必须有自己的失败和超时
  兜底，在右侧提供重试入口，不能无限等待 iframe.onload 或 page.ready 并锁住整个门户。
- 骨架脚本使用版本化文件名；更新此脚本时同步升级文件名和 HTML 引用，避免 7 天静态缓存
  保留旧的加载协议实现。

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
USER_CENTER_PORTAL_TOKEN_COOKIE=portal_access_token
USER_CENTER_REDIRECT_URI=https://edu.itic-sci.com/bkg_zp/api/v1/auth/callback
```

统一门户写入的 `portal_access_token` Cookie 必须能随 `/bkg_zp` 后端请求发送。推荐门户、
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
4. 首次进入子应用，门户收到一次 `page.ready`；子应用内部切换路由时收到 `{ code, subPath }` 的 `route.change`，目标菜单与内容一致，门户下发的深链能够恢复且不产生回发循环。
5. API 返回 401 时门户收到 `session_expired`；返回 403 时收到 `NO_PERMISSION`。
6. 门户发送 `LOGOUT` 后，本系统清除本地会话并显示退出状态。
7. 非白名单来源的消息被忽略，消息发送目标不使用 `*`。
8. 响应头只允许指定门户通过 iframe 嵌入。
9. 页面宽高适应门户内容区，子系统内部滚动，不重复实现门户主导航。
10. 人为延迟主 JS、身份接口或空间接口时，门户已收到早期 loading.hide，左侧菜单可操作，右侧显示骨架；此时还没有 page.ready。
11. 主 JS 404、路由模块失败或启动超时只在内容区显示重试，不能永久遮挡门户。
12. 门户对文档和启动脚本无法加载的情况也有独立超时兜底；不要把 iframe.onload 当作鉴权成功或页面就绪。
