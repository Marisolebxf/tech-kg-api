# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Monorepo: `backend/` (Python FastAPI) + `frontend/` (Vue 3 + TS + Vite). A top-level `docker-compose.yml` builds and runs both, plus the supporting infra services (Milvus+etcd+MinIO, RustFS, schema MinIO, m3e-embedding, auth-redis, Temporal).

The root `README.md` and `backend/README.md` are **current** — they document connection info, env vars, and the Docker setup. Treat them as authoritative for environment/connection questions.

**Gitignored / local-only — do not add to git:** `backend/app/`, root `app/`, `docs/superpowers/`, and `backend/operators/user/` (runtime cache of uploaded user operators; `backend/operators/scholar/` IS committed source). The `backend/config/*.yml` files are legacy and **not loaded** by the live app — config comes from env vars / `.env` via `python-dotenv`.

## Backend commands

All commands run from `backend/`:

```bash
uv sync --dev                      # install deps (use --frozen in CI/Docker)
uv run uvicorn main:app --reload   # dev server (entrypoint is backend/main.py, not app.main)
uv run ruff format .               # format
uv run ruff check .                # lint (auto-fix: --fix)
uv run pytest                      # all tests
PYTHONPATH=. uv run pytest tests -m "not external" -v   # what CI runs
uv run pytest tests/unit/test_trs_graph_client.py::TestExceptions::test_hierarchy  # single test
uv run pytest --extra milvus       # tests needing the milvus extra (pymilvus[model], jieba, milvus-model)
```

Python is pinned to `>=3.11.13,<3.12` (the Docker image uses `python:3.11-slim`).

### Lint/test conventions

- **ruff**: `line-length = 100`, lint selects `E F I UP B`, ignores `E501` (line length not enforced). CI runs `ruff format --check .` then `ruff check .`.
- **pytest**: `asyncio_mode = "auto"` (async tests need no decorator), `testpaths = ["tests"]`.
- **`external` marker**: tests requiring real MySQL/Redis/TRSGraph/Kafka/Milvus. CI runs `-m "not external"`; mark live-service tests with `@pytest.mark.external`.
- Unit tests for the graph client use `httpx.MockTransport` to fake the trs-graph REST API — no live service needed.
- Integration tests use the `async_client` fixture in `tests/conftest.py` (ASGI transport against `main.app`).
- `pymilvus` is a heavyweight default dep; the `milvus` project extra (`uv sync --extra milvus`) adds `milvus-model` + `jieba` needed only by `script/paper_milvus/` and paper/journal ETL.

### Tests run in containers (mandatory)

The backend and all infra (MySQL, MinIO, Temporal, Milvus, redis, trs-graph) run **only in Docker** — the host has none of them. **Never run backend-dependent tests on the host** (they fail with e.g. `Can't connect to MySQL server on 'temporal-mysql'`, DNS unresolvable; see `docs/FIVE_PAGE_DESIGN_REMEDIATION.md`). Verified in-container commands:

```bash
# Backend tests — inside the running api container (924 passed, ~28s):
docker exec -w /app tech-kg-api-dev2 .venv/bin/python -m pytest tests -m "not external" -q

# Frontend unit tests — inside the web image's builder stage (74 passed):
docker build --target builder --build-arg NPM_REGISTRY=https://registry.npmmirror.com \
  --build-arg VITE_BASE=/ --build-arg VITE_API_BASE=/api -t tech-kg-dev2-frontend-test ./frontend
docker run --rm tech-kg-dev2-frontend-test pnpm vitest run --exclude "src/__tests__/review-full-integration.spec.ts"
```

- The dev2 stack is `docker-compose.dev2.yml`: `tech-kg-api-dev2` (host port 8002) + `tech-kg-web-dev2` (host port 8089) + `temporal-mysql-dev2`/`temporal-dev2`. Inside the api container only `temporal-mysql-dev2` resolves, not the production `temporal-mysql`.
- `frontend/src/__tests__/review-full-integration.spec.ts` is **environment-gated**: it spawns its own uvicorn backend (needs `uv` + backend venv) plus a MinIO at `127.0.0.1:9000` (minioadmin) and workflow MySQL — no existing container provides all of these. Its failure anywhere is an environment issue, not a regression; exclude it from test runs.
- Frontend typecheck + build also happen inside Docker via `docker compose -f docker-compose.dev2.yml build web-dev2` (builder stage runs `vue-tsc -b && vite build`).

## Backend architecture (DDD layered)

Request flow: `main.py` → `biz/router/register.py` → `biz/handler/*` → `application/*` → `service/*` → `dao/*` + `db_model/*` + `infra/*`. Pydantic request/response models for a module live in `biz/schemas/<module>.py`.

- **`biz/handler/`** — FastAPI `APIRouter`s (the only place routes are defined). Routers are mounted by `biz/router/register.py` under `/api/v1`. Routers split into three groups: **protected** (depend on `require_authenticated_user`), **admin** (additionally `require_platform_admin`), and **internal** (no auth — `manual_review_internal`, `operator` internal). Handlers are thin: parse request, call an `application` object, return response.
- **`biz/dependencies/auth.py`** — auth dependency wiring (see Auth below).
- **`biz/schemas/`** — Pydantic v2 request/response models, one file per module. `common.py` holds the `ApiResponse` envelope.
- **`biz/prewarm_business.py`** — lifespan-triggered background prewarm of the nine business-module result caches (gated by `PREWARM_BUSINESS=true`); avoids cold-start stampede on trs-graph under load.
- **`application/`** — thin orchestration classes; one per domain module, wraps a `service`.
- **`service/`** — business logic. Each KG-construction module subclasses `service/base_module.KGModuleScaffoldService` (sets `module_code`, inherits `describe()` from `service/module_catalog.py`). The catalog in `module_catalog.py` is the registry of the nine KG-construction module codes/names/descriptions.
- **`dao/`** — MySQL query objects (e.g. `ScholarDAO`), each takes a SQLAlchemy `Session`. `dao/sql/` holds raw SQL fragments.
- **`db_model/`** — SQLAlchemy ORM models (all share `db_model/base.Base`). One model file per table family (`scholar.py`, `organization.py`, `paper.py`, `patent.py`, `platform_governance.py`, `manual_review.py`, `schema_management.py`, `llm_config.py`, ...).
- **`infra/`** — infrastructure singletons, all reading config from env vars / `.env` via `python-dotenv`:
  - `mysql.py` (sync SQLAlchemy engine + `get_mysql_client()` / `session_scope()`), `redis.py`, `llm.py`.
  - `gkx.py` / `gkx_element.py` — **read-only** MySQL session factories for the vendor source lib `gkx_local` and the element lib `gkx_element`. Sessions are explicitly switched to read-only transactions; never write through these.
  - `graph_db/` — the trs-graph client (see below).
  - `graph_api_client.py` — lower-level HTTP client used by some ETL scripts.
  - `milvus.py` — `MilvusClient` singleton + `OrganizationMilvusStore` (lazy-imports pymilvus; config from `MILVUS_URI` / `MILVUS_HOST`+`MILVUS_PORT`).
  - `s3.py` — generic boto3 S3 wrapper (MinIO-compatible). `operator_store.py` — S3-backed store for user-uploaded operator bundles (RustFS).
  - `result_cache.py` — in-process pre-serialized JSON response cache (see Performance below).
  - `user_center.py` — OAuth2 client for the 统一用户中心.
  - `operator_store.py` — persists user operator bundles to S3.
- **`operators/`** — `scholar/` (committed built-in operator sources) and `user/` (gitignored runtime cache populated by uploads). Loaded by `service/operator_registry.py`.
- **`organization_ETL/`**, **`script/`** — ETL scripts (see ETL below).
- **`schemas/`** — committed nGQL DDL/spec files + fixtures used by schema management.
- **`idl/`**, **`middleware/`**, **`utils/`**, **`static/`**, **`var/`** — interface definitions, middleware stubs, shared utils, swagger static assets, runtime state (SQLite workflow DB, patent index state).

There is one module per KG-construction feature (`expert_direct_relation`, `expert_enterprise_relation`, `industry_chain_panorama`, ...). Adding a feature means adding all five layers (schemas + handler + application + service + dao/model as needed) plus registering the router in `biz/router/register.py` and an entry in `service/module_catalog.py`. The 重点关注科技企业关系子系统 modules (below) are the most complete reference implementations.

### Auth subsystem

`AUTH_ENABLED` gates the whole thing. When false, `require_authenticated_user` returns a dev context and admin checks pass through — useful for local dev and CI. When enabled, three login paths coexist (see `biz/dependencies/auth.py`):

1. **Bearer token** — `Authorization: Bearer <token>` for third-party API callers; resolved via `application.resolve_bearer`.
2. **Session cookie** — `techkg_session` (name from `AUTH_SESSION_COOKIE`), Redis-backed (`AUTH_SESSION_BACKEND=redis`).
3. **Portal cookie SSO** — when `USER_CENTER_PORTAL_COOKIE_LOGIN_ENABLED=true`, a portal `access_token` cookie is exchanged for a local session via the 统一用户中心 OAuth2 client (`infra/user_center.py`). This is the production default.

Admin routers additionally require `require_platform_admin` (checks platform role). First-admin bootstrap via `PLATFORM_BOOTSTRAP_FIRST_ADMIN` + `PLATFORM_INITIAL_ADMIN_USER_IDS`. Auth config lives in `config/auth.py` (`AuthSettings`); audit logs go to Redis with TTL.

### Major non-KG subsystems

- **Schema management** (`/api/v1/schema-management`, admin-gated) — admin-authored nGQL schema scripts; stored in S3 (`SCHEMA_S3_*`), validated by `service/script_security.py` (AST allowlist) before execution against trs-graph via nGQL. `SCHEMA_AUTO_INIT=true` seeds the catalog on boot.
- **平台喂数批次抽取**（`kg.schema.extract`，`service/temporal_workflows.py:SchemaExtractWorkflow`）— schema 抽取主通道：来源绑定（`GraphSchemaSource`，复杂 SQL 走 `query_sql` 列）分批读 → 转换脚本 `transform(payload)` 只输出 `{entities|edges, failures}` JSON → 平台写图/消歧/索引/推游标。读取模式：querySql 绑定走水位/pk keyset（合成唯一 pk）；普通表走 LIMIT/OFFSET（主键不唯一，与旧脚本同语义），注册器 `script/register_platform_extraction.py` 按 information_schema 自动探测 pk/时间列。**实体写图必须走 nGQL `INSERT VERTEX`**（trs-graph `/nodes/merge` 会把 id/name/vid 从属性剥离，schema DDL 的 NOT NULL id/name 会 400）。逐行失败 → T_EXTRACT_FAIL 审核 case（队列 category=C）；点重跑（`POST /manual-reviews/production/rerun-extract-failures`）→ 新执行 `triggerSource=RERUN`（MANUAL/SCHEDULE/RERUN 三类在任务详情执行历史同列展示）。任务类型 `extract`（schemaId+batchSize+cron）。索引重建（`EntitySearchService.reindex`）失败降级不拖垮抽取。e2e 驱动：根目录 `dev2_extract_e2e.py`。
- **Workflow system** (`/api/v1/workflow-system`, admin-gated) — Temporal-backed workflow execution + a SQLite control plane (`service/workflow_repository.py`, `WORKFLOW_DATABASE_PATH`). User-defined workflows compose registered operators. Run the worker with `script/run_temporal_worker.py` (Temporal at `TEMPORAL_ADDRESS`). The api process also runs an in-process Temporal worker; concurrency and retry are capped (see memory: temporal retry storm) to protect the trs-graph session pool.
- **Operator registry** (`service/operator_registry.py`) — thread-safe, hot-reloadable Python operator registry. Built-ins in `service/operator_builtins.py`; user operators loaded from `operators/user/` and persisted to S3. Each operator follows `list[dict] -> operator(data, ctx) -> list[dict]`. `main.py` lifespan calls `REGISTRY.initialize_store()` + `start_watcher()`.
- **Manual review** (`/api/v1/manual-review`, admin-gated; `/api/v1/manual-review-internal`, no auth) — production review service (`service/manual_review_production.py`) with a graph-build handoff boundary; cases/drafts/decisions/audit in `db_model/manual_review.py`. The internal endpoint is called by the review worker (`script/run_manual_review_worker.py`).
- **Correction center** (`/api/v1/corrections`) — 人工修正 ledger + state machine + reliable MySQL/graph sync (`service/correction.py`, `db_model/platform_governance.py`). A background dispatcher polls due sync tasks every `CORRECTION_SYNC_INTERVAL_SECONDS` (gated by `CORRECTION_SYNC_WORKER_ENABLED`, default true in compose). Disabled in tests/CI.
- **Task center / platform overview / options / graph search / common capability** — supporting routers; `GET /kg-construction/options` aggregates dropdown options (each data source wrapped so one failure returns `[]` without breaking the response).
- **LLM** (`infra/llm.py`) — `get_llm_client()` is a process singleton; returns `None` when `LLM_API_KEY`/`ZHIPUAI_API_KEY` is unset (caller degrades). Default model `glm-4.7-flash`. `synthesize()` returns `None` on any error. Patent hybrid search uses a separate m3e embedding service (`PATENT_EMBEDDING_BASE_URL`, default `http://m3e-embedding:8010/v1`).

### Performance: result cache

`infra/result_cache.py` is an in-process dict of pre-serialized JSON keyed by request params. On hit, handlers return `Response(cached_json_str)` — zero Pydantic serialization, which matters under load (FastAPI's `response_model` jsonable_encoder is the bottleneck at ~500 concurrency). TTL via `RESULT_CACHE_TTL` (600s in load-test). `biz/prewarm_business.py` warms the nine business-module caches on boot. The cache intentionally uses no lock (dict get/set is atomic under CPython GIL); don't add one.

### Graph DB: `infra/graph_db` (trs-graph → NebulaGraph)

The graph is NebulaGraph, accessed over HTTP via the **trs-graph-service** (a Java Spring Boot REST API, default `http://localhost:8090`). Auth is `X-API-Key` header; graph space is `X-Graph-Space` header. `infra/graph_db/client.TRSGraphClient` is the ORM-style client.

- **Two thread-safe lazy singletons** in `infra/graph_db/__init__.py`: `get_trs_graph_client()` (space from `TRS_GRAPH_SPACE` env) and `get_techkg_client()` (space fixed to `techkg`). Both connect on first use; `main.py` lifespan calls `close_*_client()` on shutdown.
- **Node + edge CRUD all work via REST.** `create_node`/`merge_node`/`update_node`/`delete_node`/`get_node`/`get_nodes_by_label`/`find_nodes` for nodes, `create_edge`/`update_edge`/`get_edge`/`get_node_edges`/`get_edges_by_type` for edges. `find_nodes` returns the real vid (not a UUID). Verified 2026-08-25 against `dev2` space: create/get/update/delete/merge/find on Paper tag all succeeded. **Properties sent in `merge_node`/`create_node` must match the target tag's schema** — sending unknown columns returns `400 SemanticError: Unknown column 'X' in schema`. Use `DESCRIBE TAG <label>` (via `execute_query`) to list valid properties before writing. For DDL (CREATE/ALTER TAG/EDGE/SPACE) use nGQL via `execute_query` / `execute_write` / `execute_read`.
- Config via `TRS_GRAPH_*` env vars (`BASE_URL`, `SPACE`, `API_KEY`, `TIMEOUT`); see `infra/graph_db/config.py`. DDL has schema-propagation delay; transient 500s on a DDL that follows CREATE SPACE usually resolve on retry.

### ETL scripts (`backend/script/` and `backend/organization_ETL/`)

- `init_graph_schema.py` — `CREATE SPACE techkg` + Scholar/Organization/`EMPLOYED_BY` DDL via nGQL. CREATE SPACE has a propagation delay; transient 500s on the DDL that follows usually resolve on retry.
- `load_graph.py` — MySQL → techkg ETL (idempotent merge of nodes/edges). Uses `merge_node`.
- `init_db.py` — MySQL schema init.
- `organization_ETL/` + `script/organization_*`, `script/load_scholar_*`, `script/load_patent_*`, `script/load_project_*`, `script/load_paper_journal_graph.py` — per-domain ETL. Several build Milvus indexes (`build_*_milvus_index.py`). When running inside the api container, pass Milvus/MySQL env explicitly (see memory: `docker exec -e MILVUS_URI=... tech-kg-api ...`).
- `script/run_temporal_worker.py`, `script/run_manual_review_worker.py` — long-running workers for the workflow and manual-review subsystems.

### 重点关注科技企业关系子系统 (reference subsystem — 3 modules)

The most complete feature set. Three cooperating modules plus a shared catalog and an options endpoint:

- **`expert_enterprise_relation`** (`/kg-construction/expert-enterprise-relations`) — builds an `EMPLOYED_BY` edge. One edge per scholar↔enterprise pair (rank `@0`); multiple relation types are joined with `/` in the `relation_type` property, stored as **English codes** (`employment`/`advisor`/`rd_cooperation`/`project_cooperation`/`tech_cooperation`), mapped to Chinese labels (任职/顾问/研发合作/项目合作/技术合作) only in the response. `build` writes/merges the edge via `create_edge` and returns **all** of that scholar's enterprise relations, deduped by enterprise. Missing scholar/enterprise → `KeyError` → 404.
- **`relation_detail_annotation`** (`/kg-construction/relation-detail-annotations`) — annotates an existing `EMPLOYED_BY` edge with role/tech-field/period via `get_edge` + `update_edge`. Roles come from `ROLE_CATALOG` (chief_scientist/cto → L1, technical_advisor/rd_lead → L2, engineer → L3). Missing edge → `KeyError` → 404.
- **`enterprise_background_analysis`** (`/kg-construction/enterprise-background-analyses`) — aggregates MySQL data (行业地位/核心技术/经营财务) via `dao/organization.py` + `dao/patent.py`, then synthesizes a narrative with the LLM. LLM failure degrades gracefully (returns `None` → template/structured-only result).
- **`service/enterprise_relation_catalog.py`** — shared `RELATION_TYPES` / `ROLE_CATALOG` code tables + `validate_relation_types` / `relation_label` / `role_info`. `relation_label` tolerates non-catalog values (e.g. legacy Chinese labels already in the graph) via `.get(c, c)` — do not make it strict.
- **`service/kg_options.py`** + **`biz/handler/options.py`** (`GET /kg-construction/options`) — aggregates dropdown options for the frontend test-param modal: scholars/edges (graph), enterprises (MySQL), relationTypes/roles/dimensions/techFields/cpcCodes (catalog).

## Frontend commands

All commands run from `frontend/`:

```bash
pnpm install
pnpm dev       # dev server; /api proxied to VITE_API_TARGET (default http://localhost:8100)
pnpm build     # vue-tsc -b && vite build → dist/
pnpm preview
pnpm test              # vitest run
pnpm test:watch        # vitest
pnpm test:compatibility # playwright (playwright.compatibility.config.ts)
```

- Dev proxy: `/api` → `env.VITE_API_TARGET` (no path rewrite). Set `VITE_API_TARGET` to the backend.
- Production: nginx serves `dist/` and reverse-proxies `/api/` → `http://api:8000` (see `nginx.conf`).
- The frontend is a multi-route SPA (hash history) under `src/`:
  - **`views/business-service/`** — the nine KG-construction subfunctions as routes (`/expert-direct`, `/node-indirect`, `/two-point-achievement`, `/expert-colleague`, `/expert-alumni`, `/paper-cooperation`, `/enterprise-relation`, `/industry-chain-event`, `/industry-chain-panorama`).
  - **`views/platform/`** — workbench overview, graph build, operations center, manual-review workspace, process-instance detail.
  - **`views/admin/`** — correction center, member management.
  - **`views/auth/`** — login, user-center, account-security, operation-logs, access-denied.
  - **`stores/auth.ts`** — auth state; **`portal/iframeBridge.ts`** — when embedded in the 统一门户 iframe, bridges portal auth state into the app.
  - UI stack: element-plus + arco-design/web-vue + vue-flow (graph canvas) + echarts. API clients in `src/api/`.

## Docker

`docker-compose.yml` runs the two app services plus supporting infra (Milvus + etcd + MinIO, RustFS for operators, schema MinIO, m3e-embedding, auth-redis, Temporal):

- `api` — `./backend`, host port **8001** → container 8000. Connects to trs-graph/MySQL via `host.docker.internal` (`extra_hosts: host-gateway`) or via the compose `engine`/`graph` networks. Env defaults inline; override with a `.env` or shell env.
- `web` — `./frontend`, host port **8088** → container 80. Depends on `api`.
- Compose does **not** create MySQL — it expects an external `mysql` service on the `engine` network with `gkx_element` already loaded. Run MySQL separately or point `MYSQL_HOST` at a host DB.
- Milvus uses dedicated ports to avoid clashing with a host `tech-kg-engine` Milvus: `19531` (SDK), `9093` (health), MinIO API `9010` / console `9011`.

Both Dockerfiles accept a mirror build arg and default to Aliyun mirrors: backend `PYPI_INDEX_URL` (used for both `pip install uv` and `uv sync`), frontend `NPM_REGISTRY` (used for corepack + pnpm install). If you switch mirrors, test that `uv` itself installs (some mirrors 403 on the `uv` wheel).

If 8001/8088 are taken, change the host ports in `docker-compose.yml` — do **not** stop other services to free ports.

## Conventions

- Commit messages must **never** include `Co-Authored-By` or any co-author trailer.
- User-facing strings, comments, and module descriptions are in Chinese.
- `main` is the integration target; KG-construction feature work lands via PRs against `main` (see recent merge history for the pattern).
