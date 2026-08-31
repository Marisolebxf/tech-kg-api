# Schema 管理

> 来源：`backend/docs/schema_management_api.md` · `CLAUDE.md`

管理员在页面上编写 nGQL schema 脚本（建 Tag / Edge / Space），由后端校验后对 trs-graph 执行。路由挂载在 `/api/v1/schema-management`，**admin 鉴权**。

## 组成

| 部件 | 说明 |
|---|---|
| 脚本存储 | S3（`SCHEMA_S3_*` 配置），脚本内容与元数据对象化存储 |
| 安全校验 | `service/script_security.py`——**AST 白名单**校验，只放行允许的 nGQL 语句形态，防注入/防任意 Python |
| 执行 | 校验通过后经 nGQL 对 trs-graph 执行（`execute_write` 等） |
| 目录初始化 | `SCHEMA_AUTO_INIT=true` 时启动即播种 schema catalog |
| 前置 DDL 文件 | `backend/schemas/` 内置 nGQL DDL/spec 与 fixture |

## 前端

平台管理区的 schema 拓扑 / nGQL 控制台页面（`views/platform/SchemaBrowserView.vue`、`GraphBuildView.vue` 等）：查看图空间、Tag/Edge 拓扑、在线执行 nGQL 查询。支持 schema 删除（带数据保护校验）。

## 注意事项

- DDL 有 schema 传播延迟，紧跟的 DDL 短暂 500 时重试；
- 用户隔离：schema 目录按创建者隔离（2026-08-30 重构），普通用户不见他人条目。
