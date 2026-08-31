# 实体抽取与写入

> 来源：`docs/script-sdk/entities.html` · `docs/script-sdk/provenance.html`

`EntityRecord` → `merge_node` upsert，机构域额外享受「已有节点属性合并保护」。

## EntityRecord

```python
@dataclass(frozen=True)
class EntityRecord:
    tag: str                        # graph Tag，如 "Person"
    vid: str                        # 确定性 VID（见「标识与值语义」）
    properties: dict[str, Any]      # 含溯源 + extra_json
    merge_protect: bool = False     # 机构域置 True
    identity: dict | None = None    # merge_node 匹配键，缺省 {"vid": vid}
```

- **tag**：目标 Tag 名。写入前 Tag 必须已存在（用 nGQL `CREATE TAG` / `init_*_schema.py` 建好）；属性名必须**完全匹配 Tag schema**——传 schema 外的列会收到 `400 SemanticError: Unknown column`。
- **identity**：除了 vid 还想参与 upsert 匹配时传。
- **merge_protect**：机构域实体置 `True`，写入前先读已有节点做合并保护。

## write_records 写入路径

```python
write_records(records: list[EntityRecord], *, dry_run) -> dict[str, int]
# 逐条 merge_node upsert；dry_run 不建连接只统计
# {"scanned": 500, "written": 498, "updated": 2, "dry_run": 0}
```

写图前按 `merge_protect` 分 Tag 批量读回已有节点属性；批量写发生在主流程攒够 `batch_size` 条时，连接批内建、批末关。典型调用方是 `run_entity_extractor`，手写循环时才直接调 `write_records`。

## 机构域 merge 保护

机构域一份数据可能来自多张表（基本信息、上市公司信息、港股信息…），直接 upsert 会用稀疏行把已有完整属性冲掉。`merge_protect=True` 的记录走 `merge_existing_properties(existing, incoming)`：

| 规则 | 行为 |
|---|---|
| 标准属性 | **只填空，不覆盖**：已有非空值保留 |
| `confidence` | **只升不降** |
| `extra_json` | **多源累积**：已有 `source_records` 按 `table:record_id` 键合并新源行 |
| 无变化 | 不发起写入（避免无效写放大） |

```python
# 已有：{"name_cn": "华为", "confidence": 0.9}
# 新行：{"name_cn": None, "confidence": 0.7, "extra_json": "{...}"}
merge_existing_properties(existing, incoming)  # → {}，整体跳过
```

更新时携带全部已有非空属性 + 增量变更一起写，防稀疏行冲掉 canonical 字段。`bounded_json` 降级出的审计摘要合并时会被完整源行取代——摘要只是属性上限不够时的临时形态。

## None 属性与字符串化

写入前所有记录过 `_drop_null_props`：

- `None` 值属性**直接丢弃**（机构域「空白→NULL→省略属性」口径的落图形态；Nebula 不写该列即视为 NULL）。
- 非字符串值**显式 `str()`**——trs-graph REST 对 string 列做严格类型校验，传 int/float 会 `400 Storage Error: data type does not meet the requirements`。

**mapper 里不要预判类型**：数值属性按源口径给 float/int 即可，字符串化由写入层统一做。

## 溯源与置信度

每个点、每条边自带「从哪来、什么时候进的、可信到什么程度」——落图即审计。溯源属性与业务属性平级落图：

| 属性 | 含义 |
|---|---|
| `source_system` / `source_table` / `source_record_id` | 源系统 / 源表 / 源记录主键或稳定键 |
| `source_url` | 源记录原始链接 |
| `ingest_batch` / `ingest_time` | 写入批次号（`ENTITY_20260828T093000Z`）/ 写入时间 |
| `source_update_time` | 源行更新时间（增量水位对账依据） |
| `confidence` | 置信度 [0, 1] |
| `match_method` / `match_evidence` | 端点匹配方式与证据（匹配类边） |

三个溯源构造器：

```python
provenance(*, table, record_id, ingest_batch, source_url=None,
           source_update_time=None, confidence=1.0, source_system="gkx_element")
# 实体通用（match_method 固定 source_primary_key、主键直抽 confidence=1.0）

org_provenance(*, table, record_id, row, ingest_batch)
# 机构域：自动取 ID 候选链、entity_confidence 动态打分、URL/时间候选链

edge_provenance(*, source_table, source_record_id, ingest_batch)
# 边最小四件套；confidence/match_method/match_evidence 自行并入
```

`entity_confidence(row)` 四段累加后 clamp 到 [0,1]：DWD 溯源表基线 0.40 / 其他 0.30，有机构 ID +0.20，有外部标识 +0.10，有展示身份 +0.20，有地域/时间 +0.10。典型：DWD 全量字段 = 1.0，只有名字的资讯行 ≈ 0.7。

## mapper 实战示例

签名约定：`mapper(table: str, row: Mapping, batch: str) -> list[EntityRecord]`，返回 `[]` 表示这一行不产出。

```python
# 机构域：动态置信度 + 复合稳定键 + merge 保护
def organization_node(table, row, batch):
    org_id = organization_id_from_row(row)
    if org_id is None:
        return []
    props = {
        **organization_props(row),
        **org_provenance(table=table, row=row,
                         record_id=stable_record_id(table, row, ("org_id", "year")),
                         ingest_batch=batch),
    }
    return [EntityRecord("Organization", organization_vid(org_id), props,
                         merge_protect=True)]
```
