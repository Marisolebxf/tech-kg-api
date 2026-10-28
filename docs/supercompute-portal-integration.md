# 超算门户接入与部署交接

本次接入使用远程 kgetl 分支。应用已由使用方创建，名称为“亿级科技知识图谱引擎-超算环境”。
门户展示位置为“国科信 → AI战略咨询 → 本应用目录”，与“超大规模智算引擎”并列。
代码通过 PR 交付，由部署同事合并、部署；菜单配置在服务可用后进行。

## 接入约定

按使用方转达的门户方最新要求，统一用户中心中的应用“访问地址”登记完整回调地址：
`http://183.62.232.63/bkg_zp/api/v1/auth/callback`。不要改成业务首页。
这一登记要求尚不能确定实际登录协议；门户是否访问此地址、携带什么参数、是否先经过本应用发起授权，仍需完整链路联调确认。

当前模板设置 AUTH_LOGIN_MODE=portal，使用门户共享 Cookie 登录。独立访问时通过登录弹窗恢复原页面；上线验收须覆盖清空 Cookie 后的首次登录：

1. 用户在门户完成登录，门户把共享登录凭据写入同站 Cookie。
2. 门户菜单打开 /bkg_zp/overview?embedded=1 等子系统页面。
3. 浏览器把 Cookie 随 /bkg_zp/api/ 请求送到后端。后端向用户中心验证凭据与用户身份，创建本地 HttpOnly 会话，并继续执行既有业务/空间权限检查。
4. 用户独立打开子系统且未登录时，点击“进入平台”会在新窗口打开 USER_CENTER_PORTAL_LOGIN_URL 指定的门户入口，原页面保留登录前的站内地址，并每隔约 2 秒向自己的 `/api/v1/auth/me` 检查身份。门户写入共享 Cookie 后，后端验证用户成功，原页面自动进入目标页面并尝试关闭登录窗口。
5. 门户模式跟随共享 Cookie 的删除和变更：缺失时拒绝旧会话，变更时校验新身份。子系统主动退出只结束自己的会话，不撤销门户供其他应用使用的共享凭据。

portal 模式不让子系统自行请求 OAuth 授权码，/api/v1/auth/callback 在该模式返回 404。
如果门户实际访问登记的 callback，此模式不能完成回跳，应先确认双方交接协议再部署对应模式。
oauth 模式只处理本应用发起且通过一次性 state 校验的授权码回跳；不能为了接受门户跳转而取消 state 校验。
现有智谱环境不设置 AUTH_LOGIN_MODE 时仍采用 oauth 模式，原回调流程和混合登录行为保持兼容。
Client ID/Secret 仍用于后端验证门户令牌和查询用户信息，不能省略，也不能注入前端。

**门户自动返回原子页面的参数尚未确认。** 默认入口 /portal/ 不附加猜测的 redirect、callback、client_id 等参数。
独立访问的自动进入由保留的子系统页面检测共享登录态实现，不依赖门户回跳，也不使用本系统 `/api/v1/auth/callback`。
登录窗口在点击事件内同步打开，避免异步请求导致弹窗被拦截；若浏览器拦截，原页提示允许弹窗后重试。
等待可取消，5 分钟超时，离开页面停止检查；网络故障时延迟重试，切回原页时立即复查。
门户隔离策略可能断开窗口引用，使弹窗无法自动关闭，此时用户可手动关闭门户窗口；不以窗口关闭或任意 `postMessage` 作为登录成功依据。
门户嵌入场景继续发送既有 session_expired 消息，由门户完成重新登录；本系统不会在 iframe 内另开一套 SSO。

前后端需要一起部署：新增只读 `/api/v1/auth/login-config` 返回 `mode`，预加载不会生成 OAuth state 或清除主动退出标记；用户点击后的 `/api/v1/auth/login-url` 返回 `mode=portal` 并允许恢复共享 Cookie 检查。旧 OAuth 模式继续原来的整页跳转和 state 校验。
新前端遇到旧后端的 `login-config` 404 时保留旧整页跳转行为，因此仅部署前端不能完成本修复。
复用对方 Client 时保留对方登记的回调，本系统回调在 portal 模式继续返回 404；Client ID/Secret 只保留在后端。

## 部署配置

临时公共入口是 http://183.62.232.63，应用路径是 /bkg_zp。IP 放在部署配置里，不写进业务代码默认值。

配置模板：[deploy/supercompute.env.example](../deploy/supercompute.env.example)。
复制到未跟踪的 deploy/supercompute.env，填入该超算应用的 Client ID/Secret。
不要覆盖同事已有数据库、图服务、Redis、Temporal、S3 和业务/空间权限配置。

| 配置 | 本次值/作用 |
| --- | --- |
| PUBLIC_BASE_URL | http://183.62.232.63；只包含协议、主机及可选端口，末尾不加 / |
| APP_BASE | /bkg_zp；前后端保持一致，末尾不加 / |
| AUTH_LOGIN_MODE | 当前模板为 portal；首次登录实际链路未验收，部署前确认模式 |
| AUTH_ENABLED | true，前后端都启用 |
| USER_CENTER_PORTAL_LOGIN_URL | /portal/；以门户实际可用入口为准 |
| USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED | true |
| USER_CENTER_PORTAL_TOKEN_COOKIE | 模板沿用 access_token；联调核对实际名称和 Cookie Path |
| USER_CENTER_CLIENT_ID / USER_CENTER_CLIENT_SECRET | 本次超算应用的凭据，仅后端使用 |
| AUTH_COOKIE_SECURE | 临时 HTTP 为 false；切换 HTTPS 后为 true |
| AUTH_SESSION_BACKEND / REDIS_URL | redis，使用现有可达的会话 Redis |
| PORTAL_ALLOWED_ORIGINS / PORTAL_TARGET_ORIGIN | 前端都填 /，表示当前网站来源 |

原代码已有运行时前端配置：APP_BASE 推导接口前缀，页面在同一来源下访问接口；
PORTAL_* 填 / 会覆盖镜像可能带有的旧域名构建值，同时仍校验消息来源和父窗口，不使用通配来源。

设置 PUBLIC_BASE_URL 后，后端自动推导前端入口、同站用户中心 OAuth/Open API/账号管理地址和 Cookie 范围。
已有 AUTH_FRONTEND_URL、USER_CENTER_OAUTH_BASE_URL、USER_CENTER_OPEN_API_BASE_URL、AUTH_COOKIE_PATH 等显式配置优先，
因此要清除部署中残留的 edu/next 地址与 /bkg_zpt 路径覆盖值。
如后端必须通过内网访问用户中心，可单独指定 OAuth/Open API 的基础地址；浏览器登录入口仍使用公网入口。
未填写 Open API 地址时，后端根据实际 OAuth API 入口推导它，包括使用内网 UC 的情况。

### Docker Compose

使用根部署文件时，必须叠加 [docker-compose.supercompute.yml](../docker-compose.supercompute.yml)，
它会覆盖旧的前端构建路径、免登录开关与智谱域名默认值。
同事原有 backend/.env、根 .env、网络和基础服务需继续保留。
Compose 会直接拼接配置值，因此 PUBLIC_BASE_URL 与 APP_BASE 都不要带尾部斜杠，按模板填写。

    docker compose --env-file .env --env-file deploy/supercompute.env \
      -f docker-compose.yml -f docker-compose.supercompute.yml config --quiet
    docker compose --env-file .env --env-file deploy/supercompute.env \
      -f docker-compose.yml -f docker-compose.supercompute.yml up -d --build api web

以上启动命令由部署同事执行。若使用现有镜像发布流程，构建并发布本 PR 对应的前后端镜像后再更新服务。
此覆盖文件仅适配根 Compose 的 api/web 服务名，不能直接叠到 dev2 文件上。

### Kubernetes 或其他部署方式

不需要改用 Compose。把模板中的非敏感配置映射到现有前后端容器环境变量，
Client Secret 使用现有 Secret 管理方式注入后端。
前端构建使用 Dockerfile 默认的 /__BASE__/ 哨兵路径，启动时由 APP_BASE 注入实际前缀；
不要继续传旧的 VITE_BASE、VITE_API_BASE、VITE_AUTH_ENABLED 构建值。

使用本 PR 的标准前端镜像时，外层网关必须保留 /bkg_zp 前缀转发到 web，
由镜像内 nginx 将 /bkg_zp/api/... 转发为后端的 /api/...。
不能直接沿用旧 dev2 的剥前缀规则：标准模板在 / 上会重定向回 /bkg_zp/，
剥掉前缀后会造成入口循环跳转、深层页面 404。
如果现有网关必须剥前缀，需要另行配置并验证对应的前端 nginx 模板。
仅在菜单管理页面建目录不会创建这些转发规则。
门户共享 Cookie 必须覆盖 /bkg_zp/api/；只下发到 /portal 或 /uc 的 Cookie 无法用于此方案。

## 应用与菜单配置

应用“访问地址”按门户方最新要求填写完整回调地址：
`http://183.62.232.63/bkg_zp/api/v1/auth/callback`。
菜单页面地址才使用下面不带域名的路径。登记 callback 不会自动切换本系统的登录模式或启用回跳处理。

为现有超算应用添加一个顶层“目录”，名称“亿级科技知识图谱引擎-超算环境”，
目录编码可使用 kgetl_supercompute，目录地址留空。具体页面建为“菜单”，地址如下。
叶子菜单编码需与 frontend/src/portal/portalRoutes.ts 一致，便于门户保存和恢复子页面。

目录结构沿用智谱正式应用（不是智谱中误建的同名超算目录）：

```text
亿级科技知识图谱引擎-超算环境 (kgetl_supercompute)
├─ 工作台 (workbench)
│  └─ 平台总览
├─ 图谱建设与治理 (governance)
│  ├─ Schema 管理
│  ├─ 图谱构建
│  └─ 人工审核
├─ 平台管理 (platform_admin)
│  └─ 配置管理
└─ 知识图谱构建服务 (kg_service)
   ├─ 图谱查询 (graph_query_group)
   │  ├─ 综合查询
   │  └─ 实体列表
   └─ 科技专家/人才知识推理构建服务 (expert_service_group)
      └─ 下表九个业务应用菜单，按表中顺序排列
```

以上六个分组都建为地址为空的“目录”，同级从 1 开始排序；16 个页面放入对应父目录，不能全部平铺在根目录下。

| 分组 | 菜单名称 | 菜单编码 | 菜单地址 |
| --- | --- | --- | --- |
| 工作台 | 平台总览 | overview | /bkg_zp/overview?embedded=1 |
| 图谱建设与治理 | Schema 管理 | schema | /bkg_zp/schema?embedded=1 |
| 图谱建设与治理 | 图谱构建 | graph_build | /bkg_zp/graph-build?embedded=1 |
| 图谱建设与治理 | 人工审核 | manual_review | /bkg_zp/manual-review?embedded=1 |
| 平台管理 | 配置管理 | configurations | /bkg_zp/configurations?embedded=1 |
| 知识图谱构建服务 / 图谱查询 | 综合查询 | graph_query | /bkg_zp/graph-query?embedded=1 |
| 知识图谱构建服务 / 图谱查询 | 实体列表 | graph_query_entities | /bkg_zp/graph-query/entities?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技专家/人才直接关系 | yjkjzstp_expert_direct | /bkg_zp/expert-direct?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技单节点间接关系 | yjkjzstp_node_indirect | /bkg_zp/node-indirect?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技两点合作成果 | yjkjzstp_two_point_achievement | /bkg_zp/two-point-achievement?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技专家同事关系 | yjkjzstp_expert_colleague | /bkg_zp/expert-colleague?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技专家校友关系 | yjkjzstp_expert_alumni | /bkg_zp/expert-alumni?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技专家论文合作关系 | yjkjzstp_paper_cooperation | /bkg_zp/paper-cooperation?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 重点关注科技企业关系 | yjkjzstp_enterprise_relation | /bkg_zp/enterprise-relation?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技产业链点TOP-N事件关系 | yjkjzstp_industry_chain_event | /bkg_zp/industry-chain-event?embedded=1 |
| 知识图谱构建服务 / 科技专家/人才知识推理构建服务 | 科技产业链全景图 | yjkjzstp_industry_chain_panorama | /bkg_zp/industry-chain-panorama?embedded=1 |

目录名称与分组不影响真实页面路由。业务/空间权限继续由后端检查，添加菜单不会自动授予管理权限。
确认部署可用后，把该应用目录拖到右侧“国科信 → AI战略咨询”下，与“超大规模智算引擎”并列，再保存。
已有 /bkg_dp 应用和其他菜单无需变更。

## 后端管理员角色映射

超算用户中心已实测返回应用角色 `平台管理员 / system_admin`，这与旧接口的
`gkxUser.role=1` 是不同字段。超算 Compose 覆盖文件默认设置
`USER_CENTER_PORTAL_ADMIN_ROLE_CODES=system_admin`；其他部署默认不启用新增映射。
若同事不使用该 Compose 文件，需在后端容器环境中显式设置这个变量，再部署新版后端。
`USER_CENTER_PORTAL_ADMIN_ENABLED` 需保持开启（默认 true）。本次无需重建前端或执行 SQL。

后端只匹配用户中心实时返回的 `appPermissions.roles` 中启用的应用角色
（`code=system_admin`、`type=1`、`status=0`、`orgId=null`）。不使用角色显示名称、
组织角色或普通用户 `common` 提权，也不把继承的权限写成永久本地管理员。
角色校验复用默认 60 秒、不随访问续期的缓存；到期重新获取权限，撤销角色后
不再继承管理员权限，已有独立本地管理员授权仍然有效。

部署后重新登录，检查 `/bkg_zp/api/v1/auth/me`：角色仍为 `system_admin` 的账号应返回
`portalIsAdmin=true`、`isAdmin=true`、`platformRole=admin`、`canDevelop=true`。
没有本地管理员授权的普通账号仍应是普通用户。
`PLATFORM_BUSINESS_ONLY_USER_IDS` 中的账号仍受原有业务专用限制，不因映射而提权。
可将 `USER_CENTER_PORTAL_ADMIN_ROLE_CODES` 显式设为空并重启后端，关闭新增映射。

此映射不分配开发人员的业务归属，也不更改门户菜单授权；门户未返回图谱系统菜单时，
仍需门户方为相应角色配置菜单。页面代码、业务成员记录和图空间绑定均未改动。

## 联调与验收

1. 门户方确认 IP 入口自身的 SSO 登录及回跳地址已同步更新，不再把用户带回停用的 next 域名。
2. 同事核对实际部署版本与 AUTH_LOGIN_MODE，并验证 /bkg_zp/、深层页面刷新和静态资源。portal 模式的 /bkg_zp/api/v1/auth/login-url 返回配置的门户入口，不包含 OAuth state；oauth 模式应验证本应用发起授权及匹配 state 的回调。
3. 已登录门户后访问子系统，/auth/me 能识别当前账号。核对共享 Cookie 名称、范围及用户中心可达性；不要将令牌或密钥贴入日志、PR。
4. 切换门户账号后子系统同步身份；删除门户登录态后旧子系统会话不能继续访问；子系统退出不影响其他应用，点击登录后允许重新进入。
5. 验证总览、Schema、构建、审核和查询等实际功能，普通账号与管理账号权限正确。服务出现 502 时先由同事检查网关与后端日志。
6. 单独验证“全新未登录访问 → 门户登录 → 返回子系统”完整链路，记录实际落点及是否经过 callback。已有 Cookie 下的 /auth/me 成功会直接进入业务页，不能作为这条链路通过的证据；协议未确认前不把首次登录和自动返回原页面记为通过。

上线后的业务联调依赖真实部署，单元测试通过不代表以上验收已完成。

## 正式域名切换

同事更新 PUBLIC_BASE_URL，HTTPS 环境同步启用 AUTH_COOKIE_SECURE，然后更新应用登记的完整回调地址
以及门户自己维护的 SSO 回跳配置。站内菜单路径、前端消息来源配置无需逐条改域名，也无需仅为域名变化重建前端。
若曾显式覆盖 USER_CENTER_* 或 AUTH_FRONTEND_URL，需一起更新或移除旧覆盖值；内网 API 地址按实际网络保留。
