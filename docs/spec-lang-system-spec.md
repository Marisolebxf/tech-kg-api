# Tech KG 后端系统规格（Spec Lang 描述）

> **基线**：branch `kgetl` @ `196ba4f`（2026-09-04）
> **核验方式**：10 个并行只读探索代理逐文件通读（~150 个源文件、~120 张表、141 个测试文件）+ 人工直读 `main.py` / `biz/router/register.py` / `service/module_catalog.py`。所有断言带 `file:line` 出处；与 `CLAUDE.md` 冲突处以代码为准（差异见 §2）。
> **成文日期**：2026-09-06

---

## 1. 元模型约定（本文使用的 DSL）

```text
Unit                 // 一切软件单元：system / subsystem / module / adapter，仅 kind 不同
Contract
  provides           // 穿出边界向外提供的能力（capability.operation）
    policy           // 边界策略注解（身份/权限）
    precision        // 实装度注解：ready | scaffold | mock（本系统必需）
  requires           // 需要外部提供的能力；? 后缀 = 可缺省（缺席即降级）
Behavior             // 动态语义：步骤 / 分支 / 状态机 / 循环
contains             // 边界内的子 Unit（结构递归）
Binding              // 独立于 Spec 的技术绑定；binding-guarantee = 绑定层承诺
```

核心原则：Context 与依赖图不由人手写，全部由 `contains` + `provides/requires` 派生（§6）。

---

## 2. 重大修正清单（相对 CLAUDE.md / README）

| # | 修正 |
|---|---|
| 1 | 模块目录是 **12 个**（`service/module_catalog.py` 逐行数过），带 `status` 字段：仅 `expert_cooperation_achievement`、`expert_alumni_relation` 为 `ready`，其余 10 个 `scaffold`。"九大模块"只是预热端点集合；目录(12) ≠ 预热(9) ≠ 实际路由集，三者不对齐 |
| 2 | 边界策略实际有**四种身份**：公开（auth 自解析）、会话、服务身份（`require_graph_service`：Bearer `GRAPH_BUILD_SERVICE_TOKEN` 或 HMAC-SHA256 时间戳签名，未配置 503，`biz/dependencies/review_service_auth.py:12-35`）、网关身份（review 的 HMAC 签名 `X-User-*` 头）；`is_admin` 之外另有 5 个 review 角色码 |
| 3 | `get_techkg_client()` **不固定 techkg 空间**——与默认单例同读 `TRS_GRAPH_SPACE`（`infra/graph_db/__init__.py:85-97` docstring）；真正按空间的是第三层 `get_space_client(space)` 缓存（`:113-125`） |
| 4 | schema 脚本安全**没有 AST 白名单**：`ast.parse` 仅语法检查 + **LLM 评审（fail-closed）**（`service/script_security.py:94-103`），且 LLM 门只在 `/script/verify`（SSE）路径生效，裸 `PUT /script` 不过审（`service/schema_management.py:586-594`）。脚本是 **Python transform 函数**（隔离子进程执行），不是 nGQL 作者 |
| 5 | workflow 控制面是 **MySQL `techkg_control`**（`WORKFLOW_DATABASE_PATH` 在仓库中已不存在，grep 验证）；**进程内 Temporal worker 已删除**（commit `932fc82`，2026-08-25），只剩独立 worker；并发上限动机是防重试风暴，非"保护图会话池" |
| 6 | **算子不参与工作流编排**——工作流组合单元是上传的 Python 函数（declarative / python / steps / chain 四种定义格式）；算子注册表是独立体系，仅经 HTTP 同步调用 |
| 7 | manual review：完整 **outbox 模式** + `REVIEW_RERUN_MODE` 默认 **mock**；review worker **进程内直调** `process_outbox`（每 2s），不调 HTTP（`script/run_manual_review_worker.py:16-37`）；`T_DIRECT` 模板旁路直写 Nebula；"category=A/B/C"是查询期模板映射，不是表列（`service/manual_review_production.py:311-322`） |
| 8 | correction：**默认 `CORRECTION_SYNC_MODE=projection` 根本不写图**（只写 MySQL 隔离投影层，注释"业务数据保持隔离"，`service/correction.py:240-244`）；MySQL 先落、图失败不回滚、无 saga 补偿，终态 FAILED 后库图分歧持续存在直至人工 retry |
| 9 | "404/400/500"大多是**信封业务码**（HTTP 200 + `ApiResponse.code`），但 expert_indirect / expert_paper 两个模块用**真 HTTP 状态码**——两种错误约定并存 |
| 10 | 演示态是一等公民：task_center 硬编码变更数 / 静态源健康表 / `temporal_health` 死分支（`biz/handler/task_center.py:88` `hasattr` 永假）、platform_overview 四个板块永远 demo（`service/platform_overview.py`）、`data_mode:"mock"` 字段、`AUTH_ENABLED=false` 下 operation-logs 返回 mock |
| 11 | 各模块图访问有**两种惯用法**：直连 `TRSGraphClient`（cooperation / alumni / topn / build 系）vs **ASGI 自调用自家 `/graph-search` API**（direct / indirect / paper / panorama / key-enterprise） |
| 12 | colleague 模块会**回写 COLLEAGUE 边**（业务查询模块中唯一写者，`application/expert_colleague_relation.py:182-249`）；build 会把 role/日期重置为 `""`（先标注后重建会清空标注，`service/expert_enterprise_relation.py:149-155`）；paper 模块按图空间切换边方向语义（techkg 与 dev 相反，`service/expert_paper_cooperation_api.py:151-166`） |

---

## 3. L0 — TechKGPlatform

```text
Unit TechKGPlatform
  kind: system
  // FastAPI 单进程（无 ASGI 中间件——middleware/ 为空文件，无 CORS/限流/请求日志）
  // + 可选独立进程：temporal worker、manual-review worker

  Contract:
    provides:
      Http.v1                          // ~120 条路由，统一信封 ApiResponse{code,success,data,msg}
        policy:                        // 边界身份（路由级声明，register.py 三组 + 逐路由补丁）
          public      → auth 端点，身份在 handler 内自解析（register.py:58 无依赖）
          session     → require_authenticated_user（33 个路由，register.py:60-101）
          admin       → session + is_admin（manual-reviews / operators / admin-members，
                        register.py:102-109；另有 3 个写端点逐路由叠加 admin：
                        relation build / annotate / mine）
          service     → require_graph_service：Bearer 或 HMAC 签名（±300s）；
                        token 未配置 → 503（manual_review_internal + operator_internal）
          owner       → schema / 配置资源：admin 或 owner（service 层 assert_mutable /
                        ensure_owner_access，403）
        envelope-exceptions:            // 信封一致性的例外，契约必须写明
          GraphRepoError → HTTP 502，裸 {status,message}，不走信封（main.py:133-135）
          RequestValidationError → HTTP 200 + code=422；唯二例外返回真 422：
                        achievements/query 与 workflow definitions/*/execute（main.py:146-148）
          业务错误码 400/404/500 大多装在 HTTP 200 信封里（各 handler try/except 约定）
      Health.status

    requires:                           // optionality 是本系统 requires 的常态
      GraphStore               // nGQL DDL/DML + 点边 REST CRUD；零重试，超时默认 30s
      GraphQuery               // 图查询能力——由自家 graph-search 提供（双提供者，见 §6 诊断1）
      RelationalStore          // 平台库：治理/配置/审核/修正
      ControlStore             // techkg_control 库（temporal-mysql 上，启动自动建库）
      VendorSource             // gkx_local —— 只读【约定级，无事务强制】
      VendorElement            // gkx_element 业务表 —— 只读【强制：SET TRANSACTION READ ONLY，
                               //   gkx_element.py:49-53，且永远 rollback】
      VectorIndex              // Milvus
      ObjectStorage            // RustFS：schema 脚本 / 算子包 / 审核证据（三个桶）
      SessionStore             // Redis（async）：OAuth state / 会话 / bearer缓存 / 用户审计
      DurableExecution         // Temporal
      IdentityProvider         // 统一用户中心 OAuth2
      TextSynthesis?           // LLM：DB 配置优先 → env 兜底；缺席即降级，全程不抛错
      Embedding?               // 双提供者：GLM embedding-3（infra/llm.py:127-169）与 m3e 服务
      GraphBuildHandoff?       // 审核续跑回调目标；REVIEW_RERUN_MODE=mock 时不绑定

  Behavior boot                          // main.py:41-95 实测顺序
    REGISTRY.initialize_store → start_watcher        // 算子：S3 同步 + 0.25s 轮询热加载
    [CORRECTION_SYNC_WORKER_ENABLED] start dispatchLoop   // 代码默认 false；compose 里 true
    ensureConfigTables                  // 6 张平台配置表；MySQL 不可达 → warn 跳过
    [SCHEMA_AUTO_INIT] seedSchemaCatalog       // 只写 MySQL 47 条系统 schema，不跑图 DDL
    prewarm_stats()                     // 无条件：全库统计预热（count 全扫需几十秒）
    [PREWARM_BUSINESS] prewarm_business(app)   // 默认 false；ASGI 自 POST 9 个端点暖各 worker 缓存

  Behavior shutdown
    cancel dispatcher → stop watcher → close redis → close 三层图客户端 → close 控制面引擎

  contains:
    ApiSurface, AuthSubsystem, KgConstructionSubsystem, SchemaSubsystem,
    WorkflowSubsystem, OperatorSubsystem, ManualReviewSubsystem,
    CorrectionSubsystem, SpaceSubsystem, PlatformFacilities, ConfigCenter,
    SharedAdapters
```

---

## 4. L1 — 子系统（按实装度标注 precision）

### 4.1 ApiSurface

```text
Unit ApiSurface
  // 无中间件层；全局异常处理器 2 个（见 L0 envelope-exceptions）；自托管 Swagger（/docs + /static/swagger）
  contains: RouterRegister(三组+补丁), Envelope, ExceptionHandlers, Prewarm,
            ResultCache(infra/result_cache.py)
  // ResultCache：进程内 dict 存预序列化 JSON 串（key → (monotonic到期, str)），
  // TTL 默认 60s（压测配 600s），刻意无锁（GIL 下 dict 原子，docstring 明示禁止加锁）
```

### 4.2 AuthSubsystem（precision: full）

```text
Unit AuthSubsystem
  Contract:
    provides:
      AuthN.resolve                     // 严格顺序：AUTH_ENABLED=false 短路 → Bearer（优先于cookie）
                                        // → 会话 cookie → 门户 cookie 交换 → 401
      AuthZ.isAdmin                      // bootstrap_admin OR DB 角色行 kg_platform_user_role；
                                        //   DB 故障静默降级为仅 bootstrap_admin
      Session.create/refresh/revoke      // 滑动 TTL 1800s（每次 get_session 重写全量 TTL，
                                        //   剩余<30s 自动续）；Redis 记录含明文 access/refresh token
      Audit.userTrail                    // Redis，200 条封顶 / 90 天 / best-effort 永不抛
      Audit.adminTrail                   // MySQL kg_admin_audit_log，永久表
    requires: SessionStore, IdentityProvider, RelationalStore
  Behavior resolveCaller
    bearer   → sha256(token) 查 Redis 缓存(TTL 60s) → miss 时 user-center /check-token 远程校验
               ⚠ 缓存命中跳过过期复查：token 撤销后 ≤60s 仍可用（service/auth.py:167-169）
    session  → OAuth 完整 code flow：state 双重校验（Redis GETDEL + cookie compare_digest）
    portal   → [USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED，默认 false] 门户 access_token 换本地会话
    AUTH_ENABLED=false → dev 上下文（local_admin，权限 "*"）
  Behavior bootstrapAdmin                // 三机制并存：env 白名单常驻 / 无 admin 时首个登录者
                                          // (FOR UPDATE 抢锁) / dev 环境首用户强制 admin
  contains: BearerResolver, SessionManager, PortalSso, AdminGuard, AuditSink×2
  // ⚠ 声明未接线：require_permission() 与 6 个细粒度权限码（schema:manage 等）定义了，
  //   无任何 handler 使用（biz/dependencies/auth.py:102-115）——全系统只强制 is_admin
```

### 4.3 KgConstructionSubsystem（precision 参差）

```text
Unit KgConstructionSubsystem
  // 目录 12 模块（2 ready / 10 scaffold）+ 2 个不在目录的 kg-service 业务模块；三者与预热集不对齐
  Contract:
    provides:                           // 每模块统一形状 describe(+query/build/analyze)
      ExpertDirect.query                // graph 自调用 + 信号量5并发；强度=60+5×论文+4×标签(封顶99)；
                                        //   失败降级空结果带 fallback_reason（不抛错）
      ExpertIndirect.analyze            // DFS 简单路径(≥2跳) + 几何均值×0.92^(len-1) 衰减；
                                        //   ⚠ 用真 HTTP 404/500（错误通道双轨制）
      Cooperation.query        [ready]  // 双点成果：AUTHORED_BY 等交集 + 规则分类（长期稳定型…）
      Colleague.query                   // 同事推理：置信度加权和(0.42同机构+… 封顶0.98)；
                                        //   ⚠ 回写 COLLEAGUE 边（查询模块中唯一写者）
      Alumni.query             [ready]  // STUDIED_AT 邻域 + NFKC 归一化匹配 + LOOKUP nGQL 兜底
      PaperCooperation.analyze          // 论文合作画像；⚠ 按图空间切换边方向（techkg: Scholar-AUTHORED->Paper，
                                        //   dev: Paper-AUTHORED_BY->Person）
      EnterpriseRelation.build          // → §5.1
      RelationAnnotation.annotate       // get_edge+update_edge；update 失败未捕获 → 500
      BackgroundAnalysis.analyze        // 三维度聚合 + LLM→模板降级链（逐行核验见 §5.1 同级报告）
      EnterpriseMining.mine   [admin]   // 传记文本 LLM 抽取→rapidfuzz 消歧(cutoff 85)→
                                        //   编排 build→annotate→analyze（逐步 try/except 不中断）；
                                        //   LLM 缺席 → 正则兜底 + degraded=true
      ChainTopEvent.describe   [scaffold] // 空壳；真实 TOP-N 业务在 kg-service/industry-node-top-events
      ChainTopEventBusiness.run         // 影响力=事件权重×金额log×新近度×链评分；规则推导文案，无 LLM
      Panorama.query                    // 4 层并发构建 + 600s 缓存 stale-while-revalidate
      KeyEnterprise.run                 // 治理/项目/专利三路 2 跳关系 + 风险探针（仅 relations[0]）
      Options.aggregate                 // 每数据源独立 try/except → []，整体永不失败
    requires: GraphStore | GraphQuery（两种惯用法并存）, VendorSource, VendorElement,
              TextSynthesis?, ResultCache
  Behavior graphAccess
    idiom-A: 直连 TRSGraphClient（cooperation/alumni/topn/build 系）
    idiom-B: ASGI 自调用 /api/v1/graph-search（direct/indirect/paper/panorama/key-enterprise）
  // 缓存惯用法 ≥6 种：handler 预序列化缓存、service 60s dict、colleague 三层缓存、
  //   panorama 600s SWR、graph-search /stats 300s SWR+ThreadPool(4)、tech_enterprise 带锁类型化缓存
  contains: ModuleCatalog(12,带status), ModuleScaffold, EnterpriseRelationCatalog(码表),
            12 个模块 Unit（各含 handler→application→service→dao 四层）+ 2 个 kg-service 模块
```

### 4.4 SchemaSubsystem

```text
Unit SchemaSubsystem
  Contract:
    provides:
      Schema.crud                       // 实体/关系 schema + 属性 + 来源绑定（一 schema 多 source，
                                        //   唯一键 (schema_id,datasource_id,database,table)）
      Script.upload                     // S3 put → 注册 workflow → DB → commit；失败回滚并删已传对象；
                                        //   旧对象成功后清理（失败仅标记 previousScriptCleanupSucceeded）
      Script.verify                     // SSE：语法(ast.parse/大小/入口函数) → LLM 安全评审(fail-closed) → 保存
      Script.upload.plain               // ⚠ 裸 PUT /script 不过 LLM 评审
      ExtractTask.manage                // job 类型 extract（schemaId + batchSize 1..5000 + cron）
      permission: 系统 schema → admin 或 SCHEMA_ADMIN_USER_IDS(默认 schema-admin)；
                  用户 schema → owner 或 admin
    requires: ObjectStorage, ControlStore, DurableExecution, RelationalStore,
              ManualReview(失败case), EntitySearch(索引重建)
  Behavior extract                      // → §5.2（14 步全核验）
  contains: SchemaCatalog(seed 16实体+35关系), ScriptStore, ScriptSecurity, SourceBinding,
            Watermark(kg_script_watermark), SchemaExtractionService
```

### 4.5 WorkflowSubsystem

```text
Unit WorkflowSubsystem                  // precision: 结构完整；⚠ 无 stop/cancel 端点
  Contract:
    provides:
      Definition.manage                 // 4 种格式：declarative(步骤仅记账 no-op！) /
                                        //   python(隔离子进程, AST检查, ≤1MiB, 默认超时60s) /
                                        //   steps(StepManifest 各自带 retryPolicy，默认1次) /
                                        //   chain(引用其他 python 定义)
      Execution.run/status              // Temporal down → dispatchMode=LOCAL_FALLBACK，QUEUED，
                                        //   ⚠ 永不自愈（workflow_operations.py:274-286）
      Schedule.manage / Job.manage      // cron 落 Temporal Schedules(默认时区 Asia/Shanghai)；
                                        //   创建失败本地 LOCAL_SAVED；暂停让运行中执行跑完
      TaskCenter.view                   // ⚠ 部分 demo：变更数硬编码 / 源健康静态 /
                                        //   temporal_health 死分支；真实部分：详情透查 Temporal
                                        //   活动步骤、retry=ResetWorkflowExecution 回放
    requires: DurableExecution, ControlStore, OperatorRegistry.invoke
  quality: TEMPORAL_MAX_CONCURRENT_ACTIVITIES=4；SCHEMA_EXTRACT_MAX_INFLIGHT=3(cap 8)；
           ACTIVITY_RETRY_POLICY 硬编码：初始2s/倍增2.0/封顶30s/最多5次
           // 动机 = 防重试风暴（commit 932fc82 "prevent project retry storm (#124)"）
  contains: ControlPlane(MySQL techkg_control, 9 表：batches/tasks/reviews/source_updates/
            settings/workflow_definitions/workflow_executions/workflow_schedules/workflow_jobs，
            启动 create_all + 手工幂等 ALTER；demo 数据由 WORKFLOW_DEMO_DATA_ENABLED 门控),
            TemporalClient(进程内 client 单例), 15 workflow + 15 activity 定义
  // ⚠ 算子不在工作流 spec 里——两体系仅通过 invoke 交汇
  // ⚠ worker 仅独立进程（script/run_temporal_worker.py）；进程内 worker 已删除
```

### 4.6 OperatorSubsystem

```text
Unit OperatorSubsystem
  Contract:
    provides:
      Registry.invoke                   // list[dict]→operator(data,ctx)→list[dict]；深拷贝入参，
                                        // 出参校验 list[dict] 且可 JSON 序列化；asyncio.to_thread 执行
      Registry.reload                   // 0.25s 轮询 + (mtime,size,sha256) 快照比对；
                                        //   单算子加载失败保留旧版；删除文件即清理
      Operator.crud            [admin]  // S3 先写 → 本地原子写(.tmp+os.replace) → reload
                                        //   → 广播 /internal/operators/reload 到
                                        //   OPERATOR_WORKER_BASE_URIS 各 worker（带 X-Operator-Reload-Token）
    requires: ObjectStorage?            // OPERATOR_S3_BUCKET 空 → 纯本地模式（store=None）
  contains: Builtins(5: data_normalize / entity_extract / relation_extract /
            entity_load·仅生成plan / relation_load·仅生成plan),
            UserOperators(operators/user/), Watcher,
            ScholarOperators(5 个，经 script/register_scholar_operators.py HTTP 注册)
```

### 4.7 ManualReviewSubsystem

```text
Unit ManualReviewSubsystem
  Contract:
    provides:
      Case.manage             [admin+网关身份]  // HMAC 签名 X-User-* 头解析 reviewer 身份
                                                // （REVIEW_IDENTITY_REQUIRE_SIGNATURE 默认 true）
      Queue.claim/heartbeat/release       // 乐观并发（version 条件 UPDATE，失败 409）；
                                          //   心跳超时 5min → reclaim 回收为 OPEN
      Draft/Submit/Approve               // 四眼原则：P0 / 高危动作 / 高价值实体 需 submitter≠approver
      DirectDecide                        // T_DIRECT 旁路：一步直审 → 直写 Nebula
                                          //   (INSERT VERTEX + DESCRIBE 对齐 + 溢出字段进 extra_json)
      RerunExtractFailures               // 角色门(reviewer/data_quality/graph_governance/approver/
                                          //   review_admin) → 按 schema 分组 → mark→trigger→失败回退
      Evidence.upload                    // 预签名 S3 上传（20MB 上限，pdf/png/jpeg/plain）
      InternalApi            [service身份] // review-required / correction / execution-events；
                                          //   Idempotency-Key==eventId 强制
    accepts: ExtractFailureCase(T_EXTRACT_FAIL)   // 查询期映射 category=C（非列）：
        // A=(T_DIRECT,T_LINK,T_EVIDENCE) B=(T_MAP,T_DQ_FILL,T_DQ_MERGE,T_ATTR) C=(T_EXTRACT_FAIL)
    emits: ResumeRequest(via outbox)
  Behavior dispatchOutbox                // 条件UPDATE抢锁 → 60s 陈锁回收 → 指数退避(封顶5min)
                                          // → 5 次 DEAD；REVIEW_RERUN_MODE 默认 mock！
                                          // 真实模式 POST {GRAPH_BUILD_INTERNAL_URL}/internal/review-resumes
                                          // + Idempotency-Key=correctionId，超时 10s
  Behavior executionCallback            // 事件阶段单调递增 + 每事件允许状态映射：
                                          // RERUN_SUCCEEDED→VERIFYING→(VERIFICATION_SUCCEEDED)→RESOLVED
  // case 生命周期：OPEN→CLAIMED→IN_REVIEW→(PENDING_APPROVAL)→APPLYING→RERUNNING→VERIFYING→RESOLVED
  //   ± APPLY_FAILED / RERUN_FAILED；终态 REJECTED/CANCELLED/EXPIRED
  // SLA：P0 认领15m/解决30m，P1 1h/4h，P2 4h/1d；9 个模板；dedupe_key=sha(taskId,step,objectId,fingerprint)
  contains: CaseStore(9 张表), TemplateSet, Outbox, EvidenceStore, ReclaimReaper
  // review worker 进程内直调 process_outbox+reclaim（每 2s）；HTTP 版端点仅 admin 手动触发
```

### 4.8 CorrectionSubsystem

```text
Unit CorrectionSubsystem
  Contract:
    provides:
      Correction.submit/edit/cancel      // 台账 kg_manual_correction（before/after JSON 快照）
      Correction.review        [admin]   // 状态机：PENDING_REVIEW → REJECTED|CANCELLED|PENDING_SYNC
                                          //   → COMPLETED | SYNC_FAILED(→ admin retry → PENDING_SYNC)
    requires: RelationalStore, GraphStore?
  Behavior sync                          // SELECT ... FOR UPDATE SKIP LOCKED 批20（多worker安全）
                                         // → MySQL 投影先落（幂等守卫：projection.last_correction_id
                                         //   == correction.id 则跳过）→ 图写
                                         //   [projection 模式默认：图不动，"业务数据保持隔离"]
                                         //   [dual 模式：仅 EMPLOYED_BY，写 manual_disabled+correction_id]
                                         // 失败：退避 30·2^(n-1) 封顶 1h，默认 8 次 → FAILED
    ⚠ 无补偿：MySQL 已落不回滚；终态 FAILED 后库图分歧持续存在直至人工 retry（attempts 归零）
  contains: Ledger, StateMachine, SyncDispatcher(main.py 后台循环，间隔≥5s默认30s),
            ProjectionStore(kg_correction_projection 隔离投影层), ReviewHistory, AdminAudit
  // ⚠ 命名陷阱：review 侧 ReviewCorrection（续跑）与本子系统 ManualCorrection（台账）零共享表
```

### 4.9 SpaceSubsystem

```text
Unit SpaceSubsystem
  Contract:
    provides:
      Space.create/bind/unbind/list
        ensures: 空间本体在 Nebula（CREATE SPACE，vid FIXED_STRING(64)、partition 默认100、
                 replica 默认3；创建后轮询 SHOW SPACES 20×0.5s 等传播，service/graph_space.py:124-162）；
                 UserGraphSpace(kg_user_graph_space) 仅是每用户绑定行，多人可绑同一空间；
                 unbind 只删绑定行不删数据；名称正则 ^[A-Za-z_][A-Za-z0-9_]{0,63}$
    access: 默认空间与管理员无限制；其他用户需绑定行否则 403
            （graph_search / entity_search / graph_console 共用此规则）
  contains: SpaceRegistry, BindingTable, PerSpaceClientCache(get_space_client)
```

### 4.10 PlatformFacilities

```text
Unit PlatformFacilities
  provides:
    GraphSearch.query          // 11 端点；/stats 300s SWR + ThreadPool(4)；
                                //   paths/search 白名单 Pydantic 模型→编译成只读 MATCH nGQL；
                                //   同步客户端全部 asyncio.to_thread 包装；错误走信封 code=500
    GraphConsole.runNgql       // 关键词分类器（非解析器）：READ 首词白名单放行；
                                //   WRITE(INSERT/DELETE/UPDATE/UPSERT) 仅 admin；
                                //   DDL/管理类对所有人含 admin 一律 403；多语句/管道/USE/纯注释拒
    EntitySearch.search/reindex// 单集合 kg_entity 按 graph_space 标量分区（老 schema 自动重建）；
                                //   RRF(k=60) 混合检索，embedding/BM25 缺席降级单路；
                                //   reindex 全进程锁（并发 409）+ BM25 全语料拟合 + 状态存
                                //   kg_entity_search_state（每空间一行 LONGTEXT JSON）
    PlatformOverview.view      // 三级降级：SHOW STATS(毫秒) → 逐label count(~57s) → mock+横幅
                                //   "图数据库暂不可用"；⚠ 属性总量/变更/动态/风险四板块永远 demo；
                                //   60s 进程内缓存
    TaskCenter.*               // 见 4.5 TaskCenter.view
    CommonCapability.*         // 实体抽取/对齐/消歧/关系抽取（规则 + llm/hybrid 模式）
  requires: GraphStore, VectorIndex, Embedding?, SessionStore
```

### 4.11 ConfigCenter

```text
Unit ConfigCenter                        // 4 个路由同一模板
  provides: LlmConfig / MilvusConfig / EmbeddingConfig / MysqlDatasource 的
            CRUD + set-default + test/verify（真探活）
  invariant: owner 作用域（admin 见全部、用户只见自己，越权 403）；密钥只回显末 4 位；
             空密钥更新保旧值；每 owner 默认唯一（clear_other_defaults）；
             llm 配置变更重置进程 LLM 单例；DB 配置优先于 env；
             ⚠ llm 路由实际路径 /api/v1/llm-config/llm-configs（前缀与路径各贡献一段）
```

### 4.12 SharedAdapters

```text
Unit SharedAdapters
  contains:
    TRSGraphClient          // 节点/边 CRUD + 遍历 + execute_query/read/write（自动前置 USE <space>，
                            //   空间名正则校验，响应 spaceName 不符 → 409）+ 索引/约束 + 统计；
                            //   零重试；错误映射：传输→GraphConnectionError / 404→GraphNotFoundError /
                            //   其他→GraphRequestError；_ensure_vid 保证 vid/id/name 之一（写入路径
                            //   兜底 uuid4）；find_nodes 原样返回真实 vid（读路径无 UUID 替换）
    GraphClientTiers        // 三层：get_trs_graph_client(env空间) / get_techkg_client(⚠ 同读 env，
                            //   实际同空间两份缓存) / get_space_client(space) 每空间缓存字典
    MySQLEngine             // pool 10/20，pre_ping，recycle 3600
    ControlEngine           // techkg_control：首次访问自动 CREATE DATABASE IF NOT EXISTS
    RedisAsyncStore         // 精确 =="memory" 才用内存实现，其余（含空串）一律 Redis
    ResultCache             // 见 4.1
    LlmClient               // 进程单例；DB→env 解析；synthesize 捕获一切异常返回 None；
                            //   synthesize_json 三级降级 json_schema→json_object→prompt_only
    MilvusClient            // 连接失败 2s 冷却（冷却期直接重抛旧错）；host "milvus" 不可解析时
                            //   重写为 127.0.0.1:19531；hybrid_search dense 0.45 / sparse 0.55
    S3Stores ×3             // schema 脚本桶 / 算子桶(可缺席) / review 证据桶
    UserCenterClient        // 每次调用新建 httpx.AsyncClient，超时 15s，非单例
```

---

## 5. L2 — 深打开

### 5.1 ExpertEnterpriseRelation（逐行核验）

```text
Unit ExpertEnterpriseRelation
  kind: kg-module, status: scaffold
  Contract:
    provides:
      EnterpriseRelation.build(scholarId, enterpriseId, relationTypes)   [admin]
        errors: ScholarNotFound / EnterpriseNotFound
          ⚠ 是信封 code=404，HTTP 状态 200（biz/handler/expert_enterprise_relation.py:27-28）
        ensures:
          图中每对恰一条 EMPLOYED_BY@0 —— ⚠ 依赖服务端语义：客户端 create_edge 不发 ranking
          （infra/graph_db/client.py:275-289），写后主动删除 rank≠0 旧边
          （service/expert_enterprise_relation.py:160-165）；merge_edge API 存在但未使用
          relation_type = 既有codes ∪ 请求codes 保序并集后 '/' 连接（增量合并，非覆盖）
          响应 = 该学者全部企业关系：按 org_id 去重、首边胜出、codes 跨边并集、上限 100 边、
                 跳过 manual_disabled 的边与企业
        mapping: 英文码→中文标签仅发生在响应边界
                 （catalog:43  relation_label 用 .get(c,c)，容忍历史中文值——读宽容/写严格）
      invariant:
        图内不写中文关系标签（写严格）
        ⚠ build 会把 role/start_date/end_date 重置为 ""——先标注后重建会清空标注
    requires: GraphStore, VendorSource(gkx), EnterpriseRelationCatalog(兄弟单元)
  Behavior build
    resolve scholar ── miss → gkx DwdScholar 查源并 create_node 拉起（跨边界 fallback）
                    ── 源库也无 → KeyError
    resolve enterprise ── 同上（DwdOrgRegInfo → DwdOrgStockBase 兜底）
    upsertEdge(EMPLOYED_BY, relation_type=join(union,'/'), source="build", role="")
    cleanup rank≠0 → respond(映射中文标签)
  contains: Handler, Application(纯透传), Service, Schemas
  // 码表：RELATION_TYPES 5 项；ROLE_CATALOG 5 项分 L1/L2/L3；
  //   ⚠ InvalidRoleTypeError 定义了但从不 raise（roleType 校验实际空转）
  //   DDD 五层里 Application 对此模块是纯转发——模板并非处处有意义
```

### 5.2 SchemaExtractWorkflow（`kg.schema.extract`，14 步全核验）

```text
Behavior extract                       // service/temporal_workflows.py
  1  load_plan             // 控制面读定义+sources → S3 下载脚本到私有临时文件
  2  [cron] register_scheduled_execution   // 幂等(runId)；盖 triggerSource=SCHEDULE
  3  并发模型               // 每 source：1 读协程串行推进游标 + N worker 经
                           //   asyncio.Queue(maxsize=N) 背压；inflight=3(cap 8)
  4  分批读取               // 四种游标：ids(rerun, IN≤500) / offset(普通表 LIMIT/OFFSET) /
                           //   watermark(querySql: time>水位 ORDER BY time,pk) / keyset(pk>游标)
                           //   自适应减半直到 JSON≤512KB（避 gRPC 4MB）
  5  transform             // 隔离子进程调脚本 transform({rows,source_table,kind,source})
                           //   仅输出 {entities|edges, failures?, pendingReview?}；
                           //   pendingReview → T_DIRECT/T_LINK 审核 case
  6  write                 // 实体+关系全部 nGQL INSERT VERTEX/EDGE（REST merge 剥离 id/name，
                           //   撞 NOT NULL 必 400，WF:1000-1004）；DESCRIBE 驱动类型矫正；
                           //   未知列自愈：捕获 400 → 删该列 → 重试
  7  detectCollisions      // 同名不同 vid（含批内）→ T_LINK case（KG_EXTRACT_NAME_COLLISION）
  8  record_failures       // 逐行失败 → T_EXTRACT_FAIL case，cap 2000
  9  advance_cursor        // ⚠ 一次性：该 source 全部批次成功后才写水位（失败停在上一轮，
                           //   INSERT 幂等保证续跑安全）；keyset 写 checkpoint.pkCursor
  10 buildIndex            // 仅实体且非 rerun；失败 → {degraded:true}，抽取仍 COMPLETED
  11 [rerun] resolve       // 成功 case→RESOLVED；仍失败 → 新 case attempt+1
  12 stamp_script_health   // last_run_status ok/failed 落 kg_schema_script
  13 result                // {status, triggerSource∈{MANUAL,SCHEDULE,RERUN}, sources, failures, index}
  // e2e 已验证（dev2_extract_e2e.py）：batchSize=2 → 2批/4行 → 2 个 C 类 case →
  //   rerun 合并 1 执行 → 自动 RESOLVED → 二次触发 0 行（水位已推进）→ dev2 空间 4 节点
```

---

## 6. Binding

```text
Binding dev2
  GraphStore        → trs-graph REST（X-API-Key + X-Graph-Space=dev2）
  GraphStore:techkg → 第二单例，同读 TRS_GRAPH_SPACE（⚠ 实际与上同一空间，仅两份缓存）
  GraphStore:*      → get_space_client(space) 每空间缓存
  RelationalStore   → MySQL gkx_element（平台表）
  ControlStore      → MySQL techkg_control @ temporal-mysql-dev2（启动自动建库）
  VendorSource      → MySQL gkx_local        binding-guarantee: 只读·约定级
  VendorElement     → MySQL gkx_element 业务表 binding-guarantee: 只读·强制(SET TRANSACTION READ ONLY)
  VectorIndex       → Milvus 19531（连接失败 2s 冷却）
  ObjectStorage     → RustFS：tech-kg-schema-scripts / bkg-operators / review-evidence 三桶
  SessionStore      → Redis（async；AUTH_SESSION_BACKEND 精确 =="memory" 才用内存）
  DurableExecution  → Temporal temporal-dev2（namespace=default，queue=tech-kg-workflows）
  IdentityProvider  → 统一用户中心（门户 cookie 交换）
  TextSynthesis     → platform_llm_config 优先 → env(LLM_API_KEY/ZHIPUAI_API_KEY) → 缺席=降级
  Embedding         → GLM embedding-3 或 m3e-embedding:8010/v1（按用途）
  GraphBuildHandoff → REVIEW_RERUN_MODE=mock（默认！）→ 不绑定真实服务

Binding tests / CI
  AuthN.mode        → AUTH_ENABLED=false（人人 local_admin，权限 "*"）
  SessionStore      → memory
  GraphEndpoint     → httpx.MockTransport（graph / user_center / graph-build 替身全可注入；
                      tests/conftest.py 唯一 fixture async_client，141 个测试文件）
  Correction.worker → disabled；PREWARM → off；demo 数据 → WORKFLOW_DEMO_DATA_ENABLED
```

---

## 7. 派生视图与诊断（Compiler 可跑的检查表）

**派生 Context(TechKGPlatform)**：前端 SPA、门户 iframe、trs-graph、MySQL×3（gkx_element / gkx_local / techkg_control）、Milvus、RustFS、Redis、Temporal、m3e、GLM/用户中心、graph-build 服务（mock 时缺席）、temporal worker、review worker。

**依赖解析发现的结构性问题**（每条对应具体代码）：

1. **同能力双提供者**：`GraphQuery` 既有直连路径又有 graph-search 自调用路径 → 5 个模块绕过自家 HTTP 边界访问图（层级倒置）。
2. **声明未接线清单**：`require_permission` + 6 权限码、`InvalidRoleTypeError`、三个 stub DAO（industry_chain / paper / relation）、`response_model` 纯装饰、`temporal_health` 死分支、CLAUDE.md 的 SQLite 控制面与进程内 worker（均已不存在）。
3. **命名碰撞**：ReviewCorrection vs ManualCorrection 两套无关机制；`category` 列存模板标题而 A/B/C 是查询映射；目录 12 ≠ 预热 9 ≠ 路由集。
4. **错误通道双轨**：信封业务码 vs 真 HTTP 状态（indirect / paper）——消费方无法统一处理。
5. **缓存惯用法 ≥6 种**（锁/无锁、预序列化/对象、TTL 60/300/600、SWR 与否）——同一能力无统一契约。
6. **mock/演示面清单**：rerun mock 默认、task_center 3 处、overview 4 板块、auth operation-logs——需要 precision 标注才不会被误当真实能力。
7. **写副作用隐藏在读路径**：colleague 查询回写边、build 清空标注——纯 `provides X.query` 不足以暴露，Behavior 必须写。

---

## 8. 给 Spec Lang 的反馈（本轮新发现）

1. **precision 必须是机器可读的一级元数据**。"不同层次不同精度"被代码验证得更彻底：精度不是层级属性，是**逐能力的属性**（同一模块里 ready 的 query 和 mock 的 overview 板块共存；`data_mode:"mock"`、`degraded:true`、catalog `status` 都是手写的精度标记）。建议 `provides` 支持 `precision: ready|scaffold|mock`，且由 Binding 区分"绑定了 mock"与"代码本身就是演示"。
2. **边界策略是可派生视图，不是原语**。四种身份 + 逐路由补丁 + owner 作用域全部用 `policy:` 注解 + 编译器归并即可表达，未逼出新概念——验证了元模型的核心压缩。
3. **Binding 级 mock 优雅，代码级演示不优雅**。`REVIEW_RERUN_MODE=mock` 是完美的 Binding 缺席实例；但 task_center 的硬编码数字住在代码里，Binding 表达不了——这是语言的真实边界：规格与实现的差距要么进 precision 元数据，要么永远是诊断噪音。
4. **错误需要通道限定符**。`errors: X → 404` 不够——必须区分 `envelope:404` 与 `http:404`，本系统两种并存且消费方行为不同。
5. **"读操作带写副作用"要求 Behavior 是契约的一部分而非注释**（colleague 回写、build 清标注）。
6. **同能力多提供者 + 惯用法分歧**是最有价值的诊断类别：一眼暴露架构演化痕迹（新模块走自调用网关、老模块直连客户端）。

---

## 附录：核验覆盖

| 区域 | 覆盖 |
|---|---|
| 路由/信封/中间件/生命周期 | register.py 全文、~35 个 handler 的全部路由装饰器、main.py 全文、prewarm_business |
| 认证 | dependencies/auth.py、config/auth.py、service/auth.py、infra/user_center.py、admin_member、审计双轨 |
| 12+2 业务模块 | 每个 handler+service（部分含 application/schemas/dao），含参考子系统逐行 |
| 基础设施 | graph_db 全部文件、mysql/gkx/gkx_element/redis/workflow_mysql/result_cache/llm/milvus/s3/operator_store |
| Schema+抽取 | schema_management handler+service、script_security、temporal_workflows 抽取链、register_platform_extraction、水位表、entity_search、dev2_extract_e2e.py |
| Workflow+算子 | workflow_system handler、workflow_repository/models、temporal_runtime、operator_registry/builtins/store、run_temporal_worker |
| 审核+修正 | manual_review 两 router、manual_review_production/domain、db_model/manual_review 9 表、correction 全链、platform_governance 8 表 |
| 设施+配置 | task_center / platform_overview / entity_search / graph_console / graph_search / graph_space / common_capability / 4 配置路由 |
| 横切 | application 26 文件、dao 全量、db_model 22 文件 ~120 表、tests 141 文件、pyproject、script/ 与 organization_ETL/ 全量清单、schemas/ DDL |
