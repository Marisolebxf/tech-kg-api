# 专家同事关系：任职时间挂到工作边并据此判定同事

## 背景

专家同事关系模块的算法链路：专家 → `AFFILIATED_WITH` 出边 → 机构 → `AFFILIATED_WITH` 入边 → 同机构人 → **边上的任职时间重叠** → 同事。但改造前存在三重数据/代码缺失，导致时间过滤空转：

1. **边上无时间**：`AFFILIATED_WITH` DDL 只有 `(affiliation_name, source)`，ETL 也只写这两个 + 溯源字段，**无任何任职时间**。
2. **节点上时间未持久化**：`load_scholar_entities` 试图把 `work_experience_date` 写到 Person 节点，但 Person tag DDL 只声明 `name_en/name_zh/email/source` → 真实图实测 Person 节点只有这 4 个属性，`work_experience_date` 被 NebulaGraph 丢弃。
3. **service 从节点读时间**：`_node_period(node)` 从 Person 节点读 `work_experience_date` → 恒为 None → `_overlap` 恒走"缺时间"分支 → `effectivePeriod` 恒为"任职时间待补录"、`reviewRequired` 恒为 true，**时间过滤从未生效**。

目标：让"边上的时间判断同事"真正成立——任职时间（及部门）挂到 `AFFILIATED_WITH` 边上，service 从**边**读时间做重叠判定。

## 改动文件

| 文件 | 改动 |
|---|---|
| `backend/script/init_paper_journal_schema.py` | `CREATE EDGE AFFILIATED_WITH` 加 `work_experience_date`/`work_experience_department_zh`/`work_experience_position_zh` |
| `backend/script/load_scholar_relations.py` | `_iter_scholar_affiliations` 增列读取 3 字段（`information_schema` 探测兜底）；`load_affiliations` 写入边属性；新增 `ensure_schema` 幂等 `ALTER EDGE ADD` |
| `backend/service/expert_colleague_relation.py` | `_affiliations` 从边取 `period`/`department`；候选循环从边读时间/部门；`_expert` 机构回退取 affiliation；删除无用的 `_node_period` |
| `backend/tests/unit/test_expert_colleague_relation.py` | 边带 `work_experience_date`，验证重叠区间；新增"不重叠→排除"、"边无时间→复核"用例 |

## 设计要点

### DDL + ETL：时间挂到边上
- `AFFILIATED_WITH` 声明 3 个新属性（全新空间生效）。
- `_iter_scholar_affiliations` 沿用 `scholar_org_id` 的 `information_schema` 探测模式，对 `work_experience_date`/`work_experience_department_zh`/`work_experience_position_zh` 做存在性兜底（列缺失时 `NULL AS xxx`）。
- `load_affiliations` 把 3 字段写入边 `props`。
- `ensure_schema`（复用 `load_patent_graph.ensure_schema` 模式）：`DESCRIBE EDGE AFFILIATED_WITH` → 对缺失属性 `ALTER EDGE ADD (...)` → 15 次轮询等传播生效。在 `load_affiliations` 写边前调用。

### service：从边读时间
- `_affiliations` 除 `id/name` 外，从 edge `properties` 取 `work_experience_date`（`_parse_period` 转 `(start,end)` 存为 `period`）和 `work_experience_department_zh`（存为 `department`）。
- 候选循环：从 `org_graph["edges"]` 建 `{person_vid: edge_props}` 索引（AFFILIATED_WITH 入边），候选人时间/部门**从边读**；专家时段改用 `affiliation["period"]`（每机构一时段，非全局）。
- `_overlap(affiliation["period"], candidate_period, requested_period)`：`overlap is False` 仍跳过（时间不重叠排除）。
- 删除 `_node_period`（不再从节点读）；`_parse_period`/`_overlap` 复用不变。
- `_expert.organization` 为空时回退取第一条 affiliation 的 `name`（边上的 `affiliation_name`）。

## 数据现状（重要）

**当前 dev 图数据无法支撑该业务**（本次只改代码，未碰 dev 数据）：
- `AFFILIATED_WITH` 全图仅 **140 条**（Person 40067 个）→ 99.6% 专家查不到任职机构 → 返回 0 同事。
- 抽样 100+ Person、40 Org 跨偏移均无该边；Person 实际连的是 `AUTHORED_BY`/`BENEFICIAL_OWNER_OF`/`EXECUTIVE_OF`。说明 `load_scholar_relations.py` 基本没在 dev 跑过。

代码修复让"边时间判断同事"在**数据就绪后**生效；要让业务在真实图跑通，还需在 dev 跑 `load_scholar_relations.py` 补全 AFFILIATED_WITH 边并写入边时间（数据动作，本次未执行）。

## 数据局限

`dwd_scholar.work_experience_date` 是每人单值（全局任职时段），`load_scholar_relations` 每人只建 1 条到当前机构的边——每条边带 1 个时段，与"1 人 1 机构"匹配。多人多段任职需解析 `work_experience_zh` 自由文本，不在本次范围。`work_experience_date` 为空的学者仍落"任职时间待补录+人工复核"（仅在数据真缺失时才如此，而非恒空）。

## 验证

`PYTHONPATH=. uv run pytest tests/unit/test_expert_colleague_relation.py -v` → 3/3 通过：
- `test_query_infers_colleague_from_edge_time_overlap`：专家边 `2018-2023`、同事边 `2020-2025`、请求 `2020-2022` → `effectivePeriod=="2020-2022"`、`overlapYears==3`、`reviewRequired is False`。
- `test_non_overlapping_periods_exclude_colleague`：专家 `2010-2015`、同事 `2020-2025` → `total==0`。
- `test_missing_edge_time_is_returned_for_manual_review`：同事边无 `work_experience_date` → `effectivePeriod=="任职时间待补录"`、`reviewRequired is True`。

集成测试 `tests/integration/test_expert_colleague_relation_api.py` 2/2 通过。`ruff format`/`ruff check` 干净。

## 不在范围
- 不改 Person tag DDL（时间/部门改由边承载，节点不再作为来源）。
- 不新建 `WORKS_AT` 边（沿用 `AFFILIATED_WITH`，最小改动）。
- 不解析 `work_experience_zh` 多段任职。
- 不改 graph-search / temporal / schema_management 等公共平台。
