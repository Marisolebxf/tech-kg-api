# 外部业务方凭证管理

本系统为每个业务方分配 `client_id` 和 API Key，调用方通过 `X-Client-Id` 与 `X-API-Key` 两个 Header 调用 `POST /api/v1/kg-service/project-relations/query`。本功能独立于统一用户中心；原 Bearer/Cookie 认证继续兼容。

本文说明代码的接入与操作方式，不代表目标环境已经部署或完成验收。

## 凭证与权限

- `external_api_client` 表保存在应用业务 MySQL 中，连接沿用 `MYSQL_HOST`、`MYSQL_PORT`、`MYSQL_DATABASE`、`MYSQL_USERNAME`、`MYSQL_PASSWORD` 配置。
- 管理员按业务方分配唯一 `client_id`，不由调用方随意填写。创建时登记业务方名称并授予 `project-relations:read`，仅允许项目关系查询。
- API Key 使用 32 字节安全随机数生成，数据库仅保存 SHA-256 哈希值，不保存可恢复的明文。原始 Key 只在创建或轮换时输出一次，遗失后需轮换。
- 默认有效期为 90 天，可在签发或轮换时通过 `--expires-days` 指定。不要把生产 Key 放入源码、工单正文或请求日志。
- 携带任意一个 API Key Header 就进入 API Key 校验；缺失配对 Header 或认证失败不会尝试 Bearer/Cookie。未携带这两个 Header 时沿用原认证流程。
- 正式对外接入配置 `AUTH_ENABLED=true`。关闭登录是开发用途，会影响不携带 API Key Header 的请求，不能作为接口访问控制。

## 管理命令

命令应在运行后端的 Docker 容器内、工作目录 `/app` 执行，使用该容器配置的业务数据库。以下 `python` 指后端虚拟环境解释器；现有容器通常为 `.venv/bin/python`。

首次上线先初始化凭证表：

```bash
python -m script.manage_external_api_clients init
```

为业务方创建凭证（示例标识需替换成实际业务方）：

```bash
python -m script.manage_external_api_clients create \
  --client-id partner_project_a \
  --business-name '项目业务系统 A' \
  --expires-days 90
```

将输出的 `client_id`、原始 API Key 和接口文档交给指定调用方，并按本次 `--expires-days` 告知有效期（从签发时起计算，默认 90 天）。调用方将凭证配置在自己的后端，并在每次请求中携带；不需要获取用户登录 Token。

轮换凭证：

```bash
python -m script.manage_external_api_clients rotate \
  --client-id partner_project_a \
  --expires-days 90
```

轮换提交后旧 Key 立即失效，没有双 Key 过渡期，应与调用方协调更新时间。轮换不会自动启用已经停用的业务方。

停用业务方：

```bash
python -m script.manage_external_api_clients disable \
  --client-id partner_project_a
```

停用后后续 API Key 请求返回 401。当前 CLI 不提供启用命令，也不提供公网自助发 Key 接口。

现有 dev2 容器的初始化调用形式为：

```bash
docker exec -w /app tech-kg-api-dev2 .venv/bin/python -m script.manage_external_api_clients init
```

创建、轮换和停用时采用同样的容器命令前缀。上线顺序为部署包含本功能的后端镜像、初始化表、创建业务方凭证、使用新凭证验收查询。

## 接入与验收

完整请求和业务响应见 [项目关系查询接口](project_relations_api.md)。调用方应同时检查 HTTP 状态码与响应 JSON 的 `success` / `code`，因为现有参数校验错误使用 HTTP 200、`code=422`。

| 场景 | HTTP 状态码 |
|---|---:|
| 两个 Header 匹配、未过期、未停用且具有查询权限 | 查询按业务结果返回 |
| Header 缺失配对项、错误 Key、过期或停用 | 401 |
| 凭证有效但缺少 `project-relations:read` | 403 |
| 认证数据库异常或表尚未初始化 | 503 |

部署验收应覆盖有效凭证查询与翻页、错误凭证、缺一个 Header、轮换后旧 Key 失效、停用后拒绝，以及原 Bearer/Cookie 兼容。错误 API Key 与有效 Bearer 同时携带时也应拒绝。认证数据库故障应返回 503，不应跳过认证。
