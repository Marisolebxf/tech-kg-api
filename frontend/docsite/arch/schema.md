# Schema 管理

> 来源：`docs/Schema管理模块.md` · `CLAUDE.md`

图谱构建的**元数据中枢**：定义实体/关系结构（Nebula TAG/EDGE 的镜像目录）→ 绑定 MySQL 来源表 → 上传抽取脚本 → 触发平台喂数抽取，一条链路全部从这个页面出发。前端路由 `/schema`（`SchemaBrowserView`，admin）；API 前缀 `/api/v1/schema-management`，**admin 路由组**。

## 组成

| 部件 | 说明 |
|---|---|
| Schema 目录 | 实体（kind=entity → TAG）/ 关系（kind=relation → EDGE）CRUD，按图空间隔离（`graph_space` 列）；创建即在目标图空间执行 DDL（数据类型白名单，失败重试）；属性增删联动图库 `ALTER TAG/EDGE` 与 `property_revision` |
| 来源表绑定 | 每个实体/关系可绑多张 MySQL 来源表（数据源 + 库 + 表 + pk 列 + 时间列，复杂 SQL 走 `query_sql`），每表独立水位 |
| 抽取脚本 | 上传 `.py`：`ast.parse` 语法检查 + `transform(payload)` 入口（或顶层 `STEPS` 多步清单，`service/script_steps.py` 静态校验）→ **LLM 安全校验**（`service/script_security.py`，非 AST 白名单）→ 存 S3/RustFS（MySQL 只存元数据）；`POST /schemas/{id}/script/verify` SSE 流式回传校验进度 |
| 平台喂数抽取 | `POST /schemas/{id}/extract` 触发 Temporal `kg.schema.extract`：平台按水位分批读源 → 脚本纯转换（只输出 `{entities|edges, failures}`）→ 平台写图/消歧/索引/推水位；逐行失败落 T_EXTRACT_FAIL 审核 case，支持按执行重跑（`triggerSource=RERUN`） |
| 回填 | `POST /schemas/{id}/backfill` 清空全部来源水位后全量重跑；脚本落后于 `property_revision` 时需 `force` 强确认 |
| 目录初始化 | `SCHEMA_AUTO_INIT=true` 启动播种系统 Schema（Expert/Organization/Paper/Project/Patent…，uuid5 幂等重跑） |

## 注意事项

- 实体写图走 nGQL `INSERT VERTEX`（trs-graph `/nodes/merge` 会把 id/name/vid 从属性剥离，DDL 的 NOT NULL id/name 会 400）；
- DDL 有 schema 传播延迟，紧跟的 DDL 短暂 500 时重试；
- 权限：系统 Schema 仅平台管理员或 `SCHEMA_ADMIN_USER_IDS`；自建 Schema 仅创建者或平台管理员；
- 关系定义的起点/终点实体 FK RESTRICT——被引用实体不可删；删 Schema 为目录假删（改写 key/name 释放唯一键，允许同名重建）。
