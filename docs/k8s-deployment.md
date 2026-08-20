# Kubernetes 部署文档（tech-kg-api）

本文档描述将 `tech-kg-api`（FastAPI 后端 + Vue3 前端）及其依赖中间件部署到 Kubernetes 集群的完整方案。对应仓库根目录的 `docker-compose.yml`，按 K8s 原生方式重新组织。

> 说明：仓库内 README.md 描述的是旧的 Neo4j 版本，已过时；以本文与 `docker-compose.yml`、`CLAUDE.md` 为准。

---

## 1. 架构与组件拓扑

### 1.1 应用层（仓库自带镜像）

| 组件 | 镜像来源 | 端口 | 作用 |
|------|----------|------|------|
| `api` | `./backend` (python:3.11.13-slim) | 8000 | FastAPI 主服务，`uvicorn main:app` |
| `temporal-worker` | `./backend` | 无 | `python -m script.run_temporal_worker`，消费 Temporal 任务队列 |
| `m3e-embedding` | `./backend` | 8010 | `script.m3e_embedding_service:app`，专利向量化推理服务 |
| `web` | `./frontend` (nginx:1.27-alpine) | 80 | 前端静态资源 + `/api/` 反代到 `api:8000` |

### 1.2 中间件层

| 组件 | 镜像 | 端口 | 持久化 |
|------|------|------|--------|
| `auth-redis` | redis:7.4-alpine | 6379 | `/data` (appendonly) |
| `schema-minio` | minio/minio:RELEASE.2025-04-22T22-12-26Z | 9000 / 9001 | `/data`，schema DDL 脚本对象存储 |
| `operator-rustfs` | rustfs/rustfs:latest | 9000 / 9001 | `/data` (uid 10001)，operator 脚本对象存储 |
| `milvus-etcd` | quay.io/coreos/etcd:v3.5.5 | 2379 | `/etcd` |
| `milvus-minio` | minio/minio:RELEASE.2023-03-20T20-16-18Z | 9000 / 9001 | `/minio_data` |
| `milvus` | milvusdb/milvus:v2.4.17 | 19530 / 9091 | `/var/lib/milvus` |
| `temporal-postgresql` | postgres:16-alpine | 5432 | `/var/lib/postgresql/data` |
| `temporal` | temporalio/auto-setup:1.29.2 | 7233 | 无（数据在 pg） |
| `temporal-ui` | temporalio/ui:2.39.0 | 8080 | 无 |

### 1.3 集群外依赖（需独立提供）

- **trs-graph-service**（Java Spring Boot，NebulaGraph REST 网关）— 默认 `http://trs-graph-service:8090`，需要 `X-API-Key` 与 `X-Graph-Space` 头。生产环境以 Service / ExternalName 形式接入。
- **MySQL**（主库 `gkx_element` + 论文合作库 `gkx_local`）— 默认 `mysql:3306`。
- **LLM API**（智谱 GLM）— `https://open.bigmodel.cn/api/paas/v4`，需 `LLM_API_KEY`。
- **用户中心 SSO**（`edu.itic-sci.com`）— 可选，启用 `AUTH_ENABLED=true` 时必需。

### 1.4 端口与 Volume 对照（compose → K8s）

| compose 卷 | K8s PVC | 挂载点 | 介质建议 |
|------------|---------|--------|----------|
| `schema-minio-data` | `schema-minio-data` | `/data` | 对象存储盘 |
| `milvus-etcd-data` | `milvus-etcd-data` | `/etcd` | 高 IOPS SSD |
| `milvus-minio-data` | `milvus-minio-data` | `/minio_data` | 对象存储盘 |
| `milvus-data` | `milvus-data` | `/var/lib/milvus` | 高 IOPS SSD |
| `temporal-postgresql-data` | `temporal-postgresql-data` | `/var/lib/postgresql/data` | SSD |
| `workflow-state` | `workflow-state` | `/var/lib/tech-kg` | SSD |
| `m3e-model-cache` | `m3e-model-cache` | `/models/huggingface` | 大容量 HDD（只读缓存） |
| `patent-index-state` | `patent-index-state` | `/app/var/patent_indexes` | SSD |
| `operator-data` | `operator-data` | `/app/operators/user` | SSD |
| `operator-rustfs-data` | `operator-rustfs-data` | `/data` | 对象存储盘 |
| `auth-redis-data` | `auth-redis-data` | `/data` | SSD |

---

## 2. 前置条件

- Kubernetes ≥ 1.26，已安装 `kubectl` 并可访问集群。
- 集群内有 **Ingress Controller**（nginx-ingress 或 traefik）和 **默认 StorageClass**（支持 `WaitForFirstConsumer` 更佳）。
- 用于镜像拉取的 **私有镜像仓库**（Harbor / ACR / 自建 registry），并将 `backend`、`frontend` 镜像 push 上去。
  - 内网镜像可直接走华为云 SWR：`swr.cn-north-4.myhuaweicloud.com/ddn-k8s/...`。
- 一个 **外部 MySQL** 实例（或部署在集群内的 StatefulSet MySQL）。
- 一个 **外部 trs-graph-service**（NebulaGraph 网关）。若该服务也在集群内，可直接用 Service DNS；否则用 `ExternalName` 或 `Service + Endpoints` 接入。
- 可选：cert-manager（用于自动 HTTPS 证书）。

---

## 3. 镜像构建与推送

```bash
# 后端镜像（api / temporal-worker / m3e-embedding 共用）
docker build -t <REGISTRY>/tech-kg-api:0.1.0 \
  --build-arg PYPI_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  ./backend

# 前端镜像（web）
docker build -t <REGISTRY>/tech-kg-web:0.1.0 \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg VITE_BASE=./ \
  --build-arg VITE_API_BASE=/api \
  ./frontend

docker push <REGISTRY>/tech-kg-api:0.1.0
docker push <REGISTRY>/tech-kg-web:0.1.0
```

> `backend/Dockerfile` 默认从阿里云 PyPI 拉 `uv`，**不要切到清华源**（会 403）。
> `backend` 镜像在不同 Deployment 里通过 `command`/`args` 切换为 api / temporal-worker / m3e-embedding。

---

## 4. Namespace 与基础资源

```yaml
# k8s/00-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: tech-kg
  labels:
    app.kubernetes.io/part-of: tech-kg
```

```bash
kubectl apply -f k8s/00-namespace.yaml
kubectl config set-context --current --namespace=tech-kg
```

---

## 5. ConfigMap

把非敏感的可调参数集中到 ConfigMap，便于环境漂移。

```yaml
# k8s/10-configmap.yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: tech-kg-config
  namespace: tech-kg
data:
  # ---- 图数据库 ----
  TRS_GRAPH_BASE_URL: http://trs-graph-service:8090
  TRS_GRAPH_SPACE: dev
  TRS_GRAPH_TIMEOUT: "30"
  # ---- 主 MySQL ----
  MYSQL_HOST: mysql
  MYSQL_PORT: "3306"
  MYSQL_DATABASE: gkx_element
  MYSQL_USERNAME: root
  # ---- 论文合作 MySQL ----
  PAPER_COOP_MYSQL_HOST: mysql
  PAPER_COOP_MYSQL_PORT: "3306"
  PAPER_COOP_MYSQL_DATABASE: gkx_local
  PAPER_COOP_MYSQL_USERNAME: root
  # ---- Milvus ----
  MILVUS_HOST: milvus
  MILVUS_PORT: "19530"
  # ---- LLM ----
  LLM_MODEL: glm-4.7-flash
  LLM_BASE_URL: https://open.bigmodel.cn/api/paas/v4
  # ---- Temporal ----
  TEMPORAL_ADDRESS: temporal:7233
  TEMPORAL_NAMESPACE: default
  TEMPORAL_TASK_QUEUE: tech-kg-workflows
  WORKFLOW_DATABASE_PATH: /var/lib/tech-kg/workflows.db
  WORKFLOW_SCRIPT_DIR: /var/lib/tech-kg/scripts
  # ---- schema S3 (minio) ----
  SCHEMA_AUTO_INIT: "true"
  SCHEMA_S3_ENDPOINT_URL: http://schema-minio:9000
  SCHEMA_S3_BUCKET: tech-kg-schema-scripts
  SCHEMA_S3_REGION: us-east-1
  SCHEMA_S3_SECURE: "false"
  SCHEMA_SCRIPT_MAX_BYTES: "10485760"
  SCHEMA_ADMIN_USER_IDS: schema-admin
  # ---- 专利 embedding ----
  PATENT_EMBEDDING_PROVIDER: openai
  PATENT_EMBEDDING_BASE_URL: http://m3e-embedding:8010/v1
  PATENT_EMBEDDING_MODEL: moka-ai/m3e-small
  PATENT_EMBEDDING_DIM: "512"
  # ---- operator S3 (rustfs) ----
  OPERATOR_DIR: /app/operators/user
  OPERATOR_S3_ENDPOINT_URL: http://operator-rustfs:9000
  OPERATOR_S3_BUCKET: tech-kg-operators
  OPERATOR_S3_PREFIX: operators
  OPERATOR_S3_REGION: us-east-1
  # ---- 认证 ----
  AUTH_ENABLED: "true"
  AUTH_SESSION_BACKEND: redis
  AUTH_SESSION_COOKIE: techkg_session
  AUTH_SESSION_TTL_SECONDS: "604800"
  AUTH_STATE_TTL_SECONDS: "300"
  AUTH_AUDIT_TTL_SECONDS: "7776000"
  AUTH_AUDIT_MAX_ITEMS: "200"
  AUTH_COOKIE_SECURE: "true"
  AUTH_COOKIE_SAMESITE: lax
  AUTH_COOKIE_PATH: /bkg_zp
  AUTH_FRONTEND_URL: https://edu.itic-sci.com/bkg_zp
  USER_CENTER_SSO_LOGIN_URL: https://edu.itic-sci.com/uc/sso/login
  USER_CENTER_OAUTH_BASE_URL: https://edu.itic-sci.com/uc/admin-api/system/oauth2
  USER_CENTER_ACCOUNT_URL: https://edu.itic-sci.com/uc/admin/login?redirect=/index
  USER_CENTER_REDIRECT_URI: https://edu.itic-sci.com/bkg_zp/api/v1/auth/callback
  REDIS_URL: redis://auth-redis:6379/0
```

> 注意：compose 用 `host.docker.internal:host-gateway` 访问宿主机服务，K8s 里改为对集群内 Service DNS 或 `ExternalName`。

---

## 6. Secret

把所有凭据集中到 Secret（生产建议接 External Secrets / Vault）。

```yaml
# k8s/11-secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: tech-kg-secret
  namespace: tech-kg
type: Opaque
stringData:
  TRS_GRAPH_API_KEY: ysukeg                  # 替换为真实 key
  MYSQL_PASSWORD: "123456789"                # 替换为真实密码
  PAPER_COOP_MYSQL_PASSWORD: "123456789"
  LLM_API_KEY: ""                            # 智谱 API key
  SCHEMA_S3_ACCESS_KEY: minioadmin
  SCHEMA_S3_SECRET_KEY: minioadmin
  PATENT_EMBEDDING_API_KEY: local-no-auth
  OPERATOR_S3_ACCESS_KEY_ID: rustfsadmin
  OPERATOR_S3_SECRET_ACCESS_KEY: rustfsadmin
  USER_CENTER_CLIENT_ID: ""
  USER_CENTER_CLIENT_SECRET: ""
  OPERATOR_RELOAD_TOKEN: ""
  OPERATOR_WORKER_BASE_URIS: ""
```

```bash
kubectl apply -f k8s/11-secret.yaml
```

---

## 7. 持久化卷（PVC）

```yaml
# k8s/20-pvc.yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: schema-minio-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 50Gi } }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: milvus-etcd-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 10Gi } }
  storageClassName: ssd
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: milvus-minio-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 100Gi } }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: milvus-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 100Gi } }
  storageClassName: ssd
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: temporal-postgresql-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 20Gi } }
  storageClassName: ssd
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workflow-state
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 10Gi } }
  storageClassName: ssd
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: m3e-model-cache
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 20Gi } }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: patent-index-state
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 20Gi } }
  storageClassName: ssd
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: operator-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 10Gi } }
  storageClassName: ssd
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: operator-rustfs-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 50Gi } }
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: auth-redis-data
  namespace: tech-kg
spec:
  accessModes: ["ReadWriteOnce"]
  resources: { requests: { storage: 5Gi } }
  storageClassName: ssd
```

> 多副本可读的卷（如 `operator-data`、`workflow-state`）应使用 `ReadWriteMany`，或保持单副本以避免并发写冲突。

---

## 8. 中间件部署

### 8.1 auth-redis

```yaml
# k8s/30-auth-redis.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: auth-redis
  namespace: tech-kg
spec:
  serviceName: auth-redis
  replicas: 1
  selector:
    matchLabels: { app: auth-redis }
  template:
    metadata:
      labels: { app: auth-redis }
    spec:
      containers:
        - name: redis
          image: redis:7.4-alpine
          args: ["redis-server", "--appendonly", "yes"]
          ports: [{ containerPort: 6379 }]
          volumeMounts:
            - name: data
              mountPath: /data
          readinessProbe:
            exec: { command: ["redis-cli", "ping"] }
            periodSeconds: 5
            failureThreshold: 10
          resources:
            requests: { cpu: 100m, memory: 128Mi }
            limits: { cpu: 500m, memory: 512Mi }
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: auth-redis-data }
---
apiVersion: v1
kind: Service
metadata:
  name: auth-redis
  namespace: tech-kg
spec:
  selector: { app: auth-redis }
  ports: [{ port: 6379, targetPort: 6379 }]
```

### 8.2 schema-minio

```yaml
# k8s/31-schema-minio.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: schema-minio
  namespace: tech-kg
spec:
  serviceName: schema-minio
  replicas: 1
  selector: { matchLabels: { app: schema-minio } }
  template:
    metadata:
      labels: { app: schema-minio }
    spec:
      containers:
        - name: minio
          image: minio/minio:RELEASE.2025-04-22T22-12-26Z
          args: ["server", "/data", "--console-address", ":9001"]
          envFrom:
            - secretRef: { name: tech-kg-secret }   # 用 SCHEMA_S3_ACCESS_KEY/SECRET_KEY
          ports:
            - { containerPort: 9000, name: s3 }
            - { containerPort: 9001, name: console }
          volumeMounts:
            - { name: data, mountPath: /data }
          readinessProbe:
            httpGet: { path: /minio/health/live, port: 9000 }
            periodSeconds: 10
            failureThreshold: 10
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: schema-minio-data }
---
apiVersion: v1
kind: Service
metadata: { name: schema-minio, namespace: tech-kg }
spec:
  selector: { app: schema-minio }
  ports:
    - { name: s3, port: 9000, targetPort: 9000 }
    - { name: console, port: 9001, targetPort: 9001 }
```

### 8.3 operator-rustfs

需要先以 uid 10001 初始化数据卷（compose 用 init 容器完成 `chown`）。

```yaml
# k8s/32-operator-rustfs.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: operator-rustfs
  namespace: tech-kg
spec:
  serviceName: operator-rustfs
  replicas: 1
  selector: { matchLabels: { app: operator-rustfs } }
  template:
    metadata:
      labels: { app: operator-rustfs }
    spec:
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      initContainers:
        - name: chown
          image: alpine:3.22
          command: ["sh", "-c", "chown -R 10001:10001 /data"]
          volumeMounts:
            - { name: data, mountPath: /data }
      containers:
        - name: rustfs
          image: rustfs/rustfs:latest
          securityContext:
            allowPrivilegeEscalation: false
            capabilities: { drop: ["ALL"] }
            readOnlyRootFilesystem: false
          envFrom:
            - secretRef: { name: tech-kg-secret }
            - configMapRef: { name: tech-kg-config }
          env:
            - { name: RUSTFS_VOLUMES, value: /data }
            - { name: RUSTFS_ADDRESS, value: 0.0.0.0:9000 }
            - { name: RUSTFS_CONSOLE_ADDRESS, value: 0.0.0.0:9001 }
            - { name: RUSTFS_CONSOLE_ENABLE, value: "true" }
            - { name: RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS, value: "*" }
            - { name: RUSTFS_UNSAFE_BYPASS_DISK_CHECK, value: "true" }
          ports:
            - { containerPort: 9000, name: s3 }
            - { containerPort: 9001, name: console }
          volumeMounts:
            - { name: data, mountPath: /data }
          readinessProbe:
            httpGet: { path: /health, port: 9000 }
            periodSeconds: 10
            failureThreshold: 12
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: operator-rustfs-data }
---
apiVersion: v1
kind: Service
metadata: { name: operator-rustfs, namespace: tech-kg }
spec:
  selector: { app: operator-rustfs }
  ports:
    - { name: s3, port: 9000, targetPort: 9000 }
    - { name: console, port: 9001, targetPort: 9001 }
```

### 8.4 Milvus（etcd + minio + standalone）

```yaml
# k8s/33-milvus-etcd.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: milvus-etcd, namespace: tech-kg }
spec:
  serviceName: milvus-etcd
  replicas: 1
  selector: { matchLabels: { app: milvus-etcd } }
  template:
    metadata: { labels: { app: milvus-etcd } }
    spec:
      containers:
        - name: etcd
          image: quay.io/coreos/etcd:v3.5.5
          command:
            - etcd
            - -advertise-client-urls=http://milvus-etcd:2379
            - -listen-client-urls=http://0.0.0.0:2379
            - --data-dir=/etcd
          env:
            - { name: ETCD_AUTO_COMPACTION_MODE, value: revision }
            - { name: ETCD_AUTO_COMPACTION_RETENTION, value: "1000" }
            - { name: ETCD_QUOTA_BACKEND_BYTES, value: "4294967296" }
            - { name: ETCD_SNAPSHOT_COUNT, value: "50000" }
          ports: [{ containerPort: 2379 }]
          volumeMounts: [{ name: data, mountPath: /etcd }]
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: milvus-etcd-data }
---
apiVersion: v1
kind: Service
metadata: { name: milvus-etcd, namespace: tech-kg }
spec:
  selector: { app: milvus-etcd }
  ports: [{ port: 2379, targetPort: 2379 }]
```

```yaml
# k8s/34-milvus-minio.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: milvus-minio, namespace: tech-kg }
spec:
  serviceName: milvus-minio
  replicas: 1
  selector: { matchLabels: { app: milvus-minio } }
  template:
    metadata: { labels: { app: milvus-minio } }
    spec:
      containers:
        - name: minio
          image: minio/minio:RELEASE.2023-03-20T20-16-18Z
          args: ["server", "/minio_data", "--console-address", ":9001"]
          env:
            - { name: MINIO_ACCESS_KEY, value: minioadmin }
            - { name: MINIO_SECRET_KEY, value: minioadmin }
          ports:
            - { containerPort: 9000 }
            - { containerPort: 9001 }
          volumeMounts: [{ name: data, mountPath: /minio_data }]
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: milvus-minio-data }
---
apiVersion: v1
kind: Service
metadata: { name: milvus-minio, namespace: tech-kg }
spec:
  selector: { app: milvus-minio }
  ports:
    - { port: 9000, targetPort: 9000 }
    - { port: 9001, targetPort: 9001 }
```

```yaml
# k8s/35-milvus.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: milvus, namespace: tech-kg }
spec:
  serviceName: milvus
  replicas: 1
  selector: { matchLabels: { app: milvus } }
  template:
    metadata: { labels: { app: milvus } }
    spec:
      containers:
        - name: milvus
          image: milvusdb/milvus:v2.4.17
          args: ["milvus", "run", "standalone"]
          env:
            - { name: ETCD_ENDPOINTS, value: milvus-etcd:2379 }
            - { name: MINIO_ADDRESS, value: milvus-minio:9000 }
          ports:
            - { containerPort: 19530, name: grpc }
            - { containerPort: 9091, name: metrics }
          volumeMounts: [{ name: data, mountPath: /var/lib/milvus }]
          readinessProbe:
            tcpSocket: { port: 19530 }
            periodSeconds: 15
            failureThreshold: 20
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: milvus-data }
---
apiVersion: v1
kind: Service
metadata: { name: milvus, namespace: tech-kg }
spec:
  selector: { app: milvus }
  ports:
    - { name: grpc, port: 19530, targetPort: 19530 }
    - { name: metrics, port: 9091, targetPort: 9091 }
```

### 8.5 Temporal（postgresql + auto-setup + ui）

```yaml
# k8s/36-temporal-postgresql.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: temporal-postgresql, namespace: tech-kg }
spec:
  serviceName: temporal-postgresql
  replicas: 1
  selector: { matchLabels: { app: temporal-postgresql } }
  template:
    metadata: { labels: { app: temporal-postgresql } }
    spec:
      containers:
        - name: postgres
          image: swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/library/postgres:16-alpine
          env:
            - { name: POSTGRES_USER, value: temporal }
            - { name: POSTGRES_PASSWORD, value: temporal }
          ports: [{ containerPort: 5432 }]
          volumeMounts: [{ name: data, mountPath: /var/lib/postgresql/data }]
      volumes:
        - name: data
          persistentVolumeClaim: { claimName: temporal-postgresql-data }
---
apiVersion: v1
kind: Service
metadata: { name: temporal-postgresql, namespace: tech-kg }
spec:
  selector: { app: temporal-postgresql }
  ports: [{ port: 5432, targetPort: 5432 }]
```

```yaml
# k8s/37-temporal.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: temporal, namespace: tech-kg }
spec:
  replicas: 1
  selector: { matchLabels: { app: temporal } }
  template:
    metadata: { labels: { app: temporal } }
    spec:
      containers:
        - name: temporal
          image: swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/temporalio/auto-setup:1.29.2
          env:
            - { name: DB, value: postgres12 }
            - { name: DB_PORT, value: "5432" }
            - { name: POSTGRES_USER, value: temporal }
            - { name: POSTGRES_PWD, value: temporal }
            - { name: POSTGRES_SEEDS, value: temporal-postgresql }
          ports: [{ containerPort: 7233 }]
          readinessProbe:
            tcpSocket: { port: 7233 }
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata: { name: temporal, namespace: tech-kg }
spec:
  selector: { app: temporal }
  ports: [{ port: 7233, targetPort: 7233 }]
```

```yaml
# k8s/38-temporal-ui.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: temporal-ui, namespace: tech-kg }
spec:
  replicas: 1
  selector: { matchLabels: { app: temporal-ui } }
  template:
    metadata: { labels: { app: temporal-ui } }
    spec:
      containers:
        - name: ui
          image: swr.cn-north-4.myhuaweicloud.com/ddn-k8s/docker.io/temporalio/ui:2.39.0
          env:
            - { name: TEMPORAL_ADDRESS, value: temporal:7233 }
          ports: [{ containerPort: 8080 }]
---
apiVersion: v1
kind: Service
metadata: { name: temporal-ui, namespace: tech-kg }
spec:
  selector: { app: temporal-ui }
  ports: [{ port: 8080, targetPort: 8080 }]
```

### 8.6 m3e-embedding

启动慢（首次需下模型），`start_period` 给足 180s。

```yaml
# k8s/39-m3e-embedding.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata: { name: m3e-embedding, namespace: tech-kg }
spec:
  serviceName: m3e-embedding
  replicas: 1
  selector: { matchLabels: { app: m3e-embedding } }
  template:
    metadata: { labels: { app: m3e-embedding } }
    spec:
      containers:
        - name: m3e
          image: <REGISTRY>/tech-kg-api:0.1.0
          command: [".venv/bin/uvicorn", "script.m3e_embedding_service:app", "--host", "0.0.0.0", "--port", "8010"]
          env:
            - { name: M3E_MODEL_NAME, value: moka-ai/m3e-small }
            - { name: M3E_EMBEDDING_DIM, value: "512" }
            - { name: M3E_DEVICE, value: cpu }
            - { name: M3E_BATCH_SIZE, value: "8" }
            - { name: M3E_MAX_BATCH_SIZE, value: "64" }
            - { name: M3E_MAX_CONCURRENCY, value: "1" }
            - { name: HF_HOME, value: /models/huggingface }
          ports: [{ containerPort: 8010 }]
          volumeMounts:
            - { name: model-cache, mountPath: /models/huggingface }
          readinessProbe:
            exec:
              command: [".venv/bin/python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8010/health', timeout=5)"]
            periodSeconds: 15
            failureThreshold: 20
            initialDelaySeconds: 180
          resources:
            requests: { cpu: 1, memory: 2Gi }
            limits: { cpu: 2, memory: 4Gi }
      volumes:
        - name: model-cache
          persistentVolumeClaim: { claimName: m3e-model-cache }
---
apiVersion: v1
kind: Service
metadata: { name: m3e-embedding, namespace: tech-kg }
spec:
  selector: { app: m3e-embedding }
  ports: [{ port: 8010, targetPort: 8010 }]
```

---

## 9. 应用部署

### 9.1 api（主服务）

```yaml
# k8s/50-api.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: api, namespace: tech-kg }
spec:
  replicas: 2
  selector: { matchLabels: { app: api } }
  template:
    metadata: { labels: { app: api } }
    spec:
      containers:
        - name: api
          image: <REGISTRY>/tech-kg-api:0.1.0
          ports: [{ containerPort: 8000 }]
          envFrom:
            - configMapRef: { name: tech-kg-config }
            - secretRef: { name: tech-kg-secret }
          readinessProbe:
            httpGet: { path: /health, port: 8000 }
            periodSeconds: 5
            failureThreshold: 6
          livenessProbe:
            httpGet: { path: /health, port: 8000 }
            periodSeconds: 30
            failureThreshold: 3
          volumeMounts:
            - { name: operator-data, mountPath: /app/operators/user }
            - { name: patent-index-state, mountPath: /app/var/patent_indexes }
            - { name: workflow-state, mountPath: /var/lib/tech-kg }
          resources:
            requests: { cpu: 500m, memory: 1Gi }
            limits: { cpu: 2, memory: 4Gi }
      volumes:
        - name: operator-data
          persistentVolumeClaim: { claimName: operator-data }
        - name: patent-index-state
          persistentVolumeClaim: { claimName: patent-index-state }
        - name: workflow-state
          persistentVolumeClaim: { claimName: workflow-state }
---
apiVersion: v1
kind: Service
metadata: { name: api, namespace: tech-kg }
spec:
  selector: { app: api }
  ports: [{ port: 8000, targetPort: 8000 }]
```

> `workflow-state` 卷是 SQLite + 脚本目录，**不能多副本并发写**。若 `api` replicas > 1，把 workflow 写路径迁出 `api`，仅由 `temporal-worker` 持有；或将该卷改为 `ReadWriteOnce` 并把 `api` 改成单副本。

### 9.2 temporal-worker

```yaml
# k8s/51-temporal-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: temporal-worker, namespace: tech-kg }
spec:
  replicas: 1
  selector: { matchLabels: { app: temporal-worker } }
  template:
    metadata: { labels: { app: temporal-worker } }
    spec:
      containers:
        - name: worker
          image: <REGISTRY>/tech-kg-api:0.1.0
          command: [".venv/bin/python", "-m", "script.run_temporal_worker"]
          env:
            - { name: TEMPORAL_ADDRESS, value: temporal:7233 }
            - { name: TEMPORAL_NAMESPACE, value: default }
            - { name: TEMPORAL_TASK_QUEUE, value: tech-kg-workflows }
            - { name: WORKFLOW_DATABASE_PATH, value: /var/lib/tech-kg/workflows.db }
            - { name: WORKFLOW_SCRIPT_DIR, value: /var/lib/tech-kg/scripts }
          volumeMounts:
            - { name: workflow-state, mountPath: /var/lib/tech-kg }
          resources:
            requests: { cpu: 500m, memory: 1Gi }
            limits: { cpu: 2, memory: 4Gi }
      volumes:
        - name: workflow-state
          persistentVolumeClaim: { claimName: workflow-state }
```

### 9.3 web（前端 + nginx 反代）

```yaml
# k8s/52-web.yaml
apiVersion: apps/v1
kind: Deployment
metadata: { name: web, namespace: tech-kg }
spec:
  replicas: 2
  selector: { matchLabels: { app: web } }
  template:
    metadata: { labels: { app: web } }
    spec:
      containers:
        - name: web
          image: <REGISTRY>/tech-kg-web:0.1.0
          ports: [{ containerPort: 80 }]
          readinessProbe:
            httpGet: { path: /, port: 80 }
            periodSeconds: 5
          resources:
            requests: { cpu: 100m, memory: 128Mi }
            limits: { cpu: 500m, memory: 256Mi }
---
apiVersion: v1
kind: Service
metadata: { name: web, namespace: tech-kg }
spec:
  selector: { app: web }
  ports: [{ port: 80, targetPort: 80 }]
```

> 前端镜像的 `nginx.conf` 中 `proxy_pass http://api:8000;` 直接走集群 DNS，K8s Service `api` 会解析到对应 Endpoints。

---

## 10. 外部服务接入

### 10.1 trs-graph-service

若 trs-graph-service 在集群外（例如部署在另一台 VM 或独立 namespace 的 Service）：

```yaml
# k8s/60-trs-graph-externalname.yaml
apiVersion: v1
kind: Service
metadata:
  name: trs-graph-service
  namespace: tech-kg
spec:
  type: ExternalName
  externalName: trs-graph.host.example.com   # 真实外部地址
```

若为 IP：

```yaml
# k8s/60-trs-graph-endpoints.yaml
apiVersion: v1
kind: Service
metadata: { name: trs-graph-service, namespace: tech-kg }
spec:
  ports: [{ port: 8090, targetPort: 8090 }]
---
apiVersion: v1
kind: Endpoints
metadata: { name: trs-graph-service, namespace: tech-kg }
subsets:
  - addresses:
      - ip: 10.0.0.20
    ports:
      - port: 8090
```

### 10.2 MySQL

```yaml
# k8s/61-mysql-externalname.yaml
apiVersion: v1
kind: Service
metadata: { name: mysql, namespace: tech-kg }
spec:
  type: ExternalName
  externalName: mysql.prod.svc.cluster.local   # 或外部地址
```

---

## 11. 初始化 Job

`SCHEMA_AUTO_INIT=true` 时 api 启动会自动初始化 schema_management；其余脚本按需手动跑。建议把初始化封装为 Job，便于重跑与版本管理。

```yaml
# k8s/70-init-db-job.yaml
apiVersion: batch/v1
kind: Job
metadata: { name: init-db, namespace: tech-kg }
spec:
  backoffLimit: 4
  ttlSecondsAfterFinished: 600
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: init-db
          image: <REGISTRY>/tech-kg-api:0.1.0
          command: [".venv/bin/python", "-m", "script.init_db"]
          envFrom:
            - configMapRef: { name: tech-kg-config }
            - secretRef: { name: tech-kg-secret }
```

```yaml
# k8s/71-init-graph-schema-job.yaml
apiVersion: batch/v1
kind: Job
metadata: { name: init-graph-schema, namespace: tech-kg }
spec:
  backoffLimit: 6              # CREATE SPACE 有传播延迟，失败重试
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: init-graph
          image: <REGISTRY>/tech-kg-api:0.1.0
          command: [".venv/bin/python", "-m", "script.init_graph_schema"]
          envFrom:
            - configMapRef: { name: tech-kg-config }
            - secretRef: { name: tech-kg-secret }
```

> **注意**：`init_paper_journal_schema.py` 会 DROP dev 空间，切勿在共享环境运行。详见内部记忆条目「trs-graph-service 的三个坑」。

---

## 12. Ingress

```yaml
# k8s/80-ingress.yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: tech-kg-ingress
  namespace: tech-kg
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: 50m
    nginx.ingress.kubernetes.io/proxy-read-timeout: "600"
    nginx.ingress.kubernetes.io/proxy-send-timeout: "600"
    nginx.ingress.kubernetes.io/affinity: cookie
spec:
  ingressClassName: nginx
  tls:
    - hosts: [tech-kg.example.com]
      secretName: tech-kg-tls
  rules:
    - host: tech-kg.example.com
      http:
        paths:
          - path: /api/
            pathType: Prefix
            backend:
              service: { name: api, port: { number: 8000 } }
          - path: /
            pathType: Prefix
            backend:
              service: { name: web, port: { number: 80 } }
```

- 长连接 / SSE 流式接口需关闭 ingress buffer：`nginx.ingress.kubernetes.io/proxy-buffering: "off"`，并显式设置 `proxy-request-buffering: off`。
- 若仍走前端 nginx 反代 `/api/`，Ingress 只暴露 `web:80`，但建议直接对 api 暴露以简化链路。
- `AUTH_COOKIE_PATH=/bkg_zp` 时需保证 ingress 路径前缀与之一致，或在 web 前再压一层 path rewrite。

---

## 13. HPA（可选）

```yaml
# k8s/90-hpa-api.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata: { name: api, namespace: tech-kg }
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: api
  minReplicas: 2
  maxReplicas: 6
  metrics:
    - type: Resource
      resource: { name: cpu, target: { type: Utilization, averageUtilization: 70 } }
```

> HPA 扩容 `api` 前请先确认 `workflow-state`、`operator-data` 等 RWO 卷是否允许并发挂载，否则需迁移到独立存储或改成对象存储。

---

## 14. 部署顺序与命令

```bash
# 0) 命名空间
kubectl apply -f k8s/00-namespace.yaml

# 1) 配置与密钥
kubectl apply -f k8s/10-configmap.yaml -f k8s/11-secret.yaml

# 2) 存储
kubectl apply -f k8s/20-pvc.yaml

# 3) 中间件（按依赖顺序）
kubectl apply -f k8s/30-auth-redis.yaml
kubectl apply -f k8s/31-schema-minio.yaml
kubectl apply -f k8s/32-operator-rustfs.yaml
kubectl apply -f k8s/33-milvus-etcd.yaml -f k8s/34-milvus-minio.yaml
kubectl apply -f k8s/35-milvus.yaml
kubectl apply -f k8s/36-temporal-postgresql.yaml
kubectl apply -f k8s/37-temporal.yaml -f k8s/38-temporal-ui.yaml
kubectl apply -f k8s/39-m3e-embedding.yaml

# 4) 外部服务
kubectl apply -f k8s/60-trs-graph-externalname.yaml -f k8s/61-mysql-externalname.yaml

# 5) 应用
kubectl apply -f k8s/50-api.yaml -f k8s/51-temporal-worker.yaml -f k8s/52-web.yaml

# 6) 初始化任务
kubectl apply -f k8s/70-init-db-job.yaml -f k8s/71-init-graph-schema-job.yaml

# 7) 入口
kubectl apply -f k8s/80-ingress.yaml

# 8)（可选）HPA
kubectl apply -f k8s/90-hpa-api.yaml
```

### 等待就绪

```bash
kubectl -n tech-kg wait --for=condition=ready pod -l app=api --timeout=300s
kubectl -n tech-kg rollout status deploy/api
kubectl -n tech-kg rollout status deploy/web
```

---

## 15. 验证

```bash
# 1) Pod 全部 Running
kubectl -n tech-kg get pods -o wide

# 2) Service 端口
kubectl -n tech-kg get svc

# 3) api 健康检查
kubectl -n tech-kg port-forward svc/api 8000:8000
curl http://127.0.0.1:8000/health    # {"status":"ok"}

# 4) 前端
kubectl -n tech-kg port-forward svc/web 8080:80
curl -I http://127.0.0.1:8080/

# 5) Temporal UI
kubectl -n tech-kg port-forward svc/temporal-ui 8233:8080

# 6) 模块 catalog（需要先登录或关闭 AUTH_ENABLED）
curl http://127.0.0.1:8000/api/v1/kg-construction/options
```

---

## 16. 运维与排障

### 16.1 常用命令

```bash
# 日志
kubectl -n tech-kg logs -f deploy/api
kubectl -n tech-kg logs -f deploy/temporal-worker
kubectl -n tech-kg logs -f statefulset/m3e-embedding

# 进容器
kubectl -n tech-kg exec -it deploy/api -- .venv/bin/python -c "from infra.mysql import get_mysql_client; print(get_mysql_client())"

# 重启 Deployment
kubectl -n tech-kg rollout restart deploy/api
```

### 16.2 关键陷阱

1. **`workflow-state` / `operator-data` 是 RWO SQLite 卷**：多副本 `api` 会冲突，建议 replicas=1 或迁到对象存储。
2. **m3e-embedding 首次拉模型很慢**：readinessProbe 的 `initialDelaySeconds` 给 180s 以上；首次部署可手动 `kubectl wait` 等 Pod Ready。
3. **trs-graph 节点 CRUD 不可靠**（`find_nodes` 返回假 vid、`merge_node` 仅 ETL 用），详见内部记忆。线上业务只用 edge + node-read。
4. **`init_graph_schema.py` 创建 SPACE 后会因传播延迟报错**，Job 设置 `backoffLimit: 6`，重试即可。
5. **`init_paper_journal_schema.py` 会 DROP dev 空间**：禁止在共享环境运行。
6. **MySQL 主库与论文合作库密码分开**：`MYSQL_PASSWORD` 与 `PAPER_COOP_MYSQL_PASSWORD` 可在 Secret 中设为不同值。
7. **LLM_API_KEY 缺失时**：`get_llm_client()` 返回 `None`，`enterprise_background_analysis` 降级返回模板结果，不会崩溃。
8. **认证 Cookie 路径**：`AUTH_COOKIE_PATH=/bkg_zp` 要求 Ingress / 前端路径与之一致，否则登录态丢失。
9. **SSE 流式接口**：跨线程迭代生成器，请求 Session 不能跨线程用；新端点必须独立 Session + 单专用线程 + 队列回传（详见 `unified-auth-setup.md` 与内部记忆）。
10. **镜像源**：backend Dockerfile 不要切到清华 PyPI；frontend 用 `registry.npmmirror.com`。

### 16.3 资源建议（生产）

| 组件 | CPU req/lim | Memory req/lim | 备注 |
|------|-------------|----------------|------|
| api | 500m / 2 | 1Gi / 4Gi | HPA 2–6 |
| temporal-worker | 500m / 2 | 1Gi / 4Gi | 单副本 |
| web | 100m / 500m | 128Mi / 256Mi | HPA 2–4 |
| m3e-embedding | 1 / 2 | 2Gi / 4Gi | CPU 推理，单副本 |
| milvus | 1 / 4 | 4Gi / 8Gi | 向量库主进程 |
| auth-redis | 100m / 500m | 128Mi / 512Mi | 仅 session |
| schema-minio | 200m / 1 | 256Mi / 1Gi | |
| operator-rustfs | 200m / 1 | 256Mi / 1Gi | |
| temporal | 500m / 2 | 512Mi / 2Gi | |
| temporal-postgresql | 500m / 2 | 512Mi / 2Gi | |

### 16.4 升级流程

```bash
# 构建新 tag → 推送
docker build -t <REGISTRY>/tech-kg-api:0.2.0 ./backend
docker push <REGISTRY>/tech-kg-api:0.2.0

# 滚动更新
kubectl -n tech-kg set image deploy/api api=<REGISTRY>/tech-kg-api:0.2.0
kubectl -n tech-kg set image deploy/temporal-worker worker=<REGISTRY>/tech-kg-api:0.2.0
kubectl -n tech-kg set image statefulset/m3e-embedding m3e=<REGISTRY>/tech-kg-api:0.2.0

kubectl -n tech-kg rollout status deploy/api
```

### 16.5 备份

- **MySQL**：业务库（`gkx_element`、`gkx_local`）走 DBA 既定的备份策略。
- **temporal-postgresql-data**：定期 `pg_dump` 或 Velero 卷快照。
- **schema-minio / operator-rustfs**：通过 mc / rustfs CLI 同步到异地对象存储。
- **workflow-state**：`workflow.db` + `scripts/` 目录，建议每日 rsync 到备份盘。
- **Cluster 整体**：推荐 Velero 做 namespace 级别备份与迁移。

---

## 17. 文件清单

建议将以下清单存放在仓库 `k8s/` 目录：

```
k8s/
├── 00-namespace.yaml
├── 10-configmap.yaml
├── 11-secret.yaml
├── 20-pvc.yaml
├── 30-auth-redis.yaml
├── 31-schema-minio.yaml
├── 32-operator-rustfs.yaml
├── 33-milvus-etcd.yaml
├── 34-milvus-minio.yaml
├── 35-milvus.yaml
├── 36-temporal-postgresql.yaml
├── 37-temporal.yaml
├── 38-temporal-ui.yaml
├── 39-m3e-embedding.yaml
├── 50-api.yaml
├── 51-temporal-worker.yaml
├── 52-web.yaml
├── 60-trs-graph-externalname.yaml
├── 61-mysql-externalname.yaml
├── 70-init-db-job.yaml
├── 71-init-graph-schema-job.yaml
├── 80-ingress.yaml
└── 90-hpa-api.yaml
```

---

## 18. 与 docker-compose 的差异对照

| 维度 | docker-compose | K8s |
|------|----------------|-----|
| 跨网络访问宿主机服务 | `extra_hosts: host.docker.internal:host-gateway` | `ExternalName` Service 或集群内 Service DNS |
| 多容器共享卷 | named volume + 多 mount | PVC，注意 RWO 不支持多副本写 |
| 服务发现 | compose 服务名 | Cluster DNS（`<svc>.<ns>.svc.cluster.local`） |
| 健康检查 | `healthcheck:` | `readinessProbe` / `livenessProbe` |
| 启动顺序 | `depends_on` + `condition: service_healthy` | Job / initContainer / `kubectl wait` |
| 前端反代 `/api/` | nginx 容器内 `proxy_pass http://api:8000` | 同样可保留；或 Ingress 直接分流到 `api` Service |
| 端口暴露 | host:container 端口映射 | Service + Ingress |
| 镜像构建 | `build: ./backend` | 预先 build & push 到 registry，Deployment 引用 tag |
| 资源限制 | 无显式限制 | `resources.requests/limits` + HPA |

---

如需补充 Helm Chart / Kustomize 化，可在本结构基础上把每个 yaml 模板化为 Helm templates，并以 values 区分 dev/staging/prod。
