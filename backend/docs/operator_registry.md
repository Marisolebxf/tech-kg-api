# 算子注册服务

## 统一接口

所有算子都使用同一个 Python 接口：

```python
def operator(data: list[dict], ctx: dict) -> list[dict]: ...
```

- `data`：待处理的 JSON 对象数组。
- `ctx`：本次调用参数、规则或已有实体/关系等上下文。
- 返回值：JSON 对象数组。返回其他类型时，本次调用返回 HTTP 422。

算子只划分为五类：

| kind | 用途 | 内置实现 |
|---|---|---|
| `data_processing` | 格式化、清洗、标准化 | `builtin.data_normalize` |
| `entity_extraction` | 实体抽取 | `builtin.entity_extract` |
| `relation_extraction` | 关系抽取 | `builtin.relation_extract` |
| `entity_ingestion` | 实体对齐、消歧、入库 | `builtin.entity_load` |
| `relation_ingestion` | 关系对齐、消歧、入库 | `builtin.relation_load` |

目前两个入库算子是规则占位实现，不写真实数据库。实体按主键、名称匹配，关系按
`source + target + type` 匹配，返回带 `_ingest.action` 的 `insert` 或 `merge` 计划。

## API

| 方法 | 路径 | 说明 |
|---|---|---|
| `GET` | `/api/v1/operators` | 查询算子，可用 `kind` 过滤 |
| `GET` | `/api/v1/operators/{name}` | 查询单个算子 |
| `POST` | `/api/v1/operators` | 上传新算子 |
| `PUT` | `/api/v1/operators/{name}` | 更新源码/版本并立即热加载 |
| `DELETE` | `/api/v1/operators/{name}` | 删除用户算子 |
| `POST` | `/api/v1/operators/{name}/invoke` | 调用算子 |
| `POST` | `/internal/operators/reload` | worker 显式重载 |

上传示例：

```bash
curl -X POST http://localhost:8000/api/v1/operators \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "user.add_score",
    "version": "1.0.0",
    "kind": "data_processing",
    "description": "给记录增加分数",
    "source": "def operator(data, ctx):\n    score = ctx.get(\"score\", 1)\n    return [{**item, \"score\": score} for item in data]\n"
  }'
```

调用示例：

```bash
curl -X POST http://localhost:8000/api/v1/operators/user.add_score/invoke \
  -H 'Content-Type: application/json' \
  -d '{"data": [{"name": "Alice"}], "ctx": {"score": 10}}'
```

## 热加载

注册表不把函数引用固化到工作流或 API 路由中。每次执行均按名称从注册表获取当前函数：

1. `POST`/`PUT` 通过 Python `boto3` 的 S3 API，把源码和 manifest 作为一个 JSON bundle
   写入 RustFS；单对象覆盖保证远端版本原子切换。
2. API/worker 从 RustFS 同步 bundle 到本地 `<name>.py` 和 `<name>.json` 执行缓存，随后替换注册表项。
3. 后台线程每 250 ms 检查 `OPERATOR_DIR` 文件快照，支持开发环境直接编辑本地缓存源码。
4. 每次调用前也检查文件快照，保证下一次调用不依赖监听线程是否及时调度。
5. 设置 `OPERATOR_WORKER_BASE_URIS` 后，控制面只广播重载信号；各 worker 通过 S3 API
   从同一个 RustFS bucket 拉取最新 bundle，不要求共享文件系统。
6. 新源码编译或加载失败时记录错误并保留上一版函数。

相关环境变量：

- `OPERATOR_DIR`：用户算子目录，默认 `/app/operators/user`（本地为 `backend/operators/user`）。
- `OPERATOR_S3_ENDPOINT_URL`：S3 endpoint；Compose 内为 `http://operator-rustfs:9000`。
- `OPERATOR_S3_BUCKET`：算子 bucket；未设置时回退为纯本地模式。
- `OPERATOR_S3_PREFIX`：bucket 内对象前缀，默认 `operators`。
- `OPERATOR_S3_ACCESS_KEY_ID` / `OPERATOR_S3_SECRET_ACCESS_KEY`：S3 凭据。
- `OPERATOR_S3_REGION`：签名 region，RustFS 默认使用 `us-east-1`。
- `OPERATOR_WORKER_BASE_URIS`：逗号分隔的 worker 基础地址。
- `OPERATOR_RELOAD_TOKEN`：设置后，内部重载端点必须携带同值的
  `X-Operator-Reload-Token` 请求头。

根 Compose 同时保留 Milvus 配套的 MinIO，并额外启动 `operator-rustfs`：

- RustFS S3 API：宿主机 `http://localhost:9020`
- RustFS Console：宿主机 `http://localhost:9021`
- RustFS 数据：`operator-rustfs-data` volume
- `operator-data` volume：仅保存 API 容器的本地执行缓存

Python 后端不使用 RustFS 专用 SDK，仍然使用标准 S3 API（`boto3.client("s3", ...)`）。

## 安全边界

上传的源码会在 API/worker 进程中执行，拥有该进程的系统权限。这一接口必须仅对受信任的管理员
开放，并在网关层配置认证、审计和请求大小限制。若后续需要接收不可信租户代码，应改用独立容器、
资源配额和网络隔离执行，不能把 Python 语法检查当作安全沙箱。
