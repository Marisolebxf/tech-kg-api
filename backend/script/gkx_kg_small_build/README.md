# gkx_kg_small_build — gkx_kg 少量真实样例·dev2 全流程建图（20261027）

把 **gkx_kg 库的真实小样例**（每关系类型 ≤5 条边 + 全部端点实体，约一两百行/15 实体类型）
通过 **dev2 主栈的图谱构建全流程**（建空间 → 注册 Schema/DDL/脚本/来源 → chain 任务 →
实体批 → 关系批 A/B → 校验）抽到新图空间 `gkx_kg_sm`（平台面 trsgraph:9677）。
不造模拟数据：所有行都是 gkx_kg 真实行；少量 = 边采样驱动的小样本。

与全量包 `script/gkx_kg_dpgkx/`（另一会话）的差异：

| | gkx_kg_dpgkx（全量） | 本包（小样例） |
|---|---|---|
| 数据 | gkx_kg 全库（v_* 视图） | `gkx_kg_sm` 库 sm_* 小表（v_kg_edge 采样） |
| 实体通道 | gray-gate 撞重名组 → 改直装 | 样本内有效名去重 → 纯管道 |
| 图空间 | dp_gkx | gkx_kg_sm |

## 一次完整跑法

```bash
# 0) 送到 api 容器（每改一次都要重拷）
docker cp backend/script/gkx_kg_small_build tech-kg-api-dev2:/app/script/

# 1) 宿主：造小样例库（幂等，整库重建）
docker exec -i tech-kg-mysql mysql -uroot -pgkx_element \
    --default-character-set=utf8mb4 \
    < backend/script/gkx_kg_small_build/prep_sm_db.sql

# 2) 容器内：建图空间（真实 CREATE SPACE，等 schema 传播）
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-dev2 \
    /app/.venv/bin/python -m script.gkx_kg_small_build.create_space

# 3) 注册 40 个 Schema（定义+DDL+S3 脚本+来源绑定；落 techkg_platform_dev2）
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-dev2 \
    /app/.venv/bin/python -m script.gkx_kg_small_build.register \
    --datasource-id MYSQL-A176CF7A

# 4) 目录行搬到运行时真库 techkg_control（workflow 侧才能看到）
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-dev2 \
    /app/.venv/bin/python -m script.gkx_kg_small_build.copy_defs_to_control

# 5) 建 3 个 chain 任务（实体批 15 个 runNow；关系批 A13/B12 待触发）
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-dev2 \
    /app/.venv/bin/python -m script.gkx_kg_small_build.launch_jobs \
    --datasource-id MYSQL-A176CF7A

# 6) 实体批 SUCCEEDED 后触发关系批
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-dev2 \
    /app/.venv/bin/python -m script.gkx_kg_small_build.trigger_relations

# 7) 校验：图空间 TAG/EDGE 计数 vs gkx_kg_sm 源表计数
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-dev2 \
    /app/.venv/bin/python -m script.gkx_kg_small_build.verify_space
```

## 任务状态速查（techkg_control @ tech-kg-temporal-mysql-dev2）

```sql
SELECT j.id, j.name, j.status, e.status, e.started_at
FROM techkg_control.workflow_jobs j
LEFT JOIN techkg_control.workflow_executions e ON e.job_id = j.id
WHERE j.name LIKE 'gkx_kg_sm建图-%' ORDER BY e.started_at DESC;
```

## 回滚

```bash
docker exec -w /app -e PYTHONPATH=/app tech-kg-api-dev2 \
    /app/.venv/bin/python -m script.gkx_kg_small_build.purge_jobs   # 删任务
docker exec tech-kg-mysql mysql -uroot -pgkx_element -e "DROP DATABASE gkx_kg_sm;"
# 图空间：页面删或 nGQL DROP SPACE gkx_kg_sm（先 DISCARD 再 DROP）
```

## 坑（沿自 dp_gkx 全量会话，本包已绕开）

- `kg_` 开头表名撞 `script_resource_broker.PROTECTED_TABLE_PREFIXES` → 本包表名 `sm_*`。
- gray-gate-v2：同名候选 score≥0.85 → DEFERRED_MERGE_BLOCKED 整链 FAILED → 样本按
  "有效名"（主名列+首个回退列）整组去重、无名实体删除。
- 边写入 fail-close 校验端点存在 → 样本由边采样反推实体，双端点天然齐备。
- Schema 目录双库：注册落 techkg_platform_dev2（服务层原生），运行时读 techkg_control，
  须 copy_defs_to_control 搬 kg_schema_definition/property/script/source 四表。
- 任务 payload 内嵌来源快照：绑定改了就要删任务重建（purge_jobs + launch_jobs）。
- 实体步 name 回退列**必须逐列取值**（`for c in (...)`），写 `row.get([列表])` 会当场
  `TypeError: unhashable type: 'list'`——主名列非空的行不触发，恰好空名的行整批进
  T_EXTRACT_FAIL（首轮：人员 15/35、论文 10/10、期刊 3/3 全挂，修复后 100% 对齐）。
- 重传脚本后 `copy_defs_to_control` 只敢插入：须先删控制库本空间目录行
  （`kg_schema_script/source/property` → 按 `kind='relation'` 先删 `kg_schema_definition`）再重拷，
  否则 launch_jobs 预检报"脚本本体不存在"（控制库还指着被替换的旧 S3 key）。
- `workflow_executions.status` 回写滞后属常态：execution_reconciler 只对
  **RUNNING 超 30 分钟**的行回写真值（5 分钟一轮），Temporal 已 Completed、图已落盘时
  任务中心可能仍显示"运行中"，终态以 Temporal describe / 图计数为准。
