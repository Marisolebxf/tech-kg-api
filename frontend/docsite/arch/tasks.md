# 任务中心与公共能力

> 来源：`backend/docs/workflow_operations_api.md` · `CLAUDE.md`

## 任务中心（Job 注册表）

任务中心是平台所有**可触发任务**的统一入口。2026-08-30 重构后引入 **Job 注册表**：每种任务（工作流执行、抽取脚本、审核批处理……）在注册表中声明 id / 名称 / 参数 schema / step 输入输出，前端据此渲染触发表单与进度视图，不再为每种任务手写页面。

- 支持 step 级 I-O 展示（每步的输入 payload 与输出 summary / access report）；
- 失败任务 `POST /task-center/tasks/{id}/retry`（reset 语义，见[工作流系统](/arch/workflow)）；
- 配置资源与工作流定义**按创建者隔离**（用户只见自己的 + 平台预置）。

## 运营中心与平台总览

`views/platform/OperationsCenterView.vue` / `PlatformWorkbenchView.vue`：任务运行状况、流程实例（Temporal execution）列表与下钻（`ProcessInstanceDetailView.vue`）。

## 公共能力接口

- `GET /kg-construction/options` —— 聚合前端测试参数弹窗的全部下拉项：学者/边（图）、企业（MySQL）、relationTypes/roles/dimensions/techFields/cpcCodes（catalog）。**每个数据源独立包裹**——某一个失败只返回 `[]`，不拖垮整个响应；
- 图搜索、平台概览、配置管理（MySQL 数据源 / Milvus / LLM / embedding 配置 CRUD + 测连 + 列库）等支撑路由。

## 参考子系统：重点关注科技企业关系

三个协作模块 + 共享 code 表（`service/enterprise_relation_catalog.py`：`RELATION_TYPES` / `ROLE_CATALOG`）：

- **expert_enterprise_relation**（`/kg-construction/expert-enterprise-relations`）——建 `EMPLOYED_BY` 边；relation_type 存英文码（employment/advisor/rd_cooperation/project_cooperation/tech_cooperation），响应时才映射中文；多条关系 `/` 连接；缺学者/企业 → 404；
- **relation_detail_annotation** —— 注解既有边（角色/技术领域/时期），角色来自 `ROLE_CATALOG`（chief_scientist/cto→L1 等）；
- **enterprise_background_analysis** —— MySQL 聚合（行业地位/核心技术/经营财务）+ LLM 叙述合成；LLM 失败优雅降级为结构化结果。
