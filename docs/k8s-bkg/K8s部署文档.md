# 科技知识图谱（tech-kg）K8s 交付部署文档

## 一、文档目的

交付工程师依据本文档，部署科技知识图谱业务（命名空间 `bkg`）。

- 镜像仓库地址：<http://10.50.62.9:30303>
- 容器管理平台地址：<https://10.50.199.115>

本文档自包含全部 13 份部署清单（见下表），**不再附带独立 yaml 文件**——以本文档为唯一交付物，避免正文与文件两份拷贝漂移。部署时将各节标注编号的 yaml 内容保存为同名临时文件后 `kubectl apply`，或直接在容器平台界面按序导入；其中 02/03 须先按第七节完成地址与密码的修改：

| 清单 | 内容 |
| ------ | ------ |
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
| `23-web.yaml` | 前端（nginx，剥前缀入口挂根式模板） |
| `24-web-nginx-template.yaml` | web 的 nginx 根路径模板 ConfigMap |

## 二、修订记录

| 版本 | 文档发布日期 | 修订内容 |
| ------ | ------------ | --------- |
| v0.0.7 | 2026/9/10 | §九 新增「临时改用 IP 直连登录」清单：5 个环境变量（APP_BASE / AUTH_COOKIE_PATH / AUTH_COOKIE_SECURE / AUTH_FRONTEND_URL / USER_CENTER_REDIRECT_URI）+ 用户中心回调登记 + `set env` 快速切换/回退命令与安全注意事项 |
| v0.0.6 | 2026/9/10 | 图谱服务连接配置标注来源：§七 02-configmap 的 `TRS_GRAPH_*` 四项与 03-secret 的 `TRS_GRAPH_API_KEY`、§四 依赖表、`docs/k8s-deployment.md` ConfigMap 示例、后端 `infra/graph_db/config.py`，均注明取值对应《图数据库平台（TRS Graph）K8s 部署文档》的 §五.8 Service（trs-graph-service:8090）/ §五.3 Secret（api-key-hash 明文 ysukeg）/ §六 图空间（须与 TRS_GRAPH_SPACE 同名、replica_factor=1） |
| v0.0.5 | 2026/9/10 | 交付物收口为单一部署文档：02-configmap / 03-secret / 24-web-nginx-template 内联进正文（02/03 在 §七、24 在 §八 前端），删除全部独立 yaml 文件，本文档为唯一交付物（PVC 容量维持 a65647d 统一后的 10Gi 口径） |
| v0.0.4 | 2026/9/10 | 文档正文 9 个工作负载（auth-redis / milvus-etcd / milvus / temporal-mysql / temporal / temporal-ui / temporal-worker / api / web）补回缺失的 `imagePullSecrets: bkg-image-pull-secret-0`，与同目录 yaml 文件对齐，此前按正文直接部署会 ImagePullBackOff；正文 23-web 补回 `envFrom: bkg-config` 与 `bkg-nginx-template` 挂载（与文件对齐，否则剥前缀入口下前端静态资源/路由 404）；明确 02/03/24 内容以文件为准、正文不重复 |
| v0.0.3 | 2026/9/9 | m3e 模型内置 backend 镜像（v0.0.2）三个 Deployment 共用，启动免联网下载；删除 m3e-model-cache PVC；m3e 启动探针收紧；文档表格格式化、PVC 示例补 storageClassName |
| v0.0.2 | 2026/9/4 | 前端镜像一次构建运行时注入（APP_BASE）；与 TRS Graph 同命名空间对齐（imagePullSecrets/GRAPH_SPACE_REPLICA_FACTOR）；项目内命名统一 bkg；新增镜像准备与拉取密钥章节 |
| 1.0 | 2026/8/28 | 初版 |

## 三、名称解释

| 名称 | 解释 |
| ------ | ------ |
| 容器平台 | k8s 云业务平台，集成了多种功能在界面进行操作和监控 |
| 镜像仓库 | 用于存储业务所用的镜像仓库（本环境为 10.50.62.9:30303） |
| backend | 后端业务镜像（api / temporal-worker / m3e-embedding 三个 Deployment 共用同一镜像，已内置 m3e 模型，通过不同启动命令区分） |
| web | 前端业务镜像（nginx 静态资源 + `/api/` 反代） |
| rustfs | S3 兼容对象存储，承载 schema 脚本、operator 包、milvus 内部存储 |
| temporal | 工作流引擎，图谱构建任务通过它编排调度 |

## 四、环境说明

部署说明：以下部署操作所有镜像均上传到部署在平台的镜像仓库，所有操作都在容器管理平台界面操作，配置文件和存储以界面创建为主，业务以 yaml 方式部署到容器。

本业务（bkg 命名空间）部署需要以下中间件：

| 组件 | 版本 | 用途 |
| ------ | ------ | ------ |
| redis | 7.4-alpine | 认证会话存储（auth-redis） |
| rustfs | 1.0.0-alpha.93 | S3 对象存储（schema 脚本 / operator 包 / milvus 存储） |
| etcd | 3.5.5 | milvus 元数据 |
| milvus | 2.4.17 | 专利 / 机构向量检索 |
| mysql | 8.4 | temporal 专用库 + 业务控制面库 techkg_control |
| temporal | 1.29.2（auto-setup） | 工作流引擎 |
| temporal-ui | 2.39.0 | 工作流控制台（运维观察用） |
| backend | v0.0.2（Python 3.11） | 后端业务镜像 ×3（api / temporal-worker / m3e-embedding），已内置 m3e-small 模型 |
| web | v0.0.1（nginx 1.27） | 前端业务镜像 |

**集群外依赖**（需提前准备，yaml 中只填连接地址）：

| 依赖 | 说明 |
| ------ | ------ |
| 主 MySQL | 业务主库 `gkx_element` + 论文合作库 `gkx_local`（环境变量 `MYSQL_*` / `PAPER_COOP_MYSQL_*`） |
| trs-graph-service | NebulaGraph REST 网关（Java），环境变量 `TRS_GRAPH_BASE_URL` / `TRS_GRAPH_API_KEY` / `TRS_GRAPH_SPACE`（三项分别对应《图数据库平台（TRS Graph）K8s 部署文档》§五.8 Service、§五.3 Secret、§六 图空间，逐项对应关系见 §七 内联 yaml 注释） |
| LLM API | 智谱 GLM（可选，未配置时相关功能自动降级） |
| 用户中心 SSO | `edu.itic-sci.com`（开启 `AUTH_ENABLED=true` 时必需） |

- 镜像仓库地址：<http://10.50.62.9:30303>
- 容器管理平台地址：<https://10.50.199.115>

**与 TRS Graph 图数据库平台同命名空间（`bkg`）共存**（其部署文档：《图数据库平台（TRS Graph）K8s 部署文档》）：

- 本项目后端依赖其 `trs-graph-service:8090`（其部署文档 §五.8 的 Service；同命名空间 ClusterDNS 直连，`TRS_GRAPH_BASE_URL` 已配置）；API Key `ysukeg` 一致（其 §五.3 Secret `trsgraph-secret` 中 api-key-hash 的明文）
- Service / NodePort / Secret / ConfigMap / PVC 名称已逐一核对**无冲突**（其占用 NodePort 30090、30002；本项目占用 30880、30833）
- **必须 `GRAPH_SPACE_REPLICA_FACTOR=1`**（已配置在 02-configmap）：对方 storaged 为单副本，默认 3 副本建图空间会 `Host not enough` 失败
- 本项目命名空间不可更改（跨命名空间将解析不到 trs-graph-service）

## 五、镜像准备与拉取密钥

### 1、登录镜像仓库

```bash
docker login 10.50.62.9:30303
```

### 2、构建并推送业务镜像（后端一套、前端一套）

```bash
# 后端（api / temporal-worker / m3e-embedding 三个 Deployment 共用同一镜像；
# 构建期把 m3e-small 模型下载进镜像，m3e 服务启动即用、无需联网）
docker build -t 10.50.62.9:30303/bkg/backend:v0.0.2 \
  --build-arg PYPI_INDEX_URL=https://mirrors.aliyun.com/pypi/simple/ \
  --build-arg HF_ENDPOINT=https://hf-mirror.com \
  ./backend

# 前端（一次构建、部署期注入——不传任何 VITE_*，部署前缀由 bkg-config 的 APP_BASE 决定）
docker build -t 10.50.62.9:30303/bkg/web:v0.0.1 \
  --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  ./frontend

docker push 10.50.62.9:30303/bkg/backend:v0.0.2
docker push 10.50.62.9:30303/bkg/web:v0.0.1
```

> 版本升级沿用 v0.0.1 覆盖推送时注意：清单为 `imagePullPolicy: IfNotPresent`，节点不会自动重拉——升级后需删除对应 Pod（或节点上 `crictl rmi`）强制重拉；建议递增 tag 并同步四个 yaml 的 image 引用。

### 3、中间件镜像转推 library/ 项目

中间件镜像统一从 `10.50.62.9:30303/library/` 拉取，部署前需从公网源拉取、转推（源可用国内镜像加速替代）：

```bash
REG=10.50.62.9:30303/library
push_mw() { docker pull "$1" && docker tag "$1" "$REG/$2" && docker push "$REG/$2"; }

push_mw redis:7.4-alpine                     redis:7.4-alpine
push_mw busybox:1.36                         busybox:1.36
push_mw rustfs/rustfs:1.0.0-alpha.93         rustfs:1.0.0-alpha.93
push_mw quay.io/coreos/etcd:v3.5.5           etcd:3.5.5
push_mw milvusdb/milvus:v2.4.17              milvus:v2.4.17
push_mw mysql:8.4                            mysql:8.4
push_mw temporalio/auto-setup:1.29.2         temporal-auto-setup:1.29.2
push_mw temporalio/ui:2.39.0                 temporal-ui:2.39.0
```

### 4、创建镜像拉取密钥（全部工作负载引用 `bkg-image-pull-secret-0`）

```bash
kubectl -n bkg create secret docker-registry bkg-image-pull-secret-0 \
  --docker-server=10.50.62.9:30303 \
  --docker-username=<Harbor 用户名> \
  --docker-password=<Harbor 密码>
```

> 若 TRS Graph 侧已创建同名密钥则跳过。该密钥必须先于任何业务/中间件 Pod 创建（否则 ImagePullBackOff）。

## 六、中间件组件部署流程

以下 yaml 命名空间均为 `bkg`。中间件镜像统一从 `10.50.62.9:30303/library/` 拉取（转推命令见第五节），业务镜像见第五节构建推送，拉取密钥 `bkg-image-pull-secret-0` 需先于任何 Pod 创建。

### 1、创建命名空间与 PVC

在平台上给所有组件创建 PVC（界面创建为主；名称必须与下表一致）：

| PVC 名称 | 容量建议 | 挂载组件 |
| ---------- | --------- | --------- |
| operator-rustfs-data | 50Gi（ReadWriteMany） | operator-rustfs |
| milvus-etcd-data | 10Gi | milvus-etcd |
| milvus-data | 10Gi | milvus |
| temporal-mysql-data | 10Gi | temporal-mysql |
| workflow-state | 10Gi | temporal-worker / api |
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
  storageClassName: managed-nfs-storage
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
  storageClassName: managed-nfs-storage
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
      storage: 10Gi
  storageClassName: managed-nfs-storage
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
      storage: 10Gi
  storageClassName: managed-nfs-storage
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
      storage: 10Gi
  storageClassName: managed-nfs-storage
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
  storageClassName: managed-nfs-storage
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
  storageClassName: managed-nfs-storage
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
  storageClassName: managed-nfs-storage
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
      # 必须以 root 运行：busybox init 容器执行 chown/chmod 需要 root，
      # 非 root 的 chown 一律 Operation not permitted，pod 会卡死在 Init:Error。
      # NFS 类 storageclass（nfs-client / managed-nfs-storage）普遍忽略 fsGroup，
      # 因此用 chmod 777 兜底可写，不依赖目录属主与运行用户的匹配。
      securityContext:
        runAsUser: 0
        runAsGroup: 0
        fsGroup: 0
      initContainers:
        - name: fix-permissions
          image: 10.50.62.9:30303/library/busybox:1.36
          command: ["sh", "-c", "chmod -R 777 /data && chown -R 0:0 /data"]
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
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

## 七、数据初始化

1. **创建业务配置**（部署业务前完成；两份清单见下方，地址与密码按实际环境修改后再 apply）：

   - `02-configmap.yaml`（ConfigMap `bkg-config`）：修改 `MYSQL_HOST`（主库地址）、`TRS_GRAPH_BASE_URL`（图谱服务地址）、`TRS_GRAPH_SPACE` 等外部依赖项（图谱三项与对方部署文档的逐项对应关系见下方 yaml 内注释；`TRS_GRAPH_SPACE` 必须与其 §六 实际创建的图空间同名）。
   - `03-secret.yaml`（Secret `bkg-secrets`）：替换 `MYSQL_PASSWORD` / `PAPER_COOP_MYSQL_PASSWORD` / `TRS_GRAPH_API_KEY` 等 `CHANGE_ME` 占位值；确认 rustfs 凭证与 `rustfs-secrets` 一致。

```yaml
# 02-configmap.yaml
# bkg 业务非敏感配置（api / temporal-worker 共用，envFrom 注入）。
# ★ 部署前必须确认两类外部依赖的地址：
#   1. MYSQL_HOST / PAPER_COOP_MYSQL_* —— 主库（gkx_element）与论文合作库（gkx_local）
#   2. TRS_GRAPH_BASE_URL —— trs-graph-service（NebulaGraph 网关）
apiVersion: v1
kind: ConfigMap
metadata:
  name: bkg-config
  namespace: bkg
data:
  # 前端部署前缀（运行时注入，见 docs/前端一次构建多环境部署方案.md）
  APP_BASE: "/bkg_zpt"
  # ---- 图谱服务（外部依赖，按实际环境修改）----
  # ▼ 四项取值均来自《图数据库平台（TRS Graph）K8s 部署文档》（同命名空间 bkg），改任一侧需同步：
  #   TRS_GRAPH_BASE_URL ← 其 §五.8「部署 trs-graph-service」的 Service 名 + 端口 8090
  #     （集群内 ClusterIP 直连；集群外访问才用其 NodePort 30090 / Ingress /timks。
  #       其 §五.5 的 trsgraph:9669 是 Nebula 原生协议口，仅 Studio/图算法直连用，本项目走 REST 不涉及）
  #   TRS_GRAPH_SPACE ← 其 §六「数据初始化」实际创建的图空间名——其服务默认 space
  #     （entity_binding_demo / TRSGRAPH_SPACE 变量）对本项目不生效：客户端每请求带
  #     X-Graph-Space 头覆盖，两侧名字必须一致，否则所有图操作查不到数据
  #   GRAPH_SPACE_REPLICA_FACTOR=1 ← 其 storaged 为单副本（§五.6），建空间默认 3 副本会 Host not enough
  #   TRS_GRAPH_TIMEOUT ← 本项目侧请求超时，与对方配置无关
  TRS_GRAPH_BASE_URL: "http://trs-graph-service:8090"
  TRS_GRAPH_SPACE: "dev"
  # TRS Graph 单副本 storaged，建图空间必须 replica_factor=1（默认 3 会 Host not enough）
  GRAPH_SPACE_REPLICA_FACTOR: "1"
  TRS_GRAPH_TIMEOUT: "30"

  # ---- 主 MySQL（外部依赖，按实际环境修改）----
  MYSQL_HOST: "mysql"
  MYSQL_PORT: "3306"
  MYSQL_DATABASE: "gkx_element"
  MYSQL_USERNAME: "gkx"
  # 论文合作库可独立部署；未单独配置时沿用主 MySQL 连接参数
  PAPER_COOP_MYSQL_HOST: "mysql"
  PAPER_COOP_MYSQL_PORT: "3306"
  PAPER_COOP_MYSQL_DATABASE: "gkx_local"
  PAPER_COOP_MYSQL_USERNAME: "root"

  # ---- Milvus 向量库 ----
  MILVUS_HOST: "milvus"
  MILVUS_PORT: "19530"
  PATENT_MILVUS_COLLECTION: "patent"
  PATENT_INDEX_STATE_DIR: "/app/var/patent_indexes"
  PATENT_INDEX_PAGE_SIZE: "1000"
  PATENT_BM25_DIM: "262144"
  ORG_MILVUS_STATE_DIR: "/var/lib/bkg/organization_milvus"

  # ---- LLM（未配置 LLM_API_KEY 时相关功能自动降级）----
  LLM_MODEL: "glm-5.3-flash"
  LLM_BASE_URL: "https://open.bigmodel.cn/api/paas/v4"

  # ---- Temporal 工作流 ----
  TEMPORAL_ADDRESS: "temporal:7233"
  TEMPORAL_NAMESPACE: "default"
  TEMPORAL_TASK_QUEUE: "bkg-workflows"
  TEMPORAL_MAX_CONCURRENT_ACTIVITIES: "4"
  # 控制面 MySQL（temporal-mysql 的 techkg_control 库，跟 Temporal 共用实例但独立库）
  WORKFLOW_MYSQL_HOST: "temporal-mysql"
  WORKFLOW_MYSQL_PORT: "3306"
  WORKFLOW_MYSQL_DATABASE: "techkg_control"
  WORKFLOW_MYSQL_USERNAME: "root"
  WORKFLOW_SCRIPT_DIR: "/var/lib/bkg/scripts"
  WORKFLOW_DEMO_DATA_ENABLED: "false"

  # ---- S3（operator-rustfs，schema 脚本 / operator 包 / milvus 内部存储共用）----
  SCHEMA_S3_ENDPOINT_URL: "http://operator-rustfs:9000"
  SCHEMA_S3_BUCKET: "bkg-schema-scripts"
  SCHEMA_S3_REGION: "us-east-1"
  SCHEMA_S3_SECURE: "false"
  SCHEMA_SCRIPT_MAX_BYTES: "10485760"
  SCHEMA_ADMIN_USER_IDS: "schema-admin"
  OPERATOR_DIR: "/app/operators/user"
  OPERATOR_S3_ENDPOINT_URL: "http://operator-rustfs:9000"
  OPERATOR_S3_BUCKET: "bkg-operators"
  OPERATOR_S3_PREFIX: "operators"
  OPERATOR_S3_REGION: "us-east-1"

  # ---- 专利 embedding（m3e-embedding 服务）----
  PATENT_EMBEDDING_PROVIDER: "openai"
  PATENT_EMBEDDING_BASE_URL: "http://m3e-embedding:8010/v1"
  PATENT_EMBEDDING_MODEL: "moka-ai/m3e-small"
  PATENT_EMBEDDING_DIM: "512"

  # ---- 认证 / 用户中心 SSO ----
  AUTH_ENABLED: "true"
  AUTH_SESSION_BACKEND: "redis"
  AUTH_SESSION_COOKIE: "techkg_session"
  AUTH_SESSION_TTL_SECONDS: "604800"
  AUTH_STATE_TTL_SECONDS: "300"
  AUTH_AUDIT_TTL_SECONDS: "7776000"
  AUTH_AUDIT_MAX_ITEMS: "200"
  AUTH_COOKIE_SECURE: "true"
  AUTH_COOKIE_SAMESITE: "lax"
  AUTH_COOKIE_PATH: "/bkg_zpt"
  AUTH_FRONTEND_URL: "https://edu.itic-sci.com/bkg_zpt"
  USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED: "false"
  USER_CENTER_PORTAL_TOKEN_COOKIE: "access_token"
  USER_CENTER_SSO_LOGIN_URL: "https://edu.itic-sci.com/uc/sso/login"
  USER_CENTER_OAUTH_BASE_URL: "https://edu.itic-sci.com/uc/admin-api/system/oauth2"
  USER_CENTER_ACCOUNT_URL: "https://edu.itic-sci.com/uc/admin/login?redirect=/index"
  USER_CENTER_REDIRECT_URI: "https://edu.itic-sci.com/bkg_zpt/api/v1/auth/callback"

  # ---- Redis 会话 ----
  REDIS_URL: "redis://auth-redis:6379/0"

  # ---- 其他 ----
  SCHEMA_AUTO_INIT: "true"
  PLATFORM_BOOTSTRAP_FIRST_ADMIN: "true"
  CORRECTION_SYNC_WORKER_ENABLED: "true"
  CORRECTION_SYNC_INTERVAL_SECONDS: "30"
  CORRECTION_SYNC_MAX_ATTEMPTS: "8"
  CORRECTION_SYNC_MODE: "projection"
```

```yaml
# 03-secret.yaml
# bkg 业务敏感配置（api / temporal-worker 共用，envFrom 注入）。
# ★ 上线前务必替换所有占位值；stringData 为明文写入，kubectl apply 后可改用 sealed-secret 管理。
apiVersion: v1
kind: Secret
metadata:
  name: bkg-secrets
  namespace: bkg
type: Opaque
stringData:
  # 图谱服务 API Key ←《图数据库平台（TRS Graph）K8s 部署文档》§五.3「创建业务密钥」
  #   Secret trsgraph-secret 的 api-key-hash（= sha256(明文)）：此处填明文，请求头
  #   X-API-Key 携带明文、对方服务端哈希后比对；改 key 需两侧同步并重算哈希。
  #   同一 Secret 的 username/password（root/trsadmin）是 Nebula 9669 直连账号
  #   （Studio/图算法用），REST 调用方不涉及。
  TRS_GRAPH_API_KEY: "ysukeg"
  # 主 MySQL / 论文合作库密码
  MYSQL_PASSWORD: "gkx_element"
  PAPER_COOP_MYSQL_PASSWORD: "gkx_element"
  # 控制面 MySQL（temporal-mysql root 密码，与 temporal-mysql-secret 保持一致）
  WORKFLOW_MYSQL_PASSWORD: "temporal"
  # LLM API Key（留空则 LLM 相关功能降级）
  LLM_API_KEY: ""
  # S3（operator-rustfs）凭证，与 rustfs 部署的 ACCESS_KEY/SECRET_KEY 保持一致
  SCHEMA_S3_ACCESS_KEY: "rustfsadmin"
  SCHEMA_S3_SECRET_KEY: "rustfsadmin"
  OPERATOR_S3_ACCESS_KEY_ID: "rustfsadmin"
  OPERATOR_S3_SECRET_ACCESS_KEY: "rustfsadmin"
  # m3e-embedding 本地服务无鉴权
  PATENT_EMBEDDING_API_KEY: "local-no-auth"
  # 用户中心 SSO 客户端凭证（按实际环境填写）
  USER_CENTER_CLIENT_ID: "98OPWXDM4QZUX54HZP7FYO6DJPWDDMQ9"
  USER_CENTER_CLIENT_SECRET: "RccfLICuv5tZs4NmV2qQ4MSujQJu6KBugJjKsNVUnFEEgVVZjMkaL1bYGbHnAC7R"
```

1. **temporal 库**：`temporal-auto-setup` 首次启动自动创建并初始化 Temporal 所需数据库，无需手工导入。

2. **业务控制面库 techkg_control**（temporal-mysql 实例内，业务启动前创建一次）：

   ```sql
   CREATE DATABASE IF NOT EXISTS techkg_control DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   ```

   表结构由业务（`SCHEMA_AUTO_INIT=true`）自动初始化。

3. **主 MySQL 业务库**：在外部主 MySQL 上确认 `gkx_element`、`gkx_local` 两个库存在且账号有权限；`SCHEMA_AUTO_INIT=true` 时 `gkx_element` 表结构由 api 启动时自动创建/补齐。若交付含存量数据，按数据交付清单另行导入。

4. **rustfs bucket**：`bkg-schema-scripts`、`bkg-operators` 两个 bucket 由业务首次写入时自动创建，无需手工创建。

5. **首个管理员**：`PLATFORM_BOOTSTRAP_FIRST_ADMIN=true` 时，首个通过用户中心 SSO 登录的账号自动成为平台管理员；也可用 `PLATFORM_INITIAL_ADMIN_USER_IDS` 预置。

## 八、前后端业务部署

### 后端

后端三个 Deployment 共用镜像 `10.50.62.9:30303/bkg/backend:v0.0.2`，仅启动命令不同。

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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
      containers:
        - name: m3e-embedding
          image: 10.50.62.9:30303/bkg/backend:v0.0.2
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
            - name: HF_HUB_OFFLINE
              value: "1"
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
            periodSeconds: 5
            failureThreshold: 24 # 最长 2 分钟，本地加载模型绰绰有余
          readinessProbe:
            httpGet:
              path: /health
              port: 8010
            periodSeconds: 15
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

> m3e-small 模型已内置 backend 镜像（构建期预置，见第五节构建命令的 `HF_ENDPOINT`），启动无需联网；`HF_HUB_OFFLINE=1` 强制离线加载，Pod 无外网也能起，也不再需要 `m3e-model-cache` PVC。

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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
      containers:
        - name: temporal-worker
          image: 10.50.62.9:30303/bkg/backend:v0.0.2
          imagePullPolicy: IfNotPresent
          command: [".venv/bin/python", "-m", "script.run_temporal_worker"]
          envFrom:
            - configMapRef:
                name: bkg-config
            - secretRef:
                name: bkg-secrets
          resources:
            requests:
              cpu: 500m
              memory: 1Gi
            limits:
              cpu: "2"
              memory: 4Gi
          volumeMounts:
            - name: workflow-state
              mountPath: /var/lib/bkg
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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
      containers:
        - name: api
          image: 10.50.62.9:30303/bkg/backend:v0.0.2
          imagePullPolicy: IfNotPresent
          envFrom:
            - configMapRef:
                name: bkg-config
            - secretRef:
                name: bkg-secrets
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
              mountPath: /var/lib/bkg
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

先创建 nginx 根路径模板 ConfigMap（23-web 挂载它；模板来源 `frontend/nginx.k8s.conf`，入口剥前缀说明见 §九）：

```yaml
# 24-web-nginx-template.yaml
# web 的 nginx 根路径模板（剥前缀入口用，挂载为 /etc/nginx/templates/ 渲染）。
# 来源 frontend/nginx.k8s.conf——修改后用
#   kubectl -n bkg create configmap bkg-nginx-template \
#     --from-file=default.conf.template=frontend/nginx.k8s.conf --dry-run=client -o yaml | kubectl apply -f -
# 重新生成本清单。若入口改为不剥前缀直连，删除 23-web 的挂载即可（镜像内置前缀模板）。
apiVersion: v1
kind: ConfigMap
metadata:
  name: bkg-nginx-template
  namespace: bkg
data:
  default.conf.template: |
    # K8s 前端 nginx 模板：根路径全兜底（配合剥前缀入口）。
    # 平台入口（Ingress rewrite-target /$2，见交付文档 §八）把 /bkg_zpt 前缀剥掉后
    # 转发到本 Service——浏览器侧带前缀（runtime-config.js 注入 base=/bkg_zpt、
    # apiBase=/bkg_zpt/api，资产引用经哨兵替换），到达本 nginx 时已是根路径：
    #   /bkg_zpt/overview    → 入口转发 /overview    → location / SPA 回退
    #   /bkg_zpt/assets/x.js → 入口转发 /assets/x.js → 静态文件
    #   /bkg_zpt/api/v1/...  → 入口转发 /api/v1/...  → 下方 /api/ 代理
    # 若入口改为不剥前缀的直连子路径，删除 23-web 的本模板挂载、
    # 使用镜像内置前缀模板即可。
    server {
      listen 80;
      server_name _;

      root /usr/share/nginx/html;
      index index.html;

      gzip on;
      gzip_types text/plain text/css application/json application/javascript text/xml application/xml application/xml+rss image/svg+xml;

      # k8s Service 域名由集群 DNS 稳定解析，无需 docker 式 resolver 动态解析
      location ^~ /api/ {
        proxy_pass http://api:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
      }

      location / {
        # 门户 iframe 嵌入仅允许同源与统一门户，禁止第三方 framing
        add_header Content-Security-Policy "frame-ancestors 'self' https://edu.itic-sci.com" always;
        add_header Referrer-Policy "strict-origin-when-cross-origin" always;
        # SPA index.html 必须 no-cache，否则浏览器用 stale HTML（含旧 JS hash 引用）
        add_header Cache-Control "no-cache, no-store, must-revalidate" always;
        add_header Pragma "no-cache" always;
        add_header Expires "0" always;
        try_files $uri $uri/ /index.html;
      }

      location ~* \.(?:js|css|png|jpg|jpeg|gif|ico|svg|woff2?)$ {
        expires 7d;
        add_header Cache-Control "public, max-age=604800";
        try_files $uri =404;
      }
    }
```

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
      imagePullSecrets:
        - name: bkg-image-pull-secret-0
      containers:
        - name: web
          image: 10.50.62.9:30303/bkg/web:v0.0.1
          imagePullPolicy: IfNotPresent
          envFrom:
            - configMapRef:
                name: bkg-config
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
          volumeMounts:
            # 根路径模板（剥前缀入口用）；必须挂到 templates/ 供 20-envsubst 渲染
            - name: nginx-template
              mountPath: /etc/nginx/templates/default.conf.template
              subPath: default.conf.template
              readOnly: true
      volumes:
        - name: nginx-template
          configMap:
            name: bkg-nginx-template
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

以下命令中的文件名指本文档对应编号的 yaml 清单——先把各节内容存为同名文件（或容器平台界面按序导入），再执行：

```bash
# 顺序：存储 → 中间件 → 业务配置 → 业务
kubectl apply -f 00-namespace.yaml
kubectl apply -f 01-pvc.yaml          # 界面已建 PVC 则跳过
kubectl apply -f 10-auth-redis.yaml
kubectl apply -f 11-operator-rustfs.yaml
kubectl apply -f 12-milvus.yaml
kubectl apply -f 13-temporal.yaml
kubectl apply -f 02-configmap.yaml    # 先按第七节修改地址/密码
kubectl apply -f 03-secret.yaml
kubectl apply -f 20-m3e-embedding.yaml
kubectl apply -f 21-temporal-worker.yaml
kubectl apply -f 22-api.yaml
kubectl apply -f 24-web-nginx-template.yaml
kubectl apply -f 23-web.yaml

# 验证
kubectl -n bkg get pods -o wide
kubectl -n bkg exec deploy/api -- curl -s http://localhost:8000/health
```

## 九、代理配置

域名使用：<https://edu.itic-sci.com/bkg_zpt>

外部统一入口走平台的 nginx/Ingress 反代到 `web` 服务（NodePort 30880），路径规则：

- `https://edu.itic-sci.com/bkg_zpt/` → 前端静态资源（`web:80`）
- `https://edu.itic-sci.com/bkg_zpt/api/` → 后端接口（入口剥掉 `/bkg_zpt` 前缀转发，web 容器内根式模板将 `/api/` 反代到 `api:8000`）

下方 Ingress 是**剥前缀**转发（`rewrite-target: /$2`）：容器收到根路径，因此 23-web 挂载
`24-web-nginx-template.yaml` 的根路径模板，`APP_BASE=/bkg_zpt` 仅由 runtime-config.js
注入到浏览器侧（资产/路由/API 均带 `/bkg_zpt` 前缀）。与统一门户的实测行为一致。

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
          - path: /bkg_zpt(/|$)(.*)
            pathType: ImplementationSpecific
            backend:
              service:
                name: web
                port:
                  number: 80
```

注意事项：

1. **前端镜像一次构建、部署期注入**：`web` 镜像不再传任何 `VITE_*` 构建参数（只留 `NPM_REGISTRY`）；部署前缀等配置由 web Pod `envFrom` 同一份 `bkg-config` 运行时注入（`APP_BASE` / `TRS_GRAPH_SPACE` / `AUTH_ENABLED` / `PORTAL_*`），详见 `docs/前端一次构建多环境部署方案.md`。同一镜像已在 dev2 栈以双实例验证（门户前缀 `APP_BASE=/bkg_zpt` 与根路径 `APP_BASE=""`）。
2. **入口形态决定 nginx 配置**：本文 Ingress 为剥前缀转发，23-web 已挂载根路径模板（`24-web-nginx-template.yaml`）。若平台入口改为**不剥前缀**的直连子路径（容器收到带 `/bkg_zpt` 的路径），删除 23-web.yaml 的模板挂载、改用镜像内置前缀模板即可。
3. **认证 Cookie 路径**：`AUTH_COOKIE_PATH=/bkg_zpt`（已配置在 02-configmap.yaml），与代理路径保持一致，否则登录态无法写入。
4. **HTTPS**：`AUTH_COOKIE_SECURE=true` 要求外部入口必须是 HTTPS，平台证书按域名 `edu.itic-sci.com` 配置。
5. **SSO 回调**：`USER_CENTER_REDIRECT_URI=https://edu.itic-sci.com/bkg_zpt/api/v1/auth/callback` 需在用户中心完成客户端注册（`USER_CENTER_CLIENT_ID` / `USER_CENTER_CLIENT_SECRET`），回调白名单需同步登记 `/bkg_zpt` 路径。
6. **temporal-ui**（NodePort 30833）与 rustfs console 仅供运维排障，建议不对外网暴露。

### 临时改用 IP 直连登录（排障 / 冒烟）

正式入口永远是 `https://edu.itic-sci.com/bkg_zpt/`。平台入口未就绪或内网冒烟需要用 `http://<node_ip>:30880` 直连并完成登录时，共改 **5 个环境变量 + 用户中心 1 项登记**（登录链路：前端 → api 302 用户中心 → 认证后 302 回回调接口 → 种 session cookie → 跳回前端）：

| 配置（正式值见 02-configmap） | 临时值 | 原因 |
| ----------------------------- | ------ | ---- |
| `APP_BASE`（web Deployment） | `""` | 根路径直访；保留 `/bkg_zpt` 会因资源前缀 404 白屏 |
| `AUTH_COOKIE_PATH` | `/` | 原值 `/bkg_zpt` 不覆盖根路径，浏览器不存 cookie |
| `AUTH_COOKIE_SECURE` | `false` | **http 下浏览器拒存 Secure cookie**，不改则一切白搭 |
| `AUTH_FRONTEND_URL` | `http://<node_ip>:30880` | 登录完成后的跳转目标 |
| `USER_CENTER_REDIRECT_URI` | `http://<node_ip>:30880/api/v1/auth/callback` | OAuth 回调地址 |

- **用户中心侧必须登记**新回调 `http://<node_ip>:30880/api/v1/auth/callback`，未登记会被 redirect_uri mismatch 拒绝（我们侧改配置绕不过）
- 前提：浏览器同时可达 `edu.itic-sci.com`（SSO 页面在那）与 `<node_ip>:30880`；`bkg-secrets` 的 `USER_CENTER_CLIENT_ID/SECRET` 已填真值
- **不用改**：`USER_CENTER_SSO/OAUTH/ACCOUNT_URL`（"去哪登录"与"回到哪"无关）、nginx 模板 CSP（只限制 iframe 嵌入）、`SameSite=lax`（SSO 回调是顶层 302 导航，不受影响）

推荐用 `set env` 直接覆盖（优先级高于 `envFrom`，不污染 ConfigMap，回退一行搞定）：

```bash
kubectl -n bkg set env deploy/web APP_BASE=""
kubectl -n bkg set env deploy/api \
  AUTH_COOKIE_PATH=/ AUTH_COOKIE_SECURE=false \
  AUTH_FRONTEND_URL=http://<node_ip>:30880 \
  USER_CENTER_REDIRECT_URI=http://<node_ip>:30880/api/v1/auth/callback

# 用完回退（恢复走 bkg-config 的正式值）
kubectl -n bkg set env deploy/web APP_BASE-
kubectl -n bkg set env deploy/api AUTH_COOKIE_PATH- AUTH_COOKIE_SECURE- AUTH_FRONTEND_URL- USER_CENTER_REDIRECT_URI-
```

注意：

1. IP 与域名入口**不能在同一 web 实例并存**（`APP_BASE` 一实例一值）；要并存需第二个 root 实例（共用镜像 + `APP_BASE=""`），或在 nginx 模板加 `/bkg_zpt/` 剥前缀 location。
2. `AUTH_COOKIE_SECURE=false` 是安全降级（session id 走明文 http），仅限内网测试期，切回正式入口时连同 5 个值一起还原。
3. 只测功能、不走真实登录时可用 `kubectl -n bkg set env deploy/api AUTH_ENABLED=false`（admin 检查同样放行）——**裸奔模式，测试完必须撤销**。
