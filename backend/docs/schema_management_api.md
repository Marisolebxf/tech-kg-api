# Schema 管理服务 API

基础路径：`/api/v1/schema-management`。

写接口通过 `X-User-Id` 请求头识别当前用户。当前工程没有统一登录中间件；接入认证网关后，应由网关注入该请求头并清除客户端同名头，避免身份伪造。

## 页面所需接口

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/overview` | 当前 Schema 版本和页面顶部统计 |
| GET | `/schemas?kind=entity&keyword=&page=1&pageSize=20&includeDetails=true` | 类型目录、搜索、实体/关系筛选、属性定义和类型清单 |
| GET | `/schemas/topology` | Schema 拓扑节点和关系边 |
| GET | `/schemas/{id}` | 属性约束、来源映射、脚本元数据和删除权限 |
| POST | `/schemas/entities` | 新建实体 Schema 并上传 Python 脚本 |
| POST | `/schemas/relations` | 新建关系 Schema 并上传 Python 脚本 |
| PUT | `/schemas/{id}/script` | 为已有 Schema 上传或更换 Python 脚本 |
| GET | `/schemas/{id}/script` | 从 S3 下载关联 Python 脚本 |
| DELETE | `/schemas/{id}` | 删除当前用户创建的 Schema |

成功的 JSON 接口使用 `{code, success, data, msg}` 响应包装；参数、权限和冲突错误使用 FastAPI 的 `detail` 错误体及对应 HTTP 状态码。创建接口使用 `multipart/form-data`：

- `metadata`：JSON 字符串。
- `script`：必传 `.py` 文件，默认最大 10 MiB；服务会校验 UTF-8 编码和 Python 语法。

实体 `metadata` 示例：

```json
{
  "schemaKey": "technology",
  "name": "Technology",
  "label": "技术",
  "description": "技术实体",
  "properties": [
    {"name": "technology_id", "dataType": "string", "required": true, "rule": "全局唯一"}
  ],
  "mappings": ["technology_profile"],
  "isCore": false,
  "version": "v1.0"
}
```

关系 `metadata` 在上述公共字段外增加。`sourceExpression` 和 `targetExpression` 用于保留页面中的复合端点显示，例如 `Expert / Person`；用户新建关系时仍必须通过 ID 绑定到确定的实体 Schema：

```json
{
  "sourceSchemaId": "起点实体 Schema ID",
  "targetSchemaId": "终点实体 Schema ID",
  "sourceExpression": "Expert",
  "targetExpression": "Organization",
  "relationCategory": "fact"
}
```

实体名使用 `PascalCase`，关系名使用 `UPPER_SNAKE_CASE`。关系起点和终点必须引用已存在的实体 Schema。

## 删除规则

- `isSystem=true` 的系统原有 Schema 永远不可删除。
- 用户只能删除 `createdBy` 与当前 `X-User-Id` 一致的 Schema。
- 被任何关系引用的实体 Schema 不能直接删除，必须先删除引用关系。
- 删除成功后会清理关联的 S3 脚本对象；若对象清理失败，响应中的 `scriptCleanupSucceeded` 为 `false`，数据库删除仍然生效。

用户只能更换自己创建的用户 Schema 脚本。系统 Schema 不允许删除，但页面管理员可以为其上传或更新处理脚本；每次替换会在新对象和数据库关联提交成功后清理旧 S3 对象。

## 数据与对象存储

数据库表：

- `kg_schema_definition`：实体/关系主定义和所有权。
- `kg_schema_property`：属性及约束。
- `kg_schema_mapping`：来源映射。
- `kg_schema_script`：Schema 与 S3 对象的一对一关联。

运行 `uv run python script/init_schema_management.py` 可建表并初始化页面所需的 14 类实体、44 类事实关系和 9 类推理关系。初始化逻辑可重复运行，并会补齐新增字段、同步系统目录且保留已上传脚本。Docker Compose 默认设置 `SCHEMA_AUTO_INIT=true`，API 容器启动时会自动执行同一初始化逻辑。

脚本对象使用 boto3 标准 S3 客户端保存到独立 MinIO 服务，不使用 MinIO Python 客户端。MinIO API 默认暴露在宿主机 `9020`，控制台为 `9021`。
