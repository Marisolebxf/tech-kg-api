FROM node:22-alpine AS builder

WORKDIR /app

# Docker 构建默认使用阿里 npm 镜像，可通过 build arg 覆盖。
# 方案 B（构建一次、部署期注入）：镜像默认以哨兵 /__BASE__/ 构建，部署前缀由
# 启动脚本替换（docker/40-app-runtime-config.sh）；VITE_* 构建参数仅为本地 /
# compose 显式构建保留，生产构建不再传任何 VITE_*。
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG VITE_BASE=/__BASE__/
ARG VITE_API_BASE=
ARG VITE_GRAPH_SPACE=
ARG VITE_AUTH_ENABLED=
ARG VITE_PORTAL_EMBEDDED_DEFAULT=
ARG VITE_PORTAL_ALLOWED_ORIGINS=
ARG VITE_PORTAL_TARGET_ORIGIN=
ARG VITE_PORTAL_SOURCE=
# VITE_* 需对 build 与 docs:build 同时生效（docsite base 由 VITE_BASE 推导）
ENV npm_config_registry=${NPM_REGISTRY} \
    COREPACK_NPM_REGISTRY=${NPM_REGISTRY} \
    VITE_BASE=${VITE_BASE} \
    VITE_API_BASE=${VITE_API_BASE} \
    VITE_GRAPH_SPACE=${VITE_GRAPH_SPACE} \
    VITE_AUTH_ENABLED=${VITE_AUTH_ENABLED} \
    VITE_PORTAL_EMBEDDED_DEFAULT=${VITE_PORTAL_EMBEDDED_DEFAULT} \
    VITE_PORTAL_ALLOWED_ORIGINS=${VITE_PORTAL_ALLOWED_ORIGINS} \
    VITE_PORTAL_TARGET_ORIGIN=${VITE_PORTAL_TARGET_ORIGIN} \
    VITE_PORTAL_SOURCE=${VITE_PORTAL_SOURCE}

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Corepack 下载 pnpm 和 pnpm 安装项目依赖均使用上述镜像。
RUN corepack enable \
    && pnpm config set registry "${NPM_REGISTRY}"
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build
# 文档站（VitePress）产物写入 dist/docs/，随主应用产物一同拷入 nginx 镜像。
RUN pnpm docs:build

FROM nginx:1.27-alpine

# 部署期注入的环境变量（可用 k8s envFrom / docker run -e 覆盖）
ENV APP_BASE=/bkg_zpt

# nginx conf 模板：20-envsubst 启动期用 ${APP_BASE} 渲染到 conf.d/default.conf
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# 运行时配置注入：哨兵前缀替换 + 生成 runtime-config.js（在 envsubst 之后执行）
COPY docker/40-app-runtime-config.sh /docker-entrypoint.d/40-app-runtime-config.sh
RUN chmod +x /docker-entrypoint.d/40-app-runtime-config.sh

COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
