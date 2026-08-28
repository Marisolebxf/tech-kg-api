# 科技知识图谱（tech-kg）K8s 交付部署文档

## 一、文档目的

交付工程师依据本文档，部署科技知识图谱业务（命名空间 `bkg`）。

- 镜像仓库地址：http://10.50.62.9:30303
- 容器管理平台地址：https://10.50.199.115

本目录下的 yaml 文件与本文档内容一一对应，可直接 `kubectl apply -f` 或在容器平台界面导入：

| 文件 | 内容 |
|------|------|
| `00-namespace.yaml` | 命名空间 |
| `01-pvc.yaml` | 全部持久化存储（PVC） |
| `02-configmap.yaml` | 业务非敏感配置 |
| `03-secret.yaml` | 业务敏感配置（密码/密钥） |
| `10-auth-redis.yaml` | 会话 Redis |
| `11-operator-rustfs.yaml` | S3 对象存储（rustfs） |
| `12-milvus.yaml` | milvus-etcd + milvus 向量库 |
| `13-temporal.yaml` | temporal-mysql + temporal + temporal-ui |
| `20-m3e-embedding.yaml` | 专利向量化服务 |
| `21-temporal-worker.yaml` | 工作流消费者 |
| `22-api.yaml` | FastAPI 后端主服务 |
| `23-web.yaml` | 前端（nginx） |

## 二、修订记录

| 版本 | 文档发布日期 | 修订内容 |
|------|------------|---------|
| 1.0 | 2026/8/28 | 初版 |

## 三、名称解释

| 名称 | 解释 |
|------|------|
| 容器平台 | k8s 云业务平台，集成了多种功能在界面进行操作和监控 |
| 镜像仓库 | 用于存储业务所用的镜像仓库（本环境为 10.50.62.9:30303） |
| baked | 后端业务镜像（api / temporal-worker / m3e-embedding 三个 Deployment 共用同一镜像，通过不同启动命令区分） |
| baked-web | 前端业务镜像（nginx 静态资源 + `/api/` 反代） |
| rustfs | S3 兼容对象存储，承载 schema 脚本、operator 包、milvus 内部存储 |
| temporal | 工作流引擎，图谱构建任务通过它编排调度 |

## 四、环境说明

部署说明：以下部署操作所有镜像均上传到部署在平台的镜像仓库，所有操作都在容器管理平台界面操作，配置文件和存储以界面创建为主，业务以 yaml 方式部署到容器。

本业务（bkg 命名空间）部署需要以下中间件：

| 组件 | 版本 | 用途 |
|------|------|------|
| redis | 7.4-alpine | 认证会话存储（auth-redis） |
| rustfs | 1.0.0-alpha.93 | S3 对象存储（schema 脚本 / operator 包 / milvus 存储） |
| etcd | 3.5.5 | milvus 元数据 |
| milvus | 2.4.17 | 专利 / 机构向量检索 |
| mysql | 8.4 | temporal 专用库 + 业务控制面库 techkg_control |
| temporal | 1.29.2（auto-setup） | 工作流引擎 |
| temporal-ui | 2.39.0 | 工作流控制台（运维观察用） |
| baked | v0.0.1（Python 3.11） | 后端业务镜像 ×3（api / temporal-worker / m3e-embedding） |
| baked-web | v0.0.1（nginx 1.27） | 前端业务镜像 |

**集群外依赖**（需提前准备，yaml 中只填连接地址）：

| 依赖 | 说明 |
|------|------|
| 主 MySQL | 业务主库 `gkx_element` + 论文合作库 `gkx_local`（环境变量 `MYSQL_*` / `PAPER_COOP_MYSQL_*`） |
| trs-graph-service | NebulaGraph REST 网关（Java），环境变量 `TRS_GRAPH_BASE_URL` / `TRS_GRAPH_API_KEY` / `TRS_GRAPH_SPACE` |
| LLM API | 智谱 GLM（可选，未配置时相关功能自动降级） |
| 用户中心 SSO | `edu.itic-sci.com`（开启 `AUTH_ENABLED=true` 时必需） |

- 镜像仓库地址：http://10.50.62.9:30303
- 容器管理平台地址：https://10.50.199.115

## 五、中间件组件部署流程

以下 yaml 命名空间均为 `bkg`。中间件镜像统一从 `10.50.62.9:30303/library/` 拉取，**部署前需将对应镜像推送到该仓库**。

### 1、创建命名空间与 PVC

在平台上给所有组件创建 PVC（界面创建为主；名称必须与下表一致）：

| PVC 名称 | 容量建议 | 挂载组件 |
|----------|---------|---------|
| operator-rustfs-data | 50Gi（ReadWriteMany） | operator-rustfs |
| milvus-etcd-data | 10Gi | milvus-etcd |
| milvus-data | 100Gi | milvus |
| temporal-mysql-data | 50Gi | temporal-mysql |
| workflow-state | 20Gi | temporal-worker / api |
| m3e-model-cache | 5Gi | m3e-embedding（模型缓存） |
| patent-index-state | 20Gi | api（专利索引状态） |
| operator-data | 10Gi | api（operator 脚本） |
| auth-redis-data | 10Gi | auth-redis |

```yaml
# 00-namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: bkg
```

```yaml
# 01-pvc.yaml（界面已创建 PVC 时可跳过）
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: operator-rustfs-data
  namespace: bkg
spec:
  accessModes: ["ReadWriteMany"]
  resources:
    requests:
      storage: 50Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: milvus-etcd-data
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: milvus-data
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 100Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: temporal-mysql-data
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 50Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: workflow-state
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 20Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: m3e-model-cache
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 5Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: patent-index-state
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 20Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: operator-data
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 10Gi
---
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: auth-redis-data
  namespace: bkg
spec:
  accessModes: ["ReadWriteOnce"]
  resources:
    requests:
      storage: 10Gi
```

### 2、部署 auth-redis（会话存储）

```yaml
# 10-auth-redis.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: auth-redis
  namespace: bkg
spec:
  serviceName: auth-redis
  replicas: 1
  selector:
    matchLabels:
      app: auth-redis
  template:
    metadata:
      labels:
        app: auth-redis
    spec:
      containers:
        - name: auth-redis
          image: 10.50.62.9:30303/library/redis:7.4-alpine
          imagePullPolicy: IfNotPresent
          args: ["redis-server", "--appendonly", "yes"]
          ports:
            - containerPort: 6379
              name: server
          resources:
            requests:
              cpu: 100m
              memory: 256Mi
            limits:
              cpu: 500m
              memory: 1Gi
          livenessProbe:
            exec:
              command: ["redis-cli", "ping"]
            initialDelaySeconds: 10
            periodSeconds: 10
          volumeMounts:
            - name: auth-redis-data
              mountPath: /data
      volumes:
        - name: auth-redis-data
          persistentVolumeClaim:
            claimName: auth-redis-data
---
apiVersion: v1
kind: Service
metadata:
  name: auth-redis
  namespace: bkg
  labels:
    app: auth-redis
spec:
  selector:
    app: auth-redis
  ports:
    - name: server
      port: 6379
      targetPort: 6379
```

### 3、部署 operator-rustfs（S3 对象存储）

凭证默认 `rustfsadmin / rustfsadmin`，如修改需同步更新 `03-secret.yaml` 中 `SCHEMA_S3_*` / `OPERATOR_S3_*` 共 4 个 key。

```yaml
# 11-operator-rustfs.yaml
apiVersion: v1
kind: Secret
metadata:
  name: rustfs-secrets
  namespace: bkg
type: Opaque
stringData:
  RUSTFS_ACCESS_KEY: "rustfsadmin"
  RUSTFS_SECRET_KEY: "rustfsadmin"
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: operator-rustfs
  namespace: bkg
  labels:
    app: operator-rustfs
spec:
  replicas: 1
  selector:
    matchLabels:
      app: operator-rustfs
  template:
    metadata:
      labels:
        app: operator-rustfs
    spec:
      securityContext:
        runAsUser: 10001
        runAsGroup: 10001
        fsGroup: 10001
      initContainers:
        # 修复 NFS 等共享存储的目录属主，保证 rustfs(uid 10001) 可写
        - name: fix-permissions
          image: 10.50.62.9:30303/library/busybox:1.36
          command: ["sh", "-c", "chown -R 10001:10001 /data"]
          volumeMounts:
            - name: rustfs-data
              mountPath: /data
      containers:
        - name: rustfs
          image: 10.50.62.9:30303/library/rustfs:1.0.0-alpha.93
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 9000
              name: s3-api
            - containerPort: 9001
              name: console
          env:
            - name: RUSTFS_VOLUMES
              value: /data
            - name: RUSTFS_ADDRESS
              value: "0.0.0.0:9000"
            - name: RUSTFS_CONSOLE_ADDRESS
              value: "0.0.0.0:9001"
            - name: RUSTFS_CONSOLE_ENABLE
              value: "true"
            - name: RUSTFS_CONSOLE_CORS_ALLOWED_ORIGINS
              value: "*"
            - name: RUSTFS_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: rustfs-secrets
                  key: RUSTFS_ACCESS_KEY
            - name: RUSTFS_SECRET_KEY
              valueFrom:
                secretKeyRef:
                  name: rustfs-secrets
                  key: RUSTFS_SECRET_KEY
            - name: RUSTFS_UNSAFE_BYPASS_DISK_CHECK
              value: "true"
          resources:
            requests:
              cpu: 100m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 2Gi
          readinessProbe:
            httpGet:
              path: /health
              port: 9000
            initialDelaySeconds: 10
            periodSeconds: 10
          livenessProbe:
            httpGet:
              path: /health
              port: 9000
            initialDelaySeconds: 30
            periodSeconds: 15
          volumeMounts:
            - name: rustfs-data
              mountPath: /data
      volumes:
        - name: rustfs-data
          persistentVolumeClaim:
            claimName: operator-rustfs-data
---
apiVersion: v1
kind: Service
metadata:
  name: operator-rustfs
  namespace: bkg
  labels:
    app: operator-rustfs
spec:
  selector:
    app: operator-rustfs
  ports:
    - name: s3-api
      port: 9000
      targetPort: 9000
    - name: console
      port: 9001
      targetPort: 9001
```

### 4、部署 milvus（etcd + milvus）

milvus 的对象存储直接走 operator-rustfs，无需单独 minio。需在 rustfs 之后部署。

```yaml
# 12-milvus.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: milvus-etcd
  namespace: bkg
spec:
  serviceName: milvus-etcd
  replicas: 1
  selector:
    matchLabels:
      app: milvus-etcd
  template:
    metadata:
      labels:
        app: milvus-etcd
    spec:
      containers:
        - name: etcd
          image: 10.50.62.9:30303/library/etcd:3.5.5
          imagePullPolicy: IfNotPresent
          command:
            - etcd
            - -advertise-client-urls=http://milvus-etcd:2379
            - -listen-client-urls=http://0.0.0.0:2379
            - --data-dir
            - /etcd
          env:
            - name: ETCD_AUTO_COMPACTION_MODE
              value: revision
            - name: ETCD_AUTO_COMPACTION_RETENTION
              value: "1000"
            - name: ETCD_QUOTA_BACKEND_BYTES
              value: "4294967296"
            - name: ETCD_SNAPSHOT_COUNT
              value: "50000"
          ports:
            - containerPort: 2379
              name: client
          resources:
            requests:
              cpu: 100m
              memory: 512Mi
            limits:
              cpu: 500m
              memory: 1Gi
          volumeMounts:
            - name: etcd-data
              mountPath: /etcd
      volumes:
        - name: etcd-data
          persistentVolumeClaim:
            claimName: milvus-etcd-data
---
apiVersion: v1
kind: Service
metadata:
  name: milvus-etcd
  namespace: bkg
  labels:
    app: milvus-etcd
spec:
  selector:
    app: milvus-etcd
  ports:
    - name: client
      port: 2379
      targetPort: 2379
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: milvus
  namespace: bkg
spec:
  serviceName: milvus
  replicas: 1
  selector:
    matchLabels:
      app: milvus
  template:
    metadata:
      labels:
        app: milvus
    spec:
      containers:
        - name: milvus
          image: 10.50.62.9:30303/library/milvus:v2.4.17
          imagePullPolicy: IfNotPresent
          args: ["milvus", "run", "standalone"]
          ports:
            - containerPort: 19530
              name: grpc
            - containerPort: 9091
              name: metrics
          env:
            - name: ETCD_ENDPOINTS
              value: "milvus-etcd:2379"
            - name: MINIO_ADDRESS
              value: "operator-rustfs:9000"
            - name: MINIO_ACCESS_KEY_ID
              valueFrom:
                secretKeyRef:
                  name: rustfs-secrets
                  key: RUSTFS_ACCESS_KEY
            - name: MINIO_SECRET_ACCESS_KEY
              valueFrom:
                secretKeyRef:
                  name: rustfs-secrets
                  key: RUSTFS_SECRET_KEY
          resources:
            requests:
              cpu: 500m
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 8Gi
          readinessProbe:
            tcpSocket:
              port: 19530
            initialDelaySeconds: 30
            periodSeconds: 15
            failureThreshold: 20
          volumeMounts:
            - name: milvus-data
              mountPath: /var/lib/milvus
      volumes:
        - name: milvus-data
          persistentVolumeClaim:
            claimName: milvus-data
---
apiVersion: v1
kind: Service
metadata:
  name: milvus
  namespace: bkg
  labels:
    app: milvus
spec:
  selector:
    app: milvus
  ports:
    - name: grpc
      port: 19530
      targetPort: 19530
    - name: metrics
      port: 9091
      targetPort: 9091
```

### 5、部署 temporal（temporal-mysql + temporal + temporal-ui）

```yaml
# 13-temporal.yaml
apiVersion: v1
kind: Secret
metadata:
  name: temporal-mysql-secret
  namespace: bkg
type: Opaque
stringData:
  root_password: "temporal"
---
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: temporal-mysql
  namespace: bkg
spec:
  serviceName: temporal-mysql
  replicas: 1
  selector:
    matchLabels:
      app: temporal-mysql
  template:
    metadata:
      labels:
        app: temporal-mysql
    spec:
      containers:
        - name: mysql
          image: 10.50.62.9:30303/library/mysql:8.4
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 3306
              name: server
          env:
            - name: MYSQL_ROOT_PASSWORD
              valueFrom:
                secretKeyRef:
                  name: temporal-mysql-secret
                  key: root_password
          resources:
            requests:
              cpu: 200m
              memory: 1Gi
            limits:
              cpu: "1"
              memory: 4Gi
          readinessProbe:
            exec:
              command: ["mysqladmin", "ping", "-h", "127.0.0.1", "-u", "root", "-ptemporal"]
            initialDelaySeconds: 20
            periodSeconds: 10
            failureThreshold: 20
          volumeMounts:
            - name: temporal-mysql-data
              mountPath: /var/lib/mysql
      volumes:
        - name: temporal-mysql-data
          persistentVolumeClaim:
            claimName: temporal-mysql-data
---
apiVersion: v1
kind: Service
metadata:
  name: temporal-mysql
  namespace: bkg
  labels:
    app: temporal-mysql
spec:
  selector:
    app: temporal-mysql
  ports:
    - name: server
      port: 3306
      targetPort: 3306
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: temporal
  namespace: bkg
  labels:
    app: temporal
spec:
  replicas: 1
  selector:
    matchLabels:
      app: temporal
  template:
    metadata:
      labels:
        app: temporal
    spec:
      containers:
        - name: temporal
          image: 10.50.62.9:30303/library/temporal-auto-setup:1.29.2
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 7233
              name: frontend
          env:
            - name: DB
              value: "mysql8"
            - name: DB_PORT
              value: "3306"
            # 官方 mysql:8.4 镜像的 MYSQL_USER 不是 superuser，auto-setup 无法 CREATE DATABASE，
            # 因此用 root 连（密码在 temporal-mysql-secret 中，与 WORKFLOW_MYSQL_PASSWORD 对应）
            - name: MYSQL_USER
              value: "root"
            - name: MYSQL_PWD
              valueFrom:
                secretKeyRef:
                  name: temporal-mysql-secret
                  key: root_password
            - name: MYSQL_SEEDS
              value: "temporal-mysql"
          resources:
            requests:
              cpu: 200m
              memory: 512Mi
            limits:
              cpu: "1"
              memory: 2Gi
          readinessProbe:
            tcpSocket:
              port: 7233
            initialDelaySeconds: 30
            periodSeconds: 15
            failureThreshold: 30
---
apiVersion: v1
kind: Service
metadata:
  name: temporal
  namespace: bkg
  labels:
    app: temporal
spec:
  selector:
    app: temporal
  ports:
    - name: frontend
      port: 7233
      targetPort: 7233
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: temporal-ui
  namespace: bkg
  labels:
    app: temporal-ui
spec:
  replicas: 1
  selector:
    matchLabels:
      app: temporal-ui
  template:
    metadata:
      labels:
        app: temporal-ui
    spec:
      containers:
        - name: temporal-ui
          image: 10.50.62.9:30303/library/temporal-ui:2.39.0
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 8080
              name: http
          env:
            - name: TEMPORAL_ADDRESS
              value: "temporal:7233"
          resources:
            requests:
              cpu: 50m
              memory: 128Mi
            limits:
              cpu: 500m
              memory: 512Mi
---
apiVersion: v1
kind: Service
metadata:
  name: temporal-ui
  namespace: bkg
  labels:
    app: temporal-ui
spec:
  type: NodePort
  selector:
    app: temporal-ui
  ports:
    - name: http
      port: 8080
      targetPort: 8080
      nodePort: 30833
```

## 六、数据初始化

1. **创建业务配置**（部署业务前完成，地址与密码按实际环境修改）：

   - `02-configmap.yaml`：修改 `MYSQL_HOST`（主库地址）、`TRS_GRAPH_BASE_URL`（图谱服务地址）、`TRS_GRAPH_SPACE` 等外部依赖项。
   - `03-secret.yaml`：替换 `MYSQL_PASSWORD` / `PAPER_COOP_MYSQL_PASSWORD` / `TRS_GRAPH_API_KEY` 等 `CHANGE_ME` 占位值；确认 rustfs 凭证与 `rustfs-secrets` 一致。

2. **temporal 库**：`temporal-auto-setup` 首次启动自动创建并初始化 Temporal 所需数据库，无需手工导入。

3. **业务控制面库 techkg_control**（temporal-mysql 实例内，业务启动前创建一次）：

   ```sql
   CREATE DATABASE IF NOT EXISTS techkg_control DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

   表结构由业务（`SCHEMA_AUTO_INIT=true`）自动初始化。

4. **主 MySQL 业务库**：在外部主 MySQL 上确认 `gkx_element`、`gkx_local` 两个库存在且账号有权限；`SCHEMA_AUTO_INIT=true` 时 `gkx_element` 表结构由 api 启动时自动创建/补齐。若交付含存量数据，按数据交付清单另行导入。

5. **rustfs bucket**：`tech-kg-schema-scripts`、`tech-kg-operators` 两个 bucket 由业务首次写入时自动创建，无需手工创建。

6. **首个管理员**：`PLATFORM_BOOTSTRAP_FIRST_ADMIN=true` 时，首个通过用户中心 SSO 登录的账号自动成为平台管理员；也可用 `PLATFORM_INITIAL_ADMIN_USER_IDS` 预置。

## 七、前后端业务部署

### 后端

后端三个 Deployment 共用镜像 `10.50.62.9:30303/bkg/baked:v0.0.1`，仅启动命令不同。

**1、m3e-embedding（专利向量化服务）**

```yaml
# 20-m3e-embedding.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: m3e-embedding
  namespace: bkg
  labels:
    app: m3e-embedding
spec:
  replicas: 1
  selector:
    matchLabels:
      app: m3e-embedding
  template:
    metadata:
      labels:
        app: m3e-embedding
    spec:
      containers:
        - name: m3e-embedding
          image: 10.50.62.9:30303/bkg/baked:v0.0.1
          imagePullPolicy: IfNotPresent
          command:
            [
              ".venv/bin/uvicorn",
              "script.m3e_embedding_service:app",
              "--host",
              "0.0.0.0",
              "--port",
              "8010",
            ]
          env:
            - name: M3E_MODEL_NAME
              value: "moka-ai/m3e-small"
            - name: M3E_EMBEDDING_DIM
              value: "512"
            - name: M3E_DEVICE
              value: "cpu"
            - name: M3E_BATCH_SIZE
              value: "8"
            - name: M3E_MAX_BATCH_SIZE
              value: "64"
            - name: M3E_MAX_CONCURRENCY
              value: "1"
            - name: HF_HOME
              value: /models/huggingface
          ports:
            - containerPort: 8010
              name: http
          resources:
            requests:
              cpu: 500m
              memory: 2Gi
            limits:
              cpu: "2"
              memory: 4Gi
          startupProbe:
            httpGet:
              path: /health
              port: 8010
            periodSeconds: 15
            failureThreshold: 60 # 最长 15 分钟，覆盖首次下载模型
          readinessProbe:
            httpGet:
              path: /health
              port: 8010
            periodSeconds: 15
          volumeMounts:
            - name: m3e-model-cache
              mountPath: /models/huggingface
      volumes:
        - name: m3e-model-cache
          persistentVolumeClaim:
            claimName: m3e-model-cache
---
apiVersion: v1
kind: Service
metadata:
  name: m3e-embedding
  namespace: bkg
  labels:
    app: m3e-embedding
spec:
  selector:
    app: m3e-embedding
  ports:
    - name: http
      port: 8010
      targetPort: 8010
```

> 首次启动需从 HuggingFace 下载 m3e 模型（约 15 分钟内）；集群无法直连 HF 时在 env 中增加 `HF_ENDPOINT` 指向镜像站。

**2、temporal-worker（工作流消费者）**

```yaml
# 21-temporal-worker.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: temporal-worker
  namespace: bkg
  labels:
    app: temporal-worker
spec:
  replicas: 1
  selector:
    matchLabels:
      app: temporal-worker
  template:
    metadata:
      labels:
        app: temporal-worker
    spec:
      containers:
        - name: temporal-worker
          image: 10.50.62.9:30303/bkg/baked:v0.0.1
          imagePullPolicy: IfNotPresent
          command: [".venv/bin/python", "-m", "script.run_temporal_worker"]
          envFrom:
            - configMapRef:
                name: tech-kg-config
            - secretRef:
                name: tech-kg-secrets
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: "2"
              memory: 4Gi
          volumeMounts:
            - name: workflow-state
              mountPath: /var/lib/tech-kg
      volumes:
        - name: workflow-state
          persistentVolumeClaim:
            claimName: workflow-state
```

**3、api（FastAPI 主服务）**

注意：Service 必须命名为 `api` —— 前端镜像内 nginx 固定反代 `http://api:8000`。

```yaml
# 22-api.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
  namespace: bkg
  labels:
    app: api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      containers:
        - name: api
          image: 10.50.62.9:30303/bkg/baked:v0.0.1
          imagePullPolicy: IfNotPresent
          envFrom:
            - configMapRef:
                name: tech-kg-config
            - secretRef:
                name: tech-kg-secrets
          ports:
            - containerPort: 8000
              name: http
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: "2"
              memory: 4Gi
          readinessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 15
            periodSeconds: 10
            failureThreshold: 12
          livenessProbe:
            httpGet:
              path: /health
              port: 8000
            initialDelaySeconds: 30
            periodSeconds: 15
            failureThreshold: 12
          volumeMounts:
            - name: operator-data
              mountPath: /app/operators/user
            - name: patent-index-state
              mountPath: /app/var/patent_indexes
            - name: workflow-state
              mountPath: /var/lib/tech-kg
      volumes:
        - name: operator-data
          persistentVolumeClaim:
            claimName: operator-data
        - name: patent-index-state
          persistentVolumeClaim:
            claimName: patent-index-state
        - name: workflow-state
          persistentVolumeClaim:
            claimName: workflow-state
---
apiVersion: v1
kind: Service
metadata:
  name: api
  namespace: bkg
  labels:
    app: api
spec:
  selector:
    app: api
  ports:
    - name: http
      port: 8000
      targetPort: 8000
```

### 前端

```yaml
# 23-web.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
  namespace: bkg
  labels:
    app: web
spec:
  replicas: 1
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: web
          image: 10.50.62.9:30303/bkg/baked-web:v0.0.1
          imagePullPolicy: IfNotPresent
          ports:
            - containerPort: 80
              name: http
          resources:
            requests:
              cpu: 50m
              memory: 64Mi
            limits:
              cpu: 500m
              memory: 256Mi
          readinessProbe:
            httpGet:
              path: /
              port: 80
            initialDelaySeconds: 5
            periodSeconds: 10
---
apiVersion: v1
kind: Service
metadata:
  name: web
  namespace: bkg
  labels:
    app: web
spec:
  type: NodePort
  selector:
    app: web
  ports:
    - name: http
      port: 80
      targetPort: 80
      nodePort: 30880
```

### 部署顺序与验证

```bash
# 顺序：存储 → 中间件 → 业务配置 → 业务
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-pvc.yaml          # 界面已建 PVC 则跳过
kubectl apply -f 10-auth-redis.yaml
kubectl apply -f 11-operator-rustfs.yaml
kubectl apply -f 12-milvus.yaml
kubectl apply -f 13-temporal.yaml
kubectl apply -f 02-configmap.yaml    # 先按第六节修改地址/密码
kubectl apply -f 03-secret.yaml
kubectl apply -f 20-m3e-embedding.yaml
kubectl apply -f 21-temporal-worker.yaml
kubectl apply -f 22-api.yaml
kubectl apply -f 23-web.yaml

# 验证
kubectl -n bkg get pods -o wide
kubectl -n bkg exec deploy/api -- curl -s http://localhost:8000/health
```

## 八、代理配置

域名使用：https://edu.itic-sci.com/bkg_zp

外部统一入口走平台的 nginx/Ingress 反代到 `web` 服务（NodePort 30880），路径规则：

- `https://edu.itic-sci.com/bkg_zp/` → 前端静态资源（`web:80`）
- `https://edu.itic-sci.com/bkg_zp/api/` → 后端接口（web 容器内 nginx 已将 `/api/` 反代到 `api:8000`，无需额外配置）

Ingress 示例（平台自带入口则按同样路径规则配置）：

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: bkg-web
  namespace: bkg
  annotations:
    nginx.ingress.kubernetes.io/rewrite-target: /$2
spec:
  rules:
    - host: edu.itic-sci.com
      http:
        paths:
          - path: /bkg_zp(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: web
                port:
                  number: 80
```

注意事项：

1. **前端构建参数必须与代理路径一致**：`baked-web` 镜像构建时需传 `VITE_BASE=/bkg_zp/`、`VITE_API_BASE=/bkg_zp/api`（默认 `./` 与 `/api` 只适用于根路径部署）。
2. **认证 Cookie 路径**：`AUTH_COOKIE_PATH=/bkg_zp`（已配置在 02-configmap.yaml），与代理路径保持一致，否则登录态无法写入。
3. **HTTPS**：`AUTH_COOKIE_SECURE=true` 要求外部入口必须是 HTTPS，平台证书按域名 `edu.itic-sci.com` 配置。
4. **SSO 回调**：`USER_CENTER_REDIRECT_URI=https://edu.itic-sci.com/bkg_zp/api/v1/auth/callback` 需在用户中心完成客户端注册（`USER_CENTER_CLIENT_ID` / `USER_CENTER_CLIENT_SECRET`）。
5. **temporal-ui**（NodePort 30833）与 rustfs console 仅供运维排障，建议不对外网暴露。
