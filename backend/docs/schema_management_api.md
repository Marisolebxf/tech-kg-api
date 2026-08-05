# Schema 管理服务 API

基础路径：`/api/v1/schema-management`。

## 接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/overview` | Schema 目录统计 |
| GET | `/schemas` | 分页、搜索和类型筛选 |
| GET | `/schemas/topology` | Schema 拓扑 |
| GET | `/schemas/{id}` | Schema、属性、来源映射和脚本元数据 |
| POST | `/script-validations` | 上传到隔离区并启动脚本安全校验 |
| GET | `/script-validations/{id}` | 查询脚本安全校验状态 |
| GET | `/script-validations/{id}/events` | 通过 SSE 订阅校验进度 |
| POST | `/schemas/entities` | 创建实体 Schema 并上传脚本 |
| POST | `/schemas/relations` | 创建关系 Schema 并上传脚本 |
| PUT | `/schemas/{id}/script` | 替换脚本 |
| GET | `/schemas/{id}/script` | 下载脚本 |
| POST | `/schemas/{id}/execute` | 绑定当前脚本版本并提交 Temporal 执行 |
| DELETE | `/schemas/{id}` | 删除用户 Schema |

写入和执行接口使用 `X-User-Id`。当前服务不验证该头的真实性；生产网关必须删除客户端自带值，再注入认证后的用户 ID。

## 响应

成功和错误都使用：

```json
{"code": 200, "success": true, "data": {}, "msg": "success"}
```

错误返回真实 HTTP 状态码，不再使用 FastAPI 裸 `detail`：脚本错误 `400`、权限错误 `403`、不存在 `404`、名称或引用冲突 `409`、参数错误 `422`、对象存储错误 `502`。

## 创建 Schema

前端上传统一使用 `POST /script-validations`，请求为 `multipart/form-data`：

- `operation`：`replace`、`create_entity` 或 `create_relation`。
- `schemaId`：更换已有脚本时必填。
- `metadata`：JSON 字符串。
- `script`：UTF-8 `.py` 文件，默认最大 10 MiB，并进行 Python 语法校验。

接口返回 HTTP 202 及 `eventsUrl`。浏览器使用
`GET {eventsUrl}?userId={当前用户}` 建立 `text/event-stream` 连接，事件为：

- `status`：静态检查、LLM 审查、保存中的阶段状态；
- `completed`：审查通过且 Schema/脚本已经保存；
- `failed`：审查或保存失败，`issues` 给出风险等级、行号、原因和修复建议。

校验按以下顺序执行：隔离上传 → 文件/语法检查 → 确定性危险能力静态检查 →
LLM 全量代码安全审查 → 正式对象存储和数据库持久化。任一步失败都不会覆盖正式脚本。
未配置 LLM 或 LLM 返回不可解析结果时采用 fail-closed 策略。

实体示例：

```json
{
  "schemaKey": "technology",
  "name": "Technology",
  "label": "技术",
  "properties": [
    {"name": "technology_id", "dataType": "string", "required": true, "rule": "全局唯一"}
  ],
  "mappings": ["technology_profile"],
  "version": "v1.0"
}
```

实体名使用 `PascalCase`。关系名使用 `UPPER_SNAKE_CASE`，并必须通过 `sourceSchemaId` 和 `targetSchemaId` 引用已有实体 Schema。

## 执行 Schema 脚本

脚本必须提供 `transform(payload)`：

```python
def transform(payload):
    return {"normalized": payload}
```

请求：

```http
POST /api/v1/schema-management/schemas/{id}/execute
X-User-Id: user-a
Content-Type: application/json

{"payload": {"technology_id": "T-001"}}
```

响应为 HTTP `202`，包含 `taskId`、`executionId`、`workflowId` 和 `statusUrl`。

提交时会把以下不可变引用写入 execution payload：

- Schema ID、key 和类型；
- S3 bucket 与 object key；
- 脚本 sha256；
- 用户 payload。

Temporal Worker 的 `kg.schema.execute` Workflow 下载该对象，在 Activity 子进程中调用 `transform(payload)`。因此后续替换脚本不会改变已经提交的 execution 所绑定版本。

转换完成后，`persist_schema_result` Activity 会：

- 根据 Schema 属性创建缺失的 TAG 或 EDGE；
- 实体 Schema 接受对象、对象数组或 `{items: [...]}`，按 `identityKey`（回退 `vid/id/name`）合并节点；
- 关系 Schema 要求 `sourceId`、`targetId`，确认端点存在后创建边；
- 返回 `nodeIds` 或 `edgeIds` 及持久化数量。

脚本只负责转换，图数据库连接和写入完全由受控 Activity 执行。

用户只能执行自己创建的用户 Schema；Schema 管理员可以执行任意 Schema；已认证用户可以执行系统 Schema。

## 所有权和删除

- 系统 Schema 不可删除。
- 用户只能更换或删除自己创建的 Schema。
- Schema 管理员可以更换系统 Schema 脚本。
- 被关系引用的实体 Schema 必须先删除引用关系。
- 数据库删除成功但 S3 清理失败时，`scriptCleanupSucceeded=false`，便于后续清理孤儿对象。

## 存储

数据库表：

- `kg_schema_definition`
- `kg_schema_property`
- `kg_schema_mapping`
- `kg_schema_script`
- `kg_schema_script_validation`

初始化：

```bash
uv run python script/init_schema_management.py
```

脚本使用标准 S3 API 存储，配置项为 `SCHEMA_S3_*`。上传脚本和 Schema 执行都是高风险能力，生产环境必须增加角色授权、审计、限流、请求体限制，并把 Worker 放入受限运行环境。

## 本地真实 LLM 测试

默认测试使用模拟 LLM，不产生外部调用。真实 LLM 用例同时带有 `external` 标记和显式开关，
CI 中设置 `RUN_REAL_LLM_TESTS=false`，不会运行。

本地配置 `LLM_API_KEY` 后执行：

```bash
RUN_REAL_LLM_TESTS=true PYTHONPATH=. uv run pytest \
  tests/integration/test_schema_script_security_llm_external.py -m external -v
```

可通过 `SCHEMA_SCRIPT_LLM_MAX_CHARS` 调整单个脚本接受完整 LLM 审查的最大字符数，
默认 60000；超过上限会拒绝保存，避免只审查脚本片段。
