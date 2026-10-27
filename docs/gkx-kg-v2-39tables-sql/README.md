# gkx_kg_v2：39 张表 SQL 包（14 实体 + 25 关系 + 测试数据）

新库 `gkx_kg_v2`（宿主 tech-kg-mysql:30306）的完整 SQL 物料。上游口径：只取 14 张实体表 + 25 张关系表，
kg_scholar_organization 不作第 15 张实体表，按三档口径并入 Organization（props 逐字段展开、一列一属性）。
配套图空间 `gkx_kg_v2`（14 TAG 1,025,180 点 / 25 EDGE 1,159,390 边，39 项对账一致）与
46 组九大业务测试数据验证 42 组逐字命中 + 4 组差异全归因（报告 ~/deploy/gkx-kg-v2-build-report-1028.md）。

## 文件清单（按导入顺序）

| 文件 | 内容 | 大小 |
|---|---|---:|
| `01_schema_39_tables.sql` | 全 39 张表 DDL（v_organization 含合并新列 `confidence double`） | 57KB |
| `02a_data_full_entities.sql` | 8 张实体表**整表全量**（含 v_organization 合并版 19,895 行 = 19,870 企业 + 25 学者） | 47MB |
| `02b_data_full_edges.sql` | 22 张关系表**整表全量**（含 ev_affiliated_with 键对齐改写版 1,129 行） | 56MB |
| `03_data_testdata_subset.sql` | 9 张大表的 **46 组测试数据闭包子集**（见下方口径） | 44MB |
| `04_rebuild_full_from_gkx_kg.sql` | 从源库 gkx_kg **全量重建** 39 张表（源库只读零改动，可重复执行前先 DROP 库） | 4KB |
| `05_org_merge_audit.sql` | 学者机构合并审计件：三档口径、17 对键映射、25 行展开口径、建成后自检 SQL | 3KB |

总计 39 张表 = 14 实体（v_person/v_paper/v_patent/v_patent_family/v_project/v_organization/v_news/v_event/v_journal/v_keyword/v_report/v_product/v_industry_chain/v_industry_node）+ 25 关系（ev_acquires … ev_subsidiary_of，与 gkx_kg_full 同型同名）。

## 两键提醒

1. **ev_* 边表存带前缀 vid**（`person_xxx`/`paper_xxx`/`org_xxx`/`node_xxx`），**v_* 实体表存裸主键**（`xxx`）。
   图上 vid = 前缀 + 实体表主键。
2. **演示造数排除口径**（与 gkx_kg_full 一致）：Paper 排除 `id LIKE '889900%'`（17 篇）；
   Organization 排除 `org_id LIKE 'MOCK%'` 与首字符为引号的行（52 行）。本包的 v_paper/v_organization 表
   数据未剔除（如实快照），重建图时由构建脚本排除；46 组验证结论均基于排除后口径。

## 03 子集口径（46 组九大业务测试数据闭包）

种子 = 46 组重放响应中出现的全部实体 ID + 测试输入 ID（重放器原始输出 /tmp/nine_v2_out.json），
再做四层闭包：核心人全部论文（ev_authored_by）→ 核心人直接论文合作者双向（ev_coauthor_with）→
18 个链节点所属机构的全部事件（ev_belongs_to_node × ev_involved_in，保 M8 top-N 排序口径）→
选中论文的关键词（ev_has_keyword）。命中：v_person 11,564 / v_paper 9,022 / v_event 622 /
v_keyword 22 / v_project 3；边表按端点落子集。v_patent 单行 80KB+（摘要/权利要求大 JSON），
仅附 5 行结构示例，全量走 04。约 1.5% 响应 ID 在实体表无对应行（图上派生 ID），子集如实不含。

注意：该子集可支撑 46 组的**输入实体与主路径数据**，但 M2 间接关系 / M9 全景等走全图邻域的计数
（147/315/395 路径、356 节点等）**不能**在子集上复现，需 04 全量重建后建图验证。

## 建图与验证（完整链路见 backend/script/gkx_kg_v2_build/）

```bash
PYTHONPATH=/app python -m script.gkx_kg_v2_build.create_space             # 建空间
PYTHONPATH=/app python -m script.gkx_kg_v2_build.register --database gkx_kg_v2 \
    --graph-space gkx_kg_v2 --datasource-id MYSQL-A176CF7A                # Schema+绑定+脚本
PYTHONPATH=/app python -m script.gkx_kg_v2_build.load_entities_ngql       # 14 TAG 直写
PYTHONPATH=/app python -m script.gkx_kg_v2_build.launch_clean_relations   # 净端点 14 边型走链
PYTHONPATH=/app python -m script.gkx_kg_v2_build.load_edges_ngql          # 悬挂 11 边型直写
PYTHONPATH=/app python -m script.gkx_kg_v2_build.verify_space             # 39 项对账
```

九大业务查询带请求头 `X-Business-Graph-Space: gkx_kg_v2` 即路由到新空间。
