# kgetl 管理员权限启用说明

本次仅调整 `kgetl` 的鉴权、已有菜单显隐和成员数据处理。所有现有页面布局、样式、按钮和文案保持不变；不改变 `main` 分支或已部署的 `bkg_zp`。

## 身份与访问范围

有效管理员 = 当前门户管理员 OR 本地授权管理员（含已有首批管理员配置）。其他已登录用户为普通用户。

| 现有分组 | 管理员 | 普通用户 |
| --- | --- | --- |
| 工作台 / 平台总览 | 可访问 | 默认进入图谱查询 |
| 图谱建设与治理（Schema、构建、审核及详情） | 可访问 | 隐藏入口，页面和接口拒绝访问 |
| 平台管理 / 配置管理 | 可访问 | 隐藏入口，页面和接口拒绝访问 |
| 查询与服务（综合查询、实体列表、九大业务） | 可访问 | 可访问 |

个人中心、账号安全、个人操作记录继续开放给已登录用户。工作台暂按管理员专用；后续若开放，应一起调整菜单显隐、`/overview` 路由和 `platform_overview_router` 接口分组。

新普通用户无需进入管理页绑定空间即可查询部署配置 `TRS_GRAPH_SPACE` 的默认业务图谱；已有其他空间绑定继续有效。默认空间共享只读访问不写入绑定记录，不赋予创建空间或控制台写入权限，其他未绑定空间仍拒绝访问。

门户角色来自 v2.4 2.5 `POST /open-api/system/user/get-by-token`。请求由后端携带 Basic Auth 和 HMAC-SHA256 签名，公共参数 `clientId`、`nonce`、`timestamp` 按 ASCII 字典序拼接，业务 token 不参与签名。只接受身份 ID 与 OAuth 登录用户一致、状态正常、`gkxUser.role` 为整数 `1` 的结果；`userType`、角色名称、机构角色、前端传入的字段均不作为管理员依据。`gkxUser` 为空表示没有原官网管理员身份。

同一 token 的门户身份默认缓存 60 秒，命中不延长缓存；OAuth、门户 Cookie、Bearer 三条登录路径都遵循同一规则。缓存到期后下一次请求重新查询，接口失败或身份不匹配时不会沿用过期管理员身份。前端每次路由导航重新取得有效身份，本地撤权在下一次受保护请求生效。

已有 `kg_platform_user_role.platform_admin` 为本地授权，保持原样。`portal_admin_snapshot` 仅记录最近一次验证的门户身份，用于成员列表展示，绝不用于接口授权或“最后一位管理员”保护判断；不需要新增数据库表。离线成员显示最近访问时的门户身份，待其下一次验证更新。切勿把该展示快照当作实时权限凭证。

成员管理原按钮只授予/撤销本地权限。撤销本地授权后仍有门户身份，返回的有效 `isAdmin` 仍为 `true`；只有门户身份时，撤销请求返回 409，提示去门户撤销。成员页以接口结果为准再刷新列表，真实认证开启时不使用示例成员。门户管理员不会因首次登录而自动获得永久本地授权。

不改变现有按钮语义：普通成员可在此设为本地管理员；已经显示为门户管理员的成员，页面不提供额外叠加本地授权的操作。若其门户身份已取消，待下次登录更新身份后，可再通过原按钮授予本地管理员。

OAuth 成功和失败回跳均使用 `kgetl` 当前的 history 路径（例如 `/bkg_zpt/schema`、`/bkg_zpt/login?error=...`），不再生成旧式 `/#/` 地址；保留原目标的查询参数和锚点。

## 启用配置

当前开发环境可以继续使用根 `.env` 的 `AUTH_ENABLED=false`。免登录模式下所有人共用开发管理员，不能用它验证两种真实身份。以下值在具备真实账号和回调配置后一起启用；本次代码提交不直接改服务器配置。

```dotenv
AUTH_ENABLED=true
AUTH_SESSION_BACKEND=redis
AUTH_FRONTEND_URL=https://edu.itic-sci.com/bkg_zpt
USER_CENTER_REDIRECT_URI=https://edu.itic-sci.com/bkg_zpt/api/v1/auth/callback
USER_CENTER_CLIENT_ID=<现有客户端 ID>
USER_CENTER_CLIENT_SECRET=<现有客户端密钥>
USER_CENTER_OPEN_API_BASE_URL=https://edu.itic-sci.com/uc/open-api/system
USER_CENTER_PORTAL_ADMIN_ENABLED=true
USER_CENTER_PORTAL_ROLE_CACHE_TTL_SECONDS=60
PLATFORM_BOOTSTRAP_FIRST_ADMIN=false
PLATFORM_DEV_FIRST_USER_ADMIN=false
ADMIN_EXAMPLE_FALLBACK=false
```

`docker-compose.dev2.yml` 从根 `.env` 读取 `AUTH_ENABLED`，并向前后端传递同一个值。已有 `.env` 会覆盖 Compose 默认值，修改默认值本身不会让已部署环境自动开启登录。`PLATFORM_INITIAL_ADMIN_USER_IDS` 中的既有授权继续有效，无需为了门户继承重新配置；是否保留由交付管理员决定，不自动清除。

统一用户中心需允许 `bkg_zpt` 的生产回调（与 `bkg_zp` 不同）及该客户端访问签名接口。真实联调须确认已知门户管理员确实返回 `gkxUser.role=1`，普通用户返回 `0` 或无关联账号；文档将该字段称为“原官网角色”。如果门户的管理员由另一套应用角色表示，须先确认映射，不能按名称猜测授予权限。

加载新代码和环境变量需重建相关容器，单独 `restart` 不会重读 Compose 环境变量：

```bash
docker compose -f docker-compose.dev2.yml up -d --build api-dev2 web-dev2 web-dev2-root
```

## 验证

自动测试覆盖签名、OAuth/Cookie/Bearer 身份获取、身份不匹配、缓存到期撤权、管理员来源叠加、本地授权撤销、普通用户路由与菜单及管理接口拒绝访问。测试使用模拟用户中心和隔离数据库，不操作真实用户角色。

交付前还需以真实门户管理员、普通用户分别登录 `bkg_zpt`，确认菜单、直接 URL、管理 API 和查询服务；再检查本地授权与门户撤权后的结果。未完成真实账号联调前，不能把自动测试当成线上权限已生效。
