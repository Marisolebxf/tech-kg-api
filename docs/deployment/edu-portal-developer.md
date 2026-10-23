# EDU 门户开发人员与业务绑定

门户 `bkg_developer` 角色证明开发人员身份，本地业务成员表决定其可维护的业务；两项都满足才授予开发权限。管理员沿用现有判定。页面布局、门户菜单及登录回调不改；本次另复用现有全局消息框，在门户开发人员尚未绑定可开发业务时提示联系管理员。

## 部署配置

API 与 `temporal-worker` 使用同一 EDU 用户中心、应用凭据和以下配置：

```dotenv
AUTH_ENABLED=true
BUSINESS_RBAC_ENABLED=true
USER_CENTER_PORTAL_DEVELOPER_ROLE_CODES=bkg_developer
USER_CENTER_OPEN_API_BASE_URL=https://edu.itic-sci.com/uc/open-api/system
```

`USER_CENTER_CLIENT_ID`、`USER_CENTER_CLIENT_SECRET` 沿用 EDU 应用现有值，不使用超算应用凭据。地址仅为 EDU 部署配置，代码从配置读取。使用根目录 Compose 时，变量应放在 Compose 的插值环境（根 `.env` 或明确的 `--env-file`），只改 `backend/.env` 可能被 `environment` 覆盖。其他部署方式直接向两个进程注入相同变量。

该配置默认留空，因此合并代码不会自动改变其他环境的开发人员策略。启用后，**所有非管理员开发人员**都需要门户角色与本地业务绑定，部署前需核对现有开发人员也已加入门户角色。

## 绑定步骤

先构建包含此变更的后端镜像，在连接 EDU 业务数据库的维护容器中执行下列命令，再启用 API/worker 的角色校验。复用当前数据库迁移流程，确保业务权限表已初始化。本工具不创建表。

准备 `edu-developer-bindings.json`，实际账号清单单独交付，不提交到仓库。格式如下；提供 `userId` 时必须是 **EDU 本系统成员接口返回的编号**。若省略，脚本会在目标数据库中按完整 `username` 查找唯一账号；仅注册门户、尚未登录子系统，或账号不唯一时会停止，不创建用户、不猜测编号。

```json
{
  "userCenterOpenApiBaseUrl": "https://edu.itic-sci.com/uc/open-api/system",
  "businesses": [{"clientId": "example-team", "name": "示例团队"}],
  "members": [{"userId": "123", "username": "example@example.test", "clientId": "example-team"}]
}
```

在后端工作目录执行（Docker 镜像使用 `.venv/bin/python`）：

```sh
.venv/bin/python -m script.bind_portal_developers --plan /tmp/edu-developer-bindings.json
.venv/bin/python -m script.bind_portal_developers --plan /tmp/edu-developer-bindings.json --apply
```

第一条只核对，不写入。使用真实 EDU 应用凭据调用文档 v2.5.1 §2.7 的 `POST /open-api/system/permission/role-user`，验证全部目标账号已获角色授权，同时核对本地账号与编号。第一条成功后再执行第二条；第二条会重新核验，在一个事务中创建业务与开发成员记录，可重复执行。

`userCenterOpenApiBaseUrl` 指定计划目标环境，必须与运行实例的开放接口地址一致，不一致直接拒绝。EDU 三人计划与超算新增账号计划分别交付，不能混用。超算计划不包含 EDU 用户编号；在超算环境执行前，仍需核对当地实际开发人员角色编码并配置，使用超算应用凭据。业务编号/名称冲突或原有绑定冲突时不会自动覆盖。

遇到接口不兼容、签名/凭据错误、缺失角色、已有其他业务绑定或管理员身份时停止处理，不覆盖冲突数据。不能跳过核验直接写库。此接口的 `orgId` 是门户机构关联，不作为本系统团队归属；团队归属始终由本地绑定决定。

本次计划为久新团队两人、智树团队一人。脚本仅写 `kg_business_client`、`kg_business_membership`、`kg_business_membership_state`，不修改旧成员表、管理员角色、图空间或已有资源。

## 预期结果与验证

- 三人重新登录后，`/api/v1/auth/me` 返回 `platformRole=developer`、`canDevelop=true`、`isAdmin=false`，`developerBusinessIds` 仅包含对应团队。
- 已有门户开发人员角色但未绑定可开发业务时，接口返回 `developerBusinessBindingRequired=true`；登录显示“您已获得门户开发人员身份，但尚未绑定可开发的业务，请联系管理员为您绑定业务。”同次页面会话内不因路由校验/令牌刷新重复提示，重新登录或整页刷新会重新检查。普通用户、管理员、业务专用受限账号不提示。绑定完成并刷新身份后停止提示。
- 提示不授予权限，也不阻止公共只读访问。对于没有开发授权的账号，门户查询暂时失败时跳过提示，避免误报缺少绑定；已有本地开发绑定时仍使用原有失败关闭逻辑。
- 初始不分配私有图空间：公共空间可读，写入与审核提交拒绝；其他业务私有空间不可访问。开发人员可维护本业务配置，但没有任何现有图空间写权限。后续通过现有业务空间分配机制分配各自空间。
- API 与后台任务均核对门户角色，缓存最长 60 秒。撤销门户角色后，缓存到期失去开发权限；本地绑定记录保留。查询失败返回 503，不沿用过期授权。已经运行的操作不会被这次角色查询主动终止。
- 保持现有管理员权限，普通用户不会仅因拥有门户角色就自动加入业务。前端只消费新增提示字段，不改页面组件或样式。需同时部署本次前端脚本，只有后端更新不会显示提示。

目前已验证门户成员列表及本地账号编号，并完成离线单元/回归验证；签名开放接口在 EDU 的实际可用性、部署后身份和读写结果，需由上述只读核验及部署后登录验证确认。

若回退到原有本地开发人员策略，在 API 与 worker 同时清空 `USER_CENTER_PORTAL_DEVELOPER_ROLE_CODES` 并重建/重启。清空开关会恢复本地成员授权，**不等于撤销开发权限**；需要撤权时使用现有成员授权机制撤销本地绑定。
