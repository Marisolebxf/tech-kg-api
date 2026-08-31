# API 速查表

> 来源：`docs/script-sdk/reference.html` · `backend/sdk/kg_sdk.py` · `backend/sdk/access.py`

缩写：**E** = `script/entity_extractors_one_entity/common.py`，**R** = `script/relation_extractors_one_relation/common.py`（两份语义相同）。

## kg_sdk（运行时）

| API | 说明 |
|---|---|
| `Context(raw)` | 运行上下文；五客户端懒构造、None 降级 |
| `ctx.mysql / graph / milvus / llm / embedding` | 懒构造客户端属性，未配置返回 `None` |
| `ctx.config` | `ScriptConfig(watermark, checkpoint)`（只读） |
| `ctx.step_id / attempt / prev_outputs / execution_id / task_id / definition_id` | 调度元信息 |
| `ctx.to_dict()` | 原始注入 dict（调试） |
| `current_context()` | 单参脚本入口：读 `KG_SCRIPT_CTX` 构造 Context，未配置返回 `None` |
| `reset_current_context()` | 测试用：清缓存 |
| `access_report()` / `reset_access_report()` / `flush_access_sidecar()` | 数据访问溯源（见[观测页](/sdk/observability)） |

## 运行时与环境（E / R 各一份）

| API | 说明 |
|---|---|
| `configure_logging(level)` | basicConfig + httpx 压 WARNING |
| `mysql_engine(database="gkx_element")` | env 驱动 Engine（pool_pre_ping）；ctx 场景改用 `ctx.mysql.engine` |
| `graph_client()` | env 驱动 TRSGraphClient（自动 connect）；ctx 场景用 `ctx.graph` |
| `build_parser(description)` | 通用 7 参数 argparse（log-level/database/batch-size/limit/since/dry-run/ingest-batch） |
| `common_args_from_payload(payload)` | workflow payload → 同形态参数 dict（build_parser 的镜像） |
| `print_json(payload)` | ensure_ascii=False 缩进输出 |
| `now_utc()` | UTC ISO 秒级时间戳（仅 R） |

## 读取与增量

| API | 说明 |
|---|---|
| `iter_rows(engine, sql, *, batch_size, limit, cursor_column, params)` | 分页迭代器：默认 LIMIT/OFFSET，指定 `cursor_column` 走 keyset（SQL 需含 `:cursor` + 唯一排序） |
| `apply_since(sql, since, col="updated_time")` | 增量条件注入（兼容无 WHERE / 有 WHERE / ORDER BY 末位三种形态） |

## 值语义（E.common）

| API | 口径 | 说明 |
|---|---|---|
| `text_or_empty(v)` | 原文 | `str(v) if v else ""`，保留原文 |
| `str_or_empty(v)` | 专利 | 仅 `None` → `""` |
| `paper_text(v)` | 论文 | text_or_empty + 换行转空格 |
| `date_text(v)` / `datetime_text(v)` | 项目/专利 | 日期 → ISO 文本 |
| `text_or_none(v, max_length=20000)` | 机构 | strip + 截断，空白 → `None` |
| `clean_text(v)` | 内部键 | strip + 折叠空白（VID/键专用） |
| `to_float_or_none(v)` / `to_int_or_none(v)` | 机构 | 脏值防御转换，非法 → `None` |
| `to_float_or_zero(v)` / `to_int_or_zero(v)` | 项目 | 非法 → `0` |
| `parse_json(v)` | 专利 | 字符串尝试 `json.loads`，失败原样 |
| `json_snapshot(v)` / `original_text(v)` / `normalized_language(v)` | 专利 | JSON 快照 / 元素 text 连接 / 数组逗号串 |
| `compact_json(v)` / `bounded_json(v, max_length=64000)` | 机构 | 紧凑序列化 / 超长降级审计摘要 |
| `json_safe(v)` / `normalize_json(v)` | 通用 | 递归可序列化 / 标量归一 |
| `extra_json(row)` | 通用 | 整行源数据快照 |
| `first_value(row, *names)` / `first(row, *fields)` | 机构/新 | 字段候选链取首个非空 |
| `is_virtual_source_row(row)` | 机构 | mock/stub/virtual/placeholder/test 合成行识别 |

## VID 与稳定键（E.common）

| API | 说明 |
|---|---|
| `bounded_vid(value, max_bytes=64)` | 64 字节安全阀：超限截断 + md5 后缀 |
| `md5_hex(v)` / `normalize_key(v)` / `md5_vid(prefix, v, short=True)` | 哈希基础件 |
| `organization_vid(org_id)` / `project_vid(id)` / `news_vid(id)` | 主键直拼族 |
| `event_vid(table, record_id)` / `datasource_vid(table)` | 表名入键族 |
| `person_vid(kind, *identity)` / `product_vid(name)` | 复合身份哈希族 |
| `stable_record_id(table, row, preferred_fields)` | 复合键优先、整行 JSON md5 兜底 |
| `source_record_id(row, *fields)` | 候选链版稳定键（sha256 前 24 位兜底） |
| `edge_rank(type, src, dst, rec_id)` / `stable_rank(v)` | 边的确定性 rank（R.common） |

## 端点解析（R.resolvers）

| API | 说明 |
|---|---|
| `keyword_vid(keyword)` | 三域统一 keyword VID |
| `paper_source_id(raw)` | 论文 ID 去 `__数字` 后缀 |
| `paper_stub_vid(prefix, key)` | md5 桩 VID（悬空端点用） |
| `ExactOrganizationResolver.load(engine)` / `.resolve_exact(name)` | 机构名精确唯一解析（7 表名→id 索引） |
| `resolved_organization_vid(raw, resolver, fallback_name=)` | 名解析优先，否则视值为 ID |
| `organization_vid_from_row(row, resolver, ...)` | ID 候选链 + 名解析 |
| `person_vid_for_row(row, kind, name_field)` | 实体侧 Person 公式的 row 版 |
| `parse_entity_list(v)` | 容错解析实体列表字段 |

## 溯源与置信度

| API | 说明 |
|---|---|
| `provenance(*, table, record_id, ingest_batch, ...)` | 实体通用溯源（match_method 固定 `source_primary_key`） |
| `org_provenance(*, table, record_id, row, ingest_batch)` | 机构域溯源（动态置信度 + URL/时间候选链） |
| `edge_provenance(*, source_table, source_record_id, ingest_batch)` | 边最小溯源四件套（R.common） |
| `entity_confidence(row, source_table=)` | 机构域实体四段打分 |
| `relation_confidence(row, source_table=)` | 机构域关系打分 |
| `organization_id_from_row(row)` / `ORGANIZATION_ID_FIELDS` | 机构 ID 七字段候选链 |

## 实体写入（E.common）

| API | 说明 |
|---|---|
| `EntityRecord(tag, vid, properties, merge_protect=False, identity=None)` | 实体记录 |
| `write_records(records, *, dry_run)` | 批量 merge_node（merge_protect 分组读已有节点） |
| `merge_existing_properties(existing, incoming)` | 机构域合并保护（只填空 / confidence 只升 / extra_json 累积） |
| `existing_vertex_properties(graph, tag, vids)` | 批量读已有节点属性 |
| `run_entity_extractor(*, database, batch_size, limit, dry_run, ingest_batch, sources, since, global_limit, dedupe, cursor_column, extra_params)` | 实体主流程 |

## 关系写入（R.common）

| API | 说明 |
|---|---|
| `EdgeRecord(edge_type, source_vid, target_vid, properties, rank=None, identity=None, source_tag=None, target_tag=None, validate_endpoints=True)` | 关系记录 |
| `write_edges(records, *, dry_run)` | 端点验存 + 双通道写入 |
| `ensure_edge_schema(graph, edge_type, properties, wait_seconds=2.0)` | 属性幂等补齐（DESCRIBE → ALTER EDGE ADD） |
| `run_relation_extractor(...)` | 关系主流程（参数同实体版减 global_limit） |

## 常见错误对照

| 现象 | 原因 | 处置 |
|---|---|---|
| `400 SemanticError: Unknown column 'X' in schema` | 点/边属性名不在 Tag/Edge schema 里 | 用 `DESCRIBE TAG/EDGE` 核对；边用 `ensure_edge_schema` 补列 |
| `400 Storage Error: data type does not meet the requirements` | REST 传了 int/float 给 string 列 | 写入层已统一 `str()`；mapper 不要预判类型 |
| 写入报 VID 超长 | 自定义 VID 超 64 字节 | 公式外套 `bounded_vid(...)` |
| 重跑后点数翻倍 | VID 不确定性（uuid/行号） | 改用源主键或复合身份哈希公式 |
| 边大量 `missing_source/target` | 实体脚本没先跑，或端点公式与实体侧不一致 | 先跑实体；端点 VID 用 `resolvers` 同一套公式 |
| 属性被稀疏行冲掉 | 机构域多表未开 merge 保护 | `EntityRecord(..., merge_protect=True)` |
