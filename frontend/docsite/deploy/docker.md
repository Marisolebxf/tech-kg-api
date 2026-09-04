# Docker 部署

> 来源：`docker-compose.yml` · `docker-compose.dev2.yml` · `frontend/Dockerfile` · `CLAUDE.md`

## 两套 compose 栈

| | 生产 `docker-compose.yml` | dev2 `docker-compose.dev2.yml` |
|---|---|---|
| api | `api`，host **8001** → 8000 | `tech-kg-api-dev2`，host **8002** → 8000 |
| web | `web`，host **8088** → 80 | `tech-kg-web-dev2`，host **8089** → 80 |
| Temporal | 外部 | `temporal-dev2` + `temporal-mysql-dev2` 自带 |
| MySQL | **不创建**——期望 engine 网络上的外部 `mysql` 服务（已载 `gkx_element`），或 `MYSQL_HOST` 指向宿主库 | 容器内只解析 `temporal-mysql-dev2`，不解析生产的 `temporal-mysql` |
| nginx upstream | `api:8000`（`nginx.conf`） | `api-dev2` + resolver（`nginx.dev2.conf`） |

基础设施工件（Milvus + etcd、共用一个 RustFS S3 承载 schema 脚本 / operator 包 / Milvus 内部存储、m3e-embedding、auth-redis、Temporal）都在生产 compose 里。Milvus 用专用端口避开宿主 `tech-kg-engine` 的 Milvus：SDK `19531`、健康 `9093`；RustFS S3 宿主端口 `9020` / 控制台 `9021`。

::: warning 端口冲突
8001/8088 被占时改 compose 里的 host 端口，**不要**停其他服务腾端口。
:::

## 前端镜像（两阶段）

```dockerfile
FROM node:22-alpine AS builder   # corepack + pnpm install → pnpm build → pnpm docs:build（本文档站）
FROM nginx:1.27-alpine           # dist + dist/docs → /usr/share/nginx/html；nginx.conf
```

- builder 阶段构建参数：`NPM_REGISTRY`（默认 npmmirror 阿里镜像）、`VITE_BASE`、`VITE_API_BASE` 等（完整列表见[环境变量](/deploy/env)）；
- 文档站 VitePress 产物落在 `dist/docs/`，nginx 现有 `try_files $uri $uri/ /index.html` 直接服务 `/docs/`，无需额外 location；
- 生产 nginx 反代 `/api/` → `http://api:8000`；静态资源 7 天缓存；CSP 只限 `frame-ancestors`。

## 常用命令

```bash
# dev2 全栈
docker compose -f docker-compose.dev2.yml up -d --build

# 只重建前端（含 typecheck：builder 阶段跑 vue-tsc -b && vite build）
docker compose -f docker-compose.dev2.yml build web-dev2

# 后端测试（容器内，见「测试约定」页）
docker exec -w /app tech-kg-api-dev2 .venv/bin/python -m pytest tests -m "not external" -q
```

## 本地开发入口注意

前端 5174 端口的 dev server 跑的可能是**另一份 0827 代码副本**而非本仓库 dev2——改前端「没生效」时先确认访问的是哪个入口。
