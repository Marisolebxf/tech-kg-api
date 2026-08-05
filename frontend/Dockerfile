FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/node:22-alpine AS builder

WORKDIR /app

# Docker 构建默认使用阿里 npm 镜像，可通过 build arg 覆盖。
ARG NPM_REGISTRY=https://registry.npmmirror.com
ENV npm_config_registry=${NPM_REGISTRY} \
    COREPACK_NPM_REGISTRY=${NPM_REGISTRY}

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./

# Corepack 下载 pnpm 和 pnpm 安装项目依赖均使用上述镜像。
RUN corepack enable \
    && pnpm config set registry "${NPM_REGISTRY}"
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/nginx:1.28.0-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
