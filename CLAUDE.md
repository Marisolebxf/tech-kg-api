# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository layout

Monorepo: `backend/` (Python FastAPI) + `frontend/` (Vue 3 + TS + Vite). A top-level `docker-compose.yml` builds and runs both.

The README.md at the root is **stale** — it documents an older Neo4j-based `backend/app/` layout that is no longer the live code. Treat the structure below as the source of truth.

**Not committed / gitignored — do not add to git:** `backend/app/`, root `app/`, root `graph_db/`, and `docs/superpowers/`. These are local-only or legacy copies. The `backend/legacy/` directory IS tracked but is excluded from ruff and is not part of the live app.

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
```

Python is pinned to `>=3.11.13,<3.12` (the Docker image uses `python:3.11.13-slim`).

### Lint/test conventions

- **ruff**: `line-length = 100`, lint selects `E F I UP B`, ignores `E501` (line length not enforced), **excludes `legacy`**. CI runs `ruff format --check .` then `ruff check .`.
- **pytest**: `asyncio_mode = "auto"` (async tests need no decorator), `testpaths = ["tests"]`.
- **`external` marker**: tests requiring real MySQL/Redis/TRSGraph/Kafka/Milvus. CI runs `-m "not external"`; mark live-service tests with `@pytest.mark.external`.
- Unit tests for the graph client use `httpx.MockTransport` to fake the trs-graph REST API — no live service needed.
- Integration tests use the `async_client` fixture in `tests/conftest.py` (ASGI transport against `main.app`).

## Backend architecture (DDD layered)

Request flow: `main.py` → `biz/router/register.py` → `biz/handler/*` → `application/*` → `service/*` → `dao/*` + `db_model/*` + `infra/*`. Pydantic request/response models for a module live in `biz/schemas/<module>.py`.

- **`biz/handler/`** — FastAPI `APIRouter`s (the only place routes are defined). Routers are mounted by `biz/router/register.py` under the `/api/v1` prefix. Handlers are thin: parse request, call an `application` object, return response.
- **`biz/schemas/`** — Pydantic v2 request/response models, one file per module. Handlers reference these for `response_model` and body parsing.
- **`application/`** — thin orchestration classes; one per domain module, wraps a `service`.
- **`service/`** — business logic. Each KG-construction module subclasses `service/base_module.KGModuleScaffoldService` (sets `module_code`, inherits `describe()` from `service/module_catalog.py`). The catalog in `module_catalog.py` is the registry of module codes/names/descriptions.
- **`dao/`** — MySQL query objects (e.g. `ScholarDAO`), each takes a SQLAlchemy `Session`.
- **`db_model/`** — SQLAlchemy ORM models (all share `db_model/base.Base`). One model file per table family (`scholar.py`, `organization.py`, `paper.py`, `patent.py`, ...).
- **`infra/`** — infrastructure singletons: `infra/mysql.py` (sync SQLAlchemy engine + `get_mysql_client()`), `infra/redis.py`, `infra/llm.py`, and `infra/graph_db/` (the trs-graph client). All read config from env vars / `.env` via `python-dotenv` — the `config/*.yml` files are **legacy and not loaded** by the live app.

There is one module per KG-construction feature (`expert_direct_relation`, `expert_enterprise_relation`, `industry_chain_panorama`, ...). Adding a feature means adding all five layers (schemas + handler + application + service + dao/model as needed) plus registering the router in `biz/router/register.py`. The 重点关注科技企业关系子系统 modules (below) are the most complete reference implementations.

### Graph DB: `infra/graph_db` (trs-graph → NebulaGraph)

The graph is NebulaGraph, accessed over HTTP via the **trs-graph-service** (a Java Spring Boot REST API, default `http://localhost:8090`). Auth is `X-API-Key` header; graph space is `X-Graph-Space` header. `infra/graph_db/client.TRSGraphClient` is the ORM-style client.

- **Two thread-safe lazy singletons** in `infra/graph_db/__init__.py`: `get_trs_graph_client()` (space from `TRS_GRAPH_SPACE` env) and `get_techkg_client()` (space fixed to `techkg`). Both connect on first use; `main.py` lifespan calls `close_*_client()` on shutdown.
- **Node CRUD on the live trs-graph-service is broken; edge CRUD works.** `create_node`/`merge_node`/`find_nodes` are unreliable (`find_nodes` returns a UUID id, not the real vid). The live feature services therefore use the **edge + node-read** REST methods: `create_edge` (upserts at rank `@0`), `update_edge`, `get_edge`, `get_node`, `get_node_edges`, `get_nodes_by_label`, `get_edges_by_type`. For DDL (CREATE/ALTER TAG/EDGE/SPACE) use nGQL via `execute_query` / `execute_write` / `execute_read`. `merge_node` is only used by the `load_graph.py` ETL, which is affected by this bug.
- Config via `TRS_GRAPH_*` env vars (`BASE_URL`, `SPACE`, `API_KEY`, `TIMEOUT`); see `infra/graph_db/config.py`.

### Graph schema & ETL scripts (`backend/script/`)

- `init_graph_schema.py` — `CREATE SPACE techkg` + Scholar/Organization/`EMPLOYED_BY` DDL via nGQL. CREATE SPACE has a propagation delay; transient 500s on the DDL that follows usually resolve on retry.
- `load_graph.py` — MySQL → techkg ETL (idempotent merge of nodes/edges). Uses `merge_node`, which is unreliable on the live trs-graph-service — see the graph-DB caveat above.
- `init_db.py` — MySQL schema init.

### 重点关注科技企业关系子系统 (reference subsystem — 3 modules)

The most complete feature set. Three cooperating modules plus a shared catalog and an options endpoint:

- **`expert_enterprise_relation`** (`/kg-construction/expert-enterprise-relations`) — builds an `EMPLOYED_BY` edge. One edge per scholar↔enterprise pair (rank `@0`); multiple relation types are joined with `/` in the `relation_type` property, stored as **English codes** (`employment`/`advisor`/`rd_cooperation`/`project_cooperation`/`tech_cooperation`), mapped to Chinese labels (任职/顾问/研发合作/项目合作/技术合作) only in the response. `build` writes/merges the edge via `create_edge` and returns **all** of that scholar's enterprise relations, deduped by enterprise. Missing scholar/enterprise → `KeyError` → 404.
- **`relation_detail_annotation`** (`/kg-construction/relation-detail-annotations`) — annotates an existing `EMPLOYED_BY` edge with role/tech-field/period via `get_edge` + `update_edge`. Roles come from `ROLE_CATALOG` (chief_scientist/cto → L1, technical_advisor/rd_lead → L2, engineer → L3). Missing edge → `KeyError` → 404.
- **`enterprise_background_analysis`** (`/kg-construction/enterprise-background-analyses`) — aggregates MySQL data (行业地位/核心技术/经营财务) via `dao/organization.py` + `dao/patent.py`, then synthesizes a narrative with the LLM. LLM failure degrades gracefully (returns `None` → template/structured-only result).
- **`service/enterprise_relation_catalog.py`** — shared `RELATION_TYPES` / `ROLE_CATALOG` code tables + `validate_relation_types` / `relation_label` / `role_info`. `relation_label` tolerates non-catalog values (e.g. legacy Chinese labels already in the graph) via `.get(c, c)` — do not make it strict.
- **`service/kg_options.py`** + **`biz/handler/options.py`** (`GET /kg-construction/options`) — aggregates dropdown options for the frontend test-param modal: scholars/edges (graph), enterprises (MySQL), relationTypes/roles/dimensions/techFields/cpcCodes (catalog). Each data source is wrapped so one failing source returns `[]` without breaking the whole response.

### LLM (`infra/llm.py`)

`get_llm_client()` is a process singleton; returns `None` when `LLM_API_KEY`/`ZHIPUAI_API_KEY` is unset (caller degrades). Default model `glm-4.7-flash` (a reasoning model — read `message.content`, `max_tokens` ~2048). `synthesize()` returns `None` on any error. Only `enterprise_background_analysis` uses it.

## Frontend commands

All commands run from `frontend/`:

```bash
pnpm install
pnpm dev       # dev server; /api proxied to VITE_API_TARGET (default http://localhost:8100)
pnpm build     # vue-tsc -b && vite build → dist/
pnpm preview
```

- Dev proxy: `/api` → `env.VITE_API_TARGET` (no path rewrite). Set `VITE_API_TARGET` to the backend.
- Production: nginx serves `dist/` and reverse-proxies `/api/` → `http://api:8000` (see `nginx.conf`).
- The live app is essentially `src/App.vue` (~1800 lines): a single-page KG-construction demo with a subfunction dropdown (专家-企业关系构建 / 角色与合作详情标注 / 企业背景关联分析), a params modal, a graph canvas, request/response tables, and code examples. It fetches `GET /api/v1/kg-construction/options` on mount to populate param dropdowns (scholar/enterprise/relation/role/dimension/CPC); all other calls fire only on button click. No mock data.

## Docker

`docker-compose.yml` runs two services built from their own Dockerfiles:

- `api` — `./backend`, host port **8001** → container 8000. Connects to TRSGraph/MySQL via `host.docker.internal` (`extra_hosts: host-gateway`). Env defaults inline; override with a `.env` or shell env.
- `web` — `./frontend`, host port **8088** → container 80. Depends on `api`.

Backend Dockerfile installs `uv` from **default PyPI** (the Tsinghua mirror 403s on `uv`); don't switch it back to a mirror without testing.

If 8001/8088 are taken, change the host ports in `docker-compose.yml` — do **not** stop other services to free ports.

## Conventions

- Commit messages must **never** include `Co-Authored-By` or any co-author trailer.
- User-facing strings, comments, and module descriptions are in Chinese.
- The branch `feature/technology-company-relation` carries the KG-construction feature work; `main` is the integration target.
