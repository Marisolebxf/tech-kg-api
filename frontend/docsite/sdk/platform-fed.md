# 平台喂数模式（Schema 抽取）

> 来源：`backend/docs/kg_sdk.md` §9 · Schema 管理页「来源表绑定 + 触发抽取」

## 模式概览

在 Schema 管理页上传脚本并绑定来源表后，`POST /api/v1/schema-management/schemas/{id}/extract`
触发 `kg.schema.extract` 工作流。与自读库模式不同，**平台负责读源表与写图**，脚本只做转换：

```text
平台（按时间列水位分批读源表行）
   └─ payload["rows"] ──▶ workflow(payload)   ← 脚本：纯转换，返回实体/关系
                              └─ 返回 dict ──▶ 平台 merge_node / merge_edge 写图 + 推水位
```

- **入口签名不变**：仍是 `def workflow(payload)`（单参）或 step 双参约定；
- 脚本**不自读库、不自写图**——批次行由平台传入，写图由平台完成；
- 每张来源表独立水位（默认时间列 `update_time`），多表并行、单表内批次串行。

## 脚本返回格式

`props` 的键必须存在于 Schema 目录（未删除属性）；已删属性「插空」= 省略键即可。

```python
def workflow(payload):
    rows = payload["rows"]          # 本批行（JSON dict）
    table = payload["source_table"] # "库名.表名"
    kind = payload["kind"]          # "entity" | "relation"

    return {
        "entities": [
            {"id": row["id"], "props": {"id": row["id"], "name": row["name"]}},
        ]
    }
    # 关系改为：
    # return {"edges": [{"fromId": "S-1", "toId": "O-1", "props": {...}}]}
```

## 水位由平台管理

脚本返回的 `_watermark` / `_checkpoint` 元字段**被忽略**——平台按每批最大时间列值推进
`schema-extract-{schemaKey}` + `source:{绑定行 id}` 的独立水位。批次失败不推水位，
重跑时重读上次成功水位，重处理同一窗口（幂等语义与 step 水位一致）。

## 相关端点

| 端点 | 用途 |
|---|---|
| `PUT /api/v1/schema-management/schemas/{id}/sources` | 绑定来源表（数据源 + 库 + 表 + 主键列 + 时间列） |
| `POST /api/v1/schema-management/schemas/{id}/extract` | 触发平台喂数抽取（可带 `graphSpace` / `batchSize`） |
| `GET /mysql-datasources/{id}/tables?database=` | 列出可选表 |
| `GET /mysql-datasources/{id}/tables/{t}/columns?database=` | 列出列（选主键列 / 时间列） |
