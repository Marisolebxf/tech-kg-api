# 关系抽取与写入

> 来源：`docs/script-sdk/relations.html`

`EdgeRecord` → 两条写入通道（确定性 rank / REST merge）· 端点验存 · schema 幂等补齐。

## EdgeRecord

```python
@dataclass(frozen=True)
class EdgeRecord:
    edge_type: str                  # 如 "AUTHORED_BY"
    source_vid: str                 # 起点 VID（实体侧公式）
    target_vid: str
    properties: dict[str, Any]
    rank: int | None = None         # 非 None → rank 通道
    identity: dict | None = None    # merge 通道 identityProps
    source_tag / target_tag: str | None = None   # 端点验存 tag
    validate_endpoints: bool = True
```

两条铁律：

1. **关系脚本一律不建顶点**。实体先行（先跑对应实体脚本），端点缺失的边跳过并计数——把「点不存在」从数据问题变成可观测统计。
2. **端点 VID 必须用实体侧同一套公式**（import 自 `common` / `resolvers`）。

## 两条写入通道怎么选

| | 确定性 rank 通道 | REST merge 通道 |
|---|---|---|
| 触发条件 | `rank` 非 `None`（`rank=edge_rank(...)`；固定 `rank=0` 表示同端点唯一边） | `rank is None`（默认） |
| 幂等身份 | `(edge_type, src, dst, rank)`，rank 由 sha256 确定性生成 | `identityProps`（默认 `source_record_id`） |
| 底层语句 | 渲染多值 nGQL `INSERT EDGE T (props) VALUES "a"->"b"@rank:(...)` 批量执行 | 逐条 `graph.merge_edge(src, dst, type, identity, props)` |
| 适合 | 同一对端点可有多条不同源边（股东、投资、高管任职） | 按源记录唯一确定的边（论文-作者、项目-资助机构） |

```python
# rank 通道：同端点多条边，每条对应一个源记录
EdgeRecord("SHAREHOLDER_OF", person_vid, org_vid, props,
           rank=edge_rank("SHAREHOLDER_OF", person_vid, org_vid, rec_id))

# rank=0：同端点逻辑上唯一（覆盖更新）
EdgeRecord("AUTHORED_BY", paper_vid, person_vid, props, rank=0)

# merge 通道：按 source_record_id upsert
EdgeRecord("FUNDED_BY", project_vid, org_vid, props,
           source_tag="Project", target_tag="Organization")
```

**批量 INSERT 的属性签名约束**：rank 通道按 `(edge_type, 属性名元组)` 分组渲染多值 INSERT——同一批的记录必须**属性键完全一致**（顺序也一致）。属性集固定的 mapper 天然满足；动态拼属性键的 mapper 会被 `render_edge_insert` 拒绝。merge 通道没有此约束。

## 端点验存与悬空端点

标上 `source_tag` / `target_tag` 后，写入前按 tag 分组批量验存（一条 MATCH 查回已存在的 vid 集合），端点不在图中的边跳过并计数：

```python
write_edges([...])
# → {"scanned": 300, "written": 287, "missing_source": 9, "missing_target": 4, "dry_run": 0}
```

旧口径里存在**合法的悬空端点**——端点是「桩点」（由别的域负责建、或永远不建）：`AFFILIATED_WITH` 的机构名桩、论文 DOI 桩。这类边把 `validate_endpoints=False`：

```python
EdgeRecord("PUBLISHED_IN", paper_vid, paper_stub_vid("journal", issn), props,
           validate_endpoints=False)
```

端点解析器（`relation_extractors_one_relation/resolvers.py`）与实体侧同一套 VID 公式——边端点算出的 VID 必须与实体脚本写点时一致，否则验存永远 miss。常用：`keyword_vid`（三域统一 keyword 公式）、`paper_source_id`（论文 ID 去 `__数字` 后缀）、`ExactOrganizationResolver`（机构名 → org_id，仅精确匹配且唯一时成功）。

## ensure_edge_schema：属性幂等补齐

merge 接口对 schema 外属性返回 400（同 Tag 一样 `Unknown column`）。写边前 `DESCRIBE EDGE` 一次，缺的属性幂等 `ALTER EDGE ADD`（等 2 秒传播），返回本次补的列名：

```python
from script.relation_extractors_one_relation.common import (
    ensure_edge_schema, graph_client,
)

EDGE_SCHEMA = {
    "source_table": "string",
    "source_record_id": "string",
    "ingest_batch": "string",
    "ingest_time": "string",
    "funded_amount": "double",
    "confidence": "double",
    "match_method": "string",
    "match_evidence": "string",
}
graph = graph_client()
try:
    if not dry_run:
        ensure_edge_schema(graph, "FUNDED_BY", EDGE_SCHEMA)
finally:
    graph.close()
```

`DESCRIBE EDGE` 失败（边类型不存在/权限）时告警并跳过，不中断。**Edge 类型本身不存在时需先 `CREATE EDGE`**（各 `init_*_schema.py` 的职责），本函数只补属性列。

## write_edges 行为与统计

`write_edges(records, *, dry_run) -> dict[str, int]`：

1. `dry_run` → 只统计。
2. 端点验存：按 tag 批量查已有 vid；缺失端点的边计 `missing_source` / `missing_target` 并剔除。
3. rank 通道按 `(edge_type, 属性签名)` 分组，每组渲染一条多值 `INSERT EDGE`。
4. merge 通道逐条 `merge_edge`，identity 缺省取 `properties["source_record_id"]`——所以 **merge 通道的 properties 必须含 `source_record_id`**。
