# 专家-企业关系构建 接口设计（techkg 图空间全流程）

- 日期：2026-06-17
- 分支：`feature/technology-company-relation`（基于 `feature/trs-graph-app-service`）
- 状态：待评审

## 1. 背景与目标

前端"重点科技企业关系 → 专家-企业关系构建"目前用假数据（`enterpriseGraphNodes` 硬编码，无 fetch）。本设计实现真实接口：在 trs-graph 新建 `techkg` 图空间，按 `db_model` ORM 做 schema 映射，从 MySQL 灌数据，API 查图返回专家-企业关系，前端接线。

数据现状（已探查）：
- MySQL `techkg`：67 张 DWD 表，**全空（0 行）**。
- trs-graph `entity_binding_demo`：5 个 demo talent + 4 个 demo 高校 org，无专家-企业边。
- trs-graph `techkg` 空间：暂不存在（需创建）。

目标：建全流程，MySQL 暂空时 API 返回空结果，MySQL 有数据后 ETL 灌图即生效。

### 非目标
- 不做其余 8 个关系模块（直接关系/同事/校友/论文合作/产业链…），只做"专家-企业关系构建"。
- 不做多跳推理/间接关系。
- 不改 `legacy/`。

## 2. 架构

```
MySQL(dwd_scholar/dwd_org_reg_info) ──ETL(script/load_graph.py)──▶ trs-graph techkg 空间
   ▲ db_model ORM                                                       │ 查询
infra/mysql.py + dao/{scholar,organization}                        infra/graph_db (TRSGraphClient)
   │                                                                     │
   └─────────────── application/expert_enterprise_relation ◀─────────────┘
                          │
                    biz/handler  POST /api/v1/kg-construction/expert-enterprise-relations/build
                          │
                     前端 fetch（改 apiPath + 接真实接口）
```

## 3. techkg 图空间 schema（db_model 映射）

用 nGQL DDL 经 `TRSGraphClient.execute_write` 创建空间与 schema：

- **Space**: `techkg`
- **Tag `Scholar`** ← `db_model.scholar.DwdScholar`，属性取子集：
  - `scholar_id`（string，主键）、`name_zh`（string）、`name_en`（string）、`scholar_org_name_zh`（string）、`scholar_org_name_en`（string）、`h_index`（int）、`citation_nums`（int）、`paper_nums`（int）
- **Tag `Organization`** ← `db_model.organization.DwdOrgRegInfo`，属性取子集：
  - `org_id`（string，主键）、`name_cn`（string）、`province`（string）、`city`（string）、`org_type`（string）、`listing_status`（string）、`incorporation_year`（int）
- **Edge `EMPLOYED_BY`**（`Scholar -> Organization`），属性：
  - `relation_type`（string，默认 "任职"）、`role`（string）、`start_date`（string）、`end_date`（string）、`source`（string）
- 索引：`Scholar(scholar_id)` 唯一/二级索引；`Organization(name_cn)` 二级索引；`Organization(org_id)` 二级索引。

DDL 脚本放 `backend/script/init_graph_schema.py`（幂等：`CREATE ... IF NOT EXISTS`）。

**关系推导**（ETL 时计算）：`DwdScholar.scholar_org_name_zh` 匹配 `DwdOrgRegInfo.name_cn` → 建 `EMPLOYED_BY` 边，`relation_type="任职"`。后续可扩展用 `DwdOrgExecutiveInfo`（`executives_name`+`org_id`）补充"高管/任职"关系（本次非目标，预留）。

## 4. MySQL 接入

### `backend/infra/mysql.py`
实现真实 `MySQLClient`（替换占位）：
- 用 `sqlalchemy.create_engine`（**同步**，driver `pymysql`），URL 由 `MYSQL_*` 环境变量拼装。
- 提供 `engine`（模块级懒加载）与 `SessionLocal = sessionmaker`。
- 提供 `get_session()` 上下文管理器 / 依赖。
- pyproject 已有 `pymysql`、`sqlalchemy` 依赖（.venv 需补装 pymysql）。

### `backend/dao/scholar.py`、`backend/dao/organization.py`
实现真实 DAO（替换占位类）：
- `ScholarDAO.get(scholar_id) -> DwdScholar | None`、`ScholarDAO.list(limit, offset)`。
- `OrganizationDAO.get_by_id(org_id)`、`OrganizationDAO.get_by_name(name_cn)`、`OrganizationDAO.list(limit, offset)`。
- 基于 `db_model` ORM 查询；空表返回空。

## 5. ETL 加载器 `backend/script/load_graph.py`

- 读 MySQL：`DwdScholar` 全量（分页）、`DwdOrgRegInfo` 全量。
- 写图（`techkg` 空间，经 `TRSGraphClient`）：
  - `batch_create_nodes` 建 Scholar / Organization 节点。
  - 按 `scholar_org_name_zh`==`name_cn` 匹配，`create_edge` 建 `EMPLOYED_BY` 边。
- 幂等、可重复运行；MySQL 空时打印 "0 rows" 并退出。
- CLI：`python -m script.load_graph`（或 `python script/load_graph.py`），从 `backend/` 运行。

## 6. API 契约

**路径**：`POST /api/v1/kg-construction/expert-enterprise-relations/build`（在现有 `biz/handler/expert_enterprise_relation.py` 加 `@router.post("/build")`）。

**请求体**：
```json
{
  "dataSource": "all",
  "expertAId": "talent_001",
  "relationType": "all",
  "timeRange": {"start": "2018.03", "end": "2022.12"}
}
```
- `expertAId` 对应图 `Scholar.scholar_id`（及 MySQL `dwd_scholar.scholar_id`）。
- `relationType`、`timeRange`、`dataSource` 当前作为透传/过滤预留（数据稀疏，先不强过滤；`relationType!="all"` 时按边 `relation_type` 过滤，`timeRange` 按边 `start_date/end_date` 过滤，无值则不过滤）。

**响应体**：
```json
{
  "status": "success",
  "expert": "张伟",
  "expert_id": "talent_001",
  "title": "",
  "enterprises": [
    {
      "enterprise_id": "org_001",
      "name": "清华大学",
      "type": "高校",
      "province": "北京市",
      "relation": "任职",
      "role": "",
      "start_date": "",
      "end_date": ""
    }
  ]
}
```
- 找不到专家：`{"status":"success","expert":null,"expert_id":"talent_001","title":null,"enterprises":[]}`。
- `title`：`DwdScholar` 无职称字段，暂返回空串（或 `academician` 标志），后续扩展。

### 分层实现
- `biz/handler/expert_enterprise_relation.py`：加 `POST /build`，解析请求体（Pydantic schema），调 application，返回 JSON。
- `application/expert_enterprise_relation.py`：加 `build(payload) -> dict`，调 service。
- `service/expert_enterprise_relation.py`：加 `build(payload)`，用 `get_trs_graph_client()`（`techkg` 空间）查图：`get_node(scholar_id)` → `get_node_edges(scholar_id, edge_type="EMPLOYED_BY")` → 对端 Organization 节点属性 → 组装响应。空图/空结果返回空 enterprises。
- 请求/响应 Pydantic 模型放 `biz/handler` 或新增 `biz/schemas/`（按现有约定；现有 handler 无 schemas 目录，先在 handler 文件内定义）。

**图空间配置**：API 与 ETL 查询/写入用 `techkg` 空间。`infra/graph_db/__init__.py` 新增 `get_techkg_client()` / `close_techkg_client()` 单例（与现有 `get_trs_graph_client()` 同构，但 `TRSGraphSettings.space` 固定为 `"techkg"`，其余字段仍读 `TRS_GRAPH_*` env）。service 用 `get_techkg_client()`。

## 7. 前端接线

`frontend/src/App.vue`：
- `relationFeatures` 里"专家-企业关系构建"的 `apiPath` 改为 `/api/v1/kg-construction/expert-enterprise-relations/build`（其余子功能保持假数据，本次不动）。
- 新增 `fetch` 调用：在切换到该子功能或点击"构建/运行"时，`POST` 该 apiPath（经 vite 代理），把响应映射成 `graphNodes`（中心专家节点 + `enterprises[]` 映射为企业节点，`relation` 取 `relation` 字段）。
- 失败/空时回退到当前假数据或显示空状态（保留假数据作为兜底，避免界面空）。
- vite 代理修正：当前 `vite.config.ts` 的 proxy 把 `/api` rewrite 掉 `^/api`，与后端 `/api/v1/...` 路由冲突。改为不 strip（`rewrite` 去掉，或 target 直接到后端 8100 且保留 `/api`）。后端端口用 `VITE_API_TARGET`（默认 8100）。

## 8. 测试

- **图 schema**：`tests/unit/test_graph_schema.py`——校验 `init_graph_schema.py` 产生的 DDL 字符串/调用（MockTransport，不依赖真实图；可选 `@pytest.mark.external` 集成测试在真实图上跑 `CREATE IF NOT EXISTS`）。
- **DAO**：`tests/unit/test_dao_scholar.py`、`test_dao_organization.py`——用 sqlite/in-memory 或 mock session，验证查询逻辑（空表返回空）。MySQL 真实查询用 `@pytest.mark.external`。
- **ETL**：`tests/unit/test_load_graph.py`——mock DAO + mock TRSGraphClient，验证节点/边写入调用与关系匹配逻辑。
- **service/API**：`tests/unit/test_expert_enterprise_service.py`——mock TRSGraphClient，验证响应组装（找到/找不到/空 enterprises）。
- **集成**：`tests/integration/test_expert_enterprise_api.py`（`@pytest.mark.external`）——真实后端 + 真实图（techkg 空间有数据时）。
- 全部用 `.venv`（补装 pymysql 后）跑。

## 9. 交付物

- `backend/infra/mysql.py`（实现）
- `backend/dao/scholar.py`、`backend/dao/organization.py`（实现）
- `backend/script/init_graph_schema.py`、`backend/script/load_graph.py`
- `backend/biz/handler/expert_enterprise_relation.py`、`application/expert_enterprise_relation.py`、`service/expert_enterprise_relation.py`（实现 build）
- `backend/infra/graph_db/__init__.py`（techkg 空间访问器）
- `frontend/src/App.vue`、`frontend/vite.config.ts`（接线 + 代理修正）
- 测试文件（§8）
- `backend/.env.example`（`MYSQL_*` 已有；确认 `TRS_GRAPH_SPACE=techkg` 用于 ETL/API，或单独配置）

## 10. 实施阶段（plan 拆分参考）

1. MySQL 接入：`infra/mysql.py` + `dao/scholar`/`dao/organization` + 单测。
2. 图 schema：`script/init_graph_schema.py`（techkg 空间 DDL）+ 单测；在真实图上跑一次建空间/schema。
3. ETL：`script/load_graph.py` + 单测（MySQL 空时 0 产出）。
4. API：handler/application/service build + graph_db techkg 访问器 + 单测。
5. 前端接线 + 代理修正 + 构建验证。
6. 全量校验（ruff + pytest）。

## 11. 验收

- `pytest`（单测）全绿；`@pytest.mark.external` 集成测试在无 MySQL/图数据时 skip 或空通过。
- `init_graph_schema.py` 能在真实 trs-graph 建出 `techkg` 空间 + Scholar/Organization/EMPLOYED_BY schema。
- `load_graph.py` 在 MySQL 空时正常退出（0 产出），有数据时灌入节点/边。
- `POST /api/v1/kg-construction/expert-enterprise-relations/build` 在图空时返回 `{status:success, enterprises:[]}`，有数据时返回真实专家-企业关系。
- 前端切换到"专家-企业关系构建"调用真实接口（图空时显示空/兜底），不再是纯假数据。
- `ruff check` 全绿。
