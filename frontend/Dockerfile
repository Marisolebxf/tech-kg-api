FROM node:22-alpine AS builder

WORKDIR /app

# Docker 构建默认使用阿里 npm 镜像，可通过 build arg 覆盖。
ARG NPM_REGISTRY=https://registry.npmmirror.com
ARG VITE_BASE=./
ARG VITE_API_BASE=/api
ARG VITE_AUTH_ENABLED=false
ARG VITE_PORTAL_EMBEDDED_DEFAULT=false
ARG VITE_PORTAL_ALLOWED_ORIGINS=https://edu.itic-sci.com
ARG VITE_PORTAL_TARGET_ORIGIN=https://edu.itic-sci.com
ARG VITE_PORTAL_SOURCE=tech-kg-api
ENV npm_config_registry=${NPM_REGISTRY} \
    COREPACK_NPM_REGISTRY=${NPM_REGISTRY} \
    VITE_BASE=${VITE_BASE} \
    VITE_API_BASE=${VITE_API_BASE} \
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

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
