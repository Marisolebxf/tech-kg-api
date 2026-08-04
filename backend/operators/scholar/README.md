# 学者领域算子模板

本目录存放学者领域 5 个批处理脚本的 **算子包装源码**，用于提交到工作流平台上执行。

每个 `.py` 文件都是一个符合 `def operator(data, ctx) -> list[dict]` 契约的算子，内部
通过 `from script.xxx import run` 复用现有脚本逻辑。设计上是"薄封装"——不改动脚本，
只把命令行参数转成 `ctx` 的键值。

## 5 个算子

| 算子名 | kind | 底层脚本 |
|---|---|---|
| `user.scholar.load_entities` | `entity_extraction` | `script.load_scholar_entities` |
| `user.scholar.load_relations` | `relation_extraction` | `script.load_scholar_relations` |
| `user.scholar.build_milvus_index` | `data_processing` | `script.build_scholar_milvus_index` |
| `user.scholar.align_affiliations` | `entity_ingestion` | `script.align_scholar_affiliations` |
| `user.scholar.dedupe_persons` | `entity_ingestion` | `script.dedupe_scholar_persons` |

## 提交到工作流平台

一次性批量注册：

```bash
uv run python -m script.register_scholar_operators
```

该脚本会：
1. 读取本目录 5 个 `.py` 文件
2. 通过 `POST /api/v1/operators`（不存在时）或 `PUT /api/v1/operators/{name}`（已存在时）
   写入算子注册表
3. 执行一次 `dry_run` 调用做冒烟测试

也可以在任务中心页面手动粘贴单个 `.py` 文件内容作为"提交你的 Python 脚本"。

## 调用示例

```bash
curl -X POST http://127.0.0.1:8000/api/v1/operators/user.scholar.load_entities/invoke \
  -H 'Content-Type: application/json' \
  -d '{"data": [], "ctx": {"dry_run": true, "database": "gkx_element"}}'
```

## ctx 参数速查

| 算子 | ctx 键 | 默认值 | 说明 |
|---|---|---|---|
| load_entities | `database` | `"gkx_element"` | MySQL 数据库名 |
| load_entities | `dry_run` | `true` | 只统计不写图 |
| load_relations | `database` | `"gkx_element"` | MySQL 数据库名 |
| load_relations | `dry_run` | `true` | 只统计不写图 |
| load_relations | `include_authored_by_fallback` | `false` | 是否补 AUTHORED_BY 兜底边 |
| build_milvus_index | `dry_run` | `true` | 只统计不写 Milvus |
| build_milvus_index | `drop_existing` | `false` | 是否重建集合 |
| build_milvus_index | `preview` | `5` | 预览样本数 |
| align_affiliations | `dry_run` | `true` | 只统计不写 SAME_AS 边 |
| align_affiliations | `top_k` | `5` | Milvus 检索候选数 |
| align_affiliations | `min_score` | `0.65` | 融合分阈值 |
| dedupe_persons | `dry_run` | `true` | 只统计不写 |
| dedupe_persons | `write` | `false` | 高置信对是否写 SAME_AS |
| dedupe_persons | `top_k` | `5` | Milvus 检索候选数 |
| dedupe_persons | `high_threshold` | `0.75` | 高置信阈值 |
| dedupe_persons | `mid_threshold` | `0.55` | 疑似阈值 |
| dedupe_persons | `report_path` | 时间戳 | JSON 报表输出路径 |
